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
    "L_Source": ["Propriétaire", "Gestionnaire sortant", "Propriétaire et gestionnaire", "Visite", "Progim (interne)"],
    "L_Priorite": ["1 - Avant la prise en charge", "2 - 30 premiers jours", "3 - 90 premiers jours"],
    "L_StatutInt": ["À demander", "Demandé", "Reçu", "Intégré", "Non disponible"],
    "L_StatutDossier": ["En intégration", "Actif", "En passation", "Terminé"],
    "L_TypeJournal": ["Intégration", "Mise à jour", "Révision trimestrielle", "Passation", "Autre"],
    "L_Mois": ["01 - Janvier", "02 - Février", "03 - Mars", "04 - Avril", "05 - Mai", "06 - Juin", "07 - Juillet",
               "08 - Août", "09 - Septembre", "10 - Octobre", "11 - Novembre", "12 - Décembre", "Chaque mois"],
    "L_Onglet": ["Fiche", "Connaissances", "Calendrier", "Unités", "Assurances", "Taxes", "Contrats", "Entretien",
                 "Équipements", "Travaux", "Contacts", "Documents", "Journal", "Hopem", "SharePoint"],
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
p["B7"], p["C7"] = "Délai de relance (jours)", 10
p["B8"], p["C8"] = "Révision du dossier (jours)", 90
p["C4"].number_format = FMT["date"]
for r in (4, 5, 6, 7, 8):
    p[f"B{r}"].font = f(bold=True)
    p[f"C{r}"].border = BORD
p["C4"].fill = CALC_FILL
for r in (5, 6, 7, 8):
    p[f"C{r}"].font = f(color="0000FF")
p["D5"] = "Échéance dans ce nombre de jours ou moins : affichée en orange."
p["D6"] = "Échéance dans ce nombre de jours ou moins : affichée en jaune."
p["D7"] = "Intégration : une demande sans réponse depuis ce nombre de jours est à relancer."
p["D8"] = "Le dossier doit être révisé (inscription au journal) au moins à cet intervalle."
for r in (5, 6, 7, 8):
    p[f"D{r}"].font = f(size=9, italic=True, color=DISCRET)
p["B9"] = "LISTES DÉROULANTES (ajouter des valeurs au bas d'une liste au besoin, elles apparaîtront dans les menus)"
p["B9"].font = f(bold=True, color=ORANGE_TXT)
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
wb.defined_names["DelaiRelance"] = DefinedName("DelaiRelance", attr_text="'Paramètres'!$C$7")
wb.defined_names["DelaiRevision"] = DefinedName("DelaiRevision", attr_text="'Paramètres'!$C$8")

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

# ---------------------------------------------------------------- Intégration d'un nouveau client
P1, P2, P3 = "1 - Avant la prise en charge", "2 - 30 premiers jours", "3 - 90 premiers jours"
PR, GS, PG, VI, PI = "Propriétaire", "Gestionnaire sortant", "Propriétaire et gestionnaire", "Visite", "Progim (interne)"
INTEG = [
    ("Mandat et propriétaire", "Contrat de gestion signé et date de prise en charge", PR, P1, "Fiche"),
    ("Mandat et propriétaire", "Nom légal, NEQ, structure de propriété et signataires autorisés", PR, P1, "Fiche"),
    ("Mandat et propriétaire", "Personnes autorisées à donner des instructions à Progim, et leurs coordonnées", PR, P1, "Fiche"),
    ("Mandat et propriétaire", "Seuil d'approbation des dépenses et décisions que le propriétaire veut prendre lui-même", PR, P1, "Fiche"),
    ("Mandat et propriétaire", "Mode et fréquence de communication souhaités; format et destinataires des rapports", PR, P1, "Connaissances"),
    ("Mandat et propriétaire", "Fin d'exercice et coordonnées du comptable externe", PR, P1, "Fiche"),
    ("Mandat et propriétaire", "Objectifs pour l'immeuble (conservation, revente, repositionnement, rénovations prévues)", PR, P2, "Connaissances"),
    ("Mandat et propriétaire", "Budget d'exploitation de l'année et budget de dépenses en capital", PG, P2, "SharePoint"),
    ("Finances", "États financiers des deux dernières années", PR, P2, "SharePoint"),
    ("Finances", "Balance de vérification et grand livre à la date du transfert", GS, P1, "Hopem"),
    ("Finances", "Comptes à payer ouverts et factures en suspens", GS, P1, "Hopem"),
    ("Finances", "Arrérages par locataire et ententes de paiement en cours", GS, P1, "Hopem"),
    ("Finances", "Dépôts et avances détenus (locaux commerciaux)", GS, P1, "Hopem"),
    ("Finances", "Compte bancaire d'exploitation et procédure de changement des signataires", PR, P1, "Fiche"),
    ("Finances", "Paiements préautorisés en place (locataires et fournisseurs)", GS, P1, "Hopem"),
    ("Finances", "Prêt hypothécaire : prêteur, échéance, rapports exigés par le prêteur", PR, P2, "Fiche"),
    ("Finances", "Comptes de services publics (Hydro-Québec, Énergir, eau) et numéros de compte", GS, P1, "Contrats"),
    ("Finances", "Derniers comptes de taxes municipales et scolaires, versements et solde", PR, P1, "Taxes"),
    ("Finances", "Inscription aux fichiers de la TPS et de la TVQ (immeuble commercial ou mixte)", PR, P2, "Fiche"),
    ("Finances", "Fonds de prévoyance ou réserves (copropriété, exigence du prêteur)", PR, P2, "Fiche"),
    ("Location", "Copies des baux en vigueur et des renouvellements", GS, P1, "Unités"),
    ("Location", "Liste des loyers à jour (unité, locataire, loyer, échéance, inclusions)", GS, P1, "Unités"),
    ("Location", "Avis de modification envoyés et réponses reçues pour la prochaine période", GS, P1, "Unités"),
    ("Location", "Unités vacantes, avis de départ et annonces de location en cours", GS, P1, "Unités"),
    ("Location", "Dossiers au Tribunal administratif du logement (en cours, jugements, ententes)", GS, P1, "Connaissances"),
    ("Location", "Coordonnées des locataires (téléphone, courriel)", GS, P1, "Unités"),
    ("Location", "Baux commerciaux : renouvellement, indexation, frais d'exploitation refacturés, options", GS, P1, "Unités"),
    ("Location", "Règlements d'immeuble remis aux locataires", GS, P2, "Documents"),
    ("Location", "Registre des loyers (loyer le plus bas des 12 derniers mois, section G du bail)", GS, P2, "Documents"),
    ("Location", "Attribution des stationnements et des rangements", GS, P2, "Unités"),
    ("Location", "Électroménagers fournis et inclusions particulières par unité", GS, P3, "Unités"),
    ("Bâtiment", "Problèmes récurrents connus (infiltrations, refoulements, chauffage, vermine)", GS, P1, "Connaissances"),
    ("Bâtiment", "Particularités techniques (valve difficile, pompe à surveiller, réglages, bruits normaux)", GS, P1, "Connaissances"),
    ("Bâtiment", "Emplacement des entrées d'eau, d'électricité et de gaz, des panneaux et des valves", GS, P1, "Fiche"),
    ("Bâtiment", "Travaux en cours ou prévus (soumissions, contrats signés, permis)", PG, P1, "Travaux"),
    ("Bâtiment", "Bons de travail ouverts et demandes de locataires non réglées", GS, P1, "Travaux"),
    ("Bâtiment", "Plans du bâtiment et certificat de localisation", PR, P2, "Documents"),
    ("Bâtiment", "Rapports d'inspection (préachat, façade, structure, toiture)", PR, P2, "Documents"),
    ("Bâtiment", "Équipements : âge, marque, garanties", GS, P2, "Équipements"),
    ("Bâtiment", "Travaux majeurs des cinq dernières années, avec les coûts", PG, P2, "Travaux"),
    ("Bâtiment", "Rapports de protection incendie, d'ascenseur et d'antirefoulement", GS, P2, "Entretien"),
    ("Bâtiment", "Calendrier d'entretien préventif actuel", GS, P2, "Entretien"),
    ("Bâtiment", "Registre amiante (immeuble construit avant 1999)", PR, P2, "Documents"),
    ("Contrats et fournisseurs", "Copies des contrats de service en vigueur", GS, P1, "Contrats"),
    ("Contrats et fournisseurs", "Dates de renouvellement et préavis de résiliation des contrats", GS, P1, "Contrats"),
    ("Contrats et fournisseurs", "Fournisseurs habituels, surtout ceux qui connaissent bien l'immeuble", GS, P1, "Contacts"),
    ("Contrats et fournisseurs", "Ententes verbales ou tarifs particuliers avec des fournisseurs", GS, P2, "Connaissances"),
    ("Contrats et fournisseurs", "Concierge : employeur, horaire, tâches, rémunération, logement fourni", PG, P1, "Connaissances"),
    ("Assurances et risques", "Polices d'assurance en vigueur, courtier et franchises", PR, P1, "Assurances"),
    ("Assurances et risques", "Ajout de Progim comme assuré additionnel (responsabilité civile)", PR, P1, "Assurances"),
    ("Assurances et risques", "Réclamations d'assurance des cinq dernières années et réclamations en cours", PR, P2, "Connaissances"),
    ("Assurances et risques", "Mises en demeure, poursuites, avis d'infraction de la ville", PG, P1, "Connaissances"),
    ("Accès et sécurité", "Remise et inventaire des clés (maîtresses, logements, locaux techniques)", GS, P1, "Fiche"),
    ("Accès et sécurité", "Cartes et télécommandes d'accès, interphone", GS, P1, "Fiche"),
    ("Accès et sécurité", "Système d'alarme : fournisseur, centrale, transfert des codes (jamais dans ce fichier)", GS, P1, "Contacts"),
    ("Accès et sécurité", "Caméras : fournisseur, accès aux enregistrements, affichage", GS, P2, "Contacts"),
    ("Accès et sécurité", "Plan des mesures d'urgence et personnes-ressources", GS, P2, "Documents"),
    ("Visite", "Visite complète avec le gestionnaire sortant ou le concierge, y compris les locaux techniques", VI, P1, "Connaissances"),
    ("Visite", "Photos de l'état des aires communes et des équipements à la prise en charge", VI, P1, "SharePoint"),
    ("Visite", "Relevés des compteurs (si refacturation)", VI, P1, "SharePoint"),
    ("Visite", "Inspection d'un échantillon de logements", VI, P2, "Travaux"),
    ("Mise en place Progim", "Création de l'entité et de l'immeuble dans Hopem", PI, P1, "Hopem"),
    ("Mise en place Progim", "Dossier SharePoint de l'immeuble créé et documents déposés", PI, P1, "SharePoint"),
    ("Mise en place Progim", "Avis aux locataires : nouveau gestionnaire, coordonnées, paiement du loyer", PI, P1, "Documents"),
    ("Mise en place Progim", "Avis aux fournisseurs : facturation et coordonnées", PI, P1, "Contrats"),
    ("Mise en place Progim", "Transfert des comptes de services publics et des paiements préautorisés", PI, P1, "Hopem"),
    ("Mise en place Progim", "Ajout aux processus Progim (rapports mensuels, fin d'exercice)", PI, P1, "Hopem"),
    ("Mise en place Progim", "Rencontre de démarrage avec le propriétaire (attentes, premier rapport)", PI, P1, "Connaissances"),
    ("Mise en place Progim", "Bilan des 90 jours avec le propriétaire", PI, P3, "Journal"),
]
N_INT = 120
integ = table("Intégration", "Intégration d'un nouveau client", [
    dict(nom="No", larg=5, fmt="int"),
    dict(nom="Section", larg=20),
    dict(nom="Information ou document à obtenir", larg=58),
    dict(nom="Source", larg=25, liste="L_Source"),
    dict(nom="Priorité", larg=25, liste="L_Priorite"),
    dict(nom="Applicable", larg=9, liste="L_OuiNon", aide="Mettre Non si l'élément ne s'applique pas à cet immeuble : il sort du calcul d'avancement."),
    dict(nom="Statut", larg=12, liste="L_StatutInt"),
    dict(nom="Demandé le", larg=11, fmt="date"),
    dict(nom="Reçu le", larg=11, fmt="date"),
    dict(nom="Responsable Progim", larg=14),
    dict(nom="Consigné dans", larg=13, liste="L_Onglet", aide="Onglet ou système où l'information est inscrite une fois reçue."),
    dict(nom="Notes", larg=30),
    dict(nom="Jours en attente", larg=9, fmt="int",
         calc='IF(AND(H{r}="Demandé",ISNUMBER(I{r})),Aujourdhui-I{r},"")',
         aide="Jours depuis la demande, tant que le statut est Demandé. Orange au délai de relance, rouge au double."),
], N_INT,
    note="Filtrer Source sur Propriétaire ou Gestionnaire sortant pour obtenir la liste à envoyer. Statut : À demander › Demandé › Reçu › Intégré.",
    prerempli=[(i + 1, a, b, c, d, None, "À demander", None, None, None, e) for i, (a, b, c, d, e) in enumerate(INTEG)])
for col in "DM":
    for rr in range(DEB, DEB + N_INT):
        integ[f"{col}{rr}"].alignment = Alignment(wrap_text=True, vertical="top")
tl = f"N{DEB}"
integ.conditional_formatting.add(f"N{DEB}:N{DEB + N_INT - 1}", FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}>=2*DelaiRelance)"],
    fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True), stopIfTrue=True))
integ.conditional_formatting.add(f"N{DEB}:N{DEB + N_INT - 1}", FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}>=DelaiRelance)"],
    fill=fill(SPECIAL), font=Font(color=ORANGE_TXT, bold=True), stopIfTrue=True))
integ.conditional_formatting.add(f"H{DEB}:H{DEB + N_INT - 1}", FormulaRule(formula=[f'OR(H{DEB}="Reçu",H{DEB}="Intégré")'],
    fill=fill(OK_PALE), font=Font(color=OK)))
integ.conditional_formatting.add(f"B{DEB}:M{DEB + N_INT - 1}", FormulaRule(formula=[f'$G{DEB}="Non"'], font=Font(color="AEB6C8")))
# Exemple sur la première ligne
for c_, v in (("G5", "Oui"), ("H5", "Reçu"), ("I5", date(2026, 10, 20)), ("J5", date(2026, 10, 24)), ("K5", "Initiales")):
    integ[c_] = v
    integ[c_].font = f(italic=True, color="0000FF")
integ["B5"].comment = Comment("Ligne d'exemple (texte bleu italique) pour les colonnes de suivi.", "Progim")

# ---------------------------------------------------------------- Connaissances
CONN = [
    ("Historique", "Depuis quand le propriétaire détient-il l'immeuble, et pourquoi change-t-il de gestionnaire?"),
    ("Historique", "Quels événements ont marqué l'immeuble (sinistres, gros travaux, litiges, changements d'usage)?"),
    ("Propriétaire", "Quelles décisions le propriétaire veut-il prendre lui-même? Que peut-on faire sans lui demander?"),
    ("Propriétaire", "Comment et quand préfère-t-il être joint? Qui d'autre faut-il mettre en copie?"),
    ("Propriétaire", "Quels sujets sont sensibles pour lui (hausses de loyer, dépenses, locataires de longue date)?"),
    ("Propriétaire", "Quels sont ses objectifs et son horizon pour l'immeuble?"),
    ("Bâtiment", "Quels problèmes reviennent, et qu'est-ce qui a déjà été essayé pour les régler?"),
    ("Bâtiment", "Quels équipements demandent une attention particulière (réglages, bruits normaux ou anormaux)?"),
    ("Bâtiment", "Où sont les valves, entrées et panneaux? Y a-t-il des pièges (valve difficile, accès encombré)?"),
    ("Bâtiment", "Que faire dans cet immeuble en cas de dégât d'eau, de panne de chauffage ou d'électricité?"),
    ("Bâtiment", "Quels travaux devraient être faits dans les un à trois prochaines années?"),
    ("Locataires", "Quelles situations faut-il connaître (ententes de paiement, besoins d'accès, plaintes récurrentes)? Faits seulement."),
    ("Locataires", "Quels dossiers de non-paiement, de bruit ou de troubles de jouissance sont en cours?"),
    ("Locataires", "Y a-t-il des ententes particulières avec certains locataires (travaux, stationnement, animaux)?"),
    ("Fournisseurs", "Quels fournisseurs connaissent bien l'immeuble? Lesquels éviter, et pourquoi?"),
    ("Fournisseurs", "Y a-t-il des ententes verbales ou des tarifs particuliers?"),
    ("Concierge", "Qui est le concierge, quelles sont ses tâches réelles, ses forces et ses limites?"),
    ("Opérations", "Collecte des déchets, du recyclage et du compost : jours, bacs, particularités"),
    ("Opérations", "Déneigement : zones, consignes, bacs de sel, points de friction"),
    ("Opérations", "Quelles règles de l'immeuble posent problème ou sont mal respectées?"),
    ("Ville et voisinage", "Relations avec les voisins et la ville; plaintes ou avis reçus"),
    ("Ville et voisinage", "Droits acquis, usages particuliers, unités ou travaux non conformes connus"),
    ("Litiges et réclamations", "Dossiers au TAL, réclamations d'assurance, mises en demeure : état et prochaines étapes"),
]
N_CONN = 100
conn = table("Connaissances", "Connaissances de l'immeuble", [
    dict(nom="Thème", larg=18),
    dict(nom="Question guide", larg=48),
    dict(nom="Ce qu'il faut savoir (réponse)", larg=70),
    dict(nom="Source (qui l'a dit)", larg=18),
    dict(nom="Date", larg=11, fmt="date"),
    dict(nom="Mis à jour par", larg=14),
], N_CONN,
    note="Ce que l'équipe sait sans l'avoir écrit. À remplir en rencontre avec le gestionnaire sortant, puis à enrichir au fil de l'eau. Faits professionnels seulement.",
    prerempli=CONN)
for rr in range(DEB, DEB + N_CONN):
    for col in "CD":
        conn[f"{col}{rr}"].alignment = Alignment(wrap_text=True, vertical="top")
conn["D5"] = "Exemple : propriétaire depuis 2012, change de gestionnaire à cause de délais de réponse aux locataires."
conn["E5"], conn["F5"], conn["G5"] = "Propriétaire", date(2026, 10, 20), "Initiales"
for c_ in ("D5", "E5", "F5", "G5"):
    conn[c_].font = f(italic=True, color="0000FF")

# ---------------------------------------------------------------- Calendrier annuel
CAL = [
    ("01 - Janvier", "Inscrire les versements du compte de taxes municipales (onglet Taxes)"),
    ("01 - Janvier", "Début de la période d'envoi des avis de modification pour les baux se terminant le 30 juin"),
    ("02 - Février", "Remettre le relevé 31 aux locataires et le transmettre à Revenu Québec (au plus tard le dernier jour de février)"),
    ("03 - Mars", "Date limite d'envoi des avis de modification pour les baux se terminant le 30 juin (31 mars)"),
    ("03 - Mars", "Rappel aux locataires : vérifier les avertisseurs de fumée au changement d'heure"),
    ("04 - Avril", "Suivi des réponses des locataires aux avis de modification (délai d'un mois)"),
    ("04 - Avril", "Fin du déneigement : nettoyage du terrain et du stationnement, constat des dommages"),
    ("04 - Avril", "Inspection de la toiture et des drains après l'hiver"),
    ("05 - Mai", "Ouvrir les robinets extérieurs; aménagement paysager"),
    ("05 - Mai", "Annonces de location des logements libres au 1er juillet"),
    ("06 - Juin", "Planifier les déménagements du 1er juillet (ascenseur, conteneurs, stationnement)"),
    ("07 - Juillet", "Inspection et état des logements libérés; travaux de remise en état"),
    ("07 - Juillet", "Inscrire le compte de taxes scolaires (onglet Taxes)"),
    ("08 - Août", "Planifier les travaux d'automne; soumissions de déneigement si le contrat est à renouveler"),
    ("09 - Septembre", "Entretien du système de chauffage avant la saison"),
    ("10 - Octobre", "Fermer et purger les robinets extérieurs"),
    ("10 - Octobre", "Installation des balises; contrat de déneigement en vigueur"),
    ("11 - Novembre", "Nettoyage des gouttières après la chute des feuilles"),
    ("11 - Novembre", "Préparer le budget de l'année suivante et le présenter au propriétaire"),
    ("12 - Décembre", "Bilan annuel au propriétaire et priorités de travaux"),
    ("12 - Décembre", "Révision complète du dossier maître (inscrire au journal)"),
    ("Chaque mois", "Rapport mensuel au propriétaire"),
    ("Chaque mois", "Tournée de l'immeuble : aires communes et locaux techniques"),
]
cal = table("Calendrier", "Calendrier annuel de l'immeuble", [
    dict(nom="Mois", larg=15, liste="L_Mois"),
    dict(nom="Tâche", larg=80),
    dict(nom="Responsable", larg=18),
    dict(nom="Applicable", larg=9, liste="L_OuiNon"),
    dict(nom="Notes propres à l'immeuble", larg=40),
], 60, note="Ce qui revient chaque année. Ajouter les particularités de l'immeuble; trier par mois avec le filtre.",
    prerempli=CAL)

# ---------------------------------------------------------------- Journal et passation
N_JOU = 300
jou = table("Journal", "Journal des mises à jour", [
    dict(nom="Date", larg=11, fmt="date"),
    dict(nom="Type", larg=18, liste="L_TypeJournal"),
    dict(nom="Par", larg=14),
    dict(nom="Onglets touchés", larg=20),
    dict(nom="Description", larg=60),
], N_JOU, note="Une ligne par mise à jour importante, révision ou passation. La date la plus récente s'affiche dans la Fiche.",
    exemple=[date(2026, 11, 14), "Intégration", "Initiales", "Fiche, Intégration", "Ouverture du dossier"])
PASS = [
    "Dossier maître révisé et à jour par le gestionnaire sortant",
    "Rencontre de passation : revue de chaque onglet, surtout Connaissances",
    "Visite de l'immeuble ensemble (y compris les locaux techniques)",
    "Points ouverts listés : bons de travail, arrérages, TAL, travaux, réclamations",
    "Échéances des 90 prochains jours revues (tableau de bord de la Fiche)",
    "Clés et accès remis et inventoriés",
    "Présentation au propriétaire et au concierge",
    "Locataires et fournisseurs avisés au besoin",
    "Gestionnaire responsable changé dans la Fiche et dans Hopem",
    "Passation inscrite au journal; statut du dossier remis à Actif",
]
jou.column_dimensions["H"].width = 3
jou.column_dimensions["I"].width = 62
jou.column_dimensions["J"].width = 8
jou.column_dimensions["K"].width = 22
jou["I4"] = "LISTE DE PASSATION (vider les colonnes Fait et Notes à chaque nouvelle passation)"
jou["I4"].font = f(bold=True, color=ORANGE_TXT)
jou["I4"].alignment = Alignment(wrap_text=True, vertical="center")
for k, h in enumerate(("Étape", "Fait", "Date et notes")):
    c = jou.cell(row=5, column=9 + k, value=h)
    c.font, c.fill, c.border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
for k, t in enumerate(PASS):
    rr = 6 + k
    jou.cell(row=rr, column=9, value=f"{k + 1}. {t}").font = f()
    for col in (9, 10, 11):
        jou.cell(row=rr, column=col).border = BORD
liste(jou, "L_OuiNon", f"J6:J{5 + len(PASS)}")
jou.conditional_formatting.add(f"J6:J{5 + len(PASS)}", FormulaRule(formula=['J6="Oui"'], fill=fill(OK_PALE), font=Font(color=OK, bold=True)))
jou.cell(row=7 + len(PASS), column=9, value=f'="Étapes faites : "&COUNTIF(J6:J{5 + len(PASS)},"Oui")&" sur {len(PASS)}"').font = f(bold=True)

# ---------------------------------------------------------------- Fiche (avec tableau de bord)
fi = wb.create_sheet("Fiche", 0)
entete_feuille(fi, "Dossier maître de l'immeuble", ligne_immeuble=False, largeur=10)
fi["B2"] = '="Dernière mise à jour : "&IF(N(Fiche!$C$4)=0,"aucune inscription au journal",TEXT(Fiche!$C$4,"yyyy-mm-dd"))'
fi["B2"].font = f(size=10, italic=True, color=DISCRET)
fi.column_dimensions["B"].width = 40
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
r = champ(r, "Dernière mise à jour (journal)", calc=f"=MAX({plage('Journal','B',N_JOU)})", fmt="nextdate",
          aide="Date de la plus récente inscription dans l'onglet Journal.")
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
r = champ(r, "Seuil d'approbation des dépenses ($)", 2500, "money0",
          aide="Montant au-delà duquel le propriétaire doit approuver une dépense avant engagement.")
r = champ(r, "Honoraires de gestion (% des revenus)", 0.05, "pct")
r = champ(r, "Fin d'exercice (mois, 1 à 12)", 12, "int")
r = champ(r, "Fréquence des rapports", "Mensuel", lst="L_Frequence")
r = champ(r, "Prêteur hypothécaire", "Prêteur Exemple")
r = champ(r, "Échéance hypothécaire", date(2028, 5, 1), "date")
r = champ(r, "Gestionnaire précédent (firme et contact)", "Firme Exemple, nom, 819 555-0105")
r += 1
r = section(r, 2, "ÉQUIPE")
r = champ(r, "Statut du dossier", "En intégration", lst="L_StatutDossier")
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
rb += 2
fi.cell(row=rb, column=5, value="INTÉGRATION ET SUIVI DU DOSSIER").font = f(bold=True, color=ORANGE_TXT)
rb += 1
I = lambda col: plage("Intégration", col, N_INT)
ouvert = f'{I("D")},"<>",{I("G")},"<>Non",{I("H")},"<>Reçu",{I("H")},"<>Intégré",{I("H")},"<>Non disponible"'
suivi = [
    ("Éléments d'intégration applicables", f'=COUNTIFS({I("D")},"<>",{I("G")},"<>Non")', '0;-0;"—"'),
    ("Éléments encore ouverts", f"=COUNTIFS({ouvert})", '0;-0;"—"'),
    ("Avancement de l'intégration", "=IFERROR(1-F{o}/F{a},0)", FMT["pct"]),
    ("Priorité 1 encore ouverts", f'=COUNTIFS({ouvert},{I("F")},"1*")', '0;-0;"—"'),
    ("Demandes à relancer", f'=COUNTIF({I("N")},">="&DelaiRelance)', '0;-0;"—"'),
    ("Jours depuis la dernière mise à jour", '=IF(N(C4)=0,"",Aujourdhui-C4)', '0'),
]
deb_suivi = rb
for k, (lib, form, fm) in enumerate(suivi):
    fi.cell(row=rb, column=5, value=lib).font = f(bold=True)
    c = fi.cell(row=rb, column=6, value=form.format(a=deb_suivi, o=deb_suivi + 1) if "{" in form and "F{" in form else form)
    c.number_format, c.fill, c.border, c.font = fm, CALC_FILL, BORD, f(bold=True)
    fi.merge_cells(start_row=rb, start_column=6, end_row=rb, end_column=7)
    rb += 1
for off in (3, 4):
    fi.conditional_formatting.add(f"F{deb_suivi + off}", FormulaRule(formula=[f"F{deb_suivi + off}>0"],
                                  fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True)))
fi.conditional_formatting.add(f"F{deb_suivi + 5}", FormulaRule(
    formula=[f"AND(ISNUMBER(F{deb_suivi + 5}),F{deb_suivi + 5}>DelaiRevision)"], fill=fill(BLOQUE_PALE), font=Font(color=BLOQUE, bold=True)))
fi.cell(row=rb, column=5, value='="Révision attendue aux "&DelaiRevision&" jours; relance après "&DelaiRelance&" jours sans réponse."').font = f(size=9, italic=True, color=DISCRET)
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
    ("", "Un seul fichier par immeuble géré, qui réunit tout ce qu'il faut savoir pour le gérer. C'est la référence de toute l'équipe Progim. "
         "Il sert à trois moments : l'intégration d'un nouveau client, la gestion au quotidien et la passation d'un gestionnaire à un autre."),
    ("", "L'onglet Fiche donne le tableau de bord : occupation, revenus, échéances, avancement de l'intégration et date de la dernière mise à jour."),
    ("1. INTÉGRATION", None),
    ("Ouvrir le dossier", "Copier ce gabarit, le renommer « Dossier maître - [code d'entité] - [adresse].xlsx » et le déposer dans le dossier SharePoint "
                          "de l'immeuble. Dans la Fiche, mettre le statut du dossier à En intégration."),
    ("Préparer les demandes", "Onglet Intégration : mettre Non dans Applicable pour ce qui ne s'applique pas, puis nommer un responsable Progim par élément. "
                              "Filtrer la colonne Source sur Propriétaire, puis sur Gestionnaire sortant : chaque liste filtrée devient la demande "
                              "à envoyer. Inscrire la date dans Demandé le et passer le statut à Demandé."),
    ("Commencer par la priorité 1", "Tout ce qu'il faut avoir avant la prise en charge. Les demandes sans réponse passent en orange, puis en rouge : relancer."),
    ("Rencontre de transfert", "Avec le gestionnaire sortant et le concierge, parcourir l'onglet Connaissances question par question et écrire les réponses. "
                               "C'est là qu'on récupère ce que l'équipe sait sans l'avoir écrit. Faire la visite complète le même jour si possible."),
    ("Consigner", "À la réception, inscrire l'information dans l'onglet indiqué (Consigné dans), puis passer le statut à Intégré."),
    ("Terminer", "Quand la priorité 1 est complète, mettre le statut du dossier à Actif. Faire le bilan des 90 jours avec le propriétaire."),
    ("2. TENUE À JOUR", None),
    ("Responsable", "Le gestionnaire responsable est le gardien du dossier; toute l'équipe peut et doit le mettre à jour."),
    ("Journal", "Chaque changement important = une ligne dans l'onglet Journal (date, qui, quoi). La Fiche affiche la date de la dernière mise à jour."),
    ("Révision", "Revoir tout le dossier au moins une fois par trimestre. Après 90 jours sans inscription au journal, le compteur de la Fiche passe en rouge."),
    ("Au fil de l'eau", "Ce qu'on apprend sur le terrain va dans Connaissances au moment où on l'apprend : c'est ce qui rend la passation facile."),
    ("3. PASSATION", None),
    ("Étapes", "Mettre le statut du dossier à En passation et suivre la liste de passation dans l'onglet Journal. À la fin, changer le gestionnaire "
               "responsable dans la Fiche et dans Hopem, inscrire la passation au journal et remettre le statut à Actif."),
    ("LÉGENDE", None),
    ("Cellule blanche", "À remplir. Plusieurs colonnes ont une liste déroulante."),
    ("Cellule grise", "Calculée automatiquement. Ne pas modifier."),
    ("Texte bleu italique", "Exemple fictif : montre le format attendu. À remplacer ou supprimer."),
    ("En-tête marine", "Colonne à remplir. En-tête gris : colonne calculée."),
    ("Rouge", "Échéance dépassée, ou demande à relancer depuis longtemps."),
    ("Orange", "Échéance dans le seuil urgent (30 jours par défaut), ou demande à relancer."),
    ("Jaune", "Échéance dans le seuil d'alerte (90 jours par défaut). Les seuils et délais se changent dans l'onglet Paramètres."),
    ("RÈGLES", None),
    ("Un seul fichier", "Ouvrir le fichier depuis SharePoint, dans Excel : plusieurs personnes peuvent y travailler en même temps. Pas de copie sur un poste."),
    ("Confidentialité", "Ne jamais inscrire de code d'alarme, de mot de passe, de combinaison ni de numéro de compte complet."),
    ("Renseignements personnels", "Loi 25 : sur les locataires, seulement ce qui est nécessaire à la gestion, des faits et non des opinions. Le dossier SharePoint "
                                  "est réservé à l'équipe Progim. Ne pas transmettre le fichier complet au propriétaire ni à des tiers : extraire l'onglet utile."),
    ("Ajouter des lignes", "Les tableaux ont de la place (120 éléments d'intégration, 200 unités, 300 inscriptions au journal…). Pour en ajouter, insérer des "
                           "lignes au milieu d'un tableau pour que les totaux et le tableau de bord les comptent."),
    ("Avis de modification", "Calculés selon l'art. 1942 C.c.Q. (bail de 12 mois ou plus : 3 à 6 mois avant la fin; moins de 12 mois : 1 à 2 mois). "
                             "Logement résidentiel seulement; ne s'applique pas au bail à durée indéterminée."),
    ("Listes de départ", "Les listes d'entretien, du calendrier et les numéros d'urgence sont indicatifs : les valider pour chaque immeuble."),
]
LEGENDE = {"Cellule blanche": (fill("FFFFFF"), f()), "Cellule grise": (CALC_FILL, f()),
           "Texte bleu italique": (None, f(italic=True, color="0000FF")), "En-tête marine": (fill(MARINE), f(bold=True, color="FFFFFF")),
           "Rouge": (fill(BLOQUE_PALE), f(bold=True, color=BLOQUE)), "Orange": (fill(SPECIAL), f(bold=True, color=ORANGE_TXT)),
           "Jaune": (fill(LIGNE_SURVOL), f(color=AVERT))}
r = 3
for a, b in TXT:
    if b is None:
        r += 1
        me.cell(row=r, column=2, value=a).font = f(bold=True, color=ORANGE_TXT)
    else:
        lab = me.cell(row=r, column=2, value=a)
        lab.font, lab.alignment = f(bold=True), Alignment(vertical="top", wrap_text=True)
        c = me.cell(row=r, column=3, value=b)
        c.font, c.alignment = f(), Alignment(wrap_text=True, vertical="top")
        if a in LEGENDE:
            fl, fo = LEGENDE[a]
            lab.border, lab.font = BORD, fo
            if fl:
                lab.fill = fl
    r += 1
me.page_setup.fitToWidth, me.page_setup.fitToHeight = 1, 0
me.sheet_properties.pageSetUpPr.fitToPage = True
ORDRE = ["Mode d'emploi", "Fiche", "Intégration", "Connaissances", "Calendrier", "Unités", "Assurances", "Taxes",
         "Contrats", "Entretien", "Équipements", "Travaux", "Contacts", "Documents", "Journal", "Paramètres"]
wb._sheets.sort(key=lambda w: ORDRE.index(w.title))
wb.active = 1
wb.save(SORTIE)
print("Écrit :", SORTIE)
