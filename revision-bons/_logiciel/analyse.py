"""Assemble la proposition d'un bon : heures arrondies, matériel des factures, description révisée."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from modele import Alerte, AnalysePiece, Bon, Facture, Ligne, LigneFacture, Proposition
from pieces_jointes import analyser_piece
from progression import ErreurProgression
from redaction import rediger
from regles import Regles, garde_fous_facture, garde_fous_temps, heures_facturees, lignes_materiel


def ajuster_main_oeuvre(bon: Bon, heures: dict[str, float]) -> tuple[list[Ligne], dict[str, str]]:
    """Monte la ligne facturée de chaque technicien à ses heures arrondies. Ne réduit jamais."""
    lignes = [replace(l) for l in bon.lignes]
    par_id = {l.id: l for l in lignes if l.id is not None}
    techniciens_par_ligne: dict[int, set[str]] = defaultdict(set)
    lignes_par_tech: dict[str, list[int]] = defaultdict(list)
    for e in bon.entrees:
        if e.ligne_id in par_id:
            techniciens_par_ligne[e.ligne_id].add(e.technicien)
            if e.ligne_id not in lignes_par_tech[e.technicien]:
                lignes_par_tech[e.technicien].append(e.ligne_id)
    origine: dict[str, str] = {}
    for tech, cible in heures.items():
        ids = lignes_par_tech.get(tech)
        if not ids or any(len(techniciens_par_ligne[i]) > 1 for i in ids):
            continue  # signalé par analyser_bon
        ecart = round(cible - sum(par_id[i].quantite for i in ids), 4)
        if ecart <= 0:
            continue
        derniere = par_id[ids[-1]]
        derniere.quantite = round(derniere.quantite + ecart, 4)
        origine[str(derniere.id)] = f"Arrondi au 15 min supérieur – {tech} : {cible:g} h facturées"
    return lignes, origine


def _alertes_main_oeuvre(bon: Bon, heures: dict[str, float]) -> list[Alerte]:
    ids_lignes = {l.id for l in bon.lignes}
    alertes = []
    techs_par_ligne: dict[int, set[str]] = defaultdict(set)
    for e in bon.entrees:
        if e.ligne_id in ids_lignes:
            techs_par_ligne[e.ligne_id].add(e.technicien)
    for tech in heures:
        ids = {e.ligne_id for e in bon.entrees if e.technicien == tech and e.ligne_id in ids_lignes}
        if not ids:
            alertes.append(Alerte("main_oeuvre_introuvable",
                                  f"Aucune ligne facturée liée au temps de {tech} : arrondi non appliqué."))
        elif any(len(techs_par_ligne[i]) > 1 for i in ids):
            alertes.append(Alerte("main_oeuvre_partagee",
                                  f"La ligne de main-d'œuvre de {tech} est partagée avec un autre technicien : "
                                  "arrondi à vérifier à la main."))
    return alertes


def _fichier_cache(cache: Path, bon: Bon) -> Path:
    return Path(cache) / f"{bon.id}_{re.sub(r'[^0-9A-Za-z]', '', bon.maj)}.json"


def analyser_bon(bon: Bon, progression, client, cfg: dict, r: Regles, journal, cache: Path) -> Proposition:
    fichier = _fichier_cache(cache, bon)
    if fichier.exists():
        return proposition_depuis_dict(json.loads(fichier.read_text(encoding="utf-8")))

    alertes = garde_fous_temps(bon.entrees, r)
    heures = heures_facturees(bon.entrees, r.pas_minutes)
    lignes, origine = ajuster_main_oeuvre(bon, heures)
    alertes += _alertes_main_oeuvre(bon, heures)

    if r.regle_transports == "conserver":
        alertes.append(Alerte("transport_a_definir",
                              "Règle des transports pas encore définie : nombre de transports à vérifier."))

    deja_refacturees = journal.factures_refacturees()
    deja_dans_le_bon = {l.external_id.rsplit("|", 1)[0] for l in bon.lignes if l.external_id}
    vues: set[str] = set()
    analyses: list[AnalysePiece] = []
    for piece in bon.pieces:
        try:
            contenu = progression.telecharger_piece(piece.id)
        except ErreurProgression as e:
            analyse = AnalysePiece(piece.id, "incertain", None, f"Téléchargement impossible : {e}")
        else:
            analyse = analyser_piece(piece, contenu, client, cfg["claude"])
        analyses.append(analyse)
        if analyse.genre == "incertain":
            alertes.append(Alerte("piece_incertaine", f"Pièce « {piece.nom} » : {analyse.raison}"))
            continue
        if analyse.genre != "facture":
            continue
        f = analyse.facture
        nom = f"{f.fournisseur} {f.numero}"
        if f.cle in vues:
            alertes.append(Alerte("facture_doublon", f"Facture {nom} jointe deux fois à ce bon.", bloquante=True))
            continue
        vues.add(f.cle)
        if f.cle in deja_dans_le_bon:
            continue  # déjà refacturée dans ce bon lors d'un envoi précédent
        autre = deja_refacturees.get(f.cle)
        if autre is not None and autre != bon.id:
            alertes.append(Alerte("facture_doublon", f"Facture {nom} déjà refacturée dans le bon {autre}.",
                                  bloquante=True))
            continue
        alertes += garde_fous_facture(f, bon.date_rv, r)
        for ligne in lignes_materiel(f, r.marge):
            lignes.append(ligne)
            origine[ligne.external_id] = f"Facture {nom}, coût + {r.marge * 100:g} %"

    description, alertes_texte = rediger(bon.description, client, cfg["claude"])
    alertes += alertes_texte

    proposition = Proposition(
        bon_id=bon.id, maj=bon.maj, description=description, description_originale=bon.description,
        lignes=lignes, analyses=analyses, alertes=alertes, origine=origine)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps(proposition_vers_dict(proposition), ensure_ascii=False, indent=1), encoding="utf-8")
    return proposition


def proposition_vers_dict(p: Proposition) -> dict:
    def convertir(valeur):
        if isinstance(valeur, date):
            return valeur.isoformat()
        if isinstance(valeur, dict):
            return {k: convertir(v) for k, v in valeur.items()}
        if isinstance(valeur, list):
            return [convertir(v) for v in valeur]
        return valeur
    return convertir(asdict(p))


def proposition_depuis_dict(d: dict) -> Proposition:
    def facture(f):
        if not f:
            return None
        return Facture(f["fournisseur"], f["numero"], date.fromisoformat(f["date"]) if f["date"] else None,
                       f["sous_total"], [LigneFacture(**l) for l in f["lignes"]])
    return Proposition(
        bon_id=d["bon_id"], maj=d["maj"], description=d["description"],
        description_originale=d["description_originale"],
        lignes=[Ligne(**l) for l in d["lignes"]],
        analyses=[AnalysePiece(a["piece_id"], a["genre"], facture(a["facture"]), a["raison"]) for a in d["analyses"]],
        alertes=[Alerte(**a) for a in d["alertes"]],
        origine=dict(d["origine"]),
    )
