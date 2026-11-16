"""Kilométrage d'une période de paie : base calculée, ajustements de Hugo, validation et réouverture.

Un fichier JSON par période dans `dossier` (`<début>.json`), écrit de façon atomique.
La base (journées, tronçons, km déclaré) n'est calculée que par `calculer`, le seul appel qui
interroge Progression, Google Maps et Claude; ajuster, valider et rouvrir travaillent sur le fichier.
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import km_calcul
from journal import Journal
from km_declare import bons_du_technicien
from regles import Regles

MAGASIN_MAX_KM = 500
_REFUS_VALIDEE = "Période validée : la rouvrir avant de modifier."
_NOTE_INTROUVABLE = "code postal introuvable : trajet calculé sans le domicile"


def _admissible(config: dict | None) -> bool:
    return bool(config and config.get("paye_km") and (config.get("code_postal") or "").strip())


class Kilometrage:
    def __init__(self, progression, cartes, client_ia, cfg_claude: dict, dossier: Path, journal: Journal):
        self.progression = progression
        self.cartes = cartes
        self.client_ia = client_ia
        self.cfg_claude = cfg_claude
        self.dossier = Path(dossier)
        self.journal = journal

    # --- fichier de période -------------------------------------------------------------------
    def _fichier(self, debut: date) -> Path:
        return self.dossier / f"{debut.isoformat()}.json"

    def _lire(self, debut: date) -> dict:
        fichier = self._fichier(debut)
        if not fichier.exists():
            return {"base": None, "ajustements": {}, "statut": "brouillon", "revision": 0,
                    "valide_par": "", "valide_le": "", "instantane": None}
        return json.loads(fichier.read_text(encoding="utf-8"))

    def _ecrire(self, debut: date, donnees: dict) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        fichier = self._fichier(debut)
        temporaire = fichier.with_name(fichier.name + ".tmp")
        temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(temporaire, fichier)

    def _inscrire(self, personne: str, evenement: str, details: dict) -> None:
        journal = self.journal if personne in ("", self.journal.personne) else Journal(self.journal.dossier, personne)
        journal.inscrire(evenement, 0, "", details)

    # --- calcul -------------------------------------------------------------------------------
    def calculer(self, debut: date, fin: date, techniciens: dict,
                 progres: Callable[[str], None] = lambda m: None) -> None:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide":
            return None

        progres("Lecture des entrées de temps dans Progression…")
        entrees = self.progression.entrees_periode(debut, fin)
        ids = sorted({(e.get("task") or {}).get("id") for e in entrees} - {None})
        taches: dict[int, dict] = {}
        entrees_par_tache: dict[int, list[dict]] = {}
        for n, tache_id in enumerate(ids, 1):
            progres(f"Lecture des bons ({n} sur {len(ids)})…")
            taches[tache_id], entrees_par_tache[tache_id] = self.progression.lire_tache(tache_id)

        par_technicien: dict[str, list[km_calcul.Journee]] = {}
        for j in km_calcul.journees(entrees, taches, debut, fin):
            if j.technicien:
                par_technicien.setdefault(j.technicien, []).append(j)

        progres("Calcul des distances (Google Maps)…")
        positions: dict[str, tuple[float, float] | None] = {}
        cache_ia: dict = {}
        base_techs = {}
        for nom in sorted(par_technicien):
            config = techniciens.get(nom)
            domicile, note = None, None
            if _admissible(config):
                code = config["code_postal"].strip()
                if code not in positions:
                    positions[code] = self.cartes.geocoder(code)
                domicile = positions[code]
                if domicile is None:
                    note = _NOTE_INTROUVABLE
            jours = []
            for j in par_technicien[nom]:
                km, troncons = km_calcul.km_journee(domicile, j.arrets, self.cartes.distance_km)
                jours.append({
                    "jour": j.jour.isoformat(),
                    "arrets": [{"code": a.code, "tache_id": a.tache_id} for a in j.arrets],
                    "troncons": troncons, "km": km,
                    "a_verifier": list(j.a_verifier) + ([note] if note else []),
                    "domicile": domicile is not None, "minutes": j.minutes,
                })
            progres(f"Km déclarés : {nom}…")
            bons = bons_du_technicien(nom, entrees_par_tache, taches, debut, fin,
                                      self.client_ia, self.cfg_claude, cache_ia)
            base_techs[nom] = {"jours": jours, "bons": bons}

        donnees["base"] = {"debut": debut.isoformat(), "fin": fin.isoformat(), "techniciens": base_techs,
                           "calcule_le": datetime.now().astimezone().isoformat(timespec="seconds")}
        self._ecrire(debut, donnees)
        progres("Calcul terminé.")
        return None

    # --- lecture ------------------------------------------------------------------------------
    def periode(self, debut: date, techniciens: dict, regles: Regles) -> dict | None:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide" and donnees.get("instantane") is not None:
            return {**donnees["instantane"], "statut": "valide", "revision": donnees["revision"],
                    "valide_par": donnees["valide_par"], "valide_le": donnees["valide_le"]}
        if donnees.get("base") is None:
            return None
        totaux = km_calcul.totaliser(donnees["base"], donnees["ajustements"], regles.km_taux,
                                     regles.km_seuil_ecart, techniciens)
        return {**totaux, "statut": "brouillon", "revision": donnees["revision"]}

    # --- modifications ------------------------------------------------------------------------
    def ajuster(self, debut: date, technicien: str, jour: str, uhaul: bool, magasin_km: float,
                personne: str) -> None:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide":
            raise ValueError(_REFUS_VALIDEE)
        magasin = float(magasin_km)
        if not 0 <= magasin <= MAGASIN_MAX_KM:
            raise ValueError(f"Km magasin : entre 0 et {MAGASIN_MAX_KM}.")
        cle = f"{technicien}|{jour}"
        precedent = donnees["ajustements"].get(cle) or {}
        avant = {"uhaul": bool(precedent.get("uhaul")), "magasin_km": float(precedent.get("magasin_km") or 0)}
        apres = {"uhaul": bool(uhaul), "magasin_km": magasin}
        if apres == avant:
            return
        donnees["ajustements"][cle] = apres
        self._ecrire(debut, donnees)
        self._inscrire(personne, "km_ajustement", {"periode": debut.isoformat(), "technicien": technicien,
                                                    "jour": jour, "avant": avant, "apres": apres})

    def valider(self, debut: date, techniciens: dict, regles: Regles, personne: str) -> dict:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide":
            raise ValueError("Période déjà validée.")
        brouillon = self.periode(debut, techniciens, regles)
        if brouillon is None:
            raise ValueError("Aucun calcul pour cette période : la calculer avant de valider.")
        instantane = {k: v for k, v in brouillon.items() if k not in ("statut", "revision")}
        donnees.update(statut="valide", instantane=instantane, valide_par=personne,
                       valide_le=datetime.now().astimezone().isoformat(timespec="seconds"))
        self._ecrire(debut, donnees)
        self._inscrire(personne, "km_validation", {"periode": debut.isoformat(), "total_km": instantane["total_km"],
                                                   "total_montant": instantane["total_montant"],
                                                   "revision": donnees["revision"]})
        return self.periode(debut, techniciens, regles)

    def rouvrir(self, debut: date, raison: str, personne: str) -> None:
        raison = (raison or "").strip()
        if len(raison) < 5:
            raise ValueError("Indiquer la raison de la réouverture (au moins 5 caractères).")
        donnees = self._lire(debut)
        if donnees["statut"] != "valide":
            raise ValueError("Cette période n'est pas validée.")
        donnees.update(statut="brouillon", revision=donnees["revision"] + 1, instantane=None,
                       valide_par="", valide_le="")
        self._ecrire(debut, donnees)
        self._inscrire(personne, "km_reouverture", {"periode": debut.isoformat(), "raison": raison,
                                                    "revision": donnees["revision"]})
