"""Assemble la proposition d'un bon : heures arrondies, matériel des factures, description révisée."""

from __future__ import annotations

import hashlib
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
from regles import (Regles, garde_fou_achat, garde_fous_facture, garde_fous_temps, heures_facturees, heures_fr,
                    lignes_materiel)


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
        origine[str(derniere.id)] = f"Arrondi au 15 min supérieur – {tech} : {heures_fr(cible)} h facturées"
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


def chemin_cache(cache: Path, bon: Bon, r: Regles, cfg: dict) -> Path:
    """Un fichier par bon, par date de modification ET par version des règles et du modèle."""
    reglages = json.dumps([asdict(r), cfg.get("claude", {})], sort_keys=True, default=str)
    empreinte = hashlib.sha1(reglages.encode("utf-8")).hexdigest()[:10]
    return Path(cache) / f"{bon.id}_{re.sub(r'[^0-9A-Za-z]', '', bon.maj)}_{empreinte}.json"


def effacer_cache(cache: Path, bon_id: int) -> None:
    for fichier in Path(cache).glob(f"{bon_id}_*.json"):
        fichier.unlink(missing_ok=True)


def analyser_bon(bon: Bon, progression, client, cfg: dict, r: Regles, journal, cache: Path) -> Proposition:
    fichier = chemin_cache(cache, bon, r, cfg)
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
        if f.cle in deja_dans_le_bon or deja_refacturees.get(f.cle) == bon.id:
            continue  # déjà refacturée dans ce bon lors d'un envoi précédent
        # Une facture refacturée dans un AUTRE bon est vérifiée par doublons_externes, à chaque affichage.
        alertes += garde_fous_facture(f, bon.date_rv, r)
        for ligne in lignes_materiel(f, r.marge):
            lignes.append(ligne)
            origine[ligne.external_id] = f"Facture {nom}, coût + {r.marge * 100:g} %".replace(".", ",")

    alertes += garde_fou_achat(bon.achat, sum(1 for a in analyses if a.genre == "facture"))

    description, alertes_texte = rediger(bon.description, client, cfg["claude"])
    alertes += alertes_texte

    proposition = Proposition(
        bon_id=bon.id, maj=bon.maj, description=description, description_originale=bon.description,
        lignes=lignes, analyses=analyses, alertes=alertes, origine=origine)
    if not any(a.raison.startswith("Téléchargement impossible") for a in analyses):
        # Un échec de téléchargement est passager : on ne le garde pas, la prochaine analyse réessaie.
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(proposition_vers_dict(proposition), ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return proposition


def doublons_externes(propositions: list[Proposition], journal, progression, memo: dict) -> None:
    """Bloque un bon dont une nouvelle facture est déjà dans un autre bon : journal, lot en cours ou Progression.

    Recalculé à chaque fois (jamais mis en cache) : l'alerte apparaît ou disparaît selon l'état actuel.
    `memo` garde les réponses de Progression (externalId -> bon) pour ne pas refaire les requêtes.
    """
    refacturees = journal.factures_refacturees()
    vues: dict[str, int] = {}
    for p in propositions:
        p.alertes = [a for a in p.alertes if a.code != "facture_autre_bon"]
        signalees: set[str] = set()
        for ligne in p.lignes:
            if ligne.id is not None or not ligne.external_id:
                continue
            cle = ligne.external_id.rsplit("|", 1)[0]
            if cle in signalees:
                continue
            autre = refacturees.get(cle)
            if autre in (None, p.bon_id):
                autre = vues.get(cle)
            if autre in (None, p.bon_id) and progression is not None:
                if ligne.external_id not in memo:
                    memo[ligne.external_id] = progression.bon_avec_ligne(ligne.external_id)
                autre = memo[ligne.external_id]
            if autre not in (None, p.bon_id):
                signalees.add(cle)
                fournisseur, numero = cle.split("|", 1)
                p.alertes.append(Alerte("facture_autre_bon",
                                        f"Facture {fournisseur} {numero} déjà refacturée ou jointe au bon {autre}.",
                                        bloquante=True))
            else:
                vues.setdefault(cle, p.bon_id)


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
