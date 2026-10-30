"""Préparation de l'envoi mensuel des rapports clients.

Lit l'Excel des clients, associe les exports Hopem du mois à chaque entité,
valide qu'il ne manque rien, fusionne un PDF par entité et prépare un courriel
par client. Rien n'est jamais envoyé : le mode « brouillons » crée des
brouillons dans la boîte finance@ que l'équipe révise et envoie elle-même.

Exemples :
    python envoi_rapports.py --mois 2026-10 --exports "C:/.../2026-10" --clients clients.xlsx
    python envoi_rapports.py --mois 2026-10 --exports ... --clients ... --mode brouillons
"""

import argparse
import base64
import html
import os
import re
import sys
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader, PdfWriter

ICI = Path(__file__).resolve().parent
MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_EN = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]
COURRIEL_VALIDE = re.compile(r"^[^@\s;,]+@[^@\s;,]+\.[a-z]{2,}$", re.I)


@dataclass
class Entite:
    code: str
    nom: str
    code_client: str
    requis: list[str]
    actif: bool
    fichiers: dict[str, Path] = field(default_factory=dict)
    problemes: list[str] = field(default_factory=list)
    pdf: Path | None = None


@dataclass
class Client:
    code: str
    nom: str
    nom_contact: str
    a: list[str]
    cc: list[str]
    gestionnaire_nom: str
    gestionnaire_courriel: str
    langue: str
    actif: bool
    entites: list[Entite] = field(default_factory=list)
    problemes: list[str] = field(default_factory=list)
    objet: str = ""
    corps: str = ""
    brouillon: str = ""

    @property
    def pret(self) -> bool:
        return not self.problemes and all(not e.problemes for e in self.entites_actives)

    @property
    def entites_actives(self) -> list[Entite]:
        return [e for e in self.entites if e.actif]


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", " ", texte).strip().lower()


def oui(valeur) -> bool:
    return normaliser(valeur or "") in {"oui", "o", "x", "yes", "y", "1", "true", "vrai"}


def adresses(valeur) -> list[str]:
    return [a.strip() for a in re.split(r"[;,\n]", str(valeur or "")) if a.strip()]


def lire_onglet(classeur, nom: str) -> list[dict]:
    lignes = list(classeur[nom].iter_rows(values_only=True))
    entetes = [normaliser(c).replace(" ", "_") if c else "" for c in lignes[0]]
    return [dict(zip(entetes, ligne)) for ligne in lignes[1:] if any(ligne)]


def charger_clients(chemin: Path, config: dict) -> tuple[dict[str, Client], list[str]]:
    classeur = load_workbook(chemin, read_only=True, data_only=True)
    cles_docs = [d["cle"] for d in config["documents"]]
    alertes = []

    clients = {}
    for ligne in lire_onglet(classeur, "Clients"):
        code = str(ligne["code_client"]).strip()
        if code in clients:
            alertes.append(f"Code client {code} en double dans l'Excel.")
        clients[code] = Client(
            code=code,
            nom=str(ligne["nom_client"] or "").strip(),
            nom_contact=str(ligne.get("nom_contact") or ligne["nom_client"] or "").strip(),
            a=adresses(ligne["courriel_a"]),
            cc=adresses(ligne.get("courriel_cc")),
            gestionnaire_nom=str(ligne.get("gestionnaire_nom") or "").strip(),
            gestionnaire_courriel=str(ligne.get("gestionnaire_courriel") or "").strip(),
            langue="en" if normaliser(ligne.get("langue") or "fr") in {"en", "anglais"} else "fr",
            actif=oui(ligne.get("actif", "oui")),
        )

    for ligne in lire_onglet(classeur, "Entites"):
        code_client = str(ligne["code_client"]).strip()
        entite = Entite(
            code=str(ligne["code_entite"]).strip(),
            nom=str(ligne["nom_entite"] or "").strip(),
            code_client=code_client,
            requis=[c for c in cles_docs if oui(ligne.get(c))],
            actif=oui(ligne.get("actif", "oui")),
        )
        if code_client not in clients:
            alertes.append(f"Entité {entite.code} rattachée au client {code_client}, absent de l'onglet Clients.")
            continue
        clients[code_client].entites.append(entite)

    return clients, alertes


def identifier_document(nom_doc: str, config: dict) -> str | None:
    nom_doc = normaliser(nom_doc)
    for doc in config["documents"]:
        if any(normaliser(mot) in nom_doc for mot in doc["mots"]):
            return doc["cle"]
    return None


def associer_fichiers(dossier: Path, clients: dict[str, Client], config: dict) -> list[str]:
    """Range chaque PDF du dossier dans son entité. Retourne les fichiers non classés."""
    motif = re.compile(config["fichiers"]["motif"], re.I)
    entites = {e.code.upper(): e for c in clients.values() for e in c.entites}
    non_classes = []

    for fichier in sorted(dossier.glob("*.pdf")):
        trouve = motif.match(fichier.name)
        if not trouve:
            non_classes.append(f"{fichier.name} : nom de fichier non reconnu.")
            continue
        entite = entites.get(trouve["entite"].upper())
        if entite is None:
            non_classes.append(f"{fichier.name} : code d'entité « {trouve['entite']} » introuvable dans l'Excel.")
            continue
        cle = identifier_document(trouve["doc"], config)
        if cle is None:
            non_classes.append(f"{fichier.name} : type de rapport non reconnu.")
            continue
        if cle in entite.fichiers:
            entite.problemes.append(f"Deux fichiers pour le même rapport : {entite.fichiers[cle].name} et {fichier.name}.")
            continue
        entite.fichiers[cle] = fichier
    return non_classes


def valider(clients: dict[str, Client], config: dict) -> None:
    libelles = {d["cle"]: d["libelle_fr"] for d in config["documents"]}
    for client in clients.values():
        if not client.actif:
            continue
        if not client.a:
            client.problemes.append("Aucun destinataire principal.")
        for adresse in client.a + client.cc + [client.gestionnaire_courriel]:
            if adresse and not COURRIEL_VALIDE.match(adresse):
                client.problemes.append(f"Adresse courriel invalide : {adresse}")
        if not client.gestionnaire_courriel:
            client.problemes.append("Courriel du gestionnaire manquant.")
        if not client.entites_actives:
            client.problemes.append("Aucune entité active rattachée à ce client.")

        for entite in client.entites_actives:
            if not entite.requis:
                entite.problemes.append("Aucun document requis coché dans l'Excel.")
            for cle in entite.requis:
                if cle not in entite.fichiers:
                    entite.problemes.append(f"{libelles[cle]} manquant.")
            for cle in set(entite.fichiers) - set(entite.requis):
                entite.problemes.append(f"{libelles[cle]} reçu mais non coché dans l'Excel ({entite.fichiers[cle].name}).")
            if config["fichiers"].get("verifier_contenu"):
                for cle, fichier in entite.fichiers.items():
                    if not code_present(fichier, entite.code):
                        entite.problemes.append(f"Le code {entite.code} n'apparaît pas dans {fichier.name}. Mauvais fichier?")


def code_present(fichier: Path, code: str) -> bool:
    try:
        texte = PdfReader(fichier).pages[0].extract_text() or ""
    except Exception:
        return False
    return code.upper() in texte.upper()


def fusionner(client: Client, mois: str, sortie: Path, config: dict) -> None:
    dossier = sortie / client.code
    dossier.mkdir(parents=True, exist_ok=True)
    libelles = {d["cle"]: d[f"libelle_{client.langue}"] for d in config["documents"]}
    for entite in client.entites_actives:
        pdf = PdfWriter()
        for cle in entite.requis:
            debut = len(pdf.pages)
            pdf.append(str(entite.fichiers[cle]))
            pdf.add_outline_item(libelles[cle], debut)
        entite.pdf = dossier / f"{nom_fichier(entite.nom)}_{mois}.pdf"
        with open(entite.pdf, "wb") as f:
            pdf.write(f)


def nom_fichier(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", texte).strip("_")


def mois_texte(mois: str, langue: str) -> str:
    annee, numero = mois.split("-")
    noms = MOIS_EN if langue == "en" else MOIS_FR
    return f"{noms[int(numero) - 1]} {annee}"


def rediger(client: Client, mois: str, config: dict) -> None:
    langue = client.langue
    valeurs = {
        "nom_client": client.nom,
        "nom_contact": html.escape(client.nom_contact),
        "mois_texte": mois_texte(mois, langue),
        "gestionnaire_nom": html.escape(client.gestionnaire_nom),
        "signature": html.escape(config["envoi"]["signature"]),
        "liste_entites": "<ul>" + "".join(f"<li>{html.escape(e.nom)}</li>" for e in client.entites_actives) + "</ul>",
        "liste_documents": ", ".join(
            d[f"libelle_{langue}"].lower() for d in config["documents"]
            if any(d["cle"] in e.requis for e in client.entites_actives)
        ),
    }
    client.objet = config["envoi"][f"objet_{langue}"].format(**valeurs)
    modele = (ICI / "modeles" / f"courriel_{langue}.html").read_text(encoding="utf-8")
    client.corps = modele.format(**valeurs)


def destinataires_cc(client: Client, config: dict) -> list[str]:
    cc = client.cc + [client.gestionnaire_courriel] + config["envoi"]["cc_fixes"]
    vus, resultat = set(), []
    for adresse in cc:
        if adresse and adresse.lower() not in vus and adresse.lower() not in {a.lower() for a in client.a}:
            vus.add(adresse.lower())
            resultat.append(adresse)
    return resultat


def ecrire_apercu(client: Client, sortie: Path, config: dict) -> None:
    """Écrit un .eml qu'on peut ouvrir dans Outlook pour voir le courriel exact."""
    message = EmailMessage()
    message["From"] = config["envoi"]["expediteur"]
    message["To"] = ", ".join(client.a)
    message["Cc"] = ", ".join(destinataires_cc(client, config))
    message["Subject"] = client.objet
    message["X-Unsent"] = "1"
    message.set_content("Ce courriel est en HTML.")
    message.add_alternative(client.corps, subtype="html")
    for entite in client.entites_actives:
        message.add_attachment(entite.pdf.read_bytes(), maintype="application",
                               subtype="pdf", filename=entite.pdf.name)
    chemin = sortie / client.code / f"apercu_{client.code}.eml"
    chemin.write_bytes(bytes(message))
    client.brouillon = str(chemin.relative_to(sortie))


class Graph:
    """Création de brouillons dans la boîte de l'expéditeur via Microsoft Graph."""

    URL = "https://graph.microsoft.com/v1.0"
    LIMITE_PIECE_SIMPLE = 3 * 1024 * 1024

    def __init__(self, config: dict):
        import msal
        import requests

        self.requests = requests
        secret = os.environ.get("GRAPH_CLIENT_SECRET")
        if not (config["graph"]["tenant_id"] and config["graph"]["client_id"] and secret):
            sys.exit("Mode brouillons : tenant_id et client_id doivent être remplis dans config.toml "
                     "et la variable GRAPH_CLIENT_SECRET définie.")
        app = msal.ConfidentialClientApplication(
            config["graph"]["client_id"], client_credential=secret,
            authority=f"https://login.microsoftonline.com/{config['graph']['tenant_id']}")
        jeton = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in jeton:
            sys.exit(f"Connexion à Microsoft 365 refusée : {jeton.get('error_description')}")
        self.entetes = {"Authorization": f"Bearer {jeton['access_token']}"}
        self.boite = f"{self.URL}/users/{config['envoi']['expediteur']}"

    def appel(self, methode: str, url: str, **kwargs) -> dict:
        reponse = self.requests.request(methode, url, headers=self.entetes, timeout=60, **kwargs)
        reponse.raise_for_status()
        return reponse.json() if reponse.content else {}

    def creer_brouillon(self, client: Client, config: dict) -> str:
        message = self.appel("POST", f"{self.boite}/messages", json={
            "subject": client.objet,
            "body": {"contentType": "HTML", "content": client.corps},
            "toRecipients": [{"emailAddress": {"address": a}} for a in client.a],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in destinataires_cc(client, config)],
        })
        for entite in client.entites_actives:
            self.joindre(message["id"], entite.pdf)
        return message["webLink"]

    def joindre(self, id_message: str, fichier: Path) -> None:
        contenu = fichier.read_bytes()
        url = f"{self.boite}/messages/{id_message}/attachments"
        if len(contenu) < self.LIMITE_PIECE_SIMPLE:
            self.appel("POST", url, json={
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": fichier.name, "contentType": "application/pdf",
                "contentBytes": base64.b64encode(contenu).decode()})
            return
        # Les pièces de 3 Mo et plus (grands livres) passent par une session de téléversement.
        session = self.appel("POST", f"{url}/createUploadSession", json={"AttachmentItem": {
            "attachmentType": "file", "name": fichier.name, "size": len(contenu)}})
        morceau = 4 * 1024 * 1024
        for debut in range(0, len(contenu), morceau):
            fin = min(debut + morceau, len(contenu))
            self.requests.put(session["uploadUrl"], data=contenu[debut:fin], timeout=120, headers={
                "Content-Length": str(fin - debut),
                "Content-Range": f"bytes {debut}-{fin - 1}/{len(contenu)}"}).raise_for_status()


def ecrire_rapport(clients: dict[str, Client], alertes: list[str], mois: str, mode: str,
                   sortie: Path, config: dict) -> Path:
    actifs = [c for c in clients.values() if c.actif]
    prets = [c for c in actifs if c.pret]
    bloques = [c for c in actifs if not c.pret]
    inactifs = [c for c in clients.values() if not c.actif]
    e = html.escape

    def ligne_client(c: Client) -> str:
        etat = '<span class="pastille ok">Prêt</span>' if c.pret else '<span class="pastille bloque">Bloqué</span>'
        entites = "".join(
            f'<li><span class="code">{e(x.code)}</span> {e(x.nom)}'
            + ("".join(f'<div class="probleme">{e(p)}</div>' for p in x.problemes)
               if x.problemes else f' <span class="discret">· {len(x.requis)} rapports</span>')
            + "</li>" for x in c.entites_actives)
        problemes = "".join(f'<div class="probleme">{e(p)}</div>' for p in c.problemes)
        lien = f'<div class="discret">Aperçu : <span class="code">{e(c.brouillon)}</span></div>' if c.brouillon else ""
        return (f'<tr class="{"" if c.pret else "a-voir"}"><td>{etat}</td>'
                f'<td><strong>{e(c.nom)}</strong><div class="discret code">{e(c.code)}</div></td>'
                f'<td><div>{e(", ".join(c.a))}</div><div class="discret">cc gestionnaire : {e(c.gestionnaire_nom)}</div></td>'
                f'<td><ul class="entites">{entites}</ul>{problemes}{lien}</td></tr>')

    apercu = ""
    if prets:
        c = prets[0]
        apercu = f"""
<section>
  <h2>Aperçu d'un courriel préparé</h2>
  <div class="courriel">
    <dl>
      <dt>De</dt><dd>{e(config["envoi"]["expediteur"])}</dd>
      <dt>À</dt><dd>{e(", ".join(c.a))}</dd>
      <dt>Cc</dt><dd>{e(", ".join(destinataires_cc(c, config)))}</dd>
      <dt>Objet</dt><dd><strong>{e(c.objet)}</strong></dd>
      <dt>Pièces</dt><dd>{"".join(f'<span class="piece">{e(x.pdf.name)}</span>' for x in c.entites_actives)}</dd>
    </dl>
    <div class="corps">{c.corps}</div>
  </div>
</section>"""

    hors_excel = "".join(f"<li>{e(a)}</li>" for a in alertes)
    libelle_mode = "Brouillons créés dans Outlook" if mode == "brouillons" else "Simulation : aucun brouillon créé"
    page = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Envoi des rapports {e(mois_texte(mois, "fr"))}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Mise en page : une colonne de contrôle, sommaire d'abord, détail par client ensuite. */
:root {{
  --fond: #f6f7f5; --surface: #ffffff; --texte: #1d2522; --discret: #5d6b66;
  --ligne: #dde3df; --accent: #1f5c4d; --ok: #24734f; --ok-fond: #e3f2ea;
  --bloque: #a33a1f; --bloque-fond: #fbe9e3;
  --police: "Public Sans", system-ui, sans-serif; --mono: "IBM Plex Mono", ui-monospace, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --fond: #121715; --surface: #1a211e; --texte: #e4ebe7; --discret: #9aa8a2;
  --ligne: #2c3632; --accent: #7cc4ad; --ok: #6fd0a0; --ok-fond: #183326;
  --bloque: #f0957a; --bloque-fond: #3a1f17; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --fond: #121715; --surface: #1a211e; --texte: #e4ebe7; --discret: #9aa8a2;
  --ligne: #2c3632; --accent: #7cc4ad; --ok: #6fd0a0; --ok-fond: #183326;
  --bloque: #f0957a; --bloque-fond: #3a1f17; color-scheme: dark; }}
body {{ margin: 0; background: var(--fond); color: var(--texte); font: 15px/1.5 var(--police); }}
main {{ max-width: 1100px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 32px; }}
header {{ display: grid; gap: 6px; }}
.surtitre {{ font: 500 12px var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }}
h1 {{ margin: 0; font-size: clamp(24px, 4vw, 34px); line-height: 1.15; text-wrap: balance; }}
h2 {{ margin: 0 0 12px; font-size: 18px; }}
.discret {{ color: var(--discret); font-size: 13px; }}
.code {{ font-family: var(--mono); font-size: 12.5px; }}
.compteurs {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.compteur {{ flex: 1 1 160px; background: var(--surface); border: 1px solid var(--ligne); border-radius: 6px; padding: 14px 16px; }}
.compteur b {{ display: block; font-size: 30px; font-variant-numeric: tabular-nums; line-height: 1.1; }}
.compteur.ok b {{ color: var(--ok); }} .compteur.bloque b {{ color: var(--bloque); }}
.tableau {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--ligne); border-radius: 6px; }}
table {{ width: 100%; border-collapse: collapse; min-width: 720px; }}
th {{ text-align: left; font: 500 11.5px var(--mono); letter-spacing: .06em; text-transform: uppercase; color: var(--discret);
  padding: 10px 14px; border-bottom: 1px solid var(--ligne); }}
td {{ padding: 12px 14px; border-bottom: 1px solid var(--ligne); vertical-align: top; }}
tr:last-child td {{ border-bottom: 0; }}
tr.a-voir td:first-child {{ box-shadow: inset 3px 0 0 var(--bloque); }}
.pastille {{ display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 99px; white-space: nowrap; }}
.pastille.ok {{ color: var(--ok); background: var(--ok-fond); }}
.pastille.bloque {{ color: var(--bloque); background: var(--bloque-fond); }}
.entites {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }}
.probleme {{ color: var(--bloque); font-size: 13px; }}
.probleme::before {{ content: "→ "; }}
.alertes {{ margin: 0; padding-left: 20px; color: var(--bloque); }}
.courriel {{ background: var(--surface); border: 1px solid var(--ligne); border-radius: 6px; overflow: hidden; }}
.courriel dl {{ margin: 0; padding: 14px 18px; display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px;
  border-bottom: 1px solid var(--ligne); font-size: 14px; }}
.courriel dt {{ color: var(--discret); }} .courriel dd {{ margin: 0; min-width: 0; overflow-wrap: anywhere; }}
.piece {{ display: inline-block; font: 12.5px var(--mono); border: 1px solid var(--ligne); border-radius: 4px; padding: 1px 8px; margin: 0 6px 4px 0; }}
.corps {{ padding: 8px 18px 14px; max-width: 65ch; }}
</style></head>
<body><main>
<header>
  <div class="surtitre">Finance · rapports clients</div>
  <h1>Envoi des rapports de {e(mois_texte(mois, "fr"))}</h1>
  <div class="discret">{libelle_mode} · préparé le {datetime.now():%Y-%m-%d à %H:%M}</div>
</header>
<div class="compteurs">
  <div class="compteur ok"><b>{len(prets)}</b>clients prêts à envoyer</div>
  <div class="compteur bloque"><b>{len(bloques)}</b>clients bloqués</div>
  <div class="compteur"><b>{sum(len(c.entites_actives) for c in prets)}</b>PDF d'entités préparés</div>
  <div class="compteur"><b>{len(inactifs)}</b>clients inactifs ignorés</div>
</div>
{f'<section><h2>Fichiers ou lignes à régler</h2><ul class="alertes">{hors_excel}</ul></section>' if alertes else ""}
<section>
  <h2>Détail par client</h2>
  <div class="tableau"><table>
    <thead><tr><th>État</th><th>Client</th><th>Destinataires</th><th>Entités et vérifications</th></tr></thead>
    <tbody>{"".join(ligne_client(c) for c in bloques + prets)}</tbody>
  </table></div>
</section>
{apercu}
</main></body></html>"""
    chemin = sortie / "rapport.html"
    chemin.write_text(page, encoding="utf-8")
    return chemin


def main() -> None:
    parser = argparse.ArgumentParser(description="Prépare l'envoi mensuel des rapports clients.")
    parser.add_argument("--mois", required=True, help="Mois des rapports, format AAAA-MM")
    parser.add_argument("--exports", required=True, type=Path, help="Dossier des exports Hopem du mois")
    parser.add_argument("--clients", required=True, type=Path, help="Excel des clients")
    parser.add_argument("--sortie", type=Path, help="Dossier de sortie (défaut : ./sortie/AAAA-MM)")
    parser.add_argument("--mode", choices=["simulation", "brouillons"], default="simulation")
    parser.add_argument("--config", type=Path, default=ICI / "config.toml")
    args = parser.parse_args()

    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.mois):
        sys.exit("--mois doit être au format AAAA-MM, par exemple 2026-10.")
    config = tomllib.loads(args.config.read_text(encoding="utf-8"))
    sortie = args.sortie or ICI / "sortie" / args.mois
    sortie.mkdir(parents=True, exist_ok=True)

    clients, alertes = charger_clients(args.clients, config)
    alertes += associer_fichiers(args.exports, clients, config)
    valider(clients, config)

    graph = Graph(config) if args.mode == "brouillons" else None
    for client in clients.values():
        if not (client.actif and client.pret):
            continue
        fusionner(client, args.mois, sortie, config)
        rediger(client, args.mois, config)
        ecrire_apercu(client, sortie, config)
        if graph:
            client.brouillon = graph.creer_brouillon(client, config)

    rapport = ecrire_rapport(clients, alertes, args.mois, args.mode, sortie, config)
    actifs = [c for c in clients.values() if c.actif]
    print(f"{sum(c.pret for c in actifs)} clients prêts, {sum(not c.pret for c in actifs)} bloqués, "
          f"{len(alertes)} alertes. Rapport : {rapport}")


if __name__ == "__main__":
    main()
