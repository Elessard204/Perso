"""Crée un jeu de données fictif pour essayer l'outil sans toucher aux vrais clients.

Produit demo/clients_demo.xlsx et demo/exports/2026-10/*.pdf au format réel
(« Rapports mensuels Oct 2026_01001.pdf », un PDF combiné par entité), avec
quelques problèmes volontaires pour montrer ce que l'outil bloque.
"""

import calendar
import random
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ICI = Path(__file__).resolve().parent
ANNEE, MOIS = 2026, 10

CLIENTS = [
    # code, nom, contact, courriels clients, langue, actif
    ("C10.1", "Gestion Boréale inc.", "Julie", "julie.gagnon@exemple.com", "FR", "Oui"),
    ("C20.1", "Saint-Laurent Holdings", "David", "david.cohen@exemple.com; comptable@exemple.com", "EN", "Oui"),
    ("C30.1", "Immeubles Rivière-Noire", "Pierre", "pierre.lavoie@exemple.com", "FR", "Oui"),
    ("C40.1", "Famille Tremblay", "Nathalie", "n.tremblay@exemple.com", "FR", "Oui"),
    ("C50.1", "Société Champlain", "", "compta@champlain", "FR", "Oui"),
    ("C60.1", "Groupe Laurentides", "Isabelle", "isabelle.cote@exemple.com", "FR", "Oui"),
    ("C70.1", "Placements Outremont", "Marc", "marc@exemple.com", "FR", "Oui"),
    ("C80.1", "Habitations Verdun", "Annie", "annie@exemple.com", "FR", "Oui"),
]

ENTITES = [
    # code, immeuble(s), nom légal imprimé par Hopem, client, fin d'exercice, fréquence, gestionnaire
    ("10.1", "1200 Boréale", "Boréale Immeubles inc.", "C10.1", 12, "mensuel", "Louis"),
    ("10.2", "45-49 Des Pins", "9123-4567 Québec inc.", "C10.1", 10, "mensuel", "Jonathan"),
    ("20.1", "SLH Residential", "SLH Residential LP", "C20.1", 4, "mensuel", "Maxime"),
    ("30.1", "88 Rivière-Noire", "Rivière-Noire Habitation inc.", "C30.1", 12, "mensuel", "Louis"),
    ("40.1", "3300 Tremblay", "Tremblay Immobilier inc.", "C40.1", 12, "mensuel", "Louis"),
    ("50.1", "500 Champlain", "Champlain Logements inc.", "C50.1", 12, "mensuel", "Jonathan"),
    ("60.1", "77 Laurentides", "Laurentides Multilogements inc.", "C60.1", 12, "mensuel", "Louis"),
    ("70.1", "15 Outremont", "Placements Outremont inc.", "C70.1", 12, "trimestriel", "Maxime"),
    ("80.1", "2100 Verdun", "Habitations Verdun inc.", "C80.1", 12, "mensuel", ""),
]

GESTIONNAIRES = [("Louis", "louis@exemple-progim.com"), ("Jonathan", "jonathan@exemple-progim.com"),
                 ("Maxime", "mpaquet@progim.com")]


def creer_excel() -> None:
    classeur = Workbook()
    entete, fond = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F5C4D")
    onglets = [
        ("Clients", ["code_client", "nom_client", "nom_contact", "courriel_clients", "courriel_direction", "langue", "actif"],
         [(c, n, ct, a, "", l, ac) for c, n, ct, a, l, ac in CLIENTS]),
        ("Entites", ["code_entite", "nom_entite", "immeubles", "code_client", "fin_exercice", "frequence",
                     "gestionnaire", "courriel_gestionnaire", "actif", "notes"],
         [(c, h, n, cl, f, fr, g, "", "Oui", "") for c, n, h, cl, f, fr, g in ENTITES]),
        ("Gestionnaires", ["nom", "courriel"], GESTIONNAIRES),
    ]
    for i, (nom, colonnes, lignes) in enumerate(onglets):
        feuille = classeur.active if i == 0 else classeur.create_sheet()
        feuille.title = nom
        feuille.append(colonnes)
        for ligne in lignes:
            feuille.append(list(ligne))
        for cellule in feuille[1]:
            cellule.font, cellule.fill = entete, fond
        for colonne in feuille.columns:
            feuille.column_dimensions[colonne[0].column_letter].width = max(len(str(c.value or "")) for c in colonne) + 4
        table = Table(displayName=f"T_{nom}", ref=feuille.dimensions)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        feuille.add_table(table)
        feuille.freeze_panes = "A2"
    classeur.save(ICI / "clients_demo.xlsx")


def creer_pdf(chemin: Path, nom_hopem: str, periode: int, rapports=("Bilan", "État des résultats", "Sommaire mensuel des transactions")) -> None:
    """Imite la mise en page Hopem : nom à la 1re ligne, titre du rapport à la 3e."""
    fin = f"{ANNEE}/{MOIS:02d}/{calendar.monthrange(ANNEE, MOIS)[1]:02d}"
    sous_titres = {"Bilan": f"Au {fin}",
                   "État des résultats": f"Pour la période {periode} (Du : {ANNEE}/{MOIS:02d}/01 au {fin})",
                   "Sommaire mensuel des transactions": f"Du : {ANNEE}/{MOIS:02d} Au : {ANNEE}/{MOIS:02d}"}
    pdf = canvas.Canvas(str(chemin), pagesize=letter)
    for rapport in rapports:
        y = 740
        for ligne in (f"Page 1 {nom_hopem}", "Grand-Livre - États financiers", rapport, "2026/11/14", "13:29:31", sous_titres[rapport]):
            pdf.setFont("Helvetica-Bold" if ligne == rapport else "Helvetica", 11)
            pdf.drawString(50, y, ligne)
            y -= 16
        y -= 10
        for _ in range(18):
            pdf.drawString(50, y, f"5-{random.randint(10000, 59999)}  Poste fictif")
            pdf.drawRightString(560, y, f"{random.uniform(-20000, 90000):,.2f}")
            y -= 20
        pdf.showPage()
    pdf.save()


def creer_exports() -> None:
    dossier = ICI / "exports" / f"{ANNEE}-{MOIS:02d}"
    dossier.mkdir(parents=True, exist_ok=True)
    for ancien in dossier.glob("*.pdf"):
        ancien.unlink()
    random.seed(2026)
    for code, _, nom_hopem, _, fin, _, _ in ENTITES:
        principal, sous = code.split(".")
        nom_fichier = f"Rapports mensuels Oct {ANNEE}_{int(principal):03d}{int(sous):02d}.pdf"
        periode = (MOIS - fin - 1) % 12 + 1
        if code == "30.1":
            continue  # pas encore téléchargé : C30.1 sera bloqué
        if code == "40.1":
            nom_hopem = "Famille Gagnon inc."  # PDF d'une autre entité sous le mauvais numéro
        if code == "60.1":
            periode = 7  # fin d'exercice erronée dans l'Excel (avril plutôt que décembre)
        if code == "80.1":
            nom_fichier = nom_fichier.replace("Oct", "Sept")  # fichier du mois passé
        creer_pdf(dossier / nom_fichier, nom_hopem, periode)
    creer_pdf(dossier / "Facture 2026-118.pdf", "Placements Outremont inc.", 10)


if __name__ == "__main__":
    creer_excel()
    creer_exports()
    print(f"Données fictives créées dans {ICI}")
