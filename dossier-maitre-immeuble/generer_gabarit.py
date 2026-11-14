"""Génère le gabarit « Dossier maître de l'immeuble — Modèle Progim ».

Structure : le modèle Progim en 38 sections, réparti en onglets.
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

# ------------------------------------------------------------------ Style (design system Progim)
MARINE, ORANGE, ORANGE_TXT = "131A2F", "EE7203", "B85500"
FOND, LIGNE, DISCRET, SURVOL, PALE = "F3F4F6", "DDE2E6", "5B6770", "E8EBEF", "AEB6C8"
BLOQUE, BLOQUE_PALE, SPECIAL, AVERT, LIGNE_SURVOL = "B4471A", "FBEAE2", "FFF1E0", "6E5000", "FFF4E8"
OK, OK_PALE, INFO, INFO_PALE = "2D7A3E", "E3F2E6", "0B5D7A", "E3EFF4"
EXEMPLE = "0000FF"
POLICE = "Arial"


def f(**kw):
    kw.setdefault("name", POLICE)
    kw.setdefault("size", 10)
    return Font(**kw)


fill = lambda c: PatternFill("solid", fgColor=c)
mince = Side(style="thin", color=LIGNE)
BORD = Border(left=mince, right=mince, top=mince, bottom=mince)
CALC = fill(FOND)
FMT = {
    "date": "yyyy-mm-dd", "mois": "yyyy-mm", "money": '#,##0.00 "$";(#,##0.00 "$");"—"',
    "money0": '#,##0 "$";(#,##0 "$");"—"', "int": "0", "jours": "0;[Red]-0", "ans": "0;[Red]-0",
    "pct": "0.0%", "text": "@", "nextdate": 'yyyy-mm-dd;;"—"', "nb": '0;-0;"—"', "dec1": "0.0",
}
DEB = 5  # première ligne de données des tableaux (en-têtes en ligne 4)

wb = Workbook()
wb.remove(wb.active)
REF = {}  # clé -> référence absolue d'une valeur de formulaire

# ------------------------------------------------------------------ Paramètres et listes
LISTES = {
    "L_OuiNon": ["Oui", "Non"],
    "L_StatutInfo": ["Validé", "À valider", "Sans objet"],
    "L_TypeImmeuble": ["Résidentiel", "Commercial", "Mixte", "Copropriété", "Industriel"],
    "L_NiveauService": ["Signature", "Performance", "Croissance"],
    "L_Objectif": ["Croissance de valeur", "Flux de trésorerie", "Préservation à long terme",
                   "Repositionnement / développement", "Délégation / tranquillité d'esprit"],
    "L_PrioriteLoc": ["Maximiser le loyer", "Réduire la vacance", "Équilibre"],
    "L_StatutDossier": ["En intégration", "Actif", "En passation", "Terminé"],
    "L_StatutUnite": ["Occupé", "Vacant", "Avis de départ", "En rénovation", "Non louable"],
    "L_TypeUnite": ["Studio", "1½", "2½", "3½", "4½", "5½", "6½ et +", "Local commercial", "Bureau",
                    "Stationnement", "Rangement"],
    "L_Source": ["Propriétaire", "Ancien gestionnaire", "Propriétaire et ancien gestionnaire", "Visite", "Progim (interne)"],
    "L_Phase": ["0 - Avant la prise en charge", "1 - 0 à 30 jours", "2 - 31 à 60 jours", "3 - 61 à 90 jours"],
    "L_StatutInt": ["À demander", "Demandé", "Reçu", "Intégré", "Non disponible"],
    "L_TypeDossier": ["Arrérages", "Entente de paiement", "TAL", "Troubles de jouissance", "Juridique (autre)", "Autre"],
    "L_StatutLegal": ["Ouvert", "En attente d'audience", "Jugement rendu", "Entente conclue", "Fermé"],
    "L_Couverture": ["Biens", "Responsabilité civile", "Pertes de revenus", "Bris d'équipement", "Refoulement des égouts",
                     "Inondation", "Tremblement de terre", "Responsabilité des administrateurs", "Excédentaire (umbrella)", "Autre"],
    "L_TypeTaxe": ["Municipale", "Scolaire", "Droits de mutation", "Autre"],
    "L_CatContrat": ["Plomberie", "Électricité", "Chauffage", "Nettoyage", "Déneigement", "Paysagement", "Ascenseur",
                     "Extermination", "Sécurité", "Protection incendie", "Matières résiduelles", "Buanderie",
                     "Utilité – électricité", "Utilité – gaz", "Utilité – eau", "Internet", "Téléphonie", "Autre"],
    "L_Exigence": ["Réglementaire", "Assurance", "Recommandée"],
    "L_StatutProjet": ["Prévu", "En cours", "Réalisé", "Annulé"],
    "L_Priorite": ["Haute", "Moyenne", "Basse"],
    "L_TypeSinistre": ["Dégât d'eau", "Refoulement", "Incendie", "Vol ou vandalisme", "Bris d'équipement",
                       "Intempérie", "Blessure", "Autre"],
    "L_StatutSinistre": ["Ouvert", "Réclamation en cours", "Fermé"],
    "L_CatRisque": ["Financier", "Locatif", "Physique", "Légal", "Assurance", "Sécurité", "Réputation", "Opérationnel"],
    "L_Proba": ["Faible", "Moyenne", "Élevée"],
    "L_Impact": ["Faible", "Moyen", "Élevé"],
    "L_StatutRisque": ["Ouvert", "En traitement", "Fermé"],
    "L_TypeOpp": ["Augmentation de loyers", "Stationnements", "Rangements", "Revenus accessoires", "Réduction de vacance",
                  "Optimisation de contrats", "Réduction de dépenses", "Rénovation", "Repositionnement",
                  "Refinancement", "Développement"],
    "L_StatutOpp": ["Identifiée", "En analyse", "Approuvée", "En cours", "Réalisée", "Abandonnée"],
    "L_TypeAction": ["Action", "Question ouverte", "Décision requise"],
    "L_StatutAction": ["À faire", "En cours", "Fait", "Annulé"],
    "L_CatDoc": ["Légal", "Financier", "Technique", "Location", "Assurance"],
    "L_StatutDoc": ["Au dossier", "Manquant", "À renouveler", "Sans objet"],
    "L_TypeJournal": ["Intégration", "Mise à jour", "Révision trimestrielle", "Passation", "Autre"],
    "L_Mois": ["01 - Janvier", "02 - Février", "03 - Mars", "04 - Avril", "05 - Mai", "06 - Juin", "07 - Juillet",
               "08 - Août", "09 - Septembre", "10 - Octobre", "11 - Novembre", "12 - Décembre", "Chaque mois"],
    "L_Onglet": ["Résumé", "Fiche", "Vision", "Finances", "Bâtiment", "Intégration", "Plan 90 jours", "Unités", "Dossiers",
                 "Assurances", "Taxes", "Contrats", "Entretien", "Équipements", "Projets", "Sinistres", "Exceptions",
                 "Décisions", "Risques", "Opportunités", "KPI", "Actions", "Calendrier", "Contacts", "Documents",
                 "Journal", "Hopem", "SharePoint"],
}


def entete_feuille(ws, titre, largeur=12, ligne_immeuble=True):
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    ws["B1"] = titre
    ws["B1"].font = f(size=15, bold=True, color="FFFFFF")
    ws["B1"].alignment = Alignment(vertical="center")
    for c in range(1, largeur + 2):
        cell = ws.cell(row=1, column=c)
        cell.fill = fill(MARINE)
        cell.border = Border(bottom=Side(style="thick", color=ORANGE))
    ws.row_dimensions[1].height = 30
    if ligne_immeuble:
        n, c = REF["nom_interne"], REF["code"]
        ws["B2"] = (f'=IF({n}="","Immeuble : (à inscrire dans l\'onglet Fiche)",'
                    f'"Immeuble : "&{n}&IF({c}="",""," — entité "&{c}))')
        ws["B2"].font = f(size=10, italic=True, color=DISCRET)


def liste(ws, nom, ref):
    dv = DataValidation(type="list", formula1=f"={nom}", allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    for part in ref.split():
        dv.add(part)
    return dv


def regle(ws, ref, formule, couleur_fond, couleur_txt, gras=True):
    ws.conditional_formatting.add(ref, FormulaRule(formula=[formule], fill=fill(couleur_fond),
                                                   font=Font(color=couleur_txt, bold=gras), stopIfTrue=True))


def alerte_jours(ws, ref):
    tl = ref.split(":")[0]
    regle(ws, ref, f"AND(ISNUMBER({tl}),{tl}<0)", BLOQUE_PALE, BLOQUE)
    regle(ws, ref, f"AND(ISNUMBER({tl}),{tl}<=SeuilUrgent)", SPECIAL, ORANGE_TXT)
    regle(ws, ref, f"AND(ISNUMBER({tl}),{tl}<=SeuilAlerte)", LIGNE_SURVOL, AVERT, gras=False)


def mise_en_page(ws, titres="4:4", hauteur=0):
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, hauteur
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    if titres:
        ws.print_title_rows = titres


p = wb.create_sheet("Paramètres")
entete_feuille(p, "Paramètres", largeur=4 + len(LISTES), ligne_immeuble=False)
PARAMS = [
    ("Date du jour", "=TODAY()", "date", "Utilisée par tous les calculs d'échéance."),
    ("Seuil urgent (jours)", 30, "int", "Échéance dans ce nombre de jours ou moins : orange."),
    ("Seuil d'alerte (jours)", 90, "int", "Échéance dans ce nombre de jours ou moins : jaune."),
    ("Délai de relance (jours)", 10, "int", "Intégration : demande sans réponse depuis ce délai = à relancer."),
    ("Révision (jours)", 90, "int", "Intervalle maximal entre deux mises à jour du journal, et entre deux validations d'une exception."),
]
for k, (lib, val, fm, note) in enumerate(PARAMS):
    r = 4 + k
    p[f"B{r}"], p[f"C{r}"], p[f"D{r}"] = lib, val, note
    p[f"B{r}"].font = f(bold=True)
    p[f"C{r}"].border, p[f"C{r}"].number_format = BORD, FMT[fm]
    p[f"C{r}"].font = f() if k == 0 else f(color=EXEMPLE)
    if k == 0:
        p[f"C{r}"].fill = CALC
    p[f"D{r}"].font = f(size=9, italic=True, color=DISCRET)
for nom, r in (("Aujourdhui", 4), ("SeuilUrgent", 5), ("SeuilAlerte", 6), ("DelaiRelance", 7), ("DelaiRevision", 8)):
    wb.defined_names[nom] = DefinedName(nom, attr_text=f"'Paramètres'!$C${r}")
p.column_dimensions["B"].width, p.column_dimensions["C"].width = 26, 13
p["B10"] = "LISTES DÉROULANTES : ajouter une valeur au bas d'une liste pour qu'elle apparaisse dans les menus."
p["B10"].font = f(bold=True, color=ORANGE_TXT)
for i, (nom, valeurs) in enumerate(LISTES.items()):
    col = 5 + i
    L = get_column_letter(col)
    p.column_dimensions[L].width = 24
    h = p.cell(row=12, column=col, value=nom[2:])
    h.font, h.fill = f(bold=True, color=MARINE), fill(SURVOL)
    for j, v in enumerate(valeurs):
        p.cell(row=13 + j, column=col, value=v).font = f()
    wb.defined_names[nom] = DefinedName(nom, attr_text=f"'Paramètres'!${L}$13:${L}$45")

# ------------------------------------------------------------------ Formulaires (onglets en paires champ / valeur)
FORM_FIN = {}  # onglet -> dernière ligne


def F(lib, ex=None, fmt=None, lst=None, calc=None, key=None, aide=None, long=False):
    return dict(lib=lib, ex=ex, fmt=fmt, lst=lst, calc=calc, key=key, aide=aide, long=long)


def formulaire(nom, titre, sections, note):
    """Onglet en paires Champ / Information, avec statut, source et date de validation par champ."""
    ws = wb.create_sheet(nom)
    entete_feuille(ws, titre, largeur=6, ligne_immeuble=nom != "Fiche")
    ws["B3"] = note
    ws["B3"].font = f(size=9, italic=True, color=INFO)
    for L, w in zip("BCDEFGH", (42, 62, 12, 30, 12, 12, 4)):
        ws.column_dimensions[L].width = w
    for i, h in enumerate(["Champ", "Information", "Statut", "Source ou lien vers la source officielle", "Validé le", "Par"]):
        c = ws.cell(row=4, column=2 + i, value=h)
        c.font, c.fill, c.border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws["D4"].comment = Comment("Validé : information confirmée. À valider : reçue, pas encore confirmée. "
                               "Sans objet : ne s'applique pas. Une information vide est considérée manquante (surlignée).", "Progim")
    r = 5
    statut_cells = []
    for sec, champs in sections:
        r += 1 if r > 5 else 0
        c = ws.cell(row=r, column=2, value=sec)
        c.font = f(bold=True, color=ORANGE_TXT)
        for col in range(2, 8):
            ws.cell(row=r, column=col).fill = fill(SURVOL)
        r += 1
        for ch in champs:
            lab = ws.cell(row=r, column=2, value=ch["lib"])
            lab.font, lab.alignment = f(bold=True), Alignment(vertical="top", wrap_text=True)
            v = ws.cell(row=r, column=3)
            v.alignment = Alignment(vertical="top", wrap_text=True, horizontal="left")
            if ch["calc"]:
                v.value, v.fill, v.font = ch["calc"], CALC, f()
            elif ch["ex"] is not None:
                v.value, v.font = ch["ex"], f(italic=True, color=EXEMPLE)
            else:
                v.font = f()
            if ch["fmt"]:
                v.number_format = FMT[ch["fmt"]]
            if ch["lst"]:
                liste(ws, ch["lst"], f"C{r}")
            if ch["aide"]:
                lab.comment = Comment(ch["aide"], "Progim")
            if ch["long"]:
                ws.row_dimensions[r].height = 45
            for col in range(2, 8):
                ws.cell(row=r, column=col).border = BORD
            ws.cell(row=r, column=6).number_format = FMT["date"]
            ws.cell(row=r, column=8, value="champ" if not ch["calc"] else "calc")
            if not ch["calc"]:
                statut_cells.append(f"D{r}")
            if ch["key"]:
                REF[ch["key"]] = f"'{nom}'!$C${r}"
            r += 1
    liste(ws, "L_StatutInfo", " ".join(statut_cells))
    regle(ws, f"C6:C{r}", '=AND($H6="champ",$C6="",$D6<>"Sans objet")'[1:], SPECIAL, ORANGE_TXT, gras=False)
    regle(ws, f"D6:D{r}", 'AND($H6<>"",$D6="Validé")', OK_PALE, OK, gras=False)
    ws.column_dimensions["H"].hidden = True
    ws.freeze_panes = "C5"
    mise_en_page(ws, titres="4:4")
    FORM_FIN[nom] = r
    return ws


TYPES_RES = '{"Studio","1½","2½","3½","4½","5½","6½ et +"}'
TYPES_COM = '{"Local commercial","Bureau"}'
U_TYPE = "'Unités'!$C$5:$C$204"

# ---- Fiche : sections 1, 2, 3, 5, 14, 22
formulaire("Fiche", "Fiche de l'immeuble", [
    ("1. IDENTIFICATION DE L'IMMEUBLE", [
        F("Code d'entité (Hopem)", "99.1", "text", key="code"),
        F("Nom interne de l'immeuble", "Érables 450", key="nom_interne"),
        F("Nom commercial", "Les Résidences Exemple"),
        F("Adresse civique", "450, rue des Érables", key="adresse"),
        F("Ville", "Sherbrooke"),
        F("Code postal", "J1H 0A0"),
        F("Numéro(s) de lot", "0 000 000", "text"),
        F("Matricule municipal", "0000-00-0000", "text"),
        F("Année de construction", 1988, "int"),
        F("Année(s) de rénovation majeure", "2015 (toiture), 2021 (fenêtres)"),
        F("Type d'immeuble", "Résidentiel", lst="L_TypeImmeuble"),
        F("Nombre total de logements", calc=f"=SUMPRODUCT(COUNTIF({U_TYPE},{TYPES_RES}))+SUMPRODUCT(COUNTIF({U_TYPE},{TYPES_COM}))",
          fmt="int", key="nb_log", aide="Calculé à partir de l'onglet Unités (logements et locaux, sans stationnements ni rangements)."),
        F("Nombre de logements résidentiels", calc=f"=SUMPRODUCT(COUNTIF({U_TYPE},{TYPES_RES}))", fmt="int"),
        F("Nombre de locaux commerciaux", calc=f"=SUMPRODUCT(COUNTIF({U_TYPE},{TYPES_COM}))", fmt="int"),
        F("Nombre d'étages", 4, "int"),
        F("Nombre d'entrées", 2, "int"),
        F("Nombre d'ascenseurs", 0, "int"),
        F("Nombre de stationnements intérieurs", 0, "int"),
        F("Nombre de stationnements extérieurs", 32, "int"),
        F("Nombre de rangements", 24, "int"),
        F("Autres espaces générateurs de revenus", "Buanderie (2 laveuses, 2 sécheuses)"),
    ]),
    ("1. DESCRIPTION SOMMAIRE", [
        F("Positionnement de l'immeuble", long=True), F("Clientèle cible"),
        F("Particularités importantes", long=True, key="particularites"),
        F("Forces de l'immeuble", long=True), F("Faiblesses connues", long=True), F("Principaux risques", long=True),
    ]),
    ("2. PROPRIÉTAIRE", [
        F("Nom légal", "Propriétaire Exemple inc.", key="proprio"), F("Nom usuel"), F("Adresse"),
        F("NEQ", fmt="text"), F("TPS", fmt="text"), F("TVQ", fmt="text"),
        F("Personne-ressource principale", key="contact"), F("Téléphone", key="tel_contact"), F("Courriel"),
    ]),
    ("2. STRUCTURE DE PROPRIÉTÉ", [
        F("Société propriétaire"), F("Actionnaires / partenaires pertinents", long=True), F("Gestionnaire d'actifs externe"),
        F("Comptable externe"), F("Fiscaliste"), F("Avocat"), F("Courtier immobilier"), F("Courtier hypothécaire"),
        F("Autres conseillers"),
    ]),
    ("2. AUTORISATIONS", [
        F("Signataire autorisé"), F("Personnes autorisées à approuver des dépenses"),
        F("Personnes autorisées à recevoir les rapports"), F("Personnes à mettre en copie"),
        F("Seuil d'autorisation Progim ($)", fmt="money0", aide="Montant jusqu'auquel Progim engage une dépense sans approbation."),
        F("Seuil nécessitant approbation du propriétaire ($)", fmt="money0"),
        F("Travaux nécessitant toujours une approbation", long=True),
        F("Procédure en cas d'urgence", long=True, aide="Qui décider, jusqu'à quel montant, qui aviser et dans quel délai."),
    ]),
    ("3. MANDAT DE GESTION PROGIM", [
        F("Date de début du mandat", fmt="date"), F("Date de renouvellement", fmt="date"), F("Durée du mandat"),
        F("Niveau de service", lst="L_NiveauService", key="niveau"),
        F("Honoraires de gestion"), F("Minimum mensuel ($)", fmt="money0"), F("Frais d'intégration"), F("Frais de location"),
        F("Frais TAL"), F("Frais de supervision de travaux"), F("Autres frais"), F("Préavis de résiliation"),
        F("Particularités contractuelles", long=True),
    ]),
    ("3. PORTÉE DU MANDAT", [
        F("Inclus", long=True), F("Exclusions", long=True), F("Responsabilités conservées par le propriétaire", long=True),
    ]),
    ("ÉQUIPE PROGIM ET SUIVI DU DOSSIER", [
        F("Statut du dossier", "En intégration", lst="L_StatutDossier", key="statut_dossier"),
        F("Gestionnaire responsable", key="gestionnaire"), F("Coordonnateur location"), F("Coordonnateur technique"),
        F("Comptable responsable"), F("Remplaçant en cas d'absence"),
        F("Dernière mise à jour (journal)", calc="=MAX('Journal'!$B$5:$B$304)", fmt="nextdate", key="maj",
          aide="Date de la plus récente inscription dans l'onglet Journal."),
    ]),
    ("5. ANCIEN GESTIONNAIRE", [
        F("Nom"), F("Contact"), F("Téléphone"), F("Courriel"), F("Date de fin de mandat", fmt="date"),
        F("Raison connue du changement", long=True), F("Commentaires pertinents", long=True),
    ]),
    ("14. CONCIERGES ET PERSONNEL SUR PLACE", [
        F("Nom"), F("Rôle"), F("Téléphone"), F("Courriel"), F("Type de relation", aide="Employé du propriétaire, sous-traitant, etc."),
        F("Horaire"), F("Salaire / honoraires"), F("Logement fourni"), F("Responsabilités", long=True),
        F("Particularités"), F("Remplaçant"), F("Performance / enjeux", long=True),
    ]),
    ("22. TECHNOLOGIE ET SYSTÈMES", [
        F("Logiciel comptable", "Hopem"), F("Logiciel de gestion"), F("Portail locataire"), F("Caméras"), F("Intercom"),
        F("Contrôle d'accès"), F("Wi-Fi"), F("Capteurs"), F("Automatisations"), F("Intégrations"), F("Particularités"),
    ]),
], "Sections 1, 2, 3, 5, 14 et 22 du modèle. Une information inconnue reste vide : elle apparaît surlignée comme manquante.")

# ---- Vision : sections 4, 10 (particularités), 11, 12
formulaire("Vision", "Vision du propriétaire et stratégie", [
    ("4. VISION", [
        F("Horizon de détention"), F("Objectif principal", lst="L_Objectif", key="objectif"), F("Objectif secondaire"),
        F("Rendement recherché"), F("Niveau de risque accepté"), F("Tolérance à la vacance"), F("Tolérance aux investissements"),
        F("Priorité entre revenus immédiats et valeur à long terme", long=True),
        F("Stratégie concernant les rénovations", long=True), F("Stratégie concernant les loyers", long=True),
        F("Stratégie concernant les refinancements", long=True), F("Stratégie concernant la vente éventuelle", long=True),
    ]),
    ("4. PRIORITÉS DU PROPRIÉTAIRE", [F(f"Priorité {i}", key=f"prio{i}") for i in range(1, 6)]),
    ("4. IRRITANTS OU PRÉOCCUPATIONS HISTORIQUES", [F(f"Irritant {i}", long=True) for i in range(1, 4)]),
    ("4. PRÉFÉRENCES DE COMMUNICATION", [
        F("Fréquence"), F("Canal principal"), F("Niveau de détail"), F("Rapports supplémentaires requis"),
        F("Préférence pour décisions"), F("Sujets pour lesquels le client veut être consulté", long=True),
        F("Sujets pour lesquels Progim doit décider de façon autonome", long=True),
    ]),
    ("10. PARTICULARITÉS LOCATIVES", [
        F("Lien vers le registre locatif", aide="Le registre détaillé est dans l'onglet Unités ou dans Hopem."),
        F("Clauses particulières", long=True), F("Ententes verbales connues", long=True), F("Rabais"), F("Promotions"),
        F("Stationnements inclus"), F("Rangements inclus"), F("Services inclus"), F("Chauffage inclus"),
        F("Électricité incluse"), F("Internet inclus"), F("Autres"),
    ]),
    ("11. STRATÉGIE LOCATIVE", [
        F("Loyer cible"), F("Loyer potentiel"), F("Priorité", lst="L_PrioriteLoc"),
        F("Niveau d'autonomie du gestionnaire", long=True), F("Travaux autorisés avant relocation", long=True),
        F("Promotions permises"), F("Positionnement"), F("Profil de clientèle"), F("Particularités du marché", long=True),
    ]),
    ("11. CADENCE DE RÉVISION", [
        F("Revue location (fréquence)"), F("Responsable"), F("Coordonnateur location"),
        F("Indicateurs suivis", "Leads, visites, candidatures, jours sur le marché, loyer demandé, disponibilité réelle, "
                               "état de l'unité, retour des prospects", long=True),
    ]),
    ("12. COMPTES RECEVABLES ET ARRÉRAGES", [
        F("Méthodes de paiement acceptées"), F("PPA"), F("Interac"), F("Chèques"), F("Autres"),
        F("Processus NSF", long=True), F("Processus de relance", long=True), F("Processus TAL", long=True),
        F("Particularités client", long=True),
    ]),
], "Sections 4, 10, 11 et 12 du modèle. À remplir en rencontre avec le propriétaire, puis à revoir au moins une fois par année.")

# ---- Finances : sections 6, 7, 8
formulaire("Finances", "Diagnostic, budget et finances", [
    ("6. DIAGNOSTIC INITIAL — REVENUS", [
        F("Revenus locatifs mensuels ($)", fmt="money"), F("Revenus locatifs annuels ($)", fmt="money"),
        F("Revenus accessoires ($ / an)", fmt="money"), F("Stationnements ($ / an)", fmt="money"),
        F("Rangements ($ / an)", fmt="money"), F("Buanderie ($ / an)", fmt="money"), F("Autres revenus ($ / an)", fmt="money"),
        F("Loyer moyen par logement ($)", fmt="money"), F("Revenus potentiels estimés ($ / an)", fmt="money"),
        F("Écart entre revenus actuels et potentiels", long=True),
    ]),
    ("6. DIAGNOSTIC INITIAL — DÉPENSES", [
        F("Dépenses d'exploitation annuelles ($)", fmt="money"), F("Principales catégories", long=True),
        F("Dépenses inhabituelles", long=True), F("Contrats importants"), F("Dépenses potentiellement optimisables", long=True),
    ]),
    ("6. NOI / RNN", [
        F("NOI / RNN actuel ($ / an)", fmt="money", key="rnn"), F("NOI / RNN budgété ($ / an)", fmt="money"),
        F("NOI / RNN historique", long=True),
        F("Point de départ officiel pour le suivi de performance", aide="Montant et date de référence pour mesurer la création de valeur."),
        F("Commentaires", long=True),
    ]),
    ("6. OCCUPATION À L'INTÉGRATION", [
        F("Taux d'occupation", fmt="pct"), F("Nombre de logements vacants", fmt="int"), F("Nombre de logements à venir", fmt="int"),
        F("Nombre de logements en rénovation", fmt="int"), F("Vacance économique estimée ($ / an)", fmt="money"),
    ]),
    ("7. BUDGET", [
        F("Année budgétaire"), F("Date de fin d'exercice", fmt="date"), F("Budget approuvé", lst="L_OuiNon"),
        F("Date d'approbation", fmt="date"), F("Responsable"), F("Lien vers le budget"), F("Principales hypothèses", long=True),
        F("Réserve prévue ($)", fmt="money0"), F("CAPEX prévu ($)", fmt="money0"),
        F("Travaux majeurs prévus", aide="Le détail va dans l'onglet Projets."),
        F("Écart important à surveiller 1"), F("Écart important à surveiller 2"), F("Écart important à surveiller 3"),
    ]),
    ("8. COMPTES BANCAIRES", [
        F("Institution"), F("Numéro de compte interne", aide="Quatre derniers chiffres seulement."), F("Type"), F("Usage"),
        F("Signataires"), F("Accès Progim"), F("Particularités"),
    ]),
    ("8. HYPOTHÈQUE", [
        F("Institution"), F("Numéro de prêt", fmt="text"), F("Solde ($)", fmt="money"), F("Taux", fmt="pct"),
        F("Type de taux"), F("Amortissement"), F("Paiement ($)", fmt="money"), F("Fréquence"),
        F("Date de renouvellement", fmt="date", key="renouv_hypo"), F("Compte de prélèvement"), F("Contact"),
        F("Particularités", long=True),
    ]),
    ("8. TPS / TVQ", [
        F("Inscrit", lst="L_OuiNon"), F("Fréquence"), F("Particularités"), F("Méthode de répartition"), F("Responsable"),
    ]),
    ("8. REMISES AU PROPRIÉTAIRE", [
        F("Fréquence"), F("Méthode"), F("Montant minimal à conserver ($)", fmt="money0"), F("Règles particulières", long=True),
    ]),
    ("8. PARTICULARITÉS COMPTABLES", [
        F("Répartition multi-immeubles"), F("Intercompagnies"), F("Avances propriétaire"), F("Refacturation"),
        F("Écritures récurrentes", long=True), F("Autres"),
    ]),
], "Sections 6, 7 et 8 du modèle. Taxes : onglet Taxes. Risques et opportunités du diagnostic initial : onglets Risques et Opportunités.")

# ---- Bâtiment : sections 16 et 20, plus procédures d'urgence
formulaire("Bâtiment", "Bâtiment, systèmes et conformité", [
    ("16. STRUCTURE / ENVELOPPE", [F(x) for x in ("Fondation", "Structure", "Toiture", "Maçonnerie", "Fenêtres", "Balcons",
                                                    "Drainage", "Étanchéité")] + [F("Commentaires", long=True)]),
    ("16. PLOMBERIE", [F("Type"), F("Chauffe-eau"), F("Pompes"), F("Entrée d'eau", aide="Emplacement exact et accès."),
                       F("Clapets"), F("Particularités", long=True), F("Historique de problèmes", long=True)]),
    ("16. ÉLECTRICITÉ", [F("Entrée électrique"), F("Panneaux"), F("Génératrice"), F("Éclairage"), F("Particularités", long=True)]),
    ("16. CHAUFFAGE / VENTILATION / CLIMATISATION", [F(x) for x in (
        "Type de chauffage", "Combustible", "Équipements", "Thermostats", "Ventilation", "Climatisation", "Entretien",
        "Fournisseur")]),
    ("16. ASCENSEURS", [F("Nombre", fmt="int"), F("Fournisseur"), F("Contrat"), F("Inspection"),
                        F("Dernier entretien", fmt="date"), F("Prochaine échéance", fmt="date")]),
    ("16. SÉCURITÉ INCENDIE", [F(x) for x in ("Système", "Alarme", "Gicleurs", "Extincteurs", "Inspection annuelle",
                                                "Fournisseur")] + [F("Particularités", long=True)]),
    ("16. ACCÈS / SÉCURITÉ", [
        F("Serrures"), F("Intercom"), F("Caméras"), F("Contrôle d'accès"),
        F("Codes", aide="Où sont conservés les codes et qui y a accès. Ne jamais inscrire les codes ici."),
        F("Gestion des clés"), F("Registre des clés", aide="Lien vers le registre."), F("Personnes avec accès maître"),
    ]),
    ("PROCÉDURES D'URGENCE PROPRES À L'IMMEUBLE", [
        F("Dégât d'eau : quoi fermer, où, qui appeler", long=True),
        F("Panne de chauffage", long=True), F("Panne électrique", long=True),
        F("Incendie ou évacuation", long=True),
        F("Pièges et particularités techniques connus", long=True,
          aide="Ce que seul l'ancien gestionnaire ou le concierge sait : valve difficile, pompe à surveiller, réglages, bruits normaux."),
    ]),
    ("20. CONFORMITÉ ET INSPECTIONS", [F(x) for x in (
        "Inspection municipale", "Inspection incendie", "Inspection ascenseur", "Inspection électrique", "Inspection gaz",
        "Inspection environnementale", "Amiante", "Pyrite", "Radon", "Réservoirs", "Autres")]),
    ("20. NON-CONFORMITÉS CONNUES", [F(f"Non-conformité {i}", long=True) for i in range(1, 4)]),
], "Sections 16 et 20 du modèle. Calendrier d'entretien : onglet Entretien. Âge et garanties des équipements : onglet Équipements.")


# ------------------------------------------------------------------ Tableaux
def table(nom, titre, colonnes, n, note=None, exemple=None, prerempli=None):
    """colonnes : dicts nom, larg, fmt, calc (formule avec {r}), liste, aide, wrap, cache."""
    ws = wb.create_sheet(nom)
    entete_feuille(ws, titre, largeur=len(colonnes))
    if note:
        ws["B3"] = note
        ws["B3"].font = f(size=9, italic=True, color=INFO)
    for i, c in enumerate(colonnes):
        col = 2 + i
        L = get_column_letter(col)
        c["L"] = L
        ws.column_dimensions[L].width = c.get("larg", 14)
        if c.get("cache"):
            ws.column_dimensions[L].hidden = True
        h = ws.cell(row=4, column=col, value=c["nom"])
        calc = c.get("calc") is not None
        h.font = f(bold=True, color=MARINE if calc else "FFFFFF", size=9)
        h.fill = fill(SURVOL) if calc else fill(MARINE)
        h.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        h.border = BORD
        if c.get("aide"):
            h.comment = Comment(c["aide"], "Progim")
        for r in range(DEB, DEB + n):
            cell = ws.cell(row=r, column=col)
            cell.border, cell.font = BORD, f()
            if c.get("fmt"):
                cell.number_format = FMT[c["fmt"]]
            if calc:
                v = c["calc"].format(r=r)
                cell.value = v if v.startswith("=") else "=" + v
                cell.fill = CALC
            if c.get("wrap"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            elif c.get("fmt") in ("money", "money0", "jours", "int", "ans", "nb", "dec1", "pct"):
                cell.alignment = Alignment(horizontal="right")
        rng = f"{L}{DEB}:{L}{DEB + n - 1}"
        if c.get("liste"):
            liste(ws, c["liste"], rng)
        if c.get("fmt") == "jours":
            alerte_jours(ws, rng)
    ws.row_dimensions[4].height = 42
    ws.freeze_panes = ws.cell(row=DEB, column=3)
    ws.auto_filter.ref = f"B4:{get_column_letter(1 + len(colonnes))}{DEB + n - 1}"
    for k, valeurs in enumerate(prerempli or []):
        for i, v in enumerate(valeurs):
            if v is not None and not colonnes[i].get("calc"):
                ws.cell(row=DEB + k, column=2 + i, value=v)
    if exemple:
        r = DEB + len(prerempli or [])
        for i, v in enumerate(exemple):
            if v is not None and not colonnes[i].get("calc"):
                cell = ws.cell(row=r, column=2 + i, value=v)
                cell.font = f(italic=True, color=EXEMPLE)
        ws.cell(row=r, column=2).comment = Comment("Ligne d'exemple fictive (texte bleu italique) : la remplacer ou la supprimer.", "Progim")
    mise_en_page(ws)
    ws._n = n
    return ws


def plage(feuille, col, n):
    return f"'{feuille}'!${col}${DEB}:${col}${DEB + n - 1}"


JR = lambda d: f'IF({d}{{r}}="","",{d}{{r}}-Aujourdhui)'

# ---- Intégration (section 5 : documents reçus et suivi des informations manquantes)
P0, P1, P2, P3 = LISTES["L_Phase"]
PR, AG, PA, VI, PI = LISTES["L_Source"]
INTEG = [
    # (section, élément, source, phase, consigné dans)
    ("Mandat", "Convention de gestion signée et date de prise en charge", PR, P0, "Fiche"),
    ("Mandat", "Nom légal, NEQ, numéros de TPS et TVQ, structure de propriété", PR, P0, "Fiche"),
    ("Mandat", "Signataires et personnes autorisées (dépenses, rapports, copies)", PR, P0, "Fiche"),
    ("Mandat", "Seuils d'autorisation et procédure en cas d'urgence", PR, P0, "Fiche"),
    ("Mandat", "Rencontre vision : objectifs, priorités, irritants, préférences de communication", PR, P1, "Vision"),
    ("Mandat", "Coordonnées des conseillers (comptable, fiscaliste, avocat, courtiers)", PR, P1, "Fiche"),
    ("Location", "Baux", AG, P0, "Unités"),
    ("Location", "Registre des loyers", AG, P0, "Unités"),
    ("Location", "États de compte locataires", AG, P0, "Hopem"),
    ("Location", "Liste des dépôts / avances", AG, P0, "Hopem"),
    ("Location", "Historique des arrérages et ententes de paiement", AG, P0, "Dossiers"),
    ("Location", "Dossiers TAL", AG, P0, "Dossiers"),
    ("Location", "Avis de modification envoyés et réponses reçues", AG, P0, "Unités"),
    ("Location", "Unités vacantes, avis de départ et annonces en cours", AG, P0, "Unités"),
    ("Location", "Clauses particulières, ententes verbales, rabais en vigueur", AG, P1, "Vision"),
    ("Finances", "Budget", PA, P1, "Finances"),
    ("Finances", "États financiers", PR, P1, "Finances"),
    ("Finances", "Conciliations bancaires", AG, P0, "Hopem"),
    ("Finances", "Balance de vérification et comptes à payer ouverts à la date du transfert", AG, P0, "Hopem"),
    ("Finances", "Factures récurrentes et paiements préautorisés", AG, P0, "Contrats"),
    ("Finances", "Comptes bancaires et changement des signataires", PR, P0, "Finances"),
    ("Finances", "Informations hypothécaires", PR, P1, "Finances"),
    ("Finances", "Taxes municipales et scolaires (comptes, échéances, solde)", PR, P0, "Taxes"),
    ("Finances", "Comptes de services publics (électricité, gaz, eau)", AG, P0, "Contrats"),
    ("Contrats", "Contrats fournisseurs", AG, P0, "Contrats"),
    ("Contrats", "Concierge : entente, horaire, rémunération, logement fourni", PA, P0, "Fiche"),
    ("Assurances", "Assurances (polices, courtier, franchises) et ajout de Progim comme assuré additionnel", PR, P0, "Assurances"),
    ("Assurances", "Historique des sinistres et réclamations en cours", PR, P1, "Sinistres"),
    ("Assurances", "Mises en demeure, poursuites, avis d'infraction", PA, P0, "Dossiers"),
    ("Bâtiment", "Plans", PR, P1, "Documents"),
    ("Bâtiment", "Garanties", PA, P1, "Équipements"),
    ("Bâtiment", "Rapports d'inspection", PR, P1, "Documents"),
    ("Bâtiment", "Rapports de travaux et travaux en cours", PA, P0, "Projets"),
    ("Bâtiment", "Liste des équipements", AG, P1, "Équipements"),
    ("Bâtiment", "Calendrier d'entretien préventif et rapports d'inspection obligatoires", AG, P1, "Entretien"),
    ("Bâtiment", "Bons de travail ouverts et demandes de locataires non réglées", AG, P0, "Actions"),
    ("Bâtiment", "Registre amiante (immeuble construit avant 1999)", PR, P1, "Documents"),
    ("Accès", "Registre des clés et remise des clés", AG, P0, "Bâtiment"),
    ("Accès", "Codes d'accès : transfert par un canal sécurisé (jamais inscrits dans ce fichier)", AG, P0, "Bâtiment"),
    ("Connaissance", "Rencontre de transfert : particularités, pièges techniques, procédures d'urgence", AG, P0, "Bâtiment"),
    ("Connaissance", "Exceptions et règles particulières du client et de l'immeuble", PA, P0, "Exceptions"),
    ("Visite", "Visite complète, y compris les locaux techniques", VI, P0, "Bâtiment"),
    ("Visite", "Photos des aires communes et des équipements à la prise en charge", VI, P0, "SharePoint"),
    ("Visite", "Relevés des compteurs (si refacturation)", VI, P0, "SharePoint"),
    ("Mise en place", "Entité et immeuble créés dans Hopem; baux importés", PI, P0, "Hopem"),
    ("Mise en place", "Dossier SharePoint créé et documents déposés", PI, P0, "SharePoint"),
    ("Mise en place", "Avis aux locataires : nouveau gestionnaire, coordonnées, paiement du loyer", PI, P0, "Documents"),
    ("Mise en place", "Avis aux fournisseurs : facturation et coordonnées", PI, P0, "Contrats"),
    ("Mise en place", "Ajout aux processus Progim (rapports mensuels, fin d'exercice)", PI, P1, "Hopem"),
]
N_INT = 120
integ = table("Intégration", "Intégration — documents et informations à obtenir", [
    dict(nom="No", larg=5, fmt="int"),
    dict(nom="Section", larg=13),
    dict(nom="Élément", larg=54, wrap=True),
    dict(nom="Source", larg=22, liste="L_Source"),
    dict(nom="Phase", larg=22, liste="L_Phase"),
    dict(nom="Applicable", larg=9, liste="L_OuiNon", aide="Mettre Non si l'élément ne s'applique pas : il sort du calcul d'avancement."),
    dict(nom="Statut", larg=12, liste="L_StatutInt"),
    dict(nom="Responsable", larg=13),
    dict(nom="Date demandée", larg=11, fmt="date"),
    dict(nom="Échéance", larg=11, fmt="date"),
    dict(nom="Reçu le", larg=11, fmt="date"),
    dict(nom="Consigné dans", larg=13, liste="L_Onglet", aide="Onglet ou système où l'information est inscrite une fois reçue."),
    dict(nom="Notes", larg=28, wrap=True),
    dict(nom="Jours en attente", larg=9, fmt="int", calc='IF(AND(H{r}="Demandé",ISNUMBER(J{r})),Aujourdhui-J{r},"")',
         aide="Jours depuis la demande tant que le statut est Demandé. Orange au délai de relance, rouge au double."),
    dict(nom="Jours avant échéance", larg=9, fmt="jours",
         calc='IF(OR(K{r}="",G{r}="Non",H{r}="Reçu",H{r}="Intégré",H{r}="Non disponible"),"",K{r}-Aujourdhui)'),
], N_INT, note="Filtrer Source sur Propriétaire ou Ancien gestionnaire pour obtenir la liste à envoyer. "
               "Statut : À demander › Demandé › Reçu › Intégré.",
    prerempli=[(i + 1, a, b, c, d, None, "À demander", None, None, None, None, e) for i, (a, b, c, d, e) in enumerate(INTEG)])
regle(integ, f"O{DEB}:O{DEB + N_INT - 1}", f"AND(ISNUMBER(O{DEB}),O{DEB}>=2*DelaiRelance)", BLOQUE_PALE, BLOQUE)
regle(integ, f"O{DEB}:O{DEB + N_INT - 1}", f"AND(ISNUMBER(O{DEB}),O{DEB}>=DelaiRelance)", SPECIAL, ORANGE_TXT)
regle(integ, f"H{DEB}:H{DEB + N_INT - 1}", f'OR(H{DEB}="Reçu",H{DEB}="Intégré")', OK_PALE, OK, gras=False)
integ.conditional_formatting.add(f"B{DEB}:N{DEB + N_INT - 1}", FormulaRule(formula=[f'$G{DEB}="Non"'], font=Font(color=PALE)))
for c_, v in (("G5", "Oui"), ("H5", "Reçu"), ("I5", "Initiales"), ("J5", date(2026, 10, 20)), ("K5", date(2026, 10, 30)),
              ("L5", date(2026, 10, 24))):
    integ[c_] = v
    integ[c_].font = f(italic=True, color=EXEMPLE)
integ["B5"].comment = Comment("Ligne d'exemple : colonnes de suivi en texte bleu italique.", "Progim")

# ---- Plan 90 jours (sections 31 et 32)
PLAN = [
    ("0 à 30 jours", ["Tous les documents reçus", "Baux importés", "Locataires validés", "Comptes bancaires configurés",
                      "Fournisseurs configurés", "Assurances validées", "Hypothèque validée", "Taxes validées",
                      "Contrats recensés", "Accès récupérés", "Immeuble inspecté", "Risques urgents identifiés",
                      "Exceptions documentées", "Vision propriétaire documentée"]),
    ("31 à 60 jours", ["Budget validé", "Contrats principaux analysés", "Entretien préventif structuré", "Plan locatif validé",
                       "Opportunités initiales identifiées", "Travaux prioritaires planifiés", "KPI disponibles",
                       "Processus de reporting confirmé"]),
    ("61 à 90 jours", ["Diagnostic complet finalisé", "Plan de succès client validé", "Plan d'action annuel établi",
                       "Priorités 12 mois confirmées", "Opportunités classées", "Risques majeurs traités ou planifiés",
                       "Intégration officiellement clôturée"]),
    ("Critères de clôture", ["Progim comprend les objectifs du propriétaire", "Les informations financières principales sont validées",
                             "Les baux et revenus sont validés", "Les principaux contrats sont connus",
                             "Les risques importants sont identifiés", "Les accès critiques sont fonctionnels",
                             "Les exceptions sont documentées", "Les responsabilités sont attribuées",
                             "Les priorités 90 jours sont définies", "Les obligations récurrentes sont enregistrées",
                             "Le propriétaire sait comment Progim communiquera et décidera",
                             "Le gestionnaire peut gérer le mandat sans dépendre de la mémoire de l'ancien gestionnaire ou du propriétaire"]),
]
rows_plan = [(ph, e) for ph, etapes in PLAN for e in etapes]
N_PLAN = len(rows_plan)
plan = table("Plan 90 jours", "Plan d'intégration 30 / 60 / 90 jours et critères de clôture", [
    dict(nom="Phase", larg=18), dict(nom="Étape", larg=70, wrap=True), dict(nom="Fait", larg=7, liste="L_OuiNon"),
    dict(nom="Date", larg=11, fmt="date"), dict(nom="Responsable", larg=14), dict(nom="Notes", larg=36, wrap=True),
], N_PLAN, note="Sections 31 et 32 du modèle. Le mandat est intégré quand tous les critères de clôture sont à Oui.",
    prerempli=rows_plan)
regle(plan, f"D{DEB}:D{DEB + N_PLAN - 1}", f'D{DEB}="Oui"', OK_PALE, OK)
PLAN_RNG = (plage("Plan 90 jours", "B", N_PLAN), plage("Plan 90 jours", "D", N_PLAN))
# synthèse par phase, à droite
plan.column_dimensions["H"].width = 3
plan.column_dimensions["I"].width = 22
plan.column_dimensions["J"].width = 12
plan["I4"], plan["J4"] = "Phase", "Avancement"
for c_ in ("I4", "J4"):
    plan[c_].font, plan[c_].fill, plan[c_].border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
for k, (ph, _) in enumerate(PLAN):
    r = 5 + k
    plan[f"I{r}"] = ph
    plan[f"J{r}"] = (f'=IFERROR(COUNTIFS({PLAN_RNG[0]},I{r},{PLAN_RNG[1]},"Oui")/COUNTIF({PLAN_RNG[0]},I{r}),0)')
    plan[f"J{r}"].number_format, plan[f"J{r}"].fill = FMT["pct"], CALC
    for c_ in (f"I{r}", f"J{r}"):
        plan[c_].border = BORD
        plan[c_].font = f(bold=c_.startswith("I"))

# ---- Unités (section 10, registre locatif)
N_UNI = 200
table("Unités", "Locataires et baux — registre locatif", [
    dict(nom="No d'unité", larg=9, fmt="text"),
    dict(nom="Type", larg=12, liste="L_TypeUnite"),
    dict(nom="Étage", larg=6),
    dict(nom="Superficie (pi²)", larg=10, fmt="int"),
    dict(nom="Statut", larg=13, liste="L_StatutUnite"),
    dict(nom="Locataire(s)", larg=24),
    dict(nom="Téléphone", larg=14),
    dict(nom="Courriel", larg=24),
    dict(nom="Début du bail", larg=11, fmt="date"),
    dict(nom="Fin du bail", larg=11, fmt="date", aide="Vide pour un bail à durée indéterminée."),
    dict(nom="Loyer mensuel ($)", larg=12, fmt="money"),
    dict(nom="Loyer potentiel ($)", larg=12, fmt="money", aide="Loyer de marché estimé : sert au calcul du revenu potentiel."),
    dict(nom="Chauffage inclus", larg=9, liste="L_OuiNon"),
    dict(nom="Électricité incluse", larg=9, liste="L_OuiNon"),
    dict(nom="Stationnement / rangement", larg=13),
    dict(nom="Notes", larg=24, wrap=True),
    dict(nom="Jours avant fin du bail", larg=10, fmt="jours", calc=JR("K")),
    dict(nom="Avis de modification : à partir du", larg=12, fmt="date",
         calc='IF(OR(J{r}="",K{r}=""),"",IF(EDATE(J{r},12)<=K{r}+1,EDATE(K{r},-6),EDATE(K{r},-2)))',
         aide="Art. 1942 C.c.Q. : avis entre 3 et 6 mois avant la fin d'un bail de 12 mois ou plus; entre 1 et 2 mois "
              "pour un bail de moins de 12 mois. Logement résidentiel seulement."),
    dict(nom="Avis de modification : au plus tard le", larg=12, fmt="date",
         calc='IF(OR(J{r}="",K{r}=""),"",IF(EDATE(J{r},12)<=K{r}+1,EDATE(K{r},-3),EDATE(K{r},-1)))'),
    dict(nom="Jours avant date limite de l'avis", larg=10, fmt="jours", calc=JR("T")),
], N_UNI, note="Une ligne par unité, stationnement ou rangement loué. Si le registre est tenu dans Hopem, y mettre au minimum "
               "les unités, statuts, loyers et fins de bail.",
    exemple=["101", "4½", "1", 850, "Occupé", "Locataire Exemple", "819 555-0101", "locataire@exemple.com",
             date(2026, 7, 1), date(2027, 6, 30), 1250, 1395, "Non", "Non", "Ext. no 4", "Exemple"])

# ---- Dossiers (sections 10 et 13 : locataires à risque, TAL, juridique)
N_DOS = 80
table("Dossiers", "Dossiers sensibles, TAL et juridiques", [
    dict(nom="Logement / dossier", larg=13),
    dict(nom="Type", larg=18, liste="L_TypeDossier"),
    dict(nom="Situation", larg=40, wrap=True),
    dict(nom="Date d'ouverture", larg=11, fmt="date"),
    dict(nom="Statut", larg=16, liste="L_StatutLegal"),
    dict(nom="Prochaine action", larg=34, wrap=True),
    dict(nom="Responsable", larg=13),
    dict(nom="Prochaine échéance", larg=11, fmt="date"),
    dict(nom="No de dossier TAL ou de cour", larg=14, fmt="text"),
    dict(nom="Jours avant échéance", larg=10, fmt="jours", calc='IF(OR(I{r}="",F{r}="Fermé"),"",I{r}-Aujourdhui)'),
], N_DOS, note="Faits et actions seulement, aucune opinion sur les personnes (Loi 25). Accès réservé à l'équipe Progim.",
    exemple=["203", "Arrérages", "Deux mois de retard; entente de paiement proposée", date(2026, 10, 5), "Ouvert",
             "Relance si le versement du 1er n'est pas reçu", "Initiales", date(2026, 12, 2)])

# ---- Assurances (section 9)
N_ASS = 20
table("Assurances", "Assurances", [
    dict(nom="Couverture", larg=20, liste="L_Couverture"),
    dict(nom="Assureur", larg=18), dict(nom="Courtier", larg=18), dict(nom="Numéro de police", larg=14, fmt="text"),
    dict(nom="Montant assuré ($)", larg=13, fmt="money0"), dict(nom="Franchise ($)", larg=11, fmt="money0"),
    dict(nom="Prime annuelle ($)", larg=12, fmt="money0"),
    dict(nom="Début", larg=11, fmt="date"), dict(nom="Date de renouvellement", larg=11, fmt="date"),
    dict(nom="Progim assuré additionnel", larg=10, liste="L_OuiNon"),
    dict(nom="Exclusions importantes", larg=28, wrap=True),
    dict(nom="Contact réclamation", larg=22),
    dict(nom="Jours avant renouvellement", larg=11, fmt="jours", calc=JR("J")),
], N_ASS, note="Une ligne par couverture (biens, responsabilité, bris d'équipement, refoulement, inondation…). "
               "Historique des réclamations : onglet Sinistres.",
    exemple=["Biens", "Assureur Exemple", "Courtier Exemple", "POL-000000", 4500000, 10000, 18500, date(2026, 1, 1),
             date(2026, 12, 31), "Oui", "Valeur à neuf; exclut les dommages graduels", "819 555-0102"])

# ---- Taxes (section 8)
N_TAX = 30
tax = table("Taxes", "Taxes et évaluation foncière", [
    dict(nom="Type", larg=14, liste="L_TypeTaxe"), dict(nom="Année", larg=7, fmt="int"),
    dict(nom="Montant annuel ($)", larg=13, fmt="money"), dict(nom="Versement no", larg=9, fmt="int"),
    dict(nom="Échéance", larg=11, fmt="date"), dict(nom="Montant du versement ($)", larg=13, fmt="money"),
    dict(nom="Mode de paiement", larg=13), dict(nom="Numéro de compte", larg=14, fmt="text"),
    dict(nom="Payé", larg=7, liste="L_OuiNon"), dict(nom="Date du paiement", larg=11, fmt="date"),
    dict(nom="Jours avant échéance", larg=10, fmt="jours", calc='IF(OR(F{r}="",J{r}="Oui"),"",F{r}-Aujourdhui)'),
], N_TAX, note="Une ligne par versement. Un versement payé (Payé = Oui) sort des alertes.",
    exemple=["Municipale", 2026, 42000, 1, date(2026, 3, 1), 14000, "Prélèvement", "000000", "Oui", date(2026, 2, 25)])
tax.column_dimensions["N"].width, tax.column_dimensions["O"].width, tax.column_dimensions["P"].width = 3, 30, 15
tax["O4"] = "ÉVALUATION FONCIÈRE"
tax["O4"].font = f(bold=True, color=ORANGE_TXT)
for k, (lib, val, fm) in enumerate([("Rôle d'évaluation (années)", "2026-2028", "text"), ("Valeur du terrain ($)", 1200000, "money0"),
                                    ("Valeur du bâtiment ($)", 5300000, "money0"), ("Valeur totale ($)", "=SUM(P6:P7)", "money0"),
                                    ("Date limite de demande de révision", None, "date")]):
    r = 5 + k
    tax[f"O{r}"] = lib
    tax[f"O{r}"].font = f(bold=True)
    tax[f"P{r}"] = val
    tax[f"P{r}"].border, tax[f"P{r}"].number_format = BORD, FMT[fm]
    is_f = isinstance(val, str) and val.startswith("=")
    tax[f"P{r}"].font = f() if is_f else f(italic=True, color=EXEMPLE)
    if is_f:
        tax[f"P{r}"].fill = CALC

# ---- Contrats (sections 15 et 21)
N_CON = 50
CATS_PRE = ["Plomberie", "Électricité", "Chauffage", "Nettoyage", "Déneigement", "Paysagement", "Ascenseur", "Extermination",
            "Sécurité", "Protection incendie", "Utilité – électricité", "Utilité – gaz", "Utilité – eau", "Internet", "Téléphonie"]
con = table("Contrats", "Fournisseurs, contrats et utilités", [
    dict(nom="Catégorie", larg=19, liste="L_CatContrat"), dict(nom="Fournisseur", larg=20),
    dict(nom="Contact", larg=18), dict(nom="Téléphone", larg=13), dict(nom="Courriel", larg=20),
    dict(nom="Contrat ou numéro de compte", larg=14, fmt="text"),
    dict(nom="Début", larg=11, fmt="date"), dict(nom="Échéance", larg=11, fmt="date"),
    dict(nom="Coût annuel ($ avant taxes)", larg=12, fmt="money0"), dict(nom="Paiement", larg=12),
    dict(nom="Renouvellement automatique", larg=11, liste="L_OuiNon"),
    dict(nom="Préavis de non-renouvellement (jours)", larg=12, fmt="int"),
    dict(nom="À revoir", larg=8, liste="L_OuiNon", aide="Section 15 : contrats à revoir (prix, qualité, conditions)."),
    dict(nom="Commentaires", larg=26, wrap=True),
    dict(nom="Date limite du préavis", larg=11, fmt="date", calc='IF(I{r}="","",I{r}-N(M{r}))'),
    dict(nom="Jours avant date limite", larg=10, fmt="jours", calc=JR("P")),
    dict(nom="Clé (ne pas modifier)", larg=8, cache=True, calc='IF(C{r}="","",N(J{r})+ROW()/1000000)'),
], N_CON, note="La date à surveiller est la date limite du préavis : passée cette date, un contrat à renouvellement automatique "
               "se renouvelle. Indiquer aussi les fournisseurs à éviter et pourquoi, dans Commentaires.",
    prerempli=[(c,) for c in CATS_PRE])
for i, v in enumerate(["Déneigement Exemple inc.", "Nom", "819 555-0103", "info@exemple.com", "C-2026-01", date(2026, 11, 1),
                       date(2027, 4, 30), 9800, "Chèque", "Oui", 60, "Non", "Exemple"]):
    cell = con.cell(row=9, column=3 + i, value=v)
    cell.font = f(italic=True, color=EXEMPLE)
con["B9"].comment = Comment("Ligne d'exemple fictive (texte bleu italique).", "Progim")

# ---- Entretien (section 17)
ENTRETIEN = [
    ("Façade", "Vérification par un ingénieur ou un architecte (5 étages ou plus hors sol)", "Réglementaire", "RBQ, Code de sécurité, ch. VIII", 60),
    ("Stationnement étagé", "Vérification de la structure par un ingénieur", "Réglementaire", "RBQ, Code de sécurité, ch. VIII", 60),
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
    ("Génératrice d'urgence", "Essai sous charge et entretien", "Réglementaire", "CSA C282", 12),
    ("Chaudière / chauffage", "Entretien annuel", "Assurance", "Fabricant", 12),
    ("Panneaux électriques", "Thermographie infrarouge", "Assurance", "Assureur", 36),
    ("Toiture", "Inspection visuelle et rapport", "Recommandée", "", 12),
    ("Drains de toit et gouttières", "Nettoyage", "Recommandée", "", 6),
    ("Chauffe-eau", "Vérification (fuites, soupape)", "Recommandée", "Fabricant", 12),
    ("Ventilation / échangeurs d'air", "Remplacement des filtres", "Recommandée", "Fabricant", 3),
    ("Puisard et pompe submersible", "Vérification et essai", "Recommandée", "", 6),
    ("Drain de fondation", "Inspection par caméra", "Recommandée", "", 60),
    ("Logements", "Inspection préventive", "Recommandée", "", 12),
    ("Extermination", "Traitement préventif", "Recommandée", "", 3),
]
N_ENT = 50
ent = table("Entretien", "Entretien préventif et inspections", [
    dict(nom="Équipement / élément", larg=26), dict(nom="Tâche", larg=38, wrap=True),
    dict(nom="Exigence", larg=12, liste="L_Exigence"), dict(nom="Référence", larg=22),
    dict(nom="Fréquence (mois)", larg=9, fmt="int"),
    dict(nom="Applicable", larg=9, liste="L_OuiNon", aide="Non : la ligne sort des alertes (ex. pas d'ascenseur)."),
    dict(nom="Fournisseur", larg=18), dict(nom="Responsable", larg=13),
    dict(nom="Dernier entretien", larg=11, fmt="date"), dict(nom="Rapport (lien)", larg=18),
    dict(nom="Prochain", larg=11, fmt="date", calc='IF(OR(J{r}="",F{r}="",G{r}="Non"),"",EDATE(J{r},F{r}))'),
    dict(nom="Jours restants", larg=9, fmt="jours", calc=JR("L")),
], N_ENT, note="Liste de départ indicative : fréquences et références à valider avec les fournisseurs et la réglementation "
               "en vigueur pour cet immeuble.", prerempli=[e + (None,) for e in ENTRETIEN])
ent["G5"], ent["G6"] = "Non", "Non"
for c_, v in (("G7", "Oui"), ("H7", "Protection incendie Exemple"), ("J7", date(2025, 12, 15))):
    ent[c_] = v
for c_ in ("G5", "G6", "G7", "H7", "J7"):
    ent[c_].font = f(italic=True, color=EXEMPLE)

# ---- Équipements
N_EQU = 50
table("Équipements", "Registre des équipements", [
    dict(nom="Équipement", larg=22), dict(nom="Emplacement", larg=16), dict(nom="Marque", larg=13), dict(nom="Modèle", larg=13),
    dict(nom="No de série", larg=13, fmt="text"), dict(nom="Année d'installation", larg=10, fmt="int"),
    dict(nom="Durée de vie utile (ans)", larg=10, fmt="int"), dict(nom="Fin de garantie", larg=11, fmt="date"),
    dict(nom="Installateur", larg=16), dict(nom="Coût de remplacement estimé ($)", larg=13, fmt="money0"),
    dict(nom="Manuel (lien)", larg=16), dict(nom="Notes", larg=22, wrap=True),
    dict(nom="Fin de vie estimée", larg=9, fmt="int", calc='IF(OR(G{r}="",H{r}=""),"",G{r}+H{r})'),
    dict(nom="Années restantes", larg=9, fmt="ans", calc='IF(N{r}="","",N{r}-YEAR(Aujourdhui))'),
    dict(nom="Jours avant fin de garantie", larg=10, fmt="jours", calc=JR("I")),
], N_EQU, note="Sert à planifier les remplacements (CAPEX, onglet Projets).",
    exemple=["Chaudière principale", "Salle mécanique", "Marque", "Modèle", "SN000000", 2015, 25, date(2027, 6, 1),
             "Installateur Exemple", 85000, None, "Exemple"])
eq = wb["Équipements"]
regle(eq, f"O{DEB}:O{DEB + N_EQU - 1}", f"AND(ISNUMBER(O{DEB}),O{DEB}<=0)", BLOQUE_PALE, BLOQUE)
regle(eq, f"O{DEB}:O{DEB + N_EQU - 1}", f"AND(ISNUMBER(O{DEB}),O{DEB}<=3)", SPECIAL, ORANGE_TXT)

# ---- Projets (section 18)
N_PRO = 60
pro = table("Projets", "Travaux et CAPEX", [
    dict(nom="Projet", larg=34, wrap=True), dict(nom="Statut", larg=10, liste="L_StatutProjet"),
    dict(nom="Priorité", larg=9, liste="L_Priorite"), dict(nom="Année ou horizon", larg=10),
    dict(nom="Budget ($)", larg=12, fmt="money0"), dict(nom="Dépensé ($)", larg=12, fmt="money0"),
    dict(nom="Échéance", larg=11, fmt="date"), dict(nom="Responsable", larg=13),
    dict(nom="Garantie", larg=14), dict(nom="Impact", larg=24, wrap=True), dict(nom="Commentaires", larg=24, wrap=True),
    dict(nom="Reste au budget ($)", larg=12, fmt="money0", calc='IF(F{r}="","",F{r}-N(G{r}))'),
    dict(nom="Jours avant échéance", larg=10, fmt="jours",
         calc='IF(OR(H{r}="",C{r}="Réalisé",C{r}="Annulé"),"",H{r}-Aujourdhui)'),
    dict(nom="Clé (ne pas modifier)", larg=8, cache=True,
         calc='IF(OR(B{r}="",C{r}="Réalisé",C{r}="Annulé"),"",N(F{r})+ROW()/1000000)'),
], N_PRO, note="Section 18 : un seul tableau pour les travaux en cours (En cours), réalisés (Réalisé) et prévus (Prévu). "
               "Règles d'autorisation : onglet Fiche.",
    exemple=["Remplacement de la toiture, section nord", "Prévu", "Haute", "2027", 120000, None, date(2027, 6, 30),
             "Initiales", "10 ans (couvreur)", "Fin des infiltrations au 4e étage", "Exemple"])
regle(pro, f"M{DEB}:M{DEB + N_PRO - 1}", f"AND(ISNUMBER(M{DEB}),M{DEB}<0)", BLOQUE_PALE, BLOQUE)

# ---- Sinistres (section 19)
table("Sinistres", "Sinistres et incidents", [
    dict(nom="Date", larg=11, fmt="date"), dict(nom="Type", larg=16, liste="L_TypeSinistre"),
    dict(nom="Description", larg=46, wrap=True), dict(nom="Unités touchées", larg=12),
    dict(nom="Assurance", larg=10, liste="L_OuiNon", aide="Réclamation à l'assureur : Oui ou Non."),
    dict(nom="No de réclamation", larg=14, fmt="text"),
    dict(nom="Coût ($)", larg=12, fmt="money0"), dict(nom="Statut", larg=16, liste="L_StatutSinistre"),
    dict(nom="Cause et mesure préventive", larg=34, wrap=True),
], 50, note="Section 19. Les risques récurrents qui en découlent vont dans l'onglet Risques.",
    exemple=[date(2025, 3, 12), "Refoulement", "Refoulement au sous-sol lors d'une pluie abondante", "Sous-sol", "Oui",
             "R-0000", 18000, "Fermé", "Clapet antiretour remplacé"])

# ---- Exceptions (section 24)
N_EXC = 50
exc = table("Exceptions", "Registre des exceptions client / immeuble", [
    dict(nom="Sujet", larg=20), dict(nom="Exception / règle", larg=46, wrap=True), dict(nom="Pourquoi", larg=34, wrap=True),
    dict(nom="Responsable", larg=13), dict(nom="Fréquence", larg=12), dict(nom="Dernière validation", larg=11, fmt="date"),
    dict(nom="Jours depuis la validation", larg=10, fmt="int", calc='IF(G{r}="","",Aujourdhui-G{r})',
         aide="Rouge au-delà de l'intervalle de révision (onglet Paramètres) : à revalider."),
], N_EXC, note="Section critique : toute règle ou particularité qui serait oubliée si le gestionnaire principal était absent "
               "(répartition de dépense, année fiscale, rapport particulier, fournisseur imposé, modalité bancaire…).",
    exemple=["Travaux", "Aviser le propriétaire avant tout travail dans les aires communes, peu importe le montant",
             "Demande du propriétaire, à la suite d'un conflit avec l'ancien gestionnaire", "Gestionnaire", "Chaque fois",
             date(2026, 11, 1)])
regle(exc, f"H{DEB}:H{DEB + N_EXC - 1}", f"AND(ISNUMBER(H{DEB}),H{DEB}>DelaiRevision)", BLOQUE_PALE, BLOQUE)
regle(exc, f"B{DEB}:G{DEB + N_EXC - 1}", f'AND($B{DEB}<>"",$G{DEB}="")', SPECIAL, ORANGE_TXT, gras=False)

# ---- Décisions (section 25)
table("Décisions", "Décisions importantes", [
    dict(nom="Date", larg=11, fmt="date"), dict(nom="Décision", larg=44, wrap=True), dict(nom="Contexte", larg=36, wrap=True),
    dict(nom="Décideur", larg=16), dict(nom="Impact", larg=28, wrap=True), dict(nom="À revoir le", larg=11, fmt="date"),
    dict(nom="Jours avant révision", larg=10, fmt="jours", calc=JR("G")),
], 100, note="Section 25 : historique des décisions significatives, pour que le remplaçant sache ce qui a été décidé, par qui et pourquoi.",
    exemple=[date(2026, 11, 10), "Reporter le remplacement des fenêtres à 2028", "Priorité donnée à la toiture",
             "Propriétaire", "Budget CAPEX 2027 réduit de 60 000 $", date(2027, 9, 1)])

# ---- Risques (section 26)
N_RIS = 50
ris = table("Risques", "Risques", [
    dict(nom="Risque", larg=40, wrap=True), dict(nom="Catégorie", larg=13, liste="L_CatRisque"),
    dict(nom="Probabilité", larg=11, liste="L_Proba"), dict(nom="Impact", larg=10, liste="L_Impact"),
    dict(nom="Action", larg=38, wrap=True), dict(nom="Responsable", larg=13), dict(nom="Statut", larg=13, liste="L_StatutRisque"),
    dict(nom="Échéance de l'action", larg=11, fmt="date"),
    dict(nom="Cote (1 à 9)", larg=8, fmt="int",
         calc='IF(OR(D{r}="",E{r}=""),"",IFERROR(MATCH(D{r},L_Proba,0)*MATCH(E{r},L_Impact,0),""))',
         aide="Probabilité × impact (1 = faible, 3 = élevé). 6 et plus : rouge."),
    dict(nom="Clé (ne pas modifier)", larg=8, cache=True, calc='IF(OR(B{r}="",H{r}="Fermé"),"",N(J{r})+ROW()/1000000)'),
], N_RIS, note="Section 26. Catégories : financier, locatif, physique, légal, assurance, sécurité, réputation, opérationnel.",
    exemple=["Infiltrations d'eau par la toiture, section nord", "Physique", "Élevée", "Élevé", "Remplacement planifié (onglet Projets)",
             "Gestionnaire", "En traitement", date(2027, 6, 30)])
regle(ris, f"J{DEB}:J{DEB + N_RIS - 1}", f"AND(ISNUMBER(J{DEB}),J{DEB}>=6)", BLOQUE_PALE, BLOQUE)
regle(ris, f"J{DEB}:J{DEB + N_RIS - 1}", f"AND(ISNUMBER(J{DEB}),J{DEB}>=3)", SPECIAL, ORANGE_TXT)

# ---- Opportunités (section 27)
N_OPP = 50
opp = table("Opportunités", "Opportunités de création de valeur", [
    dict(nom="Opportunité", larg=38, wrap=True), dict(nom="Type", larg=20, liste="L_TypeOpp"),
    dict(nom="Impact potentiel ($ / an)", larg=13, fmt="money0"), dict(nom="Investissement ($)", larg=13, fmt="money0"),
    dict(nom="Priorité", larg=9, liste="L_Priorite"), dict(nom="Responsable", larg=13),
    dict(nom="Statut", larg=12, liste="L_StatutOpp"), dict(nom="Notes", larg=28, wrap=True),
    dict(nom="Retour sur l'investissement (années)", larg=12, fmt="dec1",
         calc='IF(OR(D{r}="",N(D{r})=0,E{r}=""),"",E{r}/D{r})'),
    dict(nom="Clé (ne pas modifier)", larg=8, cache=True,
         calc='IF(OR(B{r}="",H{r}="Réalisée",H{r}="Abandonnée"),"",N(D{r})+ROW()/1000000)'),
], N_OPP, note="Section 27. Impact en revenu ou en économie annuelle; le retour se calcule seul.",
    exemple=["Louer les 8 stationnements extérieurs non attribués", "Stationnements", 5760, 1500, "Haute", "Coordonnateur location",
             "Approuvée", "60 $ par mois par espace"])

# ---- KPI (section 28, à l'échelle de l'immeuble)
N_KPI = 36
kpi = table("KPI", "KPI mensuels de l'immeuble", [
    dict(nom="Mois", larg=9, fmt="mois", aide="Inscrire le 1er du mois (ex. 2026-10-01)."),
    dict(nom="Montant facturé ($)", larg=12, fmt="money0"), dict(nom="Montant collecté ($)", larg=12, fmt="money0"),
    dict(nom="Arrérages totaux ($)", larg=12, fmt="money0"), dict(nom="Arrérages > 30 j ($)", larg=11, fmt="money0"),
    dict(nom="Arrérages > 60 j ($)", larg=11, fmt="money0"), dict(nom="Arrérages > 90 j ($)", larg=11, fmt="money0"),
    dict(nom="NOI / RNN réel ($)", larg=12, fmt="money0"), dict(nom="NOI / RNN budget ($)", larg=12, fmt="money0"),
    dict(nom="Revenu potentiel ($)", larg=12, fmt="money0"), dict(nom="Unités vacantes", larg=9, fmt="int"),
    dict(nom="Commentaire et actions", larg=34, wrap=True),
    dict(nom="Taux de perception", larg=10, fmt="pct", calc='IF(N(C{r})=0,"",D{r}/C{r})'),
    dict(nom="Écart NOI vs budget ($)", larg=12, fmt="money0", calc='IF(OR(I{r}="",J{r}=""),"",I{r}-J{r})'),
    dict(nom="Écart NOI vs budget", larg=9, fmt="pct", calc='IF(N(J{r})=0,"",(I{r}-J{r})/ABS(J{r}))'),
    dict(nom="Écart revenu potentiel ($)", larg=12, fmt="money0", calc='IF(OR(K{r}="",C{r}=""),"",K{r}-C{r})'),
], N_KPI, note="Section 28, à l'échelle de l'immeuble : une ligne par mois. La perception hebdomadaire se suit dans Hopem; "
               "les revues hebdomadaire et mensuelle se font à l'échelle du portefeuille.",
    exemple=[date(2026, 10, 1), 48500, 47200, 3900, 1300, 0, 0, 21000, 20500, 52300, 1, "Exemple"])
regle(kpi, f"N{DEB}:N{DEB + N_KPI - 1}", f"AND(ISNUMBER(N{DEB}),N{DEB}<0.97)", BLOQUE_PALE, BLOQUE)
regle(kpi, f"O{DEB}:P{DEB + N_KPI - 1}", f"AND(ISNUMBER(O{DEB}),O{DEB}<0)", BLOQUE_PALE, BLOQUE)

# ---- Actions (sections 37 et 38)
N_ACT = 150
act = table("Actions", "Prochaines actions, questions ouvertes et décisions requises", [
    dict(nom="Action", larg=50, wrap=True), dict(nom="Type", larg=15, liste="L_TypeAction"),
    dict(nom="Responsable", larg=13), dict(nom="Échéance", larg=11, fmt="date"), dict(nom="Statut", larg=10, liste="L_StatutAction"),
    dict(nom="Notes", larg=34, wrap=True),
    dict(nom="Jours avant échéance", larg=10, fmt="jours",
         calc='IF(OR(E{r}="",F{r}="Fait",F{r}="Annulé"),"",E{r}-Aujourdhui)'),
    dict(nom="Clé (ne pas modifier)", larg=8, cache=True,
         calc='IF(OR(B{r}="",C{r}<>"Décision requise",F{r}="Fait",F{r}="Annulé"),"",IF(ISNUMBER(E{r}),E{r},99999)+ROW()/1000000)'),
], N_ACT, note="Sections 37 et 38. Une question ouverte ou une décision requise est une action comme une autre : "
               "elle a un responsable et une échéance.",
    exemple=["Obtenir du propriétaire la décision sur la hausse des loyers 2027", "Décision requise", "Gestionnaire",
             date(2026, 12, 15), "À faire", "Avis à envoyer avant le 31 mars"])

# ---- Calendrier annuel (obligations récurrentes)
CAL = [
    ("01 - Janvier", "Inscrire les versements du compte de taxes municipales (onglet Taxes)"),
    ("01 - Janvier", "Début de la période d'envoi des avis de modification pour les baux se terminant le 30 juin"),
    ("02 - Février", "Remettre le relevé 31 aux locataires et le transmettre à Revenu Québec (au plus tard le dernier jour de février)"),
    ("03 - Mars", "Date limite d'envoi des avis de modification pour les baux se terminant le 30 juin (31 mars)"),
    ("04 - Avril", "Suivi des réponses des locataires aux avis de modification (délai d'un mois)"),
    ("04 - Avril", "Fin du déneigement : nettoyage du terrain, constat des dommages; inspection de la toiture et des drains"),
    ("05 - Mai", "Ouvrir les robinets extérieurs; aménagement paysager; annonces des logements libres au 1er juillet"),
    ("06 - Juin", "Planifier les déménagements du 1er juillet (ascenseur, conteneurs, stationnement)"),
    ("07 - Juillet", "Inspection des logements libérés; inscrire le compte de taxes scolaires"),
    ("08 - Août", "Planifier les travaux d'automne; soumissions de déneigement si le contrat est à renouveler"),
    ("09 - Septembre", "Entretien du système de chauffage avant la saison"),
    ("10 - Octobre", "Fermer et purger les robinets extérieurs; installation des balises de déneigement"),
    ("11 - Novembre", "Nettoyage des gouttières; budget de l'année suivante à présenter au propriétaire"),
    ("12 - Décembre", "Bilan annuel au propriétaire; révision complète du dossier maître (inscrire au journal)"),
    ("Chaque mois", "Rapport mensuel au propriétaire; KPI du mois (onglet KPI)"),
    ("Chaque mois", "Tournée de l'immeuble : aires communes et locaux techniques"),
]
table("Calendrier", "Calendrier annuel — obligations récurrentes", [
    dict(nom="Mois", larg=15, liste="L_Mois"), dict(nom="Tâche", larg=80, wrap=True), dict(nom="Responsable", larg=16),
    dict(nom="Applicable", larg=9, liste="L_OuiNon"), dict(nom="Notes propres à l'immeuble", larg=40, wrap=True),
], 60, note="Liste de départ indicative, à adapter à l'immeuble (dates de taxes de la ville, fin d'exercice, etc.).", prerempli=CAL)

# ---- Contacts
CONTACTS = [
    ("Propriétaire",), ("Gestionnaire Progim", "Gestion Immobilière Progim"), ("Concierge",), ("Plombier",), ("Électricien",),
    ("Serrurier",), ("Chauffage et climatisation",), ("Ascenseur",), ("Protection incendie",), ("Déneigement",),
    ("Assureur – réclamations",), ("Courtier d'assurance",), ("Ville – travaux publics / 311",),
    ("Panne électrique", "Hydro-Québec", None, "1 800 790-2424", "1 800 790-2424", None, "Numéro à vérifier avant usage"),
    ("Fuite de gaz", "Énergir", None, "1 800 361-8003", "1 800 361-8003", None, "Numéro à vérifier avant usage"),
    ("Avant de creuser", "Info-Excavation", None, "1 800 663-9228", None, None, "Numéro à vérifier avant usage"),
    ("Urgence (police, pompiers, ambulance)", None, None, "911", "911"),
]
table("Contacts", "Contacts et urgences", [
    dict(nom="Rôle", larg=28), dict(nom="Entreprise ou organisme", larg=24), dict(nom="Nom", larg=20),
    dict(nom="Téléphone", larg=15), dict(nom="Urgence 24 h", larg=15), dict(nom="Courriel", larg=24),
    dict(nom="Notes", larg=28, wrap=True),
], 40, prerempli=CONTACTS, note="À imprimer pour le concierge. Jamais de code d'alarme, de mot de passe ni de combinaison.")

# ---- Documents (section 23)
DOCS = [("Légal", d) for d in ("Convention de gestion", "Certificat de localisation", "Acte de vente", "Permis", "Servitudes",
                                "Déclaration de copropriété (si applicable)")] + \
       [("Financier", d) for d in ("Budget", "États financiers", "Hypothèque (acte et dernier relevé)", "Comptes de taxes",
                                    "Avis d'évaluation foncière")] + \
       [("Assurance", d) for d in ("Polices et certificats d'assurance",)] + \
       [("Technique", d) for d in ("Plans", "Garanties", "Manuels", "Rapports d'inspection", "Rapports d'ingénieur",
                                    "Registre amiante (immeuble construit avant 1999)", "Rapport de vérification de façade",
                                    "Rapports de protection incendie", "Plan des mesures d'urgence",
                                    "Fiches de données de sécurité (SIMDUT)")] + \
       [("Location", d) for d in ("Baux en vigueur", "Registre des loyers (section G du bail)", "Règlements d'immeuble",
                                   "Avis de changement de gestionnaire aux locataires")]
table("Documents", "Documentation et fichiers officiels", [
    dict(nom="Catégorie", larg=11, liste="L_CatDoc"), dict(nom="Document", larg=44), dict(nom="Statut", larg=12, liste="L_StatutDoc"),
    dict(nom="Date du document", larg=11, fmt="date"), dict(nom="Expiration ou renouvellement", larg=12, fmt="date"),
    dict(nom="Lien vers la source officielle", larg=40), dict(nom="Notes", larg=24, wrap=True),
    dict(nom="Jours restants", larg=9, fmt="jours", calc='IF(OR(F{r}="",D{r}="Sans objet"),"",F{r}-Aujourdhui)'),
], 60, prerempli=DOCS, note="Section 23. Les documents restent dans leur système source (SharePoint, Hopem); ce registre pointe vers eux.")

# ---- Journal et passation (section 34)
N_JOU = 300
jou = table("Journal", "Journal des modifications", [
    dict(nom="Date", larg=11, fmt="date"), dict(nom="Section", larg=18, liste="L_Onglet"),
    dict(nom="Modification", larg=60, wrap=True), dict(nom="Auteur", larg=14), dict(nom="Type", larg=18, liste="L_TypeJournal"),
], N_JOU, note="Section 34 : une ligne par modification significative (voir la liste des déclencheurs dans le mode d'emploi).",
    exemple=[date(2026, 11, 14), "Fiche", "Ouverture du dossier", "Initiales", "Intégration"])
PASS = ["Dossier maître révisé et à jour par le gestionnaire sortant",
        "Rencontre de passation : revue de chaque onglet, surtout Exceptions, Dossiers et Bâtiment",
        "Visite de l'immeuble ensemble (y compris les locaux techniques)",
        "Actions ouvertes revues et réassignées (onglet Actions)",
        "Échéances des 90 prochains jours revues (onglet Résumé)", "Clés et accès remis",
        "Présentation au propriétaire et au concierge", "Locataires et fournisseurs avisés au besoin",
        "Gestionnaire responsable changé dans la Fiche et dans Hopem",
        "Passation inscrite au journal; statut du dossier remis à Actif"]
for L, w in (("H", 3), ("I", 62), ("J", 8), ("K", 22)):
    jou.column_dimensions[L].width = w
jou["I3"] = "LISTE DE PASSATION — vider Fait et Notes à chaque nouvelle passation"
jou["I3"].font = f(bold=True, color=ORANGE_TXT)
for k, h in enumerate(("Étape", "Fait", "Date et notes")):
    c = jou.cell(row=4, column=9 + k, value=h)
    c.font, c.fill, c.border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
for k, t in enumerate(PASS):
    for col in (9, 10, 11):
        jou.cell(row=5 + k, column=col).border = BORD
    jou.cell(row=5 + k, column=9, value=f"{k + 1}. {t}").font = f()
liste(jou, "L_OuiNon", f"J5:J{4 + len(PASS)}")
regle(jou, f"J5:J{4 + len(PASS)}", 'J5="Oui"', OK_PALE, OK)
jou.cell(row=6 + len(PASS), column=9, value=f'="Étapes faites : "&COUNTIF(J5:J{4 + len(PASS)},"Oui")&" sur {len(PASS)}"').font = f(bold=True)

# ------------------------------------------------------------------ Résumé exécutif (section 36) et tableau de bord
res = wb.create_sheet("Résumé")
entete_feuille(res, "Résumé exécutif de l'immeuble", largeur=9)
res["B3"] = "Section 36 : se lit en moins de 5 minutes. Tout est calculé à partir des autres onglets; rien à saisir ici."
res["B3"].font = f(size=9, italic=True, color=INFO)
for L, w in zip("BCDEFGHIJ", (30, 50, 3, 40, 11, 13, 13, 12, 3)):
    res.column_dimensions[L].width = w

U = lambda col: plage("Unités", col, N_UNI)
txt = lambda ref: f'=IF({ref}="","—",{ref})'


def top(feuille, n, col_val, col_cle, k, plus_grand=True, extra=None):
    cle = plage(feuille, col_cle, n)
    val = plage(feuille, col_val, n)
    fn = "LARGE" if plus_grand else "SMALL"
    pos = f"MATCH({fn}({cle},{k}),{cle},0)"
    expr = f"INDEX({val},{pos})"
    if extra:
        expr += f'&" — "&INDEX({plage(feuille, extra, n)},{pos})'
    return f'=IFERROR({expr},"—")'


def bloc_titre(r, col, titre):
    c = res.cell(row=r, column=col, value=titre)
    c.font = f(bold=True, color=ORANGE_TXT)
    return r + 1


def ligne(r, col, lib, formule, fmt=None, gras=False):
    a = res.cell(row=r, column=col, value=lib)
    a.font, a.alignment = f(bold=True), Alignment(vertical="top")
    b = res.cell(row=r, column=col + 1, value=formule)
    b.fill, b.border, b.font = CALC, BORD, f(bold=gras)
    b.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
    if fmt:
        b.number_format = FMT[fmt]
    return r + 1


occ = f'IFERROR(COUNTIF({U("F")},"Occupé")/({REF["nb_log"]}-COUNTIF({U("F")},"Non louable")),0)'
r = 5
r = bloc_titre(r, 2, "CLIENT")
r = ligne(r, 2, "Propriétaire", txt(REF["proprio"]), gras=True)
r = ligne(r, 2, "Contact principal", f'=IF({REF["contact"]}="","—",{REF["contact"]}&IF({REF["tel_contact"]}="",""," — "&{REF["tel_contact"]}))')
r = ligne(r, 2, "Objectif principal", txt(REF["objectif"]))
r = ligne(r, 2, "Niveau de service", txt(REF["niveau"]))
r = ligne(r, 2, "Particularité majeure", txt(REF["particularites"]))
r = ligne(r, 2, "Gestionnaire responsable", txt(REF["gestionnaire"]))
r = ligne(r, 2, "Statut du dossier", txt(REF["statut_dossier"]))
r += 1
r = bloc_titre(r, 2, "IMMEUBLE")
r = ligne(r, 2, "Adresse", txt(REF["adresse"]))
r = ligne(r, 2, "Nombre de logements", f"={REF['nb_log']}", "int")
r = ligne(r, 2, "Occupation", "=" + occ, "pct")
r = ligne(r, 2, "Revenus locatifs annualisés", f"=SUM({U('L')})*12", "money0")
r = ligne(r, 2, "Revenu potentiel annualisé",
          f'=(SUMPRODUCT(--({U("M")}<>""),{U("M")})+SUMPRODUCT(--({U("M")}=""),--({U("B")}<>""),{U("L")}))*12', "money0")
res[f"B{r - 1}"].comment = Comment("Loyer potentiel de l'onglet Unités, ou loyer actuel quand le potentiel n'est pas inscrit.", "Progim")
r = ligne(r, 2, "NOI / RNN (Finances)", f'=IF({REF["rnn"]}="","—",{REF["rnn"]})', "money0")
for k in (1, 2, 3):
    r = ligne(r, 2, f"Principal contrat {k}", top("Contrats", N_CON, "B", "R", k, extra="C"))
r += 1
SECTIONS_TOP = [
    ("PRIORITÉS DU PROPRIÉTAIRE", [txt(REF[f"prio{k}"]) for k in (1, 2, 3)]),
    ("RISQUES (cote la plus élevée)", [top("Risques", N_RIS, "B", "K", k) for k in (1, 2, 3)]),
    ("OPPORTUNITÉS (impact le plus élevé)", [top("Opportunités", N_OPP, "B", "K", k) for k in (1, 2, 3)]),
    ("TRAVAUX MAJEURS (budget le plus élevé)", [top("Projets", N_PRO, "B", "O", k, extra="C") for k in (1, 2, 3)]),
    ("DÉCISIONS EN ATTENTE (échéance la plus proche)", [top("Actions", N_ACT, "B", "I", k, plus_grand=False) for k in (1, 2, 3)]),
]
for titre, formules in SECTIONS_TOP:
    r = bloc_titre(r, 2, titre)
    for k, form in enumerate(formules):
        r = ligne(r, 2, f"{k + 1}.", form)
    r += 1
# --- Tableau de bord, à droite
rb = 5
c = res.cell(row=rb, column=5, value="ÉCHÉANCES")
c.font = f(bold=True, color=ORANGE_TXT)
rb += 1
for i, h in enumerate(["Catégorie", "En retard", "≤ seuil urgent", "≤ seuil d'alerte", "Prochaine"]):
    c = res.cell(row=rb, column=5 + i, value=h)
    c.font, c.fill, c.border = f(bold=True, color="FFFFFF", size=9), fill(MARINE), BORD
    c.alignment = Alignment(horizontal="center", wrap_text=True)
rb += 1
ECH = [
    ("Fins de bail", U("R"), U("K"), ""),
    ("Avis de modification de bail (date limite)", U("U"), U("T"), ""),
    ("Dossiers sensibles et TAL", plage("Dossiers", "K", N_DOS), plage("Dossiers", "I", N_DOS), f',{plage("Dossiers","F",N_DOS)},"<>Fermé"'),
    ("Assurances", plage("Assurances", "N", N_ASS), plage("Assurances", "J", N_ASS), ""),
    ("Taxes (versements non payés)", plage("Taxes", "L", N_TAX), plage("Taxes", "F", N_TAX), f',{plage("Taxes","J",N_TAX)},"<>Oui"'),
    ("Contrats (date limite de préavis)", plage("Contrats", "Q", N_CON), plage("Contrats", "P", N_CON), ""),
    ("Entretien et inspections", plage("Entretien", "M", N_ENT), plage("Entretien", "L", N_ENT), ""),
    ("Garanties d'équipements", plage("Équipements", "P", N_EQU), plage("Équipements", "I", N_EQU), ""),
    ("Projets", plage("Projets", "N", N_PRO), plage("Projets", "H", N_PRO),
     f',{plage("Projets","C",N_PRO)},"<>Réalisé",{plage("Projets","C",N_PRO)},"<>Annulé"'),
    ("Décisions à revoir", plage("Décisions", "H", 100), plage("Décisions", "G", 100), ""),
    ("Actions", plage("Actions", "H", N_ACT), plage("Actions", "E", N_ACT),
     f',{plage("Actions","F",N_ACT)},"<>Fait",{plage("Actions","F",N_ACT)},"<>Annulé"'),
    ("Documents à renouveler", plage("Documents", "I", 60), plage("Documents", "F", 60), f',{plage("Documents","D",60)},"<>Sans objet"'),
    ("Intégration (éléments ouverts)", plage("Intégration", "P", N_INT), plage("Intégration", "K", N_INT),
     "".join(f',{plage("Intégration","H",N_INT)},"<>{v}"' for v in ("Reçu", "Intégré", "Non disponible"))
     + f',{plage("Intégration","G",N_INT)},"<>Non"'),
]
deb_ech = rb
for lib, j, d, extra in ECH:
    res.cell(row=rb, column=5, value=lib).font = f()
    res.cell(row=rb, column=5).border = BORD
    forms = [f'=COUNTIF({j},"<0")', f'=COUNTIFS({j},">=0",{j},"<="&SeuilUrgent)',
             f'=COUNTIFS({j},">=0",{j},"<="&SeuilAlerte)', f'=_xlfn.MINIFS({d},{d},">="&Aujourdhui{extra})']
    for k, form in enumerate(forms):
        c = res.cell(row=rb, column=6 + k, value=form)
        c.fill, c.border, c.font = CALC, BORD, f(bold=True)
        c.alignment = Alignment(horizontal="center")
        c.number_format = FMT["nextdate"] if k == 3 else FMT["nb"]
    rb += 1
fin_ech = rb - 1
regle(res, f"F{deb_ech}:F{fin_ech}", f"F{deb_ech}>0", BLOQUE_PALE, BLOQUE)
regle(res, f"G{deb_ech}:G{fin_ech}", f"G{deb_ech}>0", SPECIAL, ORANGE_TXT)
regle(res, f"H{deb_ech}:H{fin_ech}", f"H{deb_ech}>0", LIGNE_SURVOL, AVERT)
res.cell(row=rb, column=5, value='="Au "&TEXT(Aujourdhui,"yyyy-mm-dd")&" — seuils de "&SeuilUrgent&" et "&SeuilAlerte&" jours (onglet Paramètres). Le seuil d\'alerte inclut l\'urgent."').font = f(size=9, italic=True, color=DISCRET)
rb += 2


def kpi_ligne(rb, lib, formule, fmt, alerte=None):
    a = res.cell(row=rb, column=5, value=lib)
    a.font = f(bold=True)
    c = res.cell(row=rb, column=6, value=formule)
    c.fill, c.border, c.font, c.number_format = CALC, BORD, f(bold=True), fmt
    res.merge_cells(start_row=rb, start_column=6, end_row=rb, end_column=7)
    if alerte:
        regle(res, f"F{rb}", alerte.format(c=f"F{rb}"), BLOQUE_PALE, BLOQUE)
    return rb + 1


I_ = lambda col: plage("Intégration", col, N_INT)
ouvert = f'{I_("D")},"<>",{I_("G")},"<>Non",{I_("H")},"<>Reçu",{I_("H")},"<>Intégré",{I_("H")},"<>Non disponible"'
c = res.cell(row=rb, column=5, value="INTÉGRATION")
c.font = f(bold=True, color=ORANGE_TXT)
rb += 1
a_app = rb
rb = kpi_ligne(rb, "Éléments applicables", f'=COUNTIFS({I_("D")},"<>",{I_("G")},"<>Non")', FMT["nb"])
rb = kpi_ligne(rb, "Éléments encore ouverts", f"=COUNTIFS({ouvert})", FMT["nb"])
rb = kpi_ligne(rb, "Avancement des documents", f"=IFERROR(1-F{a_app + 1}/F{a_app},0)", FMT["pct"])
rb = kpi_ligne(rb, "Ouverts « avant la prise en charge »", f'=COUNTIFS({ouvert},{I_("F")},"0*")', FMT["nb"], "{c}>0")
rb = kpi_ligne(rb, "Demandes à relancer", f'=COUNTIF({I_("O")},">="&DelaiRelance)', FMT["nb"], "{c}>0")
rb = kpi_ligne(rb, "Plan 90 jours : étapes faites",
               f'=IFERROR(COUNTIFS({PLAN_RNG[0]},"<>Critères de clôture",{PLAN_RNG[1]},"Oui")/COUNTIF({PLAN_RNG[0]},"<>Critères de clôture"),0)', FMT["pct"])
rb = kpi_ligne(rb, "Critères de clôture remplis",
               f'=COUNTIFS({PLAN_RNG[0]},"Critères de clôture",{PLAN_RNG[1]},"Oui")&" sur "&COUNTIF({PLAN_RNG[0]},"Critères de clôture")', "@")
rb += 1
c = res.cell(row=rb, column=5, value="TENUE DU DOSSIER")
c.font = f(bold=True, color=ORANGE_TXT)
rb += 1
rb = kpi_ligne(rb, "Dernière mise à jour (journal)", f"={REF['maj']}", FMT["nextdate"])
rb = kpi_ligne(rb, "Jours depuis la dernière mise à jour", f'=IF(N({REF["maj"]})=0,"",Aujourdhui-{REF["maj"]})', "0",
               "AND(ISNUMBER({c}),{c}>DelaiRevision)")
for onglet in ("Fiche", "Vision", "Finances", "Bâtiment"):
    fin = FORM_FIN[onglet]
    rb = kpi_ligne(rb, f"Informations manquantes — {onglet}",
                   f"=COUNTIFS('{onglet}'!$H$6:$H${fin},\"champ\",'{onglet}'!$C$6:$C${fin},\"\",'{onglet}'!$D$6:$D${fin},\"<>Sans objet\")",
                   FMT["nb"])
rb = kpi_ligne(rb, "Exceptions à revalider", f'=COUNTIF({plage("Exceptions","H",N_EXC)},">"&DelaiRevision)', FMT["nb"], "{c}>0")
rb = kpi_ligne(rb, "Risques ouverts cotés 6 ou plus",
               f'=COUNTIFS({plage("Risques","J",N_RIS)},">=6",{plage("Risques","H",N_RIS)},"<>Fermé")', FMT["nb"], "{c}>0")
rb += 1
c = res.cell(row=rb, column=5, value="DERNIER MOIS DE KPI")
c.font = f(bold=True, color=ORANGE_TXT)
rb += 1
K = lambda col: plage("KPI", col, N_KPI)
dernier = f"MATCH(1E+100,{K('B')})"
rb = kpi_ligne(rb, "Mois", f'=IFERROR(INDEX({K("B")},{dernier}),"")', 'yyyy-mm;;"—"')
rb = kpi_ligne(rb, "Taux de perception", f'=IFERROR(INDEX({K("N")},{dernier}),"")', FMT["pct"])
rb = kpi_ligne(rb, "Arrérages totaux", f'=IFERROR(INDEX({K("E")},{dernier}),"")', FMT["money0"])
rb = kpi_ligne(rb, "Écart NOI vs budget", f'=IFERROR(INDEX({K("O")},{dernier}),"")', FMT["money0"], "AND(ISNUMBER({c}),{c}<0)")
res.freeze_panes = "A4"
mise_en_page(res, titres=None, hauteur=1)
res.page_setup.orientation = "landscape"

# ------------------------------------------------------------------ Mode d'emploi (objectif, gouvernance, déclencheurs)
me = wb.create_sheet("Mode d'emploi")
entete_feuille(me, "Dossier maître de l'immeuble — Modèle Progim", largeur=3, ligne_immeuble=False)
me.column_dimensions["B"].width, me.column_dimensions["C"].width = 28, 105
TXT = [
    ("OBJECTIF", None),
    ("", "Ce document constitue la source de connaissance principale de l'immeuble. Il est rempli lors de l'intégration d'un "
         "nouveau mandat, puis maintenu à jour par le gestionnaire et les équipes Progim pendant toute la durée de la gestion. "
         "Il évite que l'information critique soit dispersée dans les courriels, la mémoire des employés ou plusieurs systèmes."),
    ("Principe", "Une information importante sur l'immeuble, le client, ses opérations, ses risques ou ses particularités doit pouvoir "
                 "être retrouvée rapidement ici, ou via un lien clair vers sa source officielle."),
    ("ORGANISATION DES ONGLETS", None),
    ("Synthèse", "Résumé (résumé exécutif et tableau de bord, entièrement calculé)."),
    ("Connaissance", "Fiche (identification, propriétaire, autorisations, mandat, ancien gestionnaire, concierge, technologie) · "
                     "Vision (vision, priorités, communication, stratégie locative, recevables) · Finances (diagnostic, budget, "
                     "comptabilité, hypothèque) · Bâtiment (systèmes, procédures d'urgence, conformité) · Exceptions · Décisions."),
    ("Intégration", "Intégration (documents et informations à obtenir, avec suivi) · Plan 90 jours (plan 30/60/90 et critères de clôture)."),
    ("Registres", "Unités · Dossiers · Assurances · Taxes · Contrats · Entretien · Équipements · Projets · Sinistres · "
                  "Calendrier · Contacts · Documents."),
    ("Suivi", "Risques · Opportunités · KPI · Actions · Journal (et liste de passation) · Paramètres."),
    ("1. INTÉGRATION D'UN NOUVEAU MANDAT", None),
    ("Ouvrir le dossier", "Copier ce gabarit, le renommer « Dossier maître - [code d'entité] - [adresse].xlsx » et le déposer dans le "
                          "dossier SharePoint de l'immeuble. Fiche : statut du dossier = En intégration."),
    ("Demander", "Onglet Intégration : mettre Non pour ce qui ne s'applique pas, nommer un responsable et une échéance. Filtrer la "
                 "colonne Source sur Propriétaire, puis sur Ancien gestionnaire : chaque liste filtrée devient la demande à envoyer."),
    ("Rencontrer", "Avec le propriétaire : onglet Vision. Avec l'ancien gestionnaire et le concierge : Fiche, Bâtiment (procédures "
                   "d'urgence et pièges techniques), Exceptions et Dossiers. Faire la visite complète le même jour si possible."),
    ("Consigner", "À la réception, inscrire l'information dans l'onglet indiqué, puis passer le statut à Intégré. Une information "
                  "inconnue reste vide : elle est surlignée comme manquante, on ne l'invente pas."),
    ("Clôturer", "Suivre le Plan 90 jours. Le mandat est intégré quand les 12 critères de clôture sont à Oui; statut du dossier = Actif."),
    ("2. MISE À JOUR CONTINUE", None),
    ("Quand", "Mettre le dossier à jour et l'inscrire au Journal lors de : changement de propriétaire ou de représentant; changement "
              "d'hypothèque; renouvellement d'assurance; nouveau contrat fournisseur; changement important de prix ou de stratégie "
              "locative; nouveau sinistre; nouveau dossier TAL important; rénovation majeure; remplacement d'un équipement critique; "
              "nouvelle particularité client; changement de seuil d'autorisation; changement de concierge; changement de politique "
              "de remise au propriétaire; changement d'année fiscale; nouvelle opportunité; nouveau risque; décision stratégique significative."),
    ("Révision", "Revoir tout le dossier au moins une fois par trimestre. Après 90 jours sans inscription au journal, le Résumé passe "
                 "en rouge. Une exception non revalidée depuis 90 jours passe aussi en rouge."),
    ("3. PASSATION OU ABSENCE", None),
    ("Passation", "Statut du dossier = En passation; suivre la liste de passation dans l'onglet Journal."),
    ("Remplacement", "En cas d'absence, le remplaçant commence par le Résumé, puis Exceptions, Actions et Dossiers."),
    ("35. RÈGLES DE GOUVERNANCE", None),
    ("1.", "Le dossier est la source de vérité opérationnelle de l'immeuble."),
    ("2.", "Les informations critiques ne doivent pas uniquement vivre dans les courriels."),
    ("3.", "Les exceptions doivent être documentées."),
    ("4.", "Les décisions significatives doivent être historisées."),
    ("5.", "Les données sensibles sont accessibles uniquement aux personnes autorisées."),
    ("6.", "Les documents officiels sont conservés dans leur système source; ce dossier pointe vers eux."),
    ("7.", "Le gestionnaire est responsable de maintenir à jour la connaissance de son portefeuille."),
    ("8.", "Une information inconnue est identifiée comme manquante plutôt qu'inventée."),
    ("9.", "Lorsqu'une information change, la date de modification est conservée (colonne Validé le et Journal)."),
    ("10.", "Le dossier doit être utilisable par un remplaçant en cas d'absence du gestionnaire principal."),
    ("LÉGENDE", None),
    ("Cellule blanche", "À remplir. Plusieurs colonnes ont une liste déroulante."),
    ("Cellule grise", "Calculée automatiquement. Ne pas modifier."),
    ("Texte bleu italique", "Exemple fictif : montre le format attendu. À remplacer ou supprimer."),
    ("Information manquante", "Champ de formulaire vide dont le statut n'est pas Sans objet."),
    ("Rouge", "Échéance dépassée, demande à relancer depuis longtemps, risque élevé ou dossier non révisé."),
    ("Orange", "Échéance dans le seuil urgent (30 jours par défaut)."),
    ("Jaune", "Échéance dans le seuil d'alerte (90 jours par défaut). Seuils et délais : onglet Paramètres."),
    ("RÈGLES PRATIQUES", None),
    ("Un seul fichier", "Ouvrir le fichier depuis SharePoint, dans Excel : plusieurs personnes peuvent y travailler en même temps. "
                        "Pas de copie sur un poste."),
    ("Confidentialité", "Jamais de code d'alarme, de mot de passe, de combinaison ni de numéro de compte complet."),
    ("Renseignements personnels", "Loi 25 : sur les locataires, seulement ce qui est nécessaire à la gestion, des faits et non des "
                                  "opinions. Ne pas transmettre le fichier complet au propriétaire ni à des tiers : extraire l'onglet utile."),
    ("Ajouter des lignes", "Insérer des lignes au milieu d'un tableau, jamais sous la dernière ligne, pour que le Résumé les compte."),
    ("Listes de départ", "Entretien, calendrier et numéros d'urgence sont indicatifs : les valider pour chaque immeuble."),
]
LEGENDE = {"Cellule blanche": (fill("FFFFFF"), f()), "Cellule grise": (CALC, f()),
           "Texte bleu italique": (None, f(italic=True, color=EXEMPLE)), "Information manquante": (fill(SPECIAL), f(color=ORANGE_TXT)),
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
mise_en_page(me, titres=None)
me.page_setup.orientation = "portrait"

# ------------------------------------------------------------------ Ordre et couleurs des onglets
GROUPES = [
    (ORANGE, ["Mode d'emploi", "Résumé"]),
    (MARINE, ["Fiche", "Vision", "Finances", "Bâtiment", "Exceptions", "Décisions"]),
    (INFO, ["Intégration", "Plan 90 jours"]),
    (DISCRET, ["Unités", "Dossiers", "Assurances", "Taxes", "Contrats", "Entretien", "Équipements", "Projets", "Sinistres",
               "Calendrier", "Contacts", "Documents"]),
    (OK, ["Risques", "Opportunités", "KPI", "Actions", "Journal"]),
    (PALE, ["Paramètres"]),
]
ORDRE = [n for _, noms in GROUPES for n in noms]
assert sorted(ORDRE) == sorted(wb.sheetnames), set(wb.sheetnames) ^ set(ORDRE)
wb._sheets.sort(key=lambda w: ORDRE.index(w.title))
for couleur, noms in GROUPES:
    for n in noms:
        wb[n].sheet_properties.tabColor = couleur
wb.active = 1
wb.save(SORTIE)
print("Écrit :", SORTIE)
