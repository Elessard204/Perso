"""Interface de la révision des bons, ouverte dans le navigateur par « Révision des bons.bat ».

Petit serveur local (127.0.0.1 seulement), comme l'outil des rapports clients. Il s'arrête tout seul
une minute après la fermeture de la page. Option --demo : faux bons, sans réseau ni clé.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import secrets
import sys
import threading
import time
import tomllib
import webbrowser
from dataclasses import asdict
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

# Le Python portable n'ajoute pas le dossier du script au chemin des modules.
ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

import cles  # noqa: E402
import profil  # noqa: E402
from facturation import evaluer_rabais  # noqa: E402
from analyse import (analyser_bon, chemin_cache, doublons_externes, effacer_cache,  # noqa: E402
                     proposition_vers_dict, transports_en_double)
from assistant import (STATUTS_RECO, contexte_bon, contexte_recommandations, contexte_regles,  # noqa: E402
                       rediger_recommandation, repondre)
from claude_client import creer_client  # noqa: E402
from excel import Gras, ecrire_xlsx  # noqa: E402
from envoi import envoyer  # noqa: E402
from journal import Journal  # noqa: E402
from km_calcul import periodes_proposees  # noqa: E402
from kilometrage import Kilometrage  # noqa: E402
from progression import ErreurProgression, Progression  # noqa: E402
from regles import charger_regles  # noqa: E402

TYPES_PIECES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
LONGUEUR_MAX_QUESTION = 2000
CHAMPS_REGLES = {
    # nom: (section, clé, type)
    "pas_minutes": ("heures", "pas_minutes", int),
    "marge": ("materiel", "marge", float),
    "refacturer_taxes": ("materiel", "refacturer_taxes", bool),
    "regle_transports": ("transports", "regle", str),
    "ecart_sous_total": ("garde_fous", "ecart_sous_total", float),
    "jours_max_facture": ("garde_fous", "jours_max_facture", int),
    "montant_max_ligne": ("garde_fous", "montant_max_ligne", float),
    "heures_max_jour": ("garde_fous", "heures_max_jour", float),
    "transport_max_minutes": ("heures", "transport_max_minutes", int),
    "marge_minimum": ("garde_fous", "marge_minimum", float),
    "cout_horaire_defaut": ("couts", "defaut", float),
    "charges_das": ("couts", "das", float),
    "charges_vacances": ("couts", "vacances", float),
    "charges_feries": ("couts", "feries", float),
    "seuil_rabais": ("garde_fous", "seuil_rabais", float),
}


def alerte_principale(alertes):
    """L'alerte à montrer dans la liste : bloquante d'abord, le transport à définir en dernier."""
    return sorted(alertes, key=lambda a: (not a.bloquante, a.code == "transport_a_definir"))[0]


def _valeur_toml(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_valeur_toml(x) for x in v) + "]"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v), ensure_ascii=False)


def _cle_toml(cle: str) -> str:
    return cle if re.fullmatch(r"[A-Za-z0-9_-]+", cle) else json.dumps(cle, ensure_ascii=False)


def toml_texte(donnees: dict) -> str:
    """Écrit regles.toml : sections simples, et sous-tables (tarifs."Appel de service")."""
    lignes = []
    for section, contenu in donnees.items():
        simples = {k: v for k, v in contenu.items() if not isinstance(v, dict)}
        if simples:
            lignes.append(f"[{_cle_toml(section)}]")
            lignes += [f"{_cle_toml(k)} = {_valeur_toml(v)}" for k, v in simples.items()]
        for k, v in contenu.items():
            if isinstance(v, dict):
                lignes.append(f"[{_cle_toml(section)}.{_cle_toml(k)}]")
                lignes += [f"{_cle_toml(k2)} = {_valeur_toml(v2)}" for k2, v2 in v.items()]
    return "\n".join(lignes) + "\n"


def nom_personne(brut: str) -> str:
    """Nom du fichier de journal de la personne : lettres (accents compris), chiffres, point, tiret."""
    return re.sub(r"[^\w.-]", "_", brut) or "poste"


class ErreurDemande(Exception):
    """Demande refusée, avec un message à afficher dans la page."""


def _nombre(valeur) -> float:
    if isinstance(valeur, bool):
        raise ValueError
    n = float(valeur) if isinstance(valeur, (int, float)) else float(
        str(valeur).replace(",", ".").replace(" ", "").replace(chr(0xA0), ""))
    if not math.isfinite(n):
        raise ValueError
    return n


REGLES_TRANSPORTS = {"un_par_visite"}   # quantité 1 par entrée de transport
BORNES = {"pas_minutes": (1, 60), "marge": (0, 1), "ecart_sous_total": (0, 100), "jours_max_facture": (0, 365),
          "montant_max_ligne": (0, 1_000_000), "heures_max_jour": (1, 24),
          "transport_max_minutes": (15, 240), "marge_minimum": (0, 0.9), "cout_horaire_defaut": (0, 500),
          "charges_das": (0, 0.5), "charges_vacances": (0, 0.5), "charges_feries": (0, 0.5),
          "seuil_rabais": (0, 100_000)}


MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
JOURS_COURTS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
AUJOURDHUI_DEMO = date(2026, 11, 5)   # en démo, la période courante contient les entrées du jeu d'essai


def _jour_fr(d: date) -> str:
    return "1er" if d.day == 1 else str(d.day)


def libelle_periode(debut: date, fin: date) -> str:
    """« du dim. 25 octobre au sam. 7 novembre 2026 » (sans dépendre de la langue du poste)."""
    premier = f"{JOURS_COURTS[debut.weekday()]} {_jour_fr(debut)}"
    if (debut.year, debut.month) != (fin.year, fin.month):
        premier += f" {MOIS[debut.month - 1]}"
    if debut.year != fin.year:
        premier += f" {debut.year}"
    return f"du {premier} au {JOURS_COURTS[fin.weekday()]} {_jour_fr(fin)} {MOIS[fin.month - 1]} {fin.year}"


class _Paresseux:
    """Service créé au premier usage : une page de lecture n'exige ni clé ni réseau."""

    def __init__(self, fabrique):
        self._fabrique = fabrique
        self._objet = None

    def __getattr__(self, nom):
        if nom.startswith("__"):
            raise AttributeError(nom)
        if self._objet is None:
            self._objet = self._fabrique()
        return getattr(self._objet, nom)


class Application:
    """État de la séance de révision. Indépendant du HTTP pour pouvoir le tester."""

    def __init__(self, logiciel: Path, demo: bool, personne: str, donnees: Path | None = None,
                 chemin_regles: Path | None = None):
        self.logiciel = Path(logiciel)
        self.demo = demo
        self.personne = personne
        self.donnees = Path(donnees) if donnees else (
            self.logiciel / "demo" / "sortie" if demo else self.logiciel)
        self.chemin_regles = Path(chemin_regles) if chemin_regles else self.logiciel / "regles.toml"
        self.cfg = tomllib.loads((self.logiciel / "config.toml").read_text(encoding="utf-8"))
        self.journal = Journal(self.donnees / "journal", personne)
        self.questions = Journal(self.donnees / "questions", personne)   # questions posées à Jarvis
        self.recommandations = Journal(self.donnees / "recommandations", personne)   # journal d'améliorations
        self.cache = self.donnees / "cache"
        self.verrou = threading.Lock()
        self.bons: dict[int, dict] = {}   # id -> {code, client, date, statut, raison, bon, proposition, approuve}
        self.progres = {"en_cours": False, "fait": 0, "total": 0, "message": ""}
        self.pieces_cache: dict[int, tuple[bytes, str]] = {}
        self.memo_progression: dict[str, int | None] = {}
        self.envoi_en_cours = False
        self.km_progres = {"en_cours": False, "message": ""}
        self.km_dernier_debut: date | None = None
        self._km = None
        self.jeton = secrets.token_urlsafe(24)   # exigé à chaque requête : seule la page de l'outil peut agir
        self._services = None

    # ---------- services ----------
    def services(self):
        if self._services is None:
            if self.demo:
                from demo.faux_services import FausseProgression, FauxClaude
                self._services = (FausseProgression(self.cfg["progression"]), FauxClaude())
            else:
                c = cles.lire()
                if not c.get("progression") or not c.get("claude"):
                    raise ErreurDemande("Clés manquantes : les inscrire dans l'onglet Règles, section Connexions.")
                self._services = (
                    Progression(c["progression"], self.cfg["progression"]["base"], cfg=self.cfg["progression"]),
                    creer_client(c["claude"]))
        return self._services

    def client_claude(self):
        """Le client de Claude seul : l'assistant n'a pas besoin de Progression."""
        if self.demo:
            from demo.faux_services import FauxClaude
            return FauxClaude()
        if self._services is not None:
            return self._services[1]
        cle = cles.lire().get("claude")
        if not cle:
            raise ErreurDemande("Clé Claude manquante : l'inscrire dans l'onglet Règles, section Connexions.")
        return creer_client(cle)

    def assistant(self, question, bon_id=None, historique=None) -> dict:
        """Répond à une question sur l'usage ou les règles. Ne modifie jamais un bon ni les règles."""
        question = str(question or "").strip()
        if not question:
            raise ErreurDemande("Écrire une question.")
        if len(question) > LONGUEUR_MAX_QUESTION:
            raise ErreurDemande(f"Question trop longue ({LONGUEUR_MAX_QUESTION} caractères au plus).")
        if historique is None:
            historique = []
        if not isinstance(historique, list) or not all(isinstance(e, dict) for e in historique):
            raise ErreurDemande("Historique de conversation invalide.")
        regles, contexte, code = self._contexte_jarvis(bon_id)
        recos = contexte_recommandations(self.liste_recommandations())
        try:
            reponse = repondre(self.client_claude(), self.cfg["claude"], question, historique, regles, contexte, recos)
        except ErreurDemande:
            raise
        except Exception as e:  # réseau, clé refusée, limite d'usage : message clair plutôt qu'une erreur brute
            raise ErreurDemande(f"L'assistant ne répond pas pour l'instant ({type(e).__name__}). Réessayer dans "
                                "un moment; si ça persiste, vérifier la clé Claude dans Règles, section Connexions.") from e
        self.questions.inscrire("question", int(bon_id) if code else 0, "", {"question": question, "reponse": reponse,
                                                                             "code": code})
        return {"reponse": reponse}

    def _contexte_jarvis(self, bon_id) -> tuple[str, str, str]:
        """Règles en vigueur, contexte du bon ouvert (s'il est analysé) et son code."""
        regles = contexte_regles(charger_regles(self.chemin_regles))
        with self.verrou:
            b = self.bons.get(int(bon_id)) if str(bon_id or "").isdigit() else None
            if b and b.get("proposition") and b.get("bon"):
                p = b["proposition"]
                return regles, contexte_bon(b["bon"], p, b.get("statut_force") or p.statut, bool(b.get("approuve"))), b["code"]
        return regles, "", ""

    # ---------- journal d'améliorations ----------
    def liste_recommandations(self) -> list[dict]:
        """Chaque recommandation avec son dernier statut, les plus récentes d'abord."""
        recos: dict[str, dict] = {}
        for e in self.recommandations._tous():
            d = e.get("details") or {}
            if e.get("evenement") == "recommandation" and d.get("id"):
                recos[d["id"]] = {**d, "horodatage": e.get("horodatage", ""), "personne": e.get("personne", ""),
                                  "statut": "nouvelle", "note": "", "statut_par": "", "statut_le": ""}
            elif e.get("evenement") == "statut_recommandation" and d.get("id") in recos:
                recos[d["id"]].update(statut=d.get("statut", "nouvelle"), note=d.get("note", ""),
                                      statut_par=e.get("personne", ""), statut_le=e.get("horodatage", ""))
        return sorted(recos.values(), key=lambda r: r["horodatage"], reverse=True)

    def brouillon_recommandation(self, historique=None, bon_id=None) -> dict:
        """Jarvis rédige une recommandation à partir de la conversation; vide s'il n'y a pas de conversation."""
        if historique is None:
            historique = []
        if not isinstance(historique, list) or not all(isinstance(e, dict) for e in historique):
            raise ErreurDemande("Historique de conversation invalide.")
        vide = {"titre": "", "probleme": "", "cas": "", "solutions": []}
        if not any(str(e.get("question") or "").strip() for e in historique):
            return vide
        regles, contexte, code = self._contexte_jarvis(bon_id)
        try:
            brouillon = rediger_recommandation(self.client_claude(), self.cfg["claude"], historique, regles, contexte)
        except ErreurDemande:
            raise
        except Exception as e:
            raise ErreurDemande(f"Jarvis ne répond pas pour l'instant ({type(e).__name__}). La recommandation peut "
                                "aussi s'écrire à la main.") from e
        brouillon = brouillon or vide
        if code and code not in brouillon["cas"]:
            brouillon["cas"] = f"Bon {code}" + (f" : {brouillon['cas']}" if brouillon["cas"] else "")
        return brouillon

    def ajouter_recommandation(self, corps: dict) -> dict:
        titre = " ".join(str(corps.get("titre") or "").split())[:150]
        if not titre:
            raise ErreurDemande("Donner un titre à la recommandation.")
        solutions = corps.get("solutions") or []
        if isinstance(solutions, str):
            solutions = solutions.splitlines()
        if not isinstance(solutions, list):
            raise ErreurDemande("Liste des solutions invalide.")
        bon_id = corps.get("bon_id")
        code = ""
        if str(bon_id or "").isdigit():
            with self.verrou:
                code = (self.bons.get(int(bon_id)) or {}).get("code", "")
        details = {
            "id": secrets.token_hex(4), "titre": titre,
            "probleme": str(corps.get("probleme") or "").strip()[:3000],
            "cas": str(corps.get("cas") or "").strip()[:3000],
            "solutions": [str(s).strip()[:1000] for s in solutions if str(s).strip()][:10],
            "code": code,
        }
        self.recommandations.inscrire("recommandation", int(bon_id) if code else 0, "", details)
        return {"recommandations": self.liste_recommandations()}

    def statut_recommandation(self, reco_id, statut, note="") -> dict:
        if statut not in STATUTS_RECO:
            raise ErreurDemande("Statut inconnu.")
        if reco_id not in {r["id"] for r in self.liste_recommandations()}:
            raise ErreurDemande("Recommandation introuvable.")
        self.recommandations.inscrire("statut_recommandation", 0, "", {
            "id": reco_id, "statut": statut, "note": " ".join(str(note or "").split())[:500]})
        return {"recommandations": self.liste_recommandations()}

    def export_recommandations(self) -> tuple[bytes, str]:
        lignes = [[Gras(x) for x in ("Proposée le", "Par", "Bon", "Titre", "Problème", "Cas", "Solutions proposées",
                                      "Statut", "Note", "Statut changé par")]]
        for r in self.liste_recommandations():
            lignes.append([r["horodatage"][:10], r["personne"], r.get("code", ""), r["titre"], r.get("probleme", ""),
                           r.get("cas", ""), "\n".join(f"- {s}" for s in r.get("solutions", [])),
                           STATUTS_RECO.get(r["statut"], r["statut"]), r.get("note", ""), r.get("statut_par", "")])
        return ecrire_xlsx({"Améliorations": lignes}), f"Améliorations - Révision des bons - {date.today().isoformat()}.xlsx"

    def etat(self) -> dict:
        return {"demo": self.demo, "personne": self.personne, "cles": cles.etat(),
                "mode_reel_permis": bool(self.cfg["progression"].get("ecriture_validee")) and not self.demo}

    def enregistrer_cles(self, progression: str | None, claude: str | None, google: str | None = None) -> dict:
        cles.ecrire(progression or None, claude or None, google or None)
        self._services = None
        self._km = None
        return self.etat()

    # ---------- kilométrage ----------
    def cartes(self):
        if self.demo:
            from demo.faux_services import FaussesCartes
            return FaussesCartes()
        from cartes import Cartes
        google = cles.lire().get("google")
        if not google:
            raise ErreurDemande("Clé Google manquante : l'inscrire dans l'onglet Règles, section Connexions.")
        return Cartes(google, profil.dossier() / "cache_cartes.json")

    def km(self) -> Kilometrage:
        if self._km is None:
            # Les fichiers de période contiennent les codes postaux : en mode réel, dans le profil Windows
            # (comme techniciens.json), jamais dans le dossier partagé.
            dossier = self.donnees / "kilometrage" if self.demo else profil.dossier() / "kilometrage"
            self._km = Kilometrage(_Paresseux(lambda: self.services()[0]), _Paresseux(self.cartes),
                                   _Paresseux(lambda: self.services()[1]), self.cfg["claude"],
                                   dossier, self.journal)
        return self._km

    def _aujourdhui(self) -> date:
        return AUJOURDHUI_DEMO if self.demo else date.today()

    def _debut_periode(self, texte) -> date:
        try:
            debut = date.fromisoformat(str(texte or ""))
        except ValueError:
            raise ErreurDemande("Choisir une période.") from None
        reference = charger_regles(self.chemin_regles).km_debut_reference
        if (debut - reference).days % 14 != 0:
            raise ErreurDemande("Cette date n'est pas le début d'une période de paie.")
        return debut

    def km_periodes(self) -> dict:
        reference = charger_regles(self.chemin_regles).km_debut_reference
        return {"periodes": [{"debut": d.isoformat(), "fin": f.isoformat(), "libelle": libelle_periode(d, f)}
                             for d, f in periodes_proposees(self._aujourdhui(), reference)]}

    def km_periode(self, debut: str) -> dict:
        d = self._debut_periode(debut)
        return {"periode": self.km().periode(d, profil.lire_techniciens(), charger_regles(self.chemin_regles))}

    def km_calculer(self, debut: str) -> dict:
        d = self._debut_periode(debut)
        km = self.km()
        if km._lire(d)["statut"] == "valide":
            raise ErreurDemande("Période validée : la rouvrir avant de recalculer.")
        techniciens = profil.lire_techniciens()
        with self.verrou:
            if self.km_progres["en_cours"] or self.progres["en_cours"] or self.envoi_en_cours:
                raise ErreurDemande("Un calcul, une analyse ou un envoi est déjà en cours : attendre la fin.")
            self.km_progres = {"en_cours": True, "message": "Démarrage du calcul…"}
        threading.Thread(target=self._km_calculer, args=(km, d, techniciens), daemon=True).start()
        return dict(self.km_progres)

    def _km_calculer(self, km: Kilometrage, debut: date, techniciens: dict) -> None:
        from cartes import ErreurCartes
        message = "Calcul terminé."

        def progres(texte: str) -> None:
            with self.verrou:
                self.km_progres["message"] = texte

        try:
            km.calculer(debut, debut + timedelta(days=13), techniciens, progres)
            self.km_dernier_debut = debut
        except ErreurCartes as e:
            message = f"Google Maps : {e}"
        except ErreurProgression as e:
            message = f"Progression : {e}"
        except ErreurDemande as e:
            message = str(e)
        except ValueError as e:
            message = f"Calcul refusé : {e}"
        except Exception as e:
            message = f"Calcul interrompu : {e}"
        finally:
            with self.verrou:
                self.km_progres.update(en_cours=False, message=message)

    def km_ajuster(self, corps: dict) -> dict:
        debut = self._debut_periode(corps.get("debut"))
        try:
            jour = date.fromisoformat(str(corps.get("jour") or "")).isoformat()
        except ValueError:
            raise ErreurDemande("Jour invalide.") from None
        brut = corps.get("magasin_km")
        try:
            magasin = 0.0 if brut is None or str(brut).strip() == "" else _nombre(brut)
        except ValueError:
            raise ErreurDemande("Inscrire un nombre de km (ex. 12,5).") from None
        try:
            self.km().ajuster(debut, str(corps.get("technicien") or ""), jour, bool(corps.get("uhaul")),
                              magasin, self.personne)
        except ValueError as e:
            raise ErreurDemande(str(e)) from e
        return self.km_periode(debut.isoformat())

    def km_valider(self, debut: str) -> dict:
        d = self._debut_periode(debut)
        try:
            periode = self.km().valider(d, profil.lire_techniciens(), charger_regles(self.chemin_regles),
                                        self.personne)
        except ValueError as e:
            raise ErreurDemande(str(e)) from e
        return {"periode": periode}

    def km_rouvrir(self, debut: str, raison: str) -> dict:
        d = self._debut_periode(debut)
        try:
            self.km().rouvrir(d, str(raison or ""), self.personne)
        except ValueError as e:
            raise ErreurDemande(str(e)) from e
        return self.km_periode(d.isoformat())

    def km_export(self, debut: str) -> tuple[bytes, str]:
        from excel import export_periode
        periode = self.km_periode(debut)["periode"]
        if not periode or periode.get("statut") != "valide":
            raise ErreurDemande("Valider la période avant d'exporter.")
        return export_periode(periode)

    def _noms_derniere_periode(self) -> set[str]:
        km = self.km()
        debut = self.km_dernier_debut
        if debut is None:
            fichiers = sorted(km.dossier.glob("????-??-??.json")) if km.dossier.exists() else []
            if not fichiers:
                return set()
            debut = date.fromisoformat(fichiers[-1].stem)
        base = km._lire(debut).get("base") or {}
        return set(base.get("techniciens", {}))

    def km_lire_reglages(self) -> dict:
        r = charger_regles(self.chemin_regles)
        techniciens = profil.lire_techniciens()
        return {"taux": r.km_taux, "seuil_km": r.km_seuil_ecart, "debut_reference": r.km_debut_reference.isoformat(),
                "techniciens": techniciens,
                "techniciens_connus": sorted(self._noms_derniere_periode() - set(techniciens))}

    def km_ecrire_reglages(self, valeurs: dict) -> dict:
        actuels = self.km_lire_reglages()
        try:
            taux = _nombre(valeurs.get("taux", actuels["taux"]))
            seuil = _nombre(valeurs.get("seuil_km", actuels["seuil_km"]))
        except ValueError:
            raise ErreurDemande("Le taux et le seuil doivent être des nombres.") from None
        if not 0 <= taux <= 5:
            raise ErreurDemande("Le taux doit être entre 0 et 5 $ du km.")
        if not 0 <= seuil <= 1000:
            raise ErreurDemande("Le seuil d'écart doit être entre 0 et 1000 km.")
        try:
            reference = date.fromisoformat(str(valeurs.get("debut_reference", actuels["debut_reference"])))
        except ValueError:
            raise ErreurDemande("Date de référence invalide.") from None
        if reference.weekday() != 6:
            raise ErreurDemande("La date de référence doit être un dimanche (début d'une période de paie).")
        techniciens = valeurs.get("techniciens")
        if techniciens is not None and not (
                isinstance(techniciens, dict) and all(isinstance(v, dict) for v in techniciens.values())):
            raise ErreurDemande("Liste des techniciens invalide.")
        techs_avant = actuels["techniciens"]
        techs_apres = techs_avant
        if techniciens is not None:
            try:
                techs_apres = profil.ecrire_techniciens(techniciens)
            except ValueError as e:
                raise ErreurDemande(str(e)) from e
        donnees = tomllib.loads(self.chemin_regles.read_text(encoding="utf-8"))
        donnees.setdefault("kilometrage", {}).update(taux=taux, seuil_ecart_km=seuil,
                                                     debut_reference=reference.isoformat())
        contenu = "# Règles appliquées à chaque bon de service. Modifiables dans l'onglet Règles.\n"
        contenu += f"# Dernière modification : {self.personne}\n" + toml_texte(donnees)
        self.chemin_regles.write_text(contenu, encoding="utf-8")
        self._journaliser_reglages_km(actuels, {"taux": taux, "seuil_km": seuil,
                                                "debut_reference": reference.isoformat()}, techs_avant, techs_apres)
        return self.km_lire_reglages()

    def _journaliser_reglages_km(self, actuels: dict, apres: dict, techs_avant: dict, techs_apres: dict) -> None:
        """Journal des réglages du kilométrage : jamais les codes postaux, seulement s'ils ont changé."""
        avant = {"taux": actuels["taux"], "seuil_km": actuels["seuil_km"],
                 "debut_reference": actuels["debut_reference"]}
        apres = {"taux": float(apres["taux"]), "seuil_km": float(apres["seuil_km"]),
                 "debut_reference": apres["debut_reference"]}
        techs, change = {}, avant != apres
        for nom in sorted(set(techs_avant) | set(techs_apres)):
            a, b = techs_avant.get(nom), techs_apres.get(nom)
            ligne = {"paye_km_avant": a["paye_km"] if a else None, "paye_km_apres": b["paye_km"] if b else None,
                     "code_postal_modifie": "oui" if (a or {}).get("code_postal", "") != (b or {}).get("code_postal", "")
                     else "non"}
            techs[nom] = ligne
            change = change or ligne["paye_km_avant"] != ligne["paye_km_apres"] or ligne["code_postal_modifie"] == "oui"
        if not change:
            return
        self.journal.inscrire("km_reglages", 0, "", {"avant": avant, "apres": apres, "techniciens": techs})

    # ---------- liste et analyse ----------
    def _ligne_liste(self, bon_id: int) -> dict:
        b = self.bons[bon_id]
        p = b.get("proposition")
        statut = b.get("statut_force") or (p.statut if p else "a_analyser")
        raison = b.get("erreur") or (alerte_principale(p.alertes).message if p and p.alertes else "")
        return {"id": bon_id, "code": b["code"], "client": b["client"], "date": b["date"], "statut": statut,
                "raison": raison, "nb_alertes": len(p.alertes) if p else 0, "approuve": b.get("approuve", False)}

    def liste(self) -> dict:
        with self.verrou:
            return {"bons": [self._ligne_liste(i) for i in sorted(self.bons, key=lambda i: self.bons[i]["code"])]}

    def charger(self, debut: str, fin: str) -> dict:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", debut or "") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fin or ""):
            raise ErreurDemande("Choisir une date de début et une date de fin.")
        p = self.cfg["progression"]
        if not self.demo and not p.get("logic_ids_a_facturer"):
            raise ErreurDemande("Configuration incomplète : remplir logic_ids_a_facturer dans "
                                "_logiciel/config.toml (voir l'inspection des vrais bons).")
        with self.verrou:
            if self.progres["en_cours"] or self.envoi_en_cours:
                raise ErreurDemande("Une analyse ou un envoi est en cours : attendre la fin.")
        progression, _ = self.services()
        try:
            taches = progression.lister_bons(p.get("logic_ids_a_facturer", ""), p.get("type_tache", ""), f"{debut},{fin}")
        except ErreurProgression as e:
            raise ErreurDemande(str(e)) from e
        with self.verrou:
            self.bons = {}
            for t in taches:
                self.bons[t["id"]] = {"code": t.get("code") or str(t["id"]),
                                      "client": (t.get("client") or {}).get("label") or "",
                                      "date": (t.get("rv") or "")[:10]}
        return self.liste()

    def analyser(self, bon_ids: list[int], forcer: bool = False) -> dict:
        with self.verrou:
            if self.progres["en_cours"] or self.envoi_en_cours:
                raise ErreurDemande("Une analyse ou un envoi est déjà en cours.")
            ids = [i for i in bon_ids if i in self.bons]
            self.progres = {"en_cours": True, "fait": 0, "total": len(ids), "message": ""}
        if forcer:
            for bon_id in ids:
                effacer_cache(self.cache, bon_id)
        threading.Thread(target=self._analyser, args=(ids,), daemon=True).start()
        return dict(self.progres)

    def _analyser(self, ids: list[int]) -> None:
        message = "Analyse terminée."
        try:
            progression, client = self.services()
            regles = charger_regles(self.chemin_regles)
            for bon_id in ids:
                with self.verrou:
                    b = self.bons.get(bon_id)
                    if b is None:
                        continue
                    self.progres["message"] = f"Analyse de {b['code']}…"
                try:
                    bon = progression.lire_bon(bon_id)
                    if self.journal.deja_ecrit(bon.id, bon.maj):
                        # Déjà écrit et inchangé depuis : on ne réécrit pas la description une deuxième fois.
                        with self.verrou:
                            b.update(statut_force="envoye", erreur="Déjà écrit dans Progression.", approuve=False)
                        continue
                    proposition = analyser_bon(bon, progression, client, self.cfg, regles, self.journal, self.cache)
                except Exception as e:  # le bon reste « à analyser », avec la raison affichée
                    with self.verrou:
                        b.update(erreur=f"Analyse impossible : {e}", proposition=None, statut_force=None)
                else:
                    with self.verrou:
                        b.update(bon=bon, proposition=proposition, erreur="", approuve=False, statut_force=None,
                                 regles=regles)
                finally:
                    with self.verrou:
                        self.progres["fait"] += 1
            self.verifier_doublons()
        except ErreurDemande as e:
            message = str(e)
        except Exception as e:
            message = f"Analyse interrompue : {e}"
        finally:
            with self.verrou:
                self.progres.update(en_cours=False, message=message)

    def verifier_doublons(self) -> None:
        """Bloque un bon dont une facture est déjà dans un autre bon (lot, journal ou Progression)."""
        progression = self.services()[0]
        with self.verrou:
            ordre = sorted(self.bons, key=lambda i: self.bons[i]["code"])
            propositions = [self.bons[i]["proposition"] for i in ordre
                            if self.bons[i].get("proposition") and self.bons[i].get("statut_force") != "envoye"]
        try:
            doublons_externes(propositions, self.journal, progression, self.memo_progression)
        except ErreurProgression:
            doublons_externes(propositions, self.journal, None, self.memo_progression)
        with self.verrou:
            paires = [(self.bons[i]["bon"], self.bons[i]["proposition"]) for i in ordre
                      if self.bons[i].get("proposition") and self.bons[i].get("bon")]
        transports_en_double(paires)

    # ---------- un bon ----------
    def _bon(self, bon_id: int) -> dict:
        b = self.bons.get(bon_id)
        if not b or not b.get("proposition"):
            raise ErreurDemande("Ce bon n'est pas encore analysé.")
        return b

    def detail(self, bon_id: int) -> dict:
        with self.verrou:
            b = self._bon(bon_id)
            bon, p = b["bon"], b["proposition"]
            return {
                "liste": self._ligne_liste(bon_id),
                "bon": {"description": bon.description, "achat": bon.achat, "demande": bon.demande,
                        "type": bon.type_bon, "lignes": [asdict(l) for l in bon.lignes],
                        "entrees": [{"technicien": e.technicien, "jour": str(e.jour or ""), "minutes": e.minutes}
                                    for e in bon.entrees]},
                "proposition": proposition_vers_dict(p),
                "pieces": [{"id": pc.id, "nom": pc.nom, "type": pc.type_mime} for pc in bon.pieces],
            }

    def modifier(self, bon_id: int, champ: str, valeur) -> dict:
        with self.verrou:
            b = self._bon(bon_id)
            p = b["proposition"]
            if champ == "raison_rabais":
                if not p.rabais:
                    raise ErreurDemande("Ce bon n'a pas de rabais.")
                p.rabais["raison"] = " ".join(str(valeur).split())[:300]
                if b.get("approuve"):   # déjà approuvé : la raison rejoint le relevé des rabais
                    self._journaliser_approbation(bon_id)
            elif champ == "description":
                p.description = str(valeur).strip()
                p.origine["description"] = f"Modifié par {self.personne}"
                b["approuve"] = False
            else:
                m = re.fullmatch(r"ligne:(\d+):(quantite|prix|libelle)", champ or "")
                if not m or int(m.group(1)) >= len(p.lignes):
                    raise ErreurDemande("Champ inconnu.")
                ligne = p.lignes[int(m.group(1))]
                if m.group(2) == "libelle":
                    ligne.libelle = str(valeur).strip()
                else:
                    try:
                        nombre = _nombre(valeur)
                    except ValueError:
                        raise ErreurDemande("Inscrire un nombre (ex. 2,25).") from None
                    if nombre < 0:
                        raise ErreurDemande("Le nombre ne peut pas être négatif.")
                    setattr(ligne, m.group(2), round(nombre, 4))
                    if m.group(2) == "quantite" and ligne.id is not None and nombre > 0 and ligne.id in p.lignes_retirees:
                        p.lignes_retirees = [i for i in p.lignes_retirees if i != ligne.id]   # Hugo la garde
                    if m.group(2) == "quantite" and ligne.id is not None:
                        # Hugo a fixé lui-même la quantité : l'alerte sur l'excédent ajouté à cette ligne ne tient plus.
                        p.alertes = [a for a in p.alertes if not (a.code == "transport_long" and a.ligne_id == ligne.id)]
                cle = str(ligne.id) if ligne.id is not None else ligne.external_id
                p.origine[cle] = f"Modifié par {self.personne}"
                raison = p.rabais.get("raison", "")
                p.rabais, alertes = evaluer_rabais(b["bon"], p.lignes, b["regles"])
                if p.rabais:
                    p.rabais["raison"] = raison
                p.alertes = [a for a in p.alertes if a.code != "rabais"] + alertes
                b["approuve"] = False
            self._garder(b)
        return self.detail(bon_id)

    def _garder(self, b: dict) -> None:
        """Garde la proposition modifiée dans le cache, pour la retrouver au prochain chargement."""
        fichier = chemin_cache(self.cache, b["bon"], b["regles"], self.cfg)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(proposition_vers_dict(b["proposition"]), ensure_ascii=False, indent=1),
                           encoding="utf-8")

    def approuver(self, bon_ids: list[int]) -> dict:
        with self.verrou:
            for bon_id in bon_ids:
                if self._bon(bon_id)["proposition"].statut == "bloque":
                    raise ErreurDemande(f"Le bon {self.bons[bon_id]['code']} est bloqué : corriger dans Progression "
                                        "puis réanalyser.")
            for bon_id in bon_ids:
                b = self.bons[bon_id]
                b["approuve"] = True
                self._journaliser_approbation(bon_id)
        return self.liste()

    def _journaliser_approbation(self, bon_id: int) -> None:
        b = self.bons[bon_id]
        details = {"code": b["code"], "client": b["client"]}
        if b["proposition"].rabais:
            details["rabais"] = dict(b["proposition"].rabais)
        self.journal.inscrire("approuve", bon_id, b["proposition"].maj, details)

    def envoyer(self, mode: str) -> dict:
        if mode not in ("simulation", "reel"):
            raise ErreurDemande("Mode inconnu.")
        if mode == "reel" and self.demo:
            raise ErreurDemande("Écriture réelle verrouillée en mode démo.")
        with self.verrou:
            if self.envoi_en_cours or self.progres["en_cours"]:
                raise ErreurDemande("Une analyse ou un envoi est déjà en cours : attendre la fin.")
            choisis = [b for b in self.bons.values() if b.get("approuve") and b.get("proposition")]
            if not choisis:
                raise ErreurDemande("Aucun bon approuvé à envoyer.")
            # Copies : une modification faite pendant l'envoi ne change pas ce qui part.
            approuves = [copy.deepcopy(b["proposition"]) for b in choisis]
            originaux = {b["bon"].id: copy.deepcopy(b["bon"].lignes) for b in choisis}
            self.envoi_en_cours = True
        try:
            progression, _ = self.services()
            resultats = envoyer(approuves, progression, self.journal, self.cfg["progression"], mode, originaux)
        except ValueError as e:
            raise ErreurDemande(str(e)) from e
        finally:
            with self.verrou:
                self.envoi_en_cours = False
        with self.verrou:
            for r in resultats:
                b = self.bons[r["bon_id"]]
                r["code"] = b["code"]
                if r["resultat"] in ("ecrit", "deja_ecrit"):
                    b.update(statut_force="envoye", approuve=False)
                elif r["resultat"] == "perime":
                    b.update(statut_force="a_verifier", approuve=False, erreur=r["message"])
                elif r["resultat"] == "doublon":
                    b.update(statut_force="bloque", approuve=False, erreur=r["message"])
        return {"resultats": resultats, **self.liste()}

    def piece(self, piece_id: int) -> tuple[bytes, str]:
        with self.verrou:
            connu = any(pc.id == piece_id for b in self.bons.values() if b.get("bon") for pc in b["bon"].pieces)
            mime = next((pc.type_mime for b in self.bons.values() if b.get("bon")
                         for pc in b["bon"].pieces if pc.id == piece_id), "")
        if not connu:
            raise ErreurDemande("Pièce inconnue.")
        if piece_id not in self.pieces_cache:
            progression, _ = self.services()
            self.pieces_cache[piece_id] = (progression.telecharger_piece(piece_id), mime)
        return self.pieces_cache[piece_id]

    # ---------- règles et historique ----------
    def lire_regles(self) -> dict:
        r = charger_regles(self.chemin_regles)
        with self.verrou:
            vus = {e.technicien for b in self.bons.values() if b.get("bon") for e in b["bon"].entrees if e.technicien}
        return {**asdict(r), "km_debut_reference": r.km_debut_reference.isoformat(),
                "techniciens_connus": sorted(vus - set(r.couts_techniciens) - set(r.salaire_fixe))}

    @staticmethod
    def _liste_noms(valeur, actuels: list, quoi: str) -> list:
        """Liste de noms (techniciens à salaire fixe, produits au forfait) : sans doublon ni nom vide."""
        if valeur is None:
            return actuels
        if isinstance(valeur, str):
            valeur = valeur.split(",")
        if not isinstance(valeur, list):
            raise ErreurDemande(f"Liste des {quoi} invalide.")
        noms = []
        for nom in valeur:
            nom = " ".join(str(nom).split())[:80]
            if nom and nom not in noms:
                noms.append(nom)
        return noms[:50]

    @staticmethod
    def _couts_techniciens(valeur, actuels: dict) -> dict:
        """Taux horaires inscrits par technicien : nom non vide, taux entre 0 et 500 $; un taux vide retire la ligne."""
        if valeur is None:
            return actuels
        if not isinstance(valeur, dict):
            raise ErreurDemande("Liste des coûts horaires invalide.")
        couts = {}
        for nom, taux in valeur.items():
            nom = " ".join(str(nom).split())[:80]
            if not nom or str(taux).strip() == "":
                continue
            try:
                n = _nombre(taux)
            except ValueError:
                raise ErreurDemande(f"Coût horaire invalide pour {nom}.") from None
            if not 0 < n <= 500:
                raise ErreurDemande(f"Le coût horaire de {nom} doit être entre 0 et 500 $.")
            couts[nom] = n
        return couts

    def ecrire_regles(self, valeurs: dict) -> dict:
        actuelles = self.lire_regles()
        nouvelles = {}
        for nom, (_, _, type_) in CHAMPS_REGLES.items():
            v = valeurs.get(nom, actuelles[nom])
            try:
                if type_ is bool:
                    nouvelles[nom] = v is True or str(v).lower() in ("true", "1", "oui")
                elif type_ is str:
                    nouvelles[nom] = str(v).strip() or actuelles[nom]
                else:
                    n = _nombre(v)
                    bas, haut = BORNES.get(nom, (0, math.inf))
                    if not bas <= n <= haut:
                        raise ErreurDemande(f"« {nom} » doit être entre {bas:g} et {haut:g}.")
                    nouvelles[nom] = int(n) if type_ is int else n
            except ValueError:
                raise ErreurDemande(f"Valeur invalide pour « {nom} ».") from None
        couts = self._couts_techniciens(valeurs.get("couts_techniciens"), actuelles["couts_techniciens"])
        salaire_fixe = self._liste_noms(valeurs.get("salaire_fixe"), actuelles["salaire_fixe"], "techniciens à salaire fixe")
        produits = self._liste_noms(valeurs.get("produits_forfait"), actuelles["produits_forfait"], "produits au forfait")
        if nouvelles["regle_transports"] not in REGLES_TRANSPORTS:
            raise ErreurDemande("Règle des transports inconnue.")
        # On repart du fichier actuel : les sections que la page ne modifie pas (tarifs) sont conservées.
        donnees = tomllib.loads(self.chemin_regles.read_text(encoding="utf-8"))
        for nom, (section, cle, _) in CHAMPS_REGLES.items():
            donnees.setdefault(section, {})[cle] = nouvelles[nom]
        donnees.setdefault("couts", {})["techniciens"] = couts
        donnees.setdefault("transports", {})["salaire_fixe"] = salaire_fixe
        donnees.setdefault("forfaits", {})["produits"] = produits
        contenu = "# Règles appliquées à chaque bon de service. Modifiables dans l'onglet Règles.\n"
        contenu += f"# Dernière modification : {self.personne}\n" + toml_texte(donnees)
        self.chemin_regles.write_text(contenu, encoding="utf-8")
        return self.lire_regles()

    def historique(self) -> dict:
        return {"questions": self.questions.historique(100), "evenements": self.journal.historique(),
                "rabais": self.journal.rabais()}


dernier_signe_de_vie = time.monotonic()


def creer_gestionnaire(app: Application):
    class Gestionnaire(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def envoyer(self, code: int, contenu: bytes, type_: str, entetes: dict | None = None) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", type_)
                self.send_header("Cache-Control", "no-store")
                for nom, valeur in (entetes or {}).items():
                    self.send_header(nom, valeur)
                self.end_headers()
                self.wfile.write(contenu)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

        def json(self, valeur: dict, code: int = 200) -> None:
            self.envoyer(code, json.dumps(valeur, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _autorise(self) -> bool:
            """Seule la page servie par cet outil peut l'utiliser (protège des autres sites ouverts)."""
            port = self.server.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return False
            origine = self.headers.get("Origin")
            if origine and origine not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return False
            url = urlparse(self.path)
            if self.command == "GET" and url.path in ("/", "/logo.png", "/signe-de-vie"):
                return True
            jeton = self.headers.get("X-Jeton") or parse_qs(url.query).get("jeton", [""])[0]
            return secrets.compare_digest(jeton.encode(), app.jeton.encode())

        def _traiter(self, fonction) -> None:
            global dernier_signe_de_vie
            dernier_signe_de_vie = time.monotonic()
            if not self._autorise():
                self.json({"erreur": "Accès refusé."}, 403)
                return
            try:
                fonction()
            except ErreurDemande as e:
                self.json({"erreur": str(e)}, 400)
            except Exception as e:  # affiché dans la page plutôt que de planter le serveur
                self.json({"erreur": f"Erreur inattendue : {e}"}, 500)

        def do_GET(self) -> None:
            self._traiter(self._get)

        def do_POST(self) -> None:
            self._traiter(self._post)

        def _requete(self, nom: str) -> str:
            return parse_qs(urlparse(self.path).query).get(nom, [""])[0]

        def _get(self) -> None:
            chemin = urlparse(self.path).path
            if chemin == "/":
                page = (ICI / "interface.html").read_text(encoding="utf-8").replace("__JETON__", app.jeton)
                self.envoyer(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif chemin == "/logo.png":
                self.envoyer(200, (ICI / "logo_progim.png").read_bytes(), "image/png")
            elif chemin == "/etat":
                self.json(app.etat())
            elif chemin == "/signe-de-vie":
                self.json({"ok": True})
            elif chemin == "/bons":
                self.json(app.liste())
            elif chemin == "/progres":
                self.json(dict(app.progres))
            elif chemin == "/regles":
                self.json(app.lire_regles())
            elif chemin == "/historique":
                self.json(app.historique())
            elif chemin == "/km/periodes":
                self.json(app.km_periodes())
            elif chemin == "/km/progres":
                with app.verrou:
                    self.json(dict(app.km_progres))
            elif chemin == "/km/periode":
                self.json(app.km_periode(self._requete("debut")))
            elif chemin == "/km/export":
                contenu, nom = app.km_export(self._requete("debut"))
                self.envoyer(200, contenu, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})
            elif chemin == "/km/reglages":
                self.json(app.km_lire_reglages())
            elif chemin == "/recommandations":
                self.json({"recommandations": app.liste_recommandations()})
            elif chemin == "/recommandations/export":
                contenu, nom = app.export_recommandations()
                self.envoyer(200, contenu, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(nom)}"})
            elif m := re.fullmatch(r"/bon/(\d+)", chemin):
                self.json(app.detail(int(m.group(1))))
            elif m := re.fullmatch(r"/piece/(\d+)", chemin):
                contenu, mime = app.piece(int(m.group(1)))
                if mime not in TYPES_PIECES:
                    raise ErreurDemande("Aperçu impossible pour ce format : ouvrir la pièce dans Progression.")
                self.envoyer(200, contenu, mime)
            else:
                self.json({"erreur": "Introuvable."}, 404)

        def _post(self) -> None:
            longueur = int(self.headers.get("Content-Length") or 0)
            try:
                corps = json.loads(self.rfile.read(longueur) or b"{}")
            except ValueError:
                raise ErreurDemande("Demande illisible.") from None
            chemin = urlparse(self.path).path
            if chemin == "/charger":
                self.json(app.charger(corps.get("debut", ""), corps.get("fin", "")))
            elif chemin == "/analyser":
                self.json(app.analyser([int(i) for i in corps.get("bon_ids", [])], bool(corps.get("forcer"))))
            elif chemin == "/approuver":
                self.json(app.approuver([int(i) for i in corps.get("bon_ids", [])]))
            elif chemin == "/envoyer":
                self.json(app.envoyer(corps.get("mode", "")))
            elif chemin == "/regles":
                self.json(app.ecrire_regles(corps))
            elif chemin == "/cles":
                self.json(app.enregistrer_cles(corps.get("progression"), corps.get("claude"), corps.get("google")))
            elif chemin == "/km/calculer":
                self.json(app.km_calculer(corps.get("debut", "")))
            elif chemin == "/km/ajuster":
                self.json(app.km_ajuster(corps))
            elif chemin == "/km/valider":
                self.json(app.km_valider(corps.get("debut", "")))
            elif chemin == "/km/rouvrir":
                self.json(app.km_rouvrir(corps.get("debut", ""), corps.get("raison", "")))
            elif chemin == "/km/reglages":
                self.json(app.km_ecrire_reglages(corps))
            elif chemin == "/recommandation/brouillon":
                self.json(app.brouillon_recommandation(corps.get("historique"), corps.get("bon_id")))
            elif chemin == "/recommandation":
                self.json(app.ajouter_recommandation(corps))
            elif chemin == "/recommandation/statut":
                self.json(app.statut_recommandation(corps.get("id"), corps.get("statut"), corps.get("note", "")))
            elif chemin == "/assistant":
                self.json(app.assistant(corps.get("question"), corps.get("bon_id"), corps.get("historique")))
            elif m := re.fullmatch(r"/bon/(\d+)/modifier", chemin):
                self.json(app.modifier(int(m.group(1)), corps.get("champ", ""), corps.get("valeur", "")))
            else:
                self.json({"erreur": "Introuvable."}, 404)

    return Gestionnaire


class Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


DELAI_ARRET = 300  # secondes sans signe de vie (un onglet en arrière-plan en envoie moins souvent)


def doit_arreter(app: Application, inactif_depuis: float) -> bool:
    """Jamais pendant une analyse ou un envoi; sinon après cinq minutes sans la page."""
    if app.progres.get("en_cours") or app.envoi_en_cours:
        return False
    return inactif_depuis > DELAI_ARRET


def precharger_sdk() -> None:
    """Charge le SDK de Claude en arrière-plan, une fois la page ouverte : la première analyse ou la première
    question à Jarvis n'attend pas. Jamais avant l'ouverture : ses milliers de fichiers retardaient la page."""
    try:
        import anthropic  # noqa: F401
    except Exception:
        pass


def surveiller(serveur: ThreadingHTTPServer, app: Application) -> None:
    while True:
        time.sleep(10)
        if doit_arreter(app, time.monotonic() - dernier_signe_de_vie):
            serveur.shutdown()
            return


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    personne = nom_personne(os.environ.get("USERNAME") or os.environ.get("USER") or "poste")
    app = Application(ICI, demo=demo, personne=personne)
    serveur = Serveur(("127.0.0.1", 0), creer_gestionnaire(app))
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    if "--sans-arret" not in sys.argv:
        threading.Thread(target=surveiller, args=(serveur, app), daemon=True).start()
    if "--sans-navigateur" not in sys.argv:
        webbrowser.open(adresse)
    if not demo:
        threading.Thread(target=precharger_sdk, daemon=True).start()
    print(f"Révision des bons ouverte dans le navigateur : {adresse}" + (" (démo)" if demo else ""))
    print("Cette fenêtre se ferme toute seule quelques minutes après la fermeture de la page.")
    serveur.serve_forever()
