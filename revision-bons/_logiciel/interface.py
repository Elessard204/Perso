"""Interface de la révision des bons, ouverte dans le navigateur par « Révision des bons.bat ».

Petit serveur local (127.0.0.1 seulement), comme l'outil des rapports clients. Il s'arrête tout seul
une minute après la fermeture de la page. Option --demo : faux bons, sans réseau ni clé.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import tomllib
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Le Python portable n'ajoute pas le dossier du script au chemin des modules.
ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

import cles  # noqa: E402
from analyse import analyser_bon, fichier_cache, proposition_vers_dict  # noqa: E402
from claude_client import creer_client  # noqa: E402
from envoi import envoyer  # noqa: E402
from journal import Journal  # noqa: E402
from progression import ErreurProgression, Progression  # noqa: E402
from regles import charger_regles  # noqa: E402

TYPES_PIECES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
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
}


def alerte_principale(alertes):
    """L'alerte à montrer dans la liste : bloquante d'abord, le transport à définir en dernier."""
    return sorted(alertes, key=lambda a: (not a.bloquante, a.code == "transport_a_definir"))[0]


class ErreurDemande(Exception):
    """Demande refusée, avec un message à afficher dans la page."""


def _nombre(valeur) -> float:
    if isinstance(valeur, bool):
        raise ValueError
    if isinstance(valeur, (int, float)):
        return float(valeur)
    return float(str(valeur).replace(",", ".").replace(" ", "").replace(" ", ""))


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
        self.cache = self.donnees / "cache"
        self.verrou = threading.Lock()
        self.bons: dict[int, dict] = {}   # id -> {code, client, date, statut, raison, bon, proposition, approuve}
        self.progres = {"en_cours": False, "fait": 0, "total": 0, "message": ""}
        self.pieces_cache: dict[int, tuple[bytes, str]] = {}
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

    def etat(self) -> dict:
        return {"demo": self.demo, "personne": self.personne, "cles": cles.etat(),
                "mode_reel_permis": bool(self.cfg["progression"].get("ecriture_validee")) and not self.demo}

    def enregistrer_cles(self, progression: str | None, claude: str | None) -> dict:
        cles.ecrire(progression or None, claude or None)
        self._services = None
        return self.etat()

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
        progression, _ = self.services()
        p = self.cfg["progression"]
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

    def analyser(self, bon_ids: list[int]) -> dict:
        with self.verrou:
            if self.progres["en_cours"]:
                raise ErreurDemande("Une analyse est déjà en cours.")
            ids = [i for i in bon_ids if i in self.bons]
            self.progres = {"en_cours": True, "fait": 0, "total": len(ids), "message": ""}
        threading.Thread(target=self._analyser, args=(ids,), daemon=True).start()
        return self.progres

    def _analyser(self, ids: list[int]) -> None:
        try:
            progression, client = self.services()
            regles = charger_regles(self.chemin_regles)
        except ErreurDemande as e:
            with self.verrou:
                self.progres.update(en_cours=False, message=str(e))
            return
        for bon_id in ids:
            with self.verrou:
                self.progres["message"] = f"Analyse de {self.bons[bon_id]['code']}…"
            try:
                bon = progression.lire_bon(bon_id)
                proposition = analyser_bon(bon, progression, client, self.cfg, regles, self.journal, self.cache)
            except Exception as e:  # le bon reste « à analyser », avec la raison affichée
                with self.verrou:
                    self.bons[bon_id].update(erreur=f"Analyse impossible : {e}", proposition=None, statut_force=None)
            else:
                with self.verrou:
                    self.bons[bon_id].update(bon=bon, proposition=proposition, erreur="", approuve=False,
                                             statut_force=None)
            with self.verrou:
                self.progres["fait"] += 1
        with self.verrou:
            self.progres.update(en_cours=False, message="Analyse terminée.")

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
                "bon": {"description": bon.description, "lignes": [asdict(l) for l in bon.lignes],
                        "entrees": [{"technicien": e.technicien, "jour": str(e.jour or ""), "minutes": e.minutes}
                                    for e in bon.entrees]},
                "proposition": proposition_vers_dict(p),
                "pieces": [{"id": pc.id, "nom": pc.nom, "type": pc.type_mime} for pc in bon.pieces],
            }

    def modifier(self, bon_id: int, champ: str, valeur) -> dict:
        with self.verrou:
            b = self._bon(bon_id)
            p = b["proposition"]
            if champ == "description":
                p.description = str(valeur).strip()
                p.origine["description"] = f"Modifié par {self.personne}"
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
                cle = str(ligne.id) if ligne.id is not None else ligne.external_id
                p.origine[cle] = f"Modifié par {self.personne}"
            b["approuve"] = False
            fichier = fichier_cache(self.cache, b["bon"])
            fichier.parent.mkdir(parents=True, exist_ok=True)
            fichier.write_text(json.dumps(proposition_vers_dict(p), ensure_ascii=False, indent=1), encoding="utf-8")
        return self.detail(bon_id)

    def approuver(self, bon_ids: list[int]) -> dict:
        with self.verrou:
            for bon_id in bon_ids:
                if self._bon(bon_id)["proposition"].statut == "bloque":
                    raise ErreurDemande(f"Le bon {self.bons[bon_id]['code']} est bloqué : corriger dans Progression "
                                        "puis réanalyser.")
            for bon_id in bon_ids:
                b = self.bons[bon_id]
                b["approuve"] = True
                self.journal.inscrire("approuve", bon_id, b["proposition"].maj, {"code": b["code"]})
        return self.liste()

    def envoyer(self, mode: str) -> dict:
        if mode not in ("simulation", "reel"):
            raise ErreurDemande("Mode inconnu.")
        if mode == "reel" and self.demo:
            raise ErreurDemande("Écriture réelle verrouillée en mode démo.")
        with self.verrou:
            approuves = [b["proposition"] for b in self.bons.values() if b.get("approuve") and b.get("proposition")]
        if not approuves:
            raise ErreurDemande("Aucun bon approuvé à envoyer.")
        progression, _ = self.services()
        try:
            resultats = envoyer(approuves, progression, self.journal, self.cfg["progression"], mode)
        except ValueError as e:
            raise ErreurDemande(str(e)) from e
        with self.verrou:
            for r in resultats:
                b = self.bons[r["bon_id"]]
                r["code"] = b["code"]
                if r["resultat"] in ("ecrit", "deja_ecrit"):
                    b.update(statut_force="envoye", approuve=False)
                elif r["resultat"] == "perime":
                    b.update(statut_force="a_verifier", approuve=False, erreur=r["message"])
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
        return asdict(r)

    def ecrire_regles(self, valeurs: dict) -> dict:
        actuelles = self.lire_regles()
        nouvelles = {}
        for nom, (_, _, type_) in CHAMPS_REGLES.items():
            v = valeurs.get(nom, actuelles[nom])
            try:
                if type_ is bool:
                    nouvelles[nom] = bool(v)
                elif type_ is str:
                    nouvelles[nom] = str(v).strip() or actuelles[nom]
                else:
                    n = _nombre(v)
                    if n < 0:
                        raise ValueError
                    nouvelles[nom] = int(n) if type_ is int else n
            except ValueError:
                raise ErreurDemande(f"Valeur invalide pour « {nom} ».") from None
        if nouvelles["pas_minutes"] <= 0:
            raise ErreurDemande("Le pas d'arrondi doit être plus grand que 0.")
        sections: dict[str, list[str]] = {}
        for nom, (section, cle, type_) in CHAMPS_REGLES.items():
            v = nouvelles[nom]
            texte = ("true" if v else "false") if type_ is bool else (json.dumps(v, ensure_ascii=False)
                                                                      if type_ is str else repr(v))
            sections.setdefault(section, []).append(f"{cle} = {texte}")
        contenu = "# Règles appliquées à chaque bon de service. Modifiables dans l'onglet Règles.\n"
        contenu += f"# Dernière modification : {self.personne}\n"
        for section, lignes in sections.items():
            contenu += f"[{section}]\n" + "\n".join(lignes) + "\n"
        self.chemin_regles.write_text(contenu, encoding="utf-8")
        return self.lire_regles()

    def historique(self) -> dict:
        return {"evenements": self.journal.historique()}


dernier_signe_de_vie = time.monotonic()


def creer_gestionnaire(app: Application):
    class Gestionnaire(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def envoyer(self, code: int, contenu: bytes, type_: str) -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", type_)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(contenu)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

        def json(self, valeur: dict, code: int = 200) -> None:
            self.envoyer(code, json.dumps(valeur, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _traiter(self, fonction) -> None:
            global dernier_signe_de_vie
            dernier_signe_de_vie = time.monotonic()
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

        def _get(self) -> None:
            chemin = urlparse(self.path).path
            if chemin == "/":
                self.envoyer(200, (ICI / "interface.html").read_bytes(), "text/html; charset=utf-8")
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
                self.json(app.analyser([int(i) for i in corps.get("bon_ids", [])]))
            elif chemin == "/approuver":
                self.json(app.approuver([int(i) for i in corps.get("bon_ids", [])]))
            elif chemin == "/envoyer":
                self.json(app.envoyer(corps.get("mode", "")))
            elif chemin == "/regles":
                self.json(app.ecrire_regles(corps))
            elif chemin == "/cles":
                self.json(app.enregistrer_cles(corps.get("progression"), corps.get("claude")))
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


def surveiller(serveur: ThreadingHTTPServer) -> None:
    """Arrête le serveur quand la page ne donne plus signe de vie depuis une minute."""
    while True:
        time.sleep(10)
        if time.monotonic() - dernier_signe_de_vie > 60:
            serveur.shutdown()
            return


if __name__ == "__main__":
    demo = "--demo" in sys.argv
    personne = re.sub(r"[^0-9A-Za-z._-]", "_", os.environ.get("USERNAME") or os.environ.get("USER") or "poste")
    app = Application(ICI, demo=demo, personne=personne)
    serveur = Serveur(("127.0.0.1", 0), creer_gestionnaire(app))
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    if "--sans-arret" not in sys.argv:
        threading.Thread(target=surveiller, args=(serveur,), daemon=True).start()
    if "--sans-navigateur" not in sys.argv:
        webbrowser.open(adresse)
    print(f"Révision des bons ouverte dans le navigateur : {adresse}" + (" (démo)" if demo else ""))
    print("Cette fenêtre se ferme toute seule une minute après la fermeture de la page.")
    serveur.serve_forever()
