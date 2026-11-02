"""Lecture et modification de l'Excel des clients pour l'onglet « Clients » de l'interface.

L'Excel a un onglet « Clients » (une ligne par entité Hopem, avec ses destinataires) et un onglet
« Gestionnaires ». Les entités qui ont exactement les mêmes destinataires partent dans un seul courriel.
Une copie de l'Excel est gardée dans _logiciel/sauvegardes avant chaque modification.
"""

import shutil
import tomllib
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from envoi_rapports import COURRIEL_VALIDE, ICI, MOIS_FR, adresses, cle_code, normaliser

SAUVEGARDES = ICI / "sauvegardes"
GARDER_SAUVEGARDES = 30
FREQUENCES = ["mensuel", "trimestriel", "semestriel", "annuel"]
COLONNES_DEBUT = ["code_entite", "nom_entite", "immeubles", "courriel_clients", "courriel_direction", "langue",
                  "courriel_separe", "gestionnaire", "fin_exercice", "frequence", "actif"]
# Colonnes qui ne servent plus : retirées de l'Excel si elles sont vides.
COLONNES_RETIREES = ["courriel_gestionnaire"]
# Colonnes abandonnées : retirées même si elles contiennent quelque chose (la copie de sauvegarde les garde).
COLONNES_ABANDONNEES = ["liste_cheques"]
SUIVI = "Suivi"
COLONNES_SUIVI = ["mois", "code_entite", "conciliation", "conciliation_note", "ef_verifies", "date_envoi"]
ANCIENS = "Anciens clients"


def config() -> dict:
    return tomllib.loads((ICI / "config.toml").read_text(encoding="utf-8"))


def colonnes_clients() -> list[str]:
    return COLONNES_DEBUT + [item["cle"] for item in config()["contenu"]] + ["notes"]


def sauvegarder(chemin: Path) -> None:
    """Copie datée de l'Excel avant modification; seules les plus récentes sont gardées."""
    SAUVEGARDES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chemin, SAUVEGARDES / f"{chemin.stem}_{datetime.now():%Y-%m-%d_%H%M%S}.xlsx")
    for ancienne in sorted(SAUVEGARDES.glob(f"{chemin.stem}_*.xlsx"))[:-GARDER_SAUVEGARDES]:
        ancienne.unlink(missing_ok=True)


def lignes(feuille) -> tuple[list[str], list[tuple[int, dict]]]:
    entetes = [normaliser(c.value or "").replace(" ", "_") for c in feuille[1]]
    resultat = []
    for numero, rangee in enumerate(feuille.iter_rows(min_row=2, values_only=True), start=2):
        if any(v not in (None, "") for v in rangee):
            resultat.append((numero, {e: ("" if v is None else str(v).strip()) for e, v in zip(entetes, rangee) if e}))
    return entetes, resultat


def mettre_en_forme(feuille, nom_table: str, colonnes_oui_non: list[str]) -> None:
    """En-tête Progim, tableau Excel, listes Oui/Non et largeurs de colonnes."""
    entete, fond = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="131A2F")
    for cellule in feuille[1]:
        cellule.font, cellule.fill = entete, fond
    for colonne in feuille.columns:
        largeur = max(len(str(c.value or "")) for c in colonne) + 3
        feuille.column_dimensions[colonne[0].column_letter].width = min(max(largeur, 10), 60)
    for nom in list(feuille.tables):
        del feuille.tables[nom]
    if feuille.max_row > 1:
        table = Table(displayName=nom_table, ref=feuille.dimensions)
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        feuille.add_table(table)
    if colonnes_oui_non:
        choix = DataValidation(type="list", formula1='"Oui,Non"', allow_blank=True)
        feuille.add_data_validation(choix)
        for i, cellule in enumerate(feuille[1]):
            if cellule.value in colonnes_oui_non:
                lettre = cellule.column_letter
                choix.add(f"{lettre}2:{lettre}{max(feuille.max_row, 300)}")
    feuille.freeze_panes = "C2"


def ajuster_colonnes(chemin: Path) -> bool:
    """Met l'onglet Clients à jour : ajoute les nouvelles colonnes, retire celles qui ne servent plus."""
    classeur = load_workbook(chemin)
    if "Clients" not in classeur.sheetnames:
        return False
    feuille = classeur["Clients"]
    entetes, rangees = lignes(feuille)
    a_retirer = [c for c in COLONNES_ABANDONNEES if c in entetes]
    a_retirer += [c for c in COLONNES_RETIREES if c in entetes and not any(v.get(c) for _, v in rangees)]
    a_ajouter = [c for c in colonnes_clients() if c not in entetes]
    if not a_retirer and not a_ajouter:
        return False
    sauvegarder(chemin)
    colonnes = [c for c in entetes if c and c not in a_retirer]
    # Les nouvelles colonnes vont à leur place habituelle (ex. courriel_separe après langue).
    for nouvelle in a_ajouter:
        ordre = colonnes_clients()
        avant = [c for c in ordre[:ordre.index(nouvelle)] if c in colonnes]
        colonnes.insert(colonnes.index(avant[-1]) + 1 if avant else len(colonnes), nouvelle)
    valeurs = [[v.get(c) or None for c in colonnes] for _, v in rangees]
    valeurs = [[int(x) if c == "fin_exercice" and x and str(x).isdigit() else x for c, x in zip(colonnes, rangee)]
               for rangee in valeurs]
    index = classeur.sheetnames.index("Clients")
    del classeur["Clients"]
    feuille = classeur.create_sheet("Clients", index)
    feuille.append(colonnes)
    for rangee in valeurs:
        feuille.append(rangee)
    mettre_en_forme(feuille, "T_Clients", ["actif", "courriel_separe"] + [item["cle"] for item in config()["contenu"]])
    classeur.active = index
    classeur.save(chemin)
    return True


def migrer_si_besoin(chemin: Path) -> bool:
    """Convertit l'ancien format (onglets Clients + Entites) en un seul onglet « Clients ». Retourne True si converti."""
    classeur = load_workbook(chemin)
    if "Entites" not in classeur.sheetnames:
        return ajuster_colonnes(chemin)
    sauvegarder(chemin)
    _, anciens_clients = lignes(classeur["Clients"])
    clients = {v.get("code_client", ""): v for _, v in anciens_clients}
    _, entites = lignes(classeur["Entites"])
    colonnes = colonnes_clients()
    nouvelles = []
    for _, e in entites:
        client = clients.get(e.get("code_client", ""), {})
        actif = "Oui" if (normaliser(e.get("actif", "oui")) in {"oui", "o", "x", "1"}
                          and normaliser(client.get("actif", "oui")) in {"oui", "o", "x", "1"}) else "Non"
        valeurs = {**e, "courriel_clients": client.get("courriel_clients", ""),
                   "courriel_direction": client.get("courriel_direction", ""),
                   "langue": client.get("langue", "") or "FR", "actif": actif}
        nouvelles.append([valeurs.get(c, "") or None for c in colonnes])

    index = classeur.sheetnames.index("Clients")
    del classeur["Clients"]
    del classeur["Entites"]
    feuille = classeur.create_sheet("Clients", index)
    feuille.append(colonnes)
    for rangee in nouvelles:
        feuille.append([int(v) if c == "fin_exercice" and v and str(v).isdigit() else v for c, v in zip(colonnes, rangee)])
    mettre_en_forme(feuille, "T_Clients", ["actif", "courriel_separe"] + [item["cle"] for item in config()["contenu"]])
    classeur.active = index
    classeur.save(chemin)
    return True


def lire(chemin: Path) -> dict:
    migrer_si_besoin(chemin)
    classeur = load_workbook(chemin, data_only=True)
    _, entites = lignes(classeur["Clients"])
    _, gestionnaires = lignes(classeur["Gestionnaires"]) if "Gestionnaires" in classeur.sheetnames else ([], [])
    reglages = config()
    compte = {}
    for _, e in entites:
        compte[e.get("gestionnaire", "")] = compte.get(e.get("gestionnaire", ""), 0) + 1
    return {
        "entites": [{"ligne": n, "valeurs": v} for n, v in entites],
        "gestionnaires": [{"ligne": n, "nom": v.get("nom", ""), "courriel": v.get("courriel", ""),
                           "entites": compte.get(v.get("nom", ""), 0)} for n, v in gestionnaires],
        "contenu": [{"cle": i["cle"], "libelle": i["libelle"], "defaut": i.get("defaut", False)} for i in reglages["contenu"]],
        "mois": MOIS_FR,
        "frequences": FREQUENCES,
        "direction_defaut": reglages["envoi"]["direction_defaut"],
    }


def erreurs_fiche(valeurs: dict) -> list[str]:
    erreurs = []
    if not valeurs.get("code_entite", "").strip():
        erreurs.append("Le code de l'entité est obligatoire.")
    for colonne in ("courriel_clients", "courriel_direction"):
        mauvaises = [a for a in adresses(valeurs.get(colonne, "")) if not COURRIEL_VALIDE.match(a)]
        if mauvaises:
            erreurs.append(f"Adresse courriel invalide : {', '.join(mauvaises)}")
    fin = str(valeurs.get("fin_exercice", "")).strip()
    if fin and not (fin.isdigit() and 1 <= int(fin) <= 12):
        erreurs.append("La fin d'exercice doit être un mois de 1 à 12.")
    return erreurs


def ecrire_ligne(feuille, ligne: int, valeurs: dict) -> None:
    colonnes = {normaliser(c.value or "").replace(" ", "_"): c.column for c in feuille[1] if c.value is not None}
    for colonne, valeur in valeurs.items():
        if colonne not in colonnes:
            continue
        valeur = str(valeur).strip()
        if colonne.startswith("courriel"):
            valeur = "; ".join(adresses(valeur))
        if colonne == "fin_exercice" and valeur.isdigit():
            valeur = int(valeur)
        feuille.cell(ligne, colonnes[colonne]).value = valeur if valeur != "" else None


def ajuster_tables(feuille) -> None:
    for table in feuille.tables.values():
        debut, _, fin = table.ref.partition(":")
        colonne_fin = "".join(ch for ch in fin if ch.isalpha())
        table.ref = f"{debut}:{colonne_fin}{max(feuille.max_row, 2)}"


def enregistrer_fiche(chemin: Path, ligne: int | None, valeurs: dict) -> dict:
    """Écrit la fiche d'une entité (ligne existante, ou nouvelle si ligne est vide)."""
    erreurs = erreurs_fiche(valeurs)
    if erreurs:
        return {"erreur": " · ".join(erreurs)}
    classeur = load_workbook(chemin)
    feuille = classeur["Clients"]
    _, entites = lignes(feuille)
    code = cle_code(valeurs["code_entite"])
    if any(cle_code(v.get("code_entite", "")) == code and n != ligne for n, v in entites):
        return {"erreur": f"Le code {code} existe déjà dans une autre ligne."}
    sauvegarder(chemin)
    if not ligne:
        ligne = feuille.max_row + 1
    ecrire_ligne(feuille, ligne, valeurs)
    ajuster_tables(feuille)
    classeur.save(chemin)
    return {"ok": True, "message": f"Fiche {code} enregistrée."}


def retirer_fiche(chemin: Path, ligne: int, code: str) -> dict:
    """Retire un client de la liste : sa ligne est déplacée dans l'onglet « Anciens clients », avec la date."""
    classeur = load_workbook(chemin)
    feuille = classeur["Clients"]
    entetes, entites = lignes(feuille)
    valeurs = next((v for n, v in entites if n == ligne), None)
    # Vérifie que la ligne n'a pas bougé depuis l'ouverture de la fiche (autre personne, Excel modifié...).
    if valeurs is None or cle_code(valeurs.get("code_entite", "")) != cle_code(code):
        return {"erreur": "La liste a changé depuis l'ouverture de la fiche. Fermez la fiche et recommencez."}
    sauvegarder(chemin)
    if ANCIENS not in classeur.sheetnames:
        anciens = classeur.create_sheet(ANCIENS)
        anciens.append(["date_retrait"] + [e for e in entetes if e])
        anciens.freeze_panes = "A2"
    anciens = classeur[ANCIENS]
    colonnes_anciens = [normaliser(c.value or "").replace(" ", "_") for c in anciens[1]]
    for e in entetes:
        if e and e not in colonnes_anciens:
            anciens.cell(1, len(colonnes_anciens) + 1).value = e
            colonnes_anciens.append(e)
    rangee = [datetime.now().strftime("%Y-%m-%d")] + [valeurs.get(c) or None for c in colonnes_anciens[1:]]
    anciens.append(rangee)
    for cellule in anciens[1]:
        cellule.font, cellule.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="131A2F")
    feuille.delete_rows(ligne)
    ajuster_tables(feuille)
    classeur.save(chemin)
    nom = valeurs.get("nom_entite") or ""
    return {"ok": True, "message": f"{cle_code(code)} {nom} retiré de la liste (conservé dans l'onglet « {ANCIENS} » de l'Excel)."}


def enregistrer_gestionnaire(chemin: Path, ligne: int | None, nom: str, courriel: str) -> dict:
    """Ajoute ou modifie un gestionnaire; un changement de prénom suit dans toutes ses entités."""
    nom, courriel = nom.strip(), courriel.strip()
    if not nom:
        return {"erreur": "Le prénom du gestionnaire est obligatoire."}
    if courriel and not COURRIEL_VALIDE.match(courriel):
        return {"erreur": f"Adresse courriel invalide : {courriel}"}
    classeur = load_workbook(chemin)
    feuille = classeur["Gestionnaires"]
    _, existants = lignes(feuille)
    if any(normaliser(v.get("nom", "")) == normaliser(nom) and n != ligne for n, v in existants):
        return {"erreur": f"Le gestionnaire {nom} existe déjà."}
    sauvegarder(chemin)
    ancien = next((v.get("nom", "") for n, v in existants if n == ligne), "")
    if not ligne:
        ligne = feuille.max_row + 1
    feuille.cell(ligne, 1).value, feuille.cell(ligne, 2).value = nom, courriel or None
    ajuster_tables(feuille)
    if ancien and ancien != nom:
        remplacer_gestionnaire(classeur["Clients"], ancien, nom)
    classeur.save(chemin)
    return {"ok": True, "message": f"Gestionnaire {nom} enregistré."}


def remplacer_gestionnaire(feuille, ancien: str, nouveau: str) -> int:
    entetes, entites = lignes(feuille)
    if "gestionnaire" not in entetes:
        return 0
    colonne = entetes.index("gestionnaire") + 1
    transferees = 0
    for numero, valeurs in entites:
        if normaliser(valeurs.get("gestionnaire", "")) == normaliser(ancien):
            feuille.cell(numero, colonne).value = nouveau or None
            transferees += 1
    return transferees


def supprimer_gestionnaire(chemin: Path, nom: str, remplacant: str) -> dict:
    """Transfère les entités du gestionnaire à son remplaçant, puis le retire de la liste."""
    classeur = load_workbook(chemin)
    feuille = classeur["Gestionnaires"]
    _, existants = lignes(feuille)
    ligne = next((n for n, v in existants if normaliser(v.get("nom", "")) == normaliser(nom)), None)
    if not ligne:
        return {"erreur": f"Gestionnaire {nom} introuvable."}
    sauvegarder(chemin)
    transferees = remplacer_gestionnaire(classeur["Clients"], nom, remplacant)
    feuille.delete_rows(ligne)
    ajuster_tables(feuille)
    classeur.save(chemin)
    vers = f" transférées à {remplacant}" if remplacant else " laissées sans gestionnaire"
    return {"ok": True, "message": f"{nom} supprimé. {transferees} entité{'s' if transferees > 1 else ''}{vers}."}


# ---- Onglet « Suivi » : une ligne par mois et par entité ----

def feuille_suivi(classeur):
    if SUIVI not in classeur.sheetnames:
        feuille = classeur.create_sheet(SUIVI)
        feuille.append(COLONNES_SUIVI)
        for cellule in feuille[1]:
            cellule.font, cellule.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="131A2F")
        for lettre, largeur in zip("ABCDEF", (10, 12, 14, 50, 12, 14)):
            feuille.column_dimensions[lettre].width = largeur
        feuille.freeze_panes = "C2"
    return classeur[SUIVI]


def lire_suivi(chemin: Path, mois: str) -> dict:
    """Le suivi d'un mois, avec le code, le nom légal et l'état actif repris de l'onglet Clients."""
    migrer_si_besoin(chemin)
    classeur = load_workbook(chemin, data_only=True)
    _, entites = lignes(classeur["Clients"])
    suivi = {}
    if SUIVI in classeur.sheetnames:
        for _, v in lignes(classeur[SUIVI])[1]:
            if v.get("mois", "")[:7] == mois and v.get("code_entite"):
                suivi[cle_code(v["code_entite"])] = v
    resultat = []
    for _, v in entites:
        code = cle_code(v.get("code_entite", ""))
        s = suivi.get(code, {})
        resultat.append({"code": code, "nom": v.get("nom_entite", ""),
                         "actif": normaliser(v.get("actif", "oui")) in {"oui", "o", "x", "1", ""},
                         "conciliation": normaliser(s.get("conciliation", "")) in {"oui", "o", "x", "1"},
                         "conciliation_note": s.get("conciliation_note", ""),
                         "ef_verifies": normaliser(s.get("ef_verifies", "")) in {"oui", "o", "x", "1"},
                         "date_envoi": s.get("date_envoi", "")[:10]})
    return {"mois": mois, "lignes": resultat}


def ecrire_suivi(classeur, mois: str, code: str, valeurs: dict) -> None:
    feuille = feuille_suivi(classeur)
    _, rangees = lignes(feuille)
    ligne = next((n for n, v in rangees if v.get("mois", "")[:7] == mois and cle_code(v.get("code_entite", "")) == code), None)
    if ligne is None:
        ligne = feuille.max_row + 1
        feuille.cell(ligne, 1).value, feuille.cell(ligne, 2).value = mois, code
    for colonne, valeur in valeurs.items():
        if colonne in COLONNES_SUIVI[2:]:
            if isinstance(valeur, bool):
                valeur = "Oui" if valeur else "Non"
            feuille.cell(ligne, COLONNES_SUIVI.index(colonne) + 1).value = str(valeur).strip() or None


def enregistrer_suivi(chemin: Path, mois: str, codes: list[str], valeurs: dict) -> dict:
    """Une case ou un commentaire du suivi (une entité, ou plusieurs avec « tout cocher »), enregistré tout de suite."""
    classeur = load_workbook(chemin)
    for code in codes:
        ecrire_suivi(classeur, mois, cle_code(code), valeurs)
    classeur.save(chemin)
    return {"ok": True}


def marquer_envoi(chemin: Path, mois: str, codes: list[str], date: str) -> None:
    """Inscrit la date d'envoi (création du brouillon) des entités d'un lot."""
    classeur = load_workbook(chemin)
    for code in codes:
        ecrire_suivi(classeur, mois, cle_code(code), {"date_envoi": date})
    classeur.save(chemin)


def etat_suivi(chemin: Path, mois: str) -> dict[str, dict]:
    """Conciliation et états financiers vérifiés de chaque entité pour le mois : {code: {...}}."""
    return {l["code"]: l for l in lire_suivi(chemin, mois)["lignes"]}
