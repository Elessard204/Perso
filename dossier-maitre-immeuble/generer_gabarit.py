"""Génère le gabarit « Dossier maître de l'immeuble » (Gestion Progim).

Usage : python generer_gabarit.py [sortie.xlsx]
"""
import sys
from datetime import date
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

SORTIE = sys.argv[1] if len(sys.argv) > 1 else "Dossier maitre immeuble - GABARIT.xlsx"

# Couleurs du design system Progim
MARINE, ORANGE, ORANGE_TXT = "131A2F", "EE7203", "B85500"
FOND, LIGNE, DISCRET, SURVOL = "F3F4F6", "DDE2E6", "5B6770", "E8EBEF"
BLOQUE, BLOQUE_PALE, SPECIAL, AVERT, LIGNE_SURVOL = "B4471A", "FBEAE2", "FFF1E0", "6E5000", "FFF4E8"
OK, OK_PALE, INFO, INFO_PALE = "2D7A3E", "E3F2E6", "0B5D7A", "E3EFF4"
POLICE = "Arial"

def f(**kw):
    kw.setdefault("name", POLICE); kw.setdefault("size", 10)
    return Font(**kw)

fill = lambda c: PatternFill("solid", fgColor=c)
mince = Side(style="thin", color=LIGNE)
BORD = Border(left=mince, right=mince, top=mince, bottom=mince)
FMT = {
    "date": "yyyy-mm-dd", "money": '#,##0.00 "$";(#,##0.00 "$");"—"', "money0": '#,##0 "$";(#,##0 "$");"—"',
    "int": "0", "jours": '0;[Red]-0', "pct": "0.0%", "ans": '0;[Red]-0', "text": "@", "nextdate": 'yyyy-mm-dd;;"—"',
}
CALC_FILL = fill(FOND)
DATE_EX = date(2026, 1, 1)

wb = Workbook()
wb.remove(wb.active)

# ---------------------------------------------------------------- Paramètres
LISTES = {
    "L_TypeImmeuble": ["Résidentiel", "Commercial", "Mixte", "Copropriété", "Industriel"],
    "L_StatutUnite": ["Occupé", "Vacant", "Avis de départ", "En rénovation", "Non louable"],
    "L_TypeUnite": ["Studio", "1½", "2½", "3½", "4½", "5½", "6½ et +", "Local commercial", "Bureau", "Stationnement", "Entrepôt"],
    "L_OuiNon": ["Oui", "Non"],
    "L_StatutDoc": ["Au dossier", "Manquant", "À renouveler", "Sans objet"],
    "L_CatContrat": ["Déneigement", "Entretien ménager", "Ascenseur", "Protection incendie", "Gicleurs",
                     "Chauffage, ventilation, climatisation", "Matières résiduelles", "Aménagement paysager",
                     "Extermination", "Sécurité et alarme", "Télécom et câble", "Buanderie", "Autre"],
    "L_Exigence": ["Réglementaire", "Assurance", "Recommandée"],
    "L_CatTravaux": ["Entretien", "Réparation", "Rénovation", "Remplacement", "Urgence"],
    "L_PayePar": ["Propriétaire", "Locataire", "Assurance", "Garantie"],
    "L_Frequence": ["Mensuel", "Trimestriel", "Annuel"],
    "L_Couverture": ["Biens", "Responsabilité civile", "Pertes de revenus", "Bris d'équipement",
                     "Responsabilité des administrateurs", "Excédentaire (umbrella)", "Autre"],
    "L_TypeTaxe": ["Municipale", "Scolaire", "Droits de mutation", "Autre"],
}

def entete_feuille(ws, titre, ligne_immeuble=True, largeur=12):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    ws["B1"] = titre
    ws["B1"].font = f(size=15, bold=True, color="FFFFFF")
    for c in range(1, largeur + 2):
        cell = ws.cell(row=1, column=c)
        cell.fill = fill(MARINE)
        cell.border = Border(bottom=Side(style="thick", color=ORANGE))
    ws.row_dimensions[1].height = 30
    ws["B1"].alignment = Alignment(vertical="center")
    if ligne_immeuble:
        ws["B2"] = '=IF(Fiche!$C$6="","Immeuble : (à inscrire dans l\'onglet Fiche)","Immeuble : "&Fiche!$C$6&IF(Fiche!$C$7="",""," — "&Fiche!$C$7))'
        ws["B2"].font = f(size=10, italic=True, color=DISCRET)

p = wb.create_sheet("Paramètres")
entete_feuille(p, "Paramètres", ligne_immeuble=False, largeur=3 + len(LISTES))
p["B4"], p["C4"] = "Date du jour", "=TODAY()"
p["B5"], p["C5"] = "Seuil urgent (jours)", 30
p["B6"], p["C6"] = "Seuil d'alerte (jours)", 90
p["C4"].number_format = FMT["date"]
for r in (4, 5, 6):
    p[f"B{r}"].font = f(bold=True)
    p[f"C{r}"].border = BORD
p["C4"].fill = CALC_FILL
for r in (5, 6):
    p[f"C{r}"].font = f(color="0000FF")
p["D5"] = "Échéance dans ce nombre de jours ou moins : affichée en orange."
p["D6"] = "Échéance dans ce nombre de jours ou moins : affichée en jaune."
for r in (5, 6):
    p[f"D{r}"].font = f(size=9, italic=True, color=DISCRET)
p["B8"] = "LISTES DÉROULANTES (ajouter des valeurs au bas d'une liste au besoin, elles apparaîtront dans les menus)"
p["B8"].font = f(bold=True, color=ORANGE_TXT)
p.column_dimensions["B"].width = 24
p.column_dimensions["C"].width = 14
for i, (nom, valeurs) in enumerate(LISTES.items()):
    col = 5 + i
    L = get_column_letter(col)
    p.column_dimensions[L].width = 22
    p.cell(row=10, column=col, value=nom.replace("L_", "")).font = f(bold=True, color=MARINE)
    p.cell(row=10, column=col).fill = fill(SURVOL)
    for j, v in enumerate(valeurs):
        p.cell(row=11 + j, column=col, value=v).font = f()
    wb.defined_names[nom] = DefinedName(nom, attr_text=f"'Paramètres'!${L}$11:${L}$40")
wb.defined_names["Aujourdhui"] = DefinedName("Aujourdhui", attr_text="'Paramètres'!$C$4")
wb.defined_names["SeuilUrgent"] = DefinedName("SeuilUrgent", attr_text="'Paramètres'!$C$5")
wb.defined_names["SeuilAlerte"] = DefinedName("SeuilAlerte", attr_text="'Paramètres'!$C$6")

def liste(ws, nom, plage):
    dv = DataValidation(type="list", formula1=f"={nom}", allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    dv.add(plage)

def alerte_jours(ws, plage):
    """Mise en forme conditionnelle d'une colonne « jours restants »."""
    tl = plage.split(":")[0]
    ws.conditional_formatting.add(plage, FormulaRule(
        formula=[f'AND(ISNUMBER({tl}),{tl}<0)'], fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True), stopIfTrue=True))
    ws.conditional_formatting.add(plage, FormulaRule(
        formula=[f'AND(ISNUMBER({tl}),{tl}<=SeuilUrgent)'], fill=fill(SPECIAL), font=Font(color=ORANGE_TXT, bold=True), stopIfTrue=True))
    ws.conditional_formatting.add(plage, FormulaRule(
        formula=[f'AND(ISNUMBER({tl}),{tl}<=SeuilAlerte)'], fill=fill(LIGNE_SURVOL), font=Font(color=AVERT), stopIfTrue=True))

# ---------------------------------------------------------------- Tables génériques
DEB = 5  # première ligne de données (en-têtes en ligne 4)

def table(nom_feuille, titre, colonnes, n, note=None, exemple=None, prerempli=None):
    """colonnes : liste de dict(nom, larg, fmt, calc=formule avec {r}, liste=nom, aide=commentaire)."""
    ws = wb.create_sheet(nom_feuille)
    entete_feuille(ws, titre, largeur=len(colonnes))
    if note:
        ws["B3"] = note
        ws["B3"].font = f(size=9, italic=True, color=INFO)
    for i, c in enumerate(colonnes):
        col = 2 + i
        L = get_column_letter(col)
        ws.column_dimensions[L].width = c.get("larg", 14)
        h = ws.cell(row=4, column=col, value=c["nom"])
        h.font = f(bold=True, color="FFFFFF" if c.get("calc") is None else MARINE, size=9)
        h.fill = fill(MARINE) if c.get("calc") is None else fill(SURVOL)
        h.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        h.border = BORD
        if c.get("aide"):
            h.comment = Comment(c["aide"], "Progim")
        for r in range(DEB, DEB + n):
            cell = ws.cell(row=r, column=col)
            cell.border = BORD
            cell.font = f()
            if c.get("fmt"):
                cell.number_format = FMT[c["fmt"]]
            if c.get("calc"):
                v = c["calc"].format(r=r)
                cell.value = v if v.startswith("=") else "=" + v
                cell.fill = CALC_FILL
            if c.get("fmt") in ("money", "money0", "jours", "int", "ans"):
                cell.alignment = Alignment(horizontal="right")
        if c.get("liste"):
            liste(ws, c["liste"], f"{L}{DEB}:{L}{DEB + n - 1}")
        if c.get("fmt") == "jours":
            alerte_jours(ws, f"{L}{DEB}:{L}{DEB + n - 1}")
        if c.get("fmt") == "ans":  # fin de vie : dépassée en rouge, 3 ans ou moins en orange
            tl = f"{L}{DEB}"
            ws.conditional_formatting.add(f"{L}{DEB}:{L}{DEB + n - 1}", FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}<=0)"],
                fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True), stopIfTrue=True))
            ws.conditional_formatting.add(f"{L}{DEB}:{L}{DEB + n - 1}", FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}<=3)"],
                fill=fill(SPECIAL), font=Font(color=ORANGE_TXT, bold=True), stopIfTrue=True))
    ws.row_dimensions[4].height = 42
    ws.freeze_panes = ws.cell(row=DEB, column=3)
    ws.auto_filter.ref = f"B4:{get_column_letter(1 + len(colonnes))}{DEB + n - 1}"
    for lignes, marque in ((prerempli or [], False), ([exemple] if exemple else [], True)):
        for k, valeurs in enumerate(lignes):
            r = DEB + k
            for i, v in enumerate(valeurs):
                if v is not None and not colonnes[i].get("calc"):
                    cell = ws.cell(row=r, column=2 + i, value=v)
                    if marque:
                        cell.font = f(italic=True, color="0000FF")
            if marque:
                ws.cell(row=r, column=2).comment = Comment(
                    "Ligne d'exemple (texte bleu italique) : la remplacer par les vraies données ou la supprimer.", "Progim")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "4:4"
    return ws

def plage(feuille, col, n):
    return f"'{feuille}'!${col}${DEB}:${col}${DEB + n - 1}"

JR = 'IF({d}{{r}}="","",{d}{{r}}-Aujourdhui)'.format  # jours restants

# ---------------------------------------------------------------- Unités et baux
N_UNI = 200
uni = table("Unités", "Unités et baux", [
    dict(nom="No d'unité", larg=9, fmt="text"),
    dict(nom="Type", larg=11, liste="L_TypeUnite"),
    dict(nom="Étage", larg=6),
    dict(nom="Superficie (pi²)", larg=10, fmt="int"),
    dict(nom="Statut", larg=13, liste="L_StatutUnite"),
    dict(nom="Locataire(s)", larg=24),
    dict(nom="Téléphone", larg=14),
    dict(nom="Courriel", larg=24),
    dict(nom="Début du bail", larg=11, fmt="date"),
    dict(nom="Fin du bail", larg=11, fmt="date", aide="Laisser vide pour un bail à durée indéterminée."),
    dict(nom="Loyer mensuel ($)", larg=12, fmt="money"),
    dict(nom="Chauffage inclus", larg=9, liste="L_OuiNon"),
    dict(nom="Électricité incluse", larg=9, liste="L_OuiNon"),
    dict(nom="Stationnement", larg=11),
    dict(nom="Rangement", larg=10),
    dict(nom="Notes", larg=26),
    dict(nom="Jours avant fin du bail", larg=10, fmt="jours", calc=JR(d="K")),
    dict(nom="Avis de modification : envoyer à partir du", larg=13, fmt="date",
         calc='IF(OR(J{r}="",K{r}=""),"",IF(EDATE(J{r},12)<=K{r}+1,EDATE(K{r},-6),EDATE(K{r},-2)))',
         aide="Code civil du Québec, art. 1942 : avis de modification au locataire entre 3 et 6 mois avant la fin d'un bail de 12 mois ou plus; entre 1 et 2 mois pour un bail de moins de 12 mois. Logement résidentiel seulement."),
    dict(nom="Avis de modification : au plus tard le", larg=13, fmt="date",
         calc='IF(OR(J{r}="",K{r}=""),"",IF(EDATE(J{r},12)<=K{r}+1,EDATE(K{r},-3),EDATE(K{r},-1)))'),
    dict(nom="Jours avant date limite de l'avis", larg=10, fmt="jours", calc=JR(d="T")),
], N_UNI,
    note="Une ligne par unité (logement, local, stationnement loué séparément). Colonnes grises : calculées, ne pas modifier.",
    exemple=["101", "4½", "1", 850, "Occupé", "Locataire Exemple", "819 555-0101", "locataire@exemple.com",
             date(2026, 7, 1), date(2027, 6, 30), 1250, "Non", "Non", "Ext. no 4", "Casier 12", "Exemple"])

# ---------------------------------------------------------------- Assurances
N_ASS = 20
table("Assurances", "Assurances", [
    dict(nom="Couverture", larg=20, liste="L_Couverture"),
    dict(nom="Assureur", larg=18),
    dict(nom="Courtier", larg=18),
    dict(nom="Contact du courtier", larg=22),
    dict(nom="No de police", larg=14, fmt="text"),
    dict(nom="Montant assuré ($)", larg=14, fmt="money0"),
    dict(nom="Franchise ($)", larg=11, fmt="money0"),
    dict(nom="Prime annuelle ($)", larg=12, fmt="money0"),
    dict(nom="Début", larg=11, fmt="date"),
    dict(nom="Fin", larg=11, fmt="date"),
    dict(nom="Progim assuré additionnel", larg=11, liste="L_OuiNon",
         aide="Le gestionnaire devrait être nommé assuré additionnel sur la responsabilité civile."),
    dict(nom="Notes", larg=26),
    dict(nom="Jours avant renouvellement", larg=11, fmt="jours", calc=JR(d="K")),
], N_ASS, note="Joindre la police et le certificat dans l'onglet Documents (lien SharePoint).",
    exemple=["Biens", "Assureur Exemple", "Courtier Exemple", "Nom, 819 555-0102", "POL-000000", 4500000, 10000,
             18500, DATE_EX, date(2026, 12, 31), "Oui", "Valeur à neuf"])

# ---------------------------------------------------------------- Taxes
N_TAX = 30
tax = table("Taxes", "Taxes et évaluation foncière", [
    dict(nom="Type", larg=16, liste="L_TypeTaxe"),
    dict(nom="Année", larg=7, fmt="int"),
    dict(nom="Montant annuel ($)", larg=13, fmt="money"),
    dict(nom="Versement no", larg=9, fmt="int"),
    dict(nom="Date d'échéance", larg=12, fmt="date"),
    dict(nom="Montant du versement ($)", larg=13, fmt="money"),
    dict(nom="Payé", larg=7, liste="L_OuiNon"),
    dict(nom="Date du paiement", larg=12, fmt="date"),
    dict(nom="Notes", larg=26),
    dict(nom="Jours avant échéance", larg=10, fmt="jours", calc='IF(OR(F{r}="",H{r}="Oui"),"",F{r}-Aujourdhui)'),
], N_TAX, note="Une ligne par versement. Une échéance payée (Payé = Oui) sort des alertes.",
    exemple=["Municipale", 2026, 42000, 1, date(2026, 3, 1), 14000, "Oui", date(2026, 2, 25), "Exemple"])
# Bloc évaluation foncière, à droite
c0 = 14
tax.column_dimensions[get_column_letter(c0)].width = 3
tax.column_dimensions[get_column_letter(c0 + 1)].width = 28
tax.column_dimensions[get_column_letter(c0 + 2)].width = 16
tax.cell(row=4, column=c0 + 1, value="ÉVALUATION FONCIÈRE").font = f(bold=True, color=ORANGE_TXT)
EV = [("Rôle d'évaluation (années)", None, "text", "2026-2028"), ("Valeur du terrain ($)", None, "money0", 1200000),
      ("Valeur du bâtiment ($)", None, "money0", 5300000), ("Valeur totale ($)", "=SUM(P6:P7)", "money0", None),
      ("Date de marché de référence", None, "date", date(2024, 7, 1)), ("Date limite de demande de révision", None, "date", None)]
for k, (lib, form, fm, ex) in enumerate(EV):
    r = 5 + k
    tax.cell(row=r, column=c0 + 1, value=lib).font = f(bold=True)
    cell = tax.cell(row=r, column=c0 + 2, value=form if form else ex)
    cell.border, cell.number_format = BORD, FMT[fm]
    cell.font = f() if form else f(italic=True, color="0000FF")
    if form:
        cell.fill = CALC_FILL

# ---------------------------------------------------------------- Contrats
N_CON = 40
con = table("Contrats", "Contrats de service et fournisseurs", [
    dict(nom="Catégorie", larg=20, liste="L_CatContrat"),
    dict(nom="Fournisseur", larg=20),
    dict(nom="Personne-ressource", larg=18),
    dict(nom="Téléphone", larg=14),
    dict(nom="Courriel", larg=22),
    dict(nom="No de contrat", larg=12, fmt="text"),
    dict(nom="Début", larg=11, fmt="date"),
    dict(nom="Fin", larg=11, fmt="date"),
    dict(nom="Montant annuel ($ avant taxes)", larg=13, fmt="money0"),
    dict(nom="Renouvellement automatique", larg=12, liste="L_OuiNon"),
    dict(nom="Préavis de non-renouvellement (jours)", larg=13, fmt="int"),
    dict(nom="Notes", larg=24),
    dict(nom="Date limite du préavis", larg=12, fmt="date", calc='IF(I{r}="","",I{r}-N(L{r}))'),
    dict(nom="Jours avant date limite", larg=10, fmt="jours", calc=JR(d="N")),
], N_CON, note="La date à surveiller est la date limite du préavis : passé cette date, un contrat à renouvellement automatique se renouvelle.",
    exemple=["Déneigement", "Déneigement Exemple inc.", "Nom", "819 555-0103", "info@exemple.com", "C-2026-01",
             date(2026, 11, 1), date(2027, 4, 30), 9800, "Oui", 60, "Exemple"])

# ---------------------------------------------------------------- Entretien et inspections
N_ENT = 40
ENTRETIEN = [
    ("Façade", "Vérification par un ingénieur ou un architecte (bâtiment de 5 étages ou plus hors sol)", "Réglementaire", "RBQ, Code de sécurité, ch. VIII", 60),
    ("Stationnement étagé", "Vérification par un ingénieur (structure)", "Réglementaire", "RBQ, Code de sécurité, ch. VIII", 60),
    ("Extincteurs portatifs", "Inspection et entretien annuels", "Réglementaire", "CNPI / NFPA 10", 12),
    ("Gicleurs", "Inspection, essais et entretien", "Réglementaire", "CNPI / NFPA 25", 12),
    ("Alarme incendie", "Inspection et essais annuels", "Réglementaire", "CAN/ULC-S536", 12),
    ("Éclairage d'urgence et sorties", "Essai annuel de durée", "Réglementaire", "CNPI", 12),
    ("Avertisseurs de fumée et de CO", "Vérification dans les logements et aires communes", "Réglementaire", "Règlement municipal", 12),
    ("Ascenseur", "Inspection et entretien", "Réglementaire", "RBQ / CSA B44", 12),
    ("Dispositif antirefoulement", "Essai annuel", "Réglementaire", "Règlement municipal / CSA B64.10", 12),
    ("Cheminées", "Ramonage", "Réglementaire", "Règlement municipal", 12),
    ("Tour de refroidissement à l'eau", "Échantillonnage Legionella", "Réglementaire", "RBQ, Code de sécurité, ch. I", 1),
    ("Amiante (flocages et calorifuges)", "Vérification de l'état et mise à jour du registre", "Réglementaire", "CNESST, RSST", 12),
    ("Chaudière / système de chauffage", "Entretien annuel", "Assurance", "Fabricant", 12),
    ("Génératrice d'urgence", "Essai sous charge et entretien", "Réglementaire", "CSA C282", 12),
    ("Panneaux électriques", "Thermographie infrarouge", "Assurance", "Assureur", 36),
    ("Toiture", "Inspection visuelle et rapport", "Recommandée", "", 12),
    ("Drains de toit et gouttières", "Nettoyage", "Recommandée", "", 6),
    ("Chauffe-eau", "Vérification (fuites, soupape)", "Recommandée", "Fabricant", 12),
    ("Échangeurs d'air / ventilation", "Remplacement des filtres", "Recommandée", "Fabricant", 3),
    ("Puisard et pompe submersible", "Vérification et essai", "Recommandée", "", 6),
    ("Drain de fondation", "Inspection par caméra", "Recommandée", "", 60),
    ("Logements", "Inspection préventive des logements", "Recommandée", "", 12),
    ("Extermination", "Traitement préventif", "Recommandée", "", 3),
]
ent = table("Entretien", "Entretien préventif et inspections", [
    dict(nom="Élément ou système", larg=26),
    dict(nom="Tâche", larg=40),
    dict(nom="Exigence", larg=13, liste="L_Exigence"),
    dict(nom="Référence", larg=24),
    dict(nom="Fréquence (mois)", larg=9, fmt="int"),
    dict(nom="Applicable", larg=9, liste="L_OuiNon", aide="Mettre Non pour retirer la ligne des alertes (ex. pas d'ascenseur)."),
    dict(nom="Responsable ou fournisseur", larg=20),
    dict(nom="Dernière réalisation", larg=12, fmt="date"),
    dict(nom="Rapport (lien)", larg=22),
    dict(nom="Prochaine échéance", larg=12, fmt="date",
         calc='IF(OR(I{r}="",F{r}="",G{r}="Non"),"",EDATE(I{r},F{r}))'),
    dict(nom="Jours restants", larg=10, fmt="jours", calc=JR(d="K")),
], N_ENT,
    note="Liste de départ indicative : fréquences et références à valider avec les fournisseurs et la réglementation en vigueur pour cet immeuble.",
    prerempli=[(a, b, c, d, e, None, None, None, None) for a, b, c, d, e in ENTRETIEN])
ent["G5"] = "Non"; ent["G6"] = "Non"
ent["G7"], ent["H7"], ent["I7"] = "Oui", "Protection incendie Exemple", date(2025, 12, 15)
for c in ("G5", "G6", "G7", "H7", "I7"):
    ent[c].font = f(italic=True, color="0000FF")
ent["B7"].comment = Comment("Ligne d'exemple (texte bleu italique) : remplacer par les vraies données.", "Progim")

# ---------------------------------------------------------------- Équipements
N_EQU = 40
table("Équipements", "Registre des équipements", [
    dict(nom="Équipement", larg=22),
    dict(nom="Emplacement", larg=16),
    dict(nom="Marque", larg=14),
    dict(nom="Modèle", larg=14),
    dict(nom="No de série", larg=14, fmt="text"),
    dict(nom="Année d'installation", larg=10, fmt="int"),
    dict(nom="Durée de vie utile (ans)", larg=10, fmt="int"),
    dict(nom="Fin de garantie", larg=11, fmt="date"),
    dict(nom="Installateur", larg=18),
    dict(nom="Coût de remplacement estimé ($)", larg=13, fmt="money0"),
    dict(nom="Notes", larg=24),
    dict(nom="Fin de vie estimée (année)", larg=10, fmt="int", calc='IF(OR(G{r}="",H{r}=""),"",G{r}+H{r})'),
    dict(nom="Années restantes", larg=9, fmt="ans", calc='IF(M{r}="","",M{r}-YEAR(Aujourdhui))'),
    dict(nom="Jours avant fin de garantie", larg=10, fmt="jours", calc=JR(d="I")),
], N_EQU, note="Sert à planifier les remplacements (CAPEX) à présenter au propriétaire.",
    exemple=["Chaudière principale", "Salle mécanique", "Marque", "Modèle", "SN000000", 2015, 25,
             date(2027, 6, 1), "Installateur Exemple", 85000, "Exemple"])

# ---------------------------------------------------------------- Travaux
N_TRA = 200
tra = table("Travaux", "Historique des travaux", [
    dict(nom="Date", larg=11, fmt="date"),
    dict(nom="Unité ou zone", larg=13),
    dict(nom="Description", larg=40),
    dict(nom="Catégorie", larg=13, liste="L_CatTravaux"),
    dict(nom="Fournisseur", larg=20),
    dict(nom="No de facture ou bon de travail", larg=14, fmt="text"),
    dict(nom="Coût ($ avant taxes)", larg=13, fmt="money"),
    dict(nom="Payé par", larg=12, liste="L_PayePar"),
    dict(nom="Garantie jusqu'au", larg=11, fmt="date"),
    dict(nom="Notes", larg=24),
], N_TRA, note="Une ligne par intervention. Utile pour l'historique d'une unité, les réclamations et le rapport annuel au propriétaire.",
    exemple=[date(2026, 2, 10), "203", "Remplacement du robinet de cuisine", "Réparation", "Plomberie Exemple",
             "F-1234", 285, "Propriétaire", date(2027, 2, 10), "Exemple"])

# ---------------------------------------------------------------- Contacts
CONTACTS = [
    ("Propriétaire", "", "", "", "", "", ""), ("Gestionnaire Progim", "Gestion Immobilière Progim", "", "", "", "", ""),
    ("Concierge", "", "", "", "", "", ""), ("Plombier", "", "", "", "", "", ""), ("Électricien", "", "", "", "", "", ""),
    ("Serrurier", "", "", "", "", "", ""), ("Chauffage et climatisation", "", "", "", "", "", ""),
    ("Ascenseur", "", "", "", "", "", ""), ("Protection incendie", "", "", "", "", "", ""),
    ("Déneigement", "", "", "", "", "", ""), ("Assureur – réclamations", "", "", "", "", "", ""),
    ("Courtier d'assurance", "", "", "", "", "", ""), ("Ville – travaux publics / 311", "", "", "", "", "", ""),
    ("Panne électrique", "Hydro-Québec", "", "1 800 790-2424", "1 800 790-2424", "", "Numéro à vérifier avant usage"),
    ("Fuite de gaz", "Énergir", "", "1 800 361-8003", "1 800 361-8003", "", "Numéro à vérifier avant usage"),
    ("Avant de creuser", "Info-Excavation", "", "1 800 663-9228", "", "", "Numéro à vérifier avant usage"),
    ("Urgence (police, pompiers, ambulance)", "", "", "911", "911", "", ""),
]
table("Contacts", "Contacts et urgences", [
    dict(nom="Rôle", larg=28), dict(nom="Entreprise ou organisme", larg=24), dict(nom="Nom", larg=20),
    dict(nom="Téléphone", larg=15), dict(nom="Urgence 24 h", larg=15), dict(nom="Courriel", larg=24),
    dict(nom="Notes", larg=28),
], 40, prerempli=CONTACTS,
    note="À imprimer pour le concierge. Ne jamais inscrire de code d'alarme, de mot de passe ou de combinaison dans ce fichier.")

# ---------------------------------------------------------------- Documents
DOCS = [
    "Acte d'acquisition / titre de propriété", "Certificat de localisation", "Plans (architecture, structure, mécanique, électricité)",
    "Rapport d'inspection préachat", "Évaluation environnementale (phase I / II)", "Contrat de gestion signé",
    "Polices et certificats d'assurance en vigueur", "Compte de taxes municipales", "Compte de taxes scolaires",
    "Avis d'évaluation foncière", "Baux en vigueur et renouvellements", "Registre des loyers (pour la section G du bail)",
    "Registre amiante (si construit avant 1999)", "Rapport de vérification de façade", "Certificats d'inspection d'ascenseur",
    "Rapports de protection incendie (extincteurs, gicleurs, alarme)", "Permis de construction et de rénovation",
    "Garanties (toiture, fenêtres, équipements)", "Déclaration de copropriété (si applicable)", "Plan des mesures d'urgence",
    "Liste des clés et des accès", "Fiches de données de sécurité (SIMDUT) des produits d'entretien",
]
table("Documents", "Documents au dossier", [
    dict(nom="Document", larg=48), dict(nom="Requis", larg=8, liste="L_OuiNon"), dict(nom="Statut", larg=13, liste="L_StatutDoc"),
    dict(nom="Date du document", larg=11, fmt="date"), dict(nom="Expiration ou renouvellement", larg=12, fmt="date"),
    dict(nom="Emplacement (lien SharePoint)", larg=36), dict(nom="Notes", larg=24),
    dict(nom="Jours restants", larg=10, fmt="jours", calc='IF(OR(F{r}="",D{r}="Sans objet"),"",F{r}-Aujourdhui)'),
], 40, prerempli=[(d,) for d in DOCS], note="Coller le lien SharePoint de chaque document. Statut Manquant = à obtenir.")
doc = wb["Documents"]

# ---------------------------------------------------------------- Fiche (avec tableau de bord)
fi = wb.create_sheet("Fiche", 0)
entete_feuille(fi, "Dossier maître de l'immeuble", ligne_immeuble=False, largeur=10)
fi["B2"] = '="Mis à jour le : "&IF(Fiche!$C$4="","—",TEXT(Fiche!$C$4,"yyyy-mm-dd"))'
fi["B2"].font = f(size=10, italic=True, color=DISCRET)
fi.column_dimensions["B"].width = 34
fi.column_dimensions["C"].width = 38
fi.column_dimensions["D"].width = 3
for L, w in zip("EFGHI", (40, 12, 15, 15, 13)):
    fi.column_dimensions[L].width = w

def section(r, col, titre):
    c = fi.cell(row=r, column=col, value=titre)
    c.font = f(bold=True, color=ORANGE_TXT, size=10)
    return r + 1

def champ(r, lib, ex=None, fmt=None, calc=None, aide=None, lst=None):
    fi.cell(row=r, column=2, value=lib).font = f(bold=True)
    v = fi.cell(row=r, column=3, value=calc if calc else ex)
    v.border = BORD
    v.alignment = Alignment(horizontal="left")
    if calc:
        v.fill, v.font = CALC_FILL, f()
    elif ex is not None:
        v.font = f(italic=True, color="0000FF")
    else:
        v.font = f()
    if fmt:
        v.number_format = FMT[fmt]
    if aide:
        fi.cell(row=r, column=2).comment = Comment(aide, "Progim")
    if lst:
        liste(fi, lst, f"C{r}")
    return r + 1

r = 4
r = champ(r, "Fiche mise à jour le", date(2026, 11, 14), "date")
r = section(r, 2, "IDENTIFICATION")
r = champ(r, "Code d'entité (Hopem)", "99.1", "text")              # C6
r = champ(r, "Nom de l'immeuble", "Immeuble Exemple")               # C7
r = champ(r, "Adresse civique", "450, rue des Érables")
r = champ(r, "Ville", "Sherbrooke")
r = champ(r, "Code postal", "J1H 0A0")
r = champ(r, "Numéro(s) de lot (cadastre du Québec)", "0 000 000", "text")
r = champ(r, "Matricule (rôle d'évaluation)", "0000-00-0000", "text")
r = champ(r, "Type d'immeuble", "Résidentiel", lst="L_TypeImmeuble")
r = champ(r, "Année de construction", 1988, "int")
r = champ(r, "Nombre d'étages hors sol", 4, "int")
r = champ(r, "Superficie du terrain (pi²)", 22000, "int")
r = champ(r, "Superficie du bâtiment (pi²)", 36000, "int")
r = champ(r, "Nombre d'unités", calc=f"=COUNTA({plage('Unités','B',N_UNI)})", fmt="int",
          aide="Calculé à partir de l'onglet Unités.")
r = champ(r, "Stationnements (intérieurs / extérieurs)", "0 / 32")
r += 1
r = section(r, 2, "PROPRIÉTAIRE ET MANDAT")
r = champ(r, "Propriétaire (nom légal)", "Propriétaire Exemple inc.")
r = champ(r, "NEQ", "0000000000", "text")
r = champ(r, "Représentant", "Nom du représentant")
r = champ(r, "Téléphone", "819 555-0100")
r = champ(r, "Courriel", "proprietaire@exemple.com")
r = champ(r, "Adresse de correspondance", "Adresse")
r = champ(r, "Début du mandat de gestion", date(2024, 1, 1), "date")
r = champ(r, "Fin ou renouvellement du mandat", date(2026, 12, 31), "date")
r = champ(r, "Préavis de résiliation (jours)", 90, "int")
r = champ(r, "Honoraires de gestion (% des revenus)", 0.05, "pct")
r = champ(r, "Fin d'exercice (mois, 1 à 12)", 12, "int")
r = champ(r, "Fréquence des rapports", "Mensuel", lst="L_Frequence")
r = champ(r, "Prêteur hypothécaire", "Prêteur Exemple")
r = champ(r, "Échéance hypothécaire", date(2028, 5, 1), "date")
r += 1
r = section(r, 2, "ÉQUIPE")
r = champ(r, "Gestionnaire responsable", "Nom")
r = champ(r, "Coordonnateur technique", "Nom")
r = champ(r, "Comptable responsable", "Nom")
r = champ(r, "Concierge (nom et téléphone)", "Nom, 819 555-0104")
r += 1
r = section(r, 2, "ACCÈS ET SÉCURITÉ (aucun code ni mot de passe)")
r = champ(r, "Emplacement des clés maîtresses", "Bureau Progim, boîte no 0")
r = champ(r, "Fournisseur du système d'alarme", "Fournisseur")
r = champ(r, "Entrée d'eau principale", "Sous-sol, salle mécanique")
r = champ(r, "Entrée électrique principale", "Sous-sol, local électrique")
r = champ(r, "Robinet de gaz principal", "Extérieur, côté nord")
r = champ(r, "Notes", "")
fin_fiche = r

# --- Tableau de bord (colonnes E à I)
rb = 4
fi.cell(row=rb, column=5, value="TABLEAU DE BORD").font = f(bold=True, color=ORANGE_TXT)
rb += 1
U = lambda col: plage("Unités", col, N_UNI)
kpi = [
    ("Unités inscrites", f"=COUNTA({U('B')})", "int"),
    ("Unités occupées", f'=COUNTIF({U("F")},"Occupé")', "int"),
    ("Unités vacantes", f'=COUNTIF({U("F")},"Vacant")', "int"),
    ("Taux d'occupation", f'=IFERROR(F6/(F5-COUNTIF({U("F")},"Non louable")),0)', "pct"),
    ("Revenu locatif mensuel", f"=SUM({U('L')})", "money"),
    ("Revenu locatif annualisé", "=F9*12", "money"),
    ("Loyer moyen (unités occupées)", f'=IFERROR(SUMIF({U("F")},"Occupé",{U("L")})/F6,0)', "money"),
    ("Contrats de service (annuel)", f"=SUM({plage('Contrats','J',N_CON)})", "money0"),
    ("Primes d'assurance (annuel)", f"=SUM({plage('Assurances','I',N_ASS)})", "money0"),
]
for lib, form, fm in kpi:
    fi.cell(row=rb, column=5, value=lib).font = f(bold=True)
    c = fi.cell(row=rb, column=6, value=form)
    c.number_format, c.fill, c.border, c.font = FMT[fm], CALC_FILL, BORD, f(bold=True)
    fi.merge_cells(start_row=rb, start_column=6, end_row=rb, end_column=7)
    rb += 1
rb += 1
fi.cell(row=rb, column=5, value="ÉCHÉANCES").font = f(bold=True, color=ORANGE_TXT)
rb += 1
for i, h in enumerate(["Catégorie", "En retard", "≤ seuil urgent", "≤ seuil d'alerte", "Prochaine"]):
    c = fi.cell(row=rb, column=5 + i, value=h)
    c.font, c.fill, c.border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
    c.alignment = Alignment(horizontal="center", wrap_text=True)
rb += 1
ECH = [  # (libellé, plage jours, plage dates, critère supplémentaire)
    ("Fins de bail", U("R"), U("K"), ""),
    ("Avis de modification de bail (date limite)", U("U"), U("T"), ""),
    ("Assurances", plage("Assurances", "N", N_ASS), plage("Assurances", "K", N_ASS), ""),
    ("Taxes (versements non payés)", plage("Taxes", "K", N_TAX), plage("Taxes", "F", N_TAX),
     f',{plage("Taxes","H",N_TAX)},"<>Oui"'),
    ("Contrats (date limite de préavis)", plage("Contrats", "O", N_CON), plage("Contrats", "N", N_CON), ""),
    ("Entretien et inspections", plage("Entretien", "L", N_ENT), plage("Entretien", "K", N_ENT), ""),
    ("Garanties d'équipements", plage("Équipements", "O", N_EQU), plage("Équipements", "I", N_EQU), ""),
    ("Documents à renouveler", plage("Documents", "I", 40), plage("Documents", "F", 40),
     f',{plage("Documents","D",40)},"<>Sans objet"'),
]
deb_ech = rb
for lib, j, d, extra in ECH:
    fi.cell(row=rb, column=5, value=lib).font = f()
    forms = [f'=COUNTIF({j},"<0")', f'=COUNTIFS({j},">=0",{j},"<="&SeuilUrgent)',
             f'=COUNTIFS({j},">=0",{j},"<="&SeuilAlerte)',
             f'=_xlfn.MINIFS({d},{d},">="&Aujourdhui{extra})']
    for k, form in enumerate(forms):
        c = fi.cell(row=rb, column=6 + k, value=form)
        c.fill, c.border, c.font = CALC_FILL, BORD, f(bold=True)
        c.alignment = Alignment(horizontal="center")
        c.number_format = FMT["nextdate"] if k == 3 else '0;-0;"—"'
    fi.cell(row=rb, column=5).border = BORD
    rb += 1
fin_ech = rb - 1
fi.conditional_formatting.add(f"F{deb_ech}:F{fin_ech}", FormulaRule(formula=[f"F{deb_ech}>0"],
                              fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True)))
fi.conditional_formatting.add(f"G{deb_ech}:G{fin_ech}", FormulaRule(formula=[f"G{deb_ech}>0"],
                              fill=fill(SPECIAL), font=Font(color=ORANGE_TXT, bold=True)))
fi.conditional_formatting.add(f"H{deb_ech}:H{fin_ech}", FormulaRule(formula=[f"H{deb_ech}>0"],
                              fill=fill(LIGNE_SURVOL), font=Font(color=AVERT, bold=True)))
rb += 1
fi.cell(row=rb, column=5, value='="Calculé au "&TEXT(Aujourdhui,"yyyy-mm-dd")&" — seuils : "&SeuilUrgent&" et "&SeuilAlerte&" jours (onglet Paramètres)."').font = f(size=9, italic=True, color=DISCRET)
rb += 1
fi.cell(row=rb, column=5, value="Le seuil d'alerte inclut les échéances du seuil urgent. Détail dans chaque onglet (filtre sur la colonne des jours).").font = f(size=9, italic=True, color=DISCRET)
fi.freeze_panes = "A4"
fi.page_setup.orientation = "landscape"
fi.page_setup.fitToWidth, fi.page_setup.fitToHeight = 1, 1
fi.sheet_properties.pageSetUpPr.fitToPage = True

# ---------------------------------------------------------------- Mode d'emploi
me = wb.create_sheet("Mode d'emploi", 0)
entete_feuille(me, "Dossier maître de l'immeuble — mode d'emploi", ligne_immeuble=False, largeur=4)
me.column_dimensions["B"].width = 26
me.column_dimensions["C"].width = 100
TXT = [
    ("À QUOI ÇA SERT", None),
    ("", "Un seul fichier par immeuble géré qui réunit tout ce qu'il faut savoir pour le gérer : identification, propriétaire et mandat, "
         "unités et baux, assurances, taxes, contrats, entretien, équipements, travaux, contacts et documents."),
    ("", "L'onglet Fiche donne un tableau de bord : occupation, revenus et toutes les échéances à venir ou dépassées."),
    ("DÉMARRER UN DOSSIER", None),
    ("1.", "Copier ce gabarit et le renommer : « Dossier maître - [code d'entité] - [adresse].xlsx » (ex. Dossier maître - 99.1 - 450 des Érables.xlsx)."),
    ("2.", "Le déposer dans le dossier SharePoint de l'immeuble."),
    ("3.", "Remplir l'onglet Fiche, puis les autres onglets. Remplacer ou supprimer les lignes d'exemple."),
    ("4.", "Dans l'onglet Entretien, mettre Non dans « Applicable » pour ce qui ne s'applique pas à l'immeuble, puis inscrire les dernières dates."),
    ("LÉGENDE", None),
    ("Cellule blanche", "À remplir. Plusieurs colonnes ont une liste déroulante."),
    ("Cellule grise", "Calculée automatiquement. Ne pas modifier."),
    ("Texte bleu italique", "Ligne d'exemple fictive : montre le format attendu. À remplacer ou supprimer."),
    ("En-tête marine", "Colonne à remplir. En-tête gris : colonne calculée."),
    ("Rouge", "Échéance dépassée."),
    ("Orange", "Échéance dans le seuil urgent (30 jours par défaut)."),
    ("Jaune", "Échéance dans le seuil d'alerte (90 jours par défaut). Les seuils se changent dans l'onglet Paramètres."),
    ("RÈGLES", None),
    ("Confidentialité", "Ne jamais inscrire de code d'alarme, de mot de passe, de combinaison ni de numéro de compte complet."),
    ("Mise à jour", "Changer la date « Fiche mise à jour le » à chaque révision. Revoir le dossier au moins une fois par trimestre et à chaque renouvellement de bail."),
    ("Ajouter des lignes", "Les tableaux ont de la place (200 unités, 200 travaux, 40 contrats…). Pour en ajouter, insérer des lignes AU MILIEU d'un tableau pour que les totaux et le tableau de bord les comptent."),
    ("Avis de modification de bail", "Calculés selon l'art. 1942 C.c.Q. (bail de 12 mois ou plus : 3 à 6 mois avant la fin; moins de 12 mois : 1 à 2 mois). Logement résidentiel seulement; ne s'applique pas au bail à durée indéterminée."),
    ("Entretien et inspections", "La liste de départ est indicative. Valider les fréquences et les exigences réglementaires avec les fournisseurs pour chaque immeuble."),
]
r = 3
for a, b in TXT:
    if b is None:
        r += 1
        me.cell(row=r, column=2, value=a).font = f(bold=True, color=ORANGE_TXT)
    else:
        me.cell(row=r, column=2, value=a).font = f(bold=True)
        c = me.cell(row=r, column=3, value=b)
        c.font, c.alignment = f(), Alignment(wrap_text=True, vertical="top")
        me.cell(row=r, column=2).alignment = Alignment(vertical="top")
    r += 1
# échantillons de légende
for row_, (fl, fo) in {15: (fill("FFFFFF"), f()), 16: (CALC_FILL, f()), 17: (None, f(italic=True, color="0000FF")),
                       18: (fill(MARINE), f(bold=True, color="FFFFFF")), 19: (fill(BLOQUE_PALE), f(bold=True, color=BLOQUE)),
                       20: (fill(SPECIAL), f(bold=True, color=ORANGE_TXT)), 21: (fill(LIGNE_SURVOL), f(color=AVERT))}.items():
    c = me.cell(row=row_, column=2)
    c.border = BORD
    if fl:
        c.fill = fl
    c.font = fo

me.page_setup.fitToWidth, me.page_setup.fitToHeight = 1, 1
me.sheet_properties.pageSetUpPr.fitToPage = True
wb.move_sheet("Paramètres", offset=len(wb.sheetnames))
wb.active = 1
wb.save(SORTIE)
print("Écrit :", SORTIE)
