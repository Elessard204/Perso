"""Lecture et modification de l'Excel des clients pour l'onglet « Clients et entités » de l'interface."""

import tomllib
from pathlib import Path

from openpyxl import load_workbook

from envoi_rapports import COURRIEL_VALIDE, ICI, MOIS_FR, adresses

ONGLETS = ["Clients", "Entites", "Gestionnaires"]
FREQUENCES = ["mensuel", "trimestriel", "semestriel", "annuel"]


def cles_contenu() -> list[str]:
    config = tomllib.loads((ICI / "config.toml").read_text(encoding="utf-8"))
    return [item["cle"] for item in config["contenu"]]


def genre_colonne(colonne: str) -> str:
    """Comment l'interface affiche et valide une colonne."""
    if colonne == "actif" or colonne in cles_contenu():
        return "case"
    if colonne.startswith("courriel"):
        return "courriel"
    if colonne in ("frequence", "fin_exercice", "gestionnaire", "code_client", "langue"):
        return "liste"
    if colonne in ("notes", "immeubles"):
        return "long"
    return "texte"


def lire(chemin: Path) -> dict:
    classeur = load_workbook(chemin, data_only=True)
    onglets = {}
    for nom in ONGLETS:
        if nom not in classeur.sheetnames:
            continue
        feuille = classeur[nom]
        colonnes = [str(c.value).strip() if c.value is not None else "" for c in feuille[1]]
        lignes = []
        for numero, rangee in enumerate(feuille.iter_rows(min_row=2, values_only=True), start=2):
            if not any(v not in (None, "") for v in rangee):
                continue
            lignes.append({"ligne": numero, "valeurs": {c: ("" if v is None else str(v)) for c, v in zip(colonnes, rangee) if c}})
        onglets[nom] = {"colonnes": [{"nom": c, "genre": genre_colonne(c)} for c in colonnes if c], "lignes": lignes}

    noms_gestionnaires = [l["valeurs"].get("nom", "") for l in onglets.get("Gestionnaires", {}).get("lignes", [])]
    codes_clients = [l["valeurs"].get("code_client", "") for l in onglets.get("Clients", {}).get("lignes", [])]
    listes = {
        "frequence": FREQUENCES,
        "fin_exercice": [{"valeur": str(i + 1), "libelle": f"{i + 1} – {m}"} for i, m in enumerate(MOIS_FR)],
        "gestionnaire": [""] + [n for n in noms_gestionnaires if n],
        "code_client": [c for c in codes_clients if c],
        "langue": ["FR", "EN"],
    }
    return {"onglets": onglets, "listes": listes}


def valider(colonne: str, valeur: str) -> str:
    """Message d'erreur pour une valeur refusée, sinon une chaîne vide."""
    if colonne.startswith("courriel"):
        mauvaises = [a for a in adresses(valeur) if not COURRIEL_VALIDE.match(a)]
        if mauvaises:
            return f"Adresse courriel invalide : {', '.join(mauvaises)}"
    if colonne == "fin_exercice" and valeur and not (valeur.isdigit() and 1 <= int(valeur) <= 12):
        return "La fin d'exercice doit être un mois de 1 à 12."
    return ""


def enregistrer(chemin: Path, onglet: str, modifications: list[dict]) -> dict:
    """Applique les modifications d'un onglet : {ligne: numéro ou null pour une nouvelle ligne, valeurs: {colonne: valeur}}."""
    if onglet not in ONGLETS:
        return {"erreur": f"Onglet inconnu : {onglet}"}
    erreurs = [f"{c} : {m}" for mod in modifications for c, v in mod["valeurs"].items() if (m := valider(c, v))]
    if erreurs:
        return {"erreur": " · ".join(erreurs)}

    classeur = load_workbook(chemin)
    feuille = classeur[onglet]
    colonnes = {str(c.value).strip(): c.column for c in feuille[1] if c.value is not None}
    numeriques = {"fin_exercice"}
    ajoutees = 0
    for mod in modifications:
        ligne = mod.get("ligne")
        if not ligne:
            ligne = feuille.max_row + 1
            ajoutees += 1
        for colonne, valeur in mod["valeurs"].items():
            if colonne not in colonnes:
                continue
            valeur = valeur.strip()
            if colonne in numeriques and valeur.isdigit():
                valeur = int(valeur)
            elif colonne.startswith("courriel"):
                valeur = "; ".join(adresses(valeur))
            feuille.cell(ligne, colonnes[colonne]).value = valeur or None
    # Garde le tableau Excel à la bonne taille quand des lignes sont ajoutées.
    if ajoutees:
        for table in feuille.tables.values():
            debut, _, fin = table.ref.partition(":")
            colonne_fin = "".join(ch for ch in fin if ch.isalpha())
            table.ref = f"{debut}:{colonne_fin}{feuille.max_row}"
    classeur.save(chemin)
    return {"ok": True, "message": f"{len(modifications)} ligne{'s' if len(modifications) > 1 else ''} enregistrée{'s' if len(modifications) > 1 else ''} dans l'Excel."}
