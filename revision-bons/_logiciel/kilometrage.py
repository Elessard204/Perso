"""Kilométrage d'une période de paie : base calculée, ajustements de Hugo, validation et réouverture.

Un fichier JSON par période dans `dossier` (`<début>.json`), écrit de façon atomique.
La base (journées, tronçons, km déclaré) n'est calculée que par `calculer`, le seul appel qui
interroge Progression, Google Maps et Claude; ajuster, valider et rouvrir travaillent sur le fichier.
"""
from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import km_calcul
from cartes import ErreurCartes
from journal import Journal
from km_declare import bons_du_technicien
from regles import Regles, cents

MAGASIN_MAX_KM = 500
_REFUS_VALIDEE = "Période validée : la rouvrir avant de modifier."
_NOTE_INTROUVABLE = "code postal introuvable : aucun km payé tant qu'il n'est pas corrigé"
RECALCUL_REQUIS = "recalcul_requis"

# Un verrou par dossier de périodes, partagé par toutes les instances (fils de l'interface).
_VERROUS: dict[str, threading.Lock] = {}
_VERROUS_GARDE = threading.Lock()


def _verrou(dossier: Path) -> threading.Lock:
    with _VERROUS_GARDE:
        return _VERROUS.setdefault(str(Path(dossier).resolve()), threading.Lock())


def _admissible(config: dict | None) -> bool:
    return bool(config and config.get("paye_km") and (config.get("code_postal") or "").strip())


def _code_utilise(config: dict | None) -> str | None:
    """Code postal qui sert au calcul : celui d'un technicien admissible, sinon None."""
    return config["code_postal"].strip() if _admissible(config) else None


class Kilometrage:
    def __init__(self, progression, cartes, client_ia, cfg_claude: dict, dossier: Path, journal: Journal):
        self.progression = progression
        self.cartes = cartes
        self.client_ia = client_ia
        self.cfg_claude = cfg_claude
        self.dossier = Path(dossier)
        self.journal = journal
        self._verrou = _verrou(self.dossier)

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
            code = _code_utilise(techniciens.get(nom))
            domicile, note = None, None
            if code is not None:
                if code not in positions:
                    positions[code] = self.cartes.geocoder(code)
                domicile = positions[code]
                if domicile is None:
                    note = _NOTE_INTROUVABLE
            jours = []
            for j in par_technicien[nom]:
                if code is None:
                    # Sous-traitant ou à configurer : rien à payer, donc pas de trajet à demander à Google.
                    # Une configuration ajoutée plus tard demande un recalcul (statut « recalcul requis »).
                    km, troncons = 0.0, []
                else:
                    km, troncons = self._km_journee(nom, j, domicile)
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
            base_techs[nom] = {"code_postal": code, "jours": jours, "bons": bons,
                               "code_introuvable": code is not None and domicile is None}

        base = {"debut": debut.isoformat(), "fin": fin.isoformat(), "techniciens": base_techs,
                "calcule_le": datetime.now().astimezone().isoformat(timespec="seconds")}
        with self._verrou:
            # Relu juste avant d'écrire : une validation ou un ajustement fait pendant le calcul est gardé.
            donnees = self._lire(debut)
            if donnees["statut"] == "valide":
                return None
            donnees["base"] = base
            self._ecrire(debut, donnees)
        progres("Calcul terminé.")
        return None

    def _km_journee(self, nom: str, journee: km_calcul.Journee, domicile) -> tuple[float, list[dict]]:
        try:
            return km_calcul.km_journee(domicile, journee.arrets, self.cartes.distance_km)
        except ErreurCartes as e:
            codes = ", ".join(dict.fromkeys(a.code for a in journee.arrets if a.code))
            raise ErreurCartes(f"{e} (technicien {nom}, jour {journee.jour.isoformat()}, bons {codes})") from e

    # --- lecture ------------------------------------------------------------------------------
    def periode(self, debut: date, techniciens: dict, regles: Regles) -> dict | None:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide" and donnees.get("instantane") is not None:
            return {**donnees["instantane"], "statut": "valide", "revision": donnees["revision"],
                    "valide_par": donnees["valide_par"], "valide_le": donnees["valide_le"]}
        if donnees.get("base") is None:
            return None
        # Une période déjà validée puis rouverte garde le taux et le seuil de sa validation.
        taux = donnees.get("taux", regles.km_taux)
        seuil = donnees.get("seuil_km", regles.km_seuil_ecart)
        totaux = km_calcul.totaliser(donnees["base"], donnees["ajustements"], taux, seuil, techniciens)
        self._marquer_recalcul(totaux, donnees["base"], techniciens)
        return {**totaux, "calcule_le": donnees["base"].get("calcule_le", ""), "statut": "brouillon",
                "revision": donnees["revision"]}

    @staticmethod
    def _marquer_recalcul(totaux: dict, base: dict, techniciens: dict) -> None:
        """Un technicien admissible dont le code postal n'est plus celui du calcul n'est pas payé
        sur des distances périmées : statut « recalcul requis », sans montant, hors des totaux."""
        calcules = base.get("techniciens", {})
        for ligne in totaux["techniciens"]:
            actuel = _code_utilise(techniciens.get(ligne["nom"]))
            if actuel is not None and actuel != (calcules.get(ligne["nom"]) or {}).get("code_postal"):
                ligne.update(statut=RECALCUL_REQUIS, paie=False, km_a_payer=0.0, montant=None, ecart=None,
                             note=None)
        payees = [l for l in totaux["techniciens"] if l["paie"]]
        totaux["total_km"] = round(sum(l["km_a_payer"] for l in payees), 1)
        totaux["total_montant"] = cents(sum(l["montant"] for l in payees))

    # --- modifications ------------------------------------------------------------------------
    def ajuster(self, debut: date, technicien: str, jour: str, uhaul: bool, magasin_km: float,
                personne: str) -> None:
        magasin = round(float(magasin_km), 1)   # au dixième, comme les km du jour
        if not 0 <= magasin <= MAGASIN_MAX_KM:
            raise ValueError(f"Km magasin : entre 0 et {MAGASIN_MAX_KM}.")
        with self._verrou:
            self._ajuster(debut, technicien, jour, bool(uhaul), magasin, personne)

    def _ajuster(self, debut: date, technicien: str, jour: str, uhaul: bool, magasin: float,
                 personne: str) -> None:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide":
            raise ValueError(_REFUS_VALIDEE)
        cle = f"{technicien}|{jour}"
        precedent = donnees["ajustements"].get(cle) or {}
        avant = {"uhaul": bool(precedent.get("uhaul")), "magasin_km": float(precedent.get("magasin_km") or 0)}
        apres = {"uhaul": uhaul, "magasin_km": magasin}
        if apres == avant:
            return
        donnees["ajustements"][cle] = apres
        self._ecrire(debut, donnees)
        self._inscrire(personne, "km_ajustement", {"periode": debut.isoformat(), "technicien": technicien,
                                                    "jour": jour, "avant": avant, "apres": apres})

    def valider(self, debut: date, techniciens: dict, regles: Regles, personne: str) -> dict:
        with self._verrou:
            return self._valider(debut, techniciens, regles, personne)

    def _valider(self, debut: date, techniciens: dict, regles: Regles, personne: str) -> dict:
        donnees = self._lire(debut)
        if donnees["statut"] == "valide":
            raise ValueError("Période déjà validée.")
        brouillon = self.periode(debut, techniciens, regles)
        if brouillon is None:
            raise ValueError("Aucun calcul pour cette période : la calculer avant de valider.")
        a_recalculer = [l["nom"] for l in brouillon["techniciens"] if l["statut"] == RECALCUL_REQUIS]
        if a_recalculer:
            raise ValueError(f"Recalcul requis pour : {', '.join(a_recalculer)} — recalculer la période avant de valider.")
        a_configurer = [l["nom"] for l in brouillon["techniciens"] if l["statut"] == "a_configurer"]
        if a_configurer:
            raise ValueError(f"À configurer avant de valider : {', '.join(a_configurer)} — inscrire le code postal "
                             "ou décocher « Employé Progim » (sous-traitant).")
        instantane = {k: v for k, v in brouillon.items() if k not in ("statut", "revision")}
        donnees.update(statut="valide", instantane=instantane, valide_par=personne,
                       taux=brouillon["taux"], seuil_km=brouillon["seuil_km"],
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
        with self._verrou:
            self._rouvrir(debut, raison, personne)

    def _rouvrir(self, debut: date, raison: str, personne: str) -> None:
        donnees = self._lire(debut)
        if donnees["statut"] != "valide":
            raise ValueError("Cette période n'est pas validée.")
        donnees.update(statut="brouillon", revision=donnees["revision"] + 1, instantane=None,
                       valide_par="", valide_le="")
        self._ecrire(debut, donnees)
        self._inscrire(personne, "km_reouverture", {"periode": debut.isoformat(), "raison": raison,
                                                    "revision": donnees["revision"]})
