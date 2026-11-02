"""Interface de l'outil d'envoi des rapports clients, ouverte dans le navigateur par « Rapports clients.bat ».

Petit serveur local (127.0.0.1 seulement) : le Python portable de Progim n'a pas de quoi afficher
une fenêtre Windows, comme pour l'outil de facturation. Le serveur s'arrête tout seul quand la page
est fermée depuis une minute.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Le Python portable n'ajoute pas le dossier du script au chemin des modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import edition_excel  # noqa: E402
from envoi_rapports import ICI, MOIS_FR, outlook_configure, preparer  # noqa: E402

# Réglages propres à chaque personne (pas dans le dossier partagé) : les chemins OneDrive
# diffèrent d'un poste à l'autre, par exemple C:\Users\<nom>\OneDrive - Progim\...
PARAMETRES = Path(os.environ.get("APPDATA") or Path.home()) / "Progim Rapports clients" / "parametres.json"
SORTIE = ICI / "sortie"
# Le code est rangé dans « _logiciel »; l'équipe ne voit que le dossier de l'outil, juste au-dessus.
DOSSIER_OUTIL = ICI.parent if ICI.name == "_logiciel" else ICI
dernier_signe_de_vie = time.monotonic()


def lire_parametres() -> dict:
    try:
        return json.loads(PARAMETRES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_parametres(valeurs: dict) -> None:
    try:
        PARAMETRES.parent.mkdir(parents=True, exist_ok=True)
        PARAMETRES.write_text(json.dumps(valeurs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def mois_recents(nombre: int = 6) -> list[dict]:
    """Les derniers mois terminés, le plus récent en premier."""
    annee, mois = date.today().year, date.today().month
    resultat = []
    for _ in range(nombre):
        mois -= 1
        if mois == 0:
            annee, mois = annee - 1, 12
        resultat.append({"code": f"{annee}-{mois:02d}", "libelle": f"{MOIS_FR[mois - 1].capitalize()} {annee}"})
    return resultat


def racine_clients(parametres: dict) -> str:
    """Le dossier 1_CLIENTS : celui choisi sur ce poste, sinon celui à côté du dossier de l'outil."""
    racine = parametres.get("racine", "")
    if racine and Path(racine).is_dir():
        return racine
    voisine = DOSSIER_OUTIL.parent / "1_CLIENTS"
    return str(voisine) if voisine.is_dir() else ""


def trouver_dossier_du_mois(racine: str, mois: str) -> str:
    """Dans 1_CLIENTS, trouve le sous-dossier du mois, par exemple « 09-septembre 2026 »."""
    racine_ = Path(racine)
    if not racine or not racine_.is_dir():
        return ""
    for dossier in sorted(racine_.iterdir()):
        if dossier.is_dir() and re.match(rf"^0?{int(mois[5:])}\D", dossier.name) and mois[:4] in dossier.name:
            return str(dossier)
    return ""


def excel_clients(parametres: dict) -> str:
    excel = parametres.get("excel", "")
    return excel if excel and Path(excel).is_file() else str(DOSSIER_OUTIL / "clients_rapports.xlsx")


def chemin(plein: str) -> dict:
    """Chemin complet (utilisé par l'outil) et version courte à afficher, sans « C:\\Users\\<nom>\\OneDrive - ... »."""
    bibliotheque = DOSSIER_OUTIL.parent.parent  # p. ex. « COMPTABILITÉ - Documents »
    try:
        court = str(Path(plein).relative_to(bibliotheque)) if plein else ""
    except ValueError:
        court = plein
    return {"plein": plein, "court": court}


def choisir_dossier(depart: str) -> str:
    """Boîte « Choisir un dossier » de Windows, par PowerShell."""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description = 'Dossier des rapports Hopem du mois';"
        f"$d.SelectedPath = '{depart.replace(chr(39), chr(39) * 2)}';"
        "if ($d.ShowDialog() -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $d.SelectedPath }"
    )
    resultat = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script],
                              capture_output=True, text=True, encoding="utf-8", check=False)
    return resultat.stdout.strip()


def ouvrir(chemin: Path) -> bool:
    if not chemin.exists():
        return False
    if sys.platform == "win32":
        os.startfile(chemin)  # noqa: S606 — ouvre avec l'application par défaut de Windows
    else:
        webbrowser.open(chemin.as_uri())
    return True


def brouillons_deja_crees(mois: str) -> dict[str, str]:
    """Courriels déjà créés ce mois-ci, d'après le journal : {code du courriel: date et heure}."""
    journal = SORTIE / mois / "brouillons.txt"
    deja = {}
    if journal.exists():
        for ligne in journal.read_text(encoding="utf-8").splitlines():
            trouve = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) par .*? : (.+)$", ligne)
            if trouve:
                for code in trouve.group(2).split(","):
                    deja[code.strip()] = trouve.group(1)
    return deja


def pluriel(nombre: int, singulier: str, pluriel_: str) -> str:
    return f"{nombre} {singulier if nombre <= 1 else pluriel_}"


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def envoyer(self, code: int, contenu: bytes, type_: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(contenu)

    def json(self, valeur: dict, code: int = 200) -> None:
        self.envoyer(code, json.dumps(valeur, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        global dernier_signe_de_vie
        dernier_signe_de_vie = time.monotonic()
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}

        if url.path == "/":
            self.envoyer(200, (ICI / "interface.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/logo.png":
            self.envoyer(200, (ICI / "logo_progim.png").read_bytes(), "image/png")
        elif url.path == "/etat":
            parametres = lire_parametres()
            mois = mois_recents()
            racine = racine_clients(parametres)
            self.json({"mois": mois, "excel": chemin(excel_clients(parametres)),
                       "dossiers": {m["code"]: chemin(trouver_dossier_du_mois(racine, m["code"])) for m in mois},
                       "outlook": outlook_configure()})
        elif url.path == "/donnees":
            excel = Path(params.get("excel") or excel_clients(lire_parametres()))
            try:
                self.json(edition_excel.lire(excel))
            except Exception as erreur:  # affiché dans la page
                self.json({"erreur": f"Impossible de lire l'Excel des clients ({erreur})."})
        elif url.path == "/suivi":
            excel = Path(params.get("excel") or excel_clients(lire_parametres()))
            try:
                self.json(edition_excel.lire_suivi(excel, params.get("mois", "")))
            except Exception as erreur:  # affiché dans la page
                self.json({"erreur": f"Impossible de lire le suivi ({erreur})."})
        elif url.path == "/signe-de-vie":
            self.json({"ok": True})
        elif url.path == "/rapport":
            # Sert seulement les rapports du dossier « sortie » de l'outil.
            fichier = (SORTIE / params.get("chemin", "")).resolve()
            if SORTIE.resolve() in fichier.parents and fichier.suffix == ".html" and fichier.is_file():
                self.envoyer(200, fichier.read_bytes(), "text/html; charset=utf-8")
            else:
                self.envoyer(404, "Rapport introuvable.".encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self.envoyer(404, b"", "text/plain")

    def do_POST(self) -> None:
        global dernier_signe_de_vie
        dernier_signe_de_vie = time.monotonic()
        longueur = int(self.headers.get("Content-Length") or 0)
        donnees = json.loads(self.rfile.read(longueur) or b"{}")
        url = urlparse(self.path)

        if url.path == "/choisir-dossier":
            parametres = lire_parametres()
            dossier = choisir_dossier(donnees.get("depart") or racine_clients(parametres))
            if dossier:
                # Le dossier parent (1_CLIENTS) sert à retrouver tout seul le dossier des mois suivants.
                parametres["racine"] = str(Path(dossier).parent)
                ecrire_parametres(parametres)
            self.json({"dossier": chemin(dossier)})
        elif url.path == "/ouvrir":
            mois = donnees.get("mois", "")
            cibles = {"excel": Path(donnees.get("excel") or excel_clients(lire_parametres())),
                      "apercus": SORTIE / mois / "apercus",
                      "dossier": Path(donnees.get("dossier") or ".")}
            cible = cibles.get(donnees.get("quoi"))
            self.json({"ok": bool(cible) and ouvrir(cible)})
        elif url.path == "/lancer":
            self.json(lancer(donnees))
        elif url.path in ("/fiche", "/fiche/retirer", "/gestionnaire", "/gestionnaire/supprimer", "/suivi"):
            excel = Path(donnees.get("excel") or excel_clients(lire_parametres()))
            try:
                if url.path == "/suivi":
                    codes = donnees.get("codes") or [donnees.get("code", "")]
                    self.json(edition_excel.enregistrer_suivi(excel, donnees.get("mois", ""), codes, donnees.get("valeurs", {})))
                elif url.path == "/fiche":
                    self.json(edition_excel.enregistrer_fiche(excel, donnees.get("ligne"), donnees.get("valeurs", {})))
                elif url.path == "/fiche/retirer":
                    self.json(edition_excel.retirer_fiche(excel, int(donnees.get("ligne") or 0), donnees.get("code", "")))
                elif url.path == "/gestionnaire":
                    self.json(edition_excel.enregistrer_gestionnaire(excel, donnees.get("ligne"), donnees.get("nom", ""),
                                                                     donnees.get("courriel", "")))
                else:
                    self.json(edition_excel.supprimer_gestionnaire(excel, donnees.get("nom", ""), donnees.get("remplacant", "")))
            except PermissionError:
                self.json({"erreur": "L'Excel des clients est ouvert ailleurs. Fermez-le et enregistrez de nouveau."})
            except Exception as erreur:  # affiché dans la page
                self.json({"erreur": f"Enregistrement impossible ({erreur})."})
        else:
            self.envoyer(404, b"", "text/plain")


def lancer(donnees: dict) -> dict:
    mois, mode = donnees.get("mois", ""), donnees.get("mode", "simulation")
    excel = Path(donnees.get("excel") or "")
    dossier = donnees.get("dossier") or ""
    if not excel.is_file():
        return {"erreur": f"L'Excel des clients est introuvable : {excel}"}
    exports = None
    if mode != "liste":
        if not dossier or not Path(dossier).is_dir():
            return {"erreur": "Choisissez le dossier où les rapports Hopem du mois ont été téléchargés."}
        exports = Path(dossier)
    codes = set(donnees["codes"]) if donnees.get("codes") else None
    deja = brouillons_deja_crees(mois)
    if mode == "brouillons" and not donnees.get("forcer"):
        # Garde-fou : recréer un courriel déjà fait mettrait un doublon dans la boîte Finance.
        doublons = sorted(c for c in (codes or deja) if c in deja)
        if doublons:
            return {"confirmer": f"{pluriel(len(doublons), 'courriel déjà créé', 'courriels déjà créés')} ce mois-ci "
                                 f"(le {deja[doublons[0]]}). Recliquez pour les recréer quand même; "
                                 "supprimez les anciens dans Outlook au besoin."}
    try:
        suivi = edition_excel.etat_suivi(excel, mois) if mode != "liste" else None
    except PermissionError:
        return {"erreur": "L'Excel des clients est ouvert ailleurs. Fermez-le et recommencez."}
    except Exception as erreur:
        return {"erreur": f"Impossible de lire l'onglet Suivi ({erreur})."}
    parametres = lire_parametres()
    parametres["excel"] = str(excel)
    ecrire_parametres(parametres)
    try:
        resultat = preparer(mois, excel, exports, "simulation" if mode == "liste" else mode,
                            completer=exports is not None, codes=codes, suivi=suivi)
    except PermissionError:
        return {"erreur": "Un fichier est ouvert ailleurs (probablement l'Excel des clients). Fermez-le et recommencez."}
    except Exception as erreur:  # affiché à l'employé plutôt que d'arrêter l'outil
        return {"erreur": str(erreur)}
    reponse = {"rapport": "/rapport?chemin=" + resultat.rapport.relative_to(SORTIE).as_posix()}
    if exports is None:
        reponse["resume"] = "Liste des périodes prête."
        reponse["ok"] = True
    elif mode == "brouillons":
        crees = sum(1 for l in resultat.messages if l.startswith("OK|") and "brouillon créé" in l)
        reponse["resume"] = (f"{pluriel(crees, 'brouillon créé', 'brouillons créés')} dans Outlook > Finance > Brouillons"
                             if resultat.reussi else "La création des brouillons a échoué ou est incomplète.")
        reponse["ok"] = resultat.reussi
        reponse["messages"] = resultat.messages
        # Date d'envoi inscrite dans l'onglet Suivi pour chaque courriel créé.
        crees_noms = {l[3:].split(" : brouillon créé")[0] for l in resultat.messages if "brouillon créé" in l}
        entites = [e for c in resultat.courriels if c["nom"] in crees_noms for e in c["entites"]]
        if entites:
            try:
                edition_excel.marquer_envoi(excel, mois, entites, f"{date.today():%Y-%m-%d}")
            except Exception:
                reponse["messages"].append("AVERT|La date d'envoi n'a pas pu être inscrite dans le Suivi "
                                           "(Excel des clients ouvert ailleurs?).")
        deja = brouillons_deja_crees(mois)
    else:
        reponse["resume"] = (f"{pluriel(resultat.prets, 'courriel prêt', 'courriels prêts')} · "
                             f"{pluriel(resultat.bloques, 'bloqué', 'bloqués')} · "
                             f"{pluriel(resultat.alertes, 'fichier à regarder', 'fichiers à regarder')}")
        reponse["ok"] = resultat.bloques == 0
    # Les aperçus n'existent qu'à l'étape 2 et 3, pour les courriels prêts.
    reponse["apercus"] = exports is not None and resultat.prets > 0
    reponse["courriels"] = [{**c, "deja": deja.get(c["code"], "")} for c in resultat.courriels]
    if resultat.complete:
        reponse["complete"] = f"Noms lus dans les PDF ajoutés dans une copie de l'Excel, à réviser : {resultat.complete.name}"
    return reponse


def surveiller(serveur: ThreadingHTTPServer) -> None:
    """Arrête le serveur quand la page ne donne plus signe de vie depuis une minute."""
    while True:
        time.sleep(10)
        if time.monotonic() - dernier_signe_de_vie > 60:
            serveur.shutdown()
            return


if __name__ == "__main__":
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
    adresse = f"http://127.0.0.1:{serveur.server_address[1]}/"
    threading.Thread(target=surveiller, args=(serveur,), daemon=True).start()
    if "--sans-navigateur" not in sys.argv:
        webbrowser.open(adresse)
    print(f"Rapports clients ouvert dans le navigateur : {adresse}")
    print("Cette fenêtre se ferme toute seule une minute après la fermeture de la page.")
    serveur.serve_forever()
