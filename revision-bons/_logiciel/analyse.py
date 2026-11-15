"""Assemble la proposition d'un bon : heures arrondies, matériel des factures, description révisée."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

from modele import Alerte, AnalysePiece, Bon, Facture, Ligne, LigneFacture, Proposition
from pieces_jointes import analyser_piece
from progression import ErreurProgression
from redaction import rediger
from facturation import (ajuster_heures_transport, alertes_inventaire, alertes_marge, classer, estimer_marge)
from regles import Regles, garde_fou_achat, garde_fous_facture, garde_fous_temps, ligne_materiel


def chemin_cache(cache: Path, bon: Bon, r: Regles, cfg: dict) -> Path:
    """Un fichier par bon, par date de modification ET par version des règles et du modèle."""
    reglages = json.dumps([asdict(r), cfg.get("claude", {})], sort_keys=True, default=str)
    empreinte = hashlib.sha1(reglages.encode("utf-8")).hexdigest()[:10]
    return Path(cache) / f"{bon.id}_{re.sub(r'[^0-9A-Za-z]', '', bon.maj)}_{empreinte}.json"


def effacer_cache(cache: Path, bon_id: int) -> None:
    for fichier in Path(cache).glob(f"{bon_id}_*.json"):
        fichier.unlink(missing_ok=True)


def _ligne_vide(l: Ligne) -> bool:
    return classer(l) == "materiel" and l.id is not None and not l.external_id and l.quantite == 0 and l.prix == 0


def analyser_bon(bon: Bon, progression, client, cfg: dict, r: Regles, journal, cache: Path) -> Proposition:
    fichier = chemin_cache(cache, bon, r, cfg)
    if fichier.exists():
        return proposition_depuis_dict(json.loads(fichier.read_text(encoding="utf-8")))

    alertes = garde_fous_temps(bon.entrees, r)
    lignes, origine, alertes_heures = ajuster_heures_transport(bon, r)
    alertes += alertes_heures

    deja_refacturees = journal.factures_refacturees()
    deja_dans_le_bon = {l.external_id.rsplit("|", 1)[0] for l in bon.lignes if l.external_id}
    vides = [l for l in lignes if _ligne_vide(l)]   # lignes « Matériel acheté » vides, réutilisées en premier
    vues: set[str] = set()
    analyses: list[AnalysePiece] = []
    photos: list[tuple[str, bytes]] = []
    for piece in bon.pieces:
        try:
            contenu = progression.telecharger_piece(piece.id)
        except ErreurProgression as e:
            analyse = AnalysePiece(piece.id, "incertain", None, f"Téléchargement impossible : {e}")
        else:
            analyse = analyser_piece(piece, contenu, client, cfg["claude"])
            if analyse.genre == "photo":
                photos.append((piece.type_mime, contenu))
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
        nouvelle = ligne_materiel(f, r.marge)
        if vides:
            existante = vides.pop(0)
            for champ in ("libelle", "description", "quantite", "prix", "cout_unitaire", "external_id"):
                setattr(existante, champ, getattr(nouvelle, champ))
            cle_origine = str(existante.id)
        else:
            lignes.append(nouvelle)
            cle_origine = nouvelle.external_id
        origine[cle_origine] = f"Facture {nom}, coût avant taxes + {r.marge * 100:g} %".replace(".", ",")

    retirees = [l.id for l in vides]
    for i in retirees:
        origine[str(i)] = "Ligne « Matériel acheté » vide : retirée"
    alertes += alertes_inventaire(lignes)
    alertes += garde_fou_achat(bon.achat, sum(1 for a in analyses if a.genre == "facture"))

    description, alertes_texte = rediger(bon.description, client, cfg["claude"], photos=photos, demande=bon.demande)
    alertes += alertes_texte

    marge = estimer_marge(bon, lignes, retirees)
    alertes += alertes_marge(marge, r)

    proposition = Proposition(
        bon_id=bon.id, maj=bon.maj, description=description, description_originale=bon.description,
        lignes=lignes, analyses=analyses, alertes=alertes, origine=origine, lignes_retirees=retirees, marge=marge)
    if not any(a.raison.startswith("Téléchargement impossible") for a in analyses):
        # Un échec de téléchargement est passager : on ne le garde pas, la prochaine analyse réessaie.
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(json.dumps(proposition_vers_dict(proposition), ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return proposition


def transports_en_double(paires: list[tuple[Bon, Proposition]]) -> None:
    """Signale un transport facturé alors que le même technicien était déjà dans le même immeuble le même jour
    pour un autre bon du lot. Recalculé à chaque fois (jamais mis en cache)."""
    vus: dict[tuple, str] = {}
    for bon, p in sorted(paires, key=lambda x: min((e.debut.isoformat() if e.debut else "") for e in x[0].entrees)
                         if x[0].entrees else ""):
        p.alertes = [a for a in p.alertes if a.code != "transport_double"]
        cles = {(e.technicien, e.jour, bon.lieu.split("/")[0]) for e in bon.entrees
                if "en route" in (e.activite or "").lower() and e.jour}
        for cle in sorted(cles, key=str):
            if cle in vus and vus[cle] != bon.code:
                p.alertes.append(Alerte("transport_double",
                                        f"{cle[0]} était déjà dans cet immeuble le {cle[1]} pour le bon {vus[cle]} : "
                                        "transport possiblement facturé en double."))
            else:
                vus.setdefault(cle, bon.code)


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
        lignes_retirees=list(d.get("lignes_retirees") or []),
        marge=dict(d.get("marge") or {}),
    )
