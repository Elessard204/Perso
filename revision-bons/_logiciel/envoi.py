"""Construit et écrit les mises à jour approuvées dans Progression (simulation par défaut)."""

from __future__ import annotations

from typing import Literal

from modele import Ligne, Proposition
from progression import ErreurProgression


def _sans_none(objet):
    """Progression efface une donnée reçue à null : on retire toute clé à None."""
    if isinstance(objet, dict):
        return {k: _sans_none(v) for k, v in objet.items() if v is not None}
    if isinstance(objet, list):
        return [_sans_none(v) for v in objet]
    return objet


def _item(ligne: Ligne, cfg: dict) -> dict:
    item = {
        "id": ligne.id,
        "label": ligne.libelle,
        "description": ligne.description,
        "quantity": ligne.quantite,
        "price": ligne.prix,
        "unitCost": ligne.cout_unitaire,
        "externalId": ligne.external_id if ligne.id is None else None,
    }
    if ligne.id is None and cfg.get("produit_materiel"):
        item["product"] = {"code": cfg["produit_materiel"]}
    return item


def corps_mise_a_jour(p: Proposition, cfg: dict, tache: dict | None) -> dict:
    """Description révisée + liste COMPLÈTE des lignes (existantes avec leur id, nouvelles sans id)."""
    corps: dict = {"itemList": {"items": [_item(l, cfg) for l in p.lignes]}}
    champ = cfg.get("champ_description") or "description"
    if champ.startswith("properties."):
        # On renvoie tous les champs personnalisés existants pour ne rien écraser.
        proprietes = dict((tache or {}).get("properties") or {})
        proprietes[champ.split(".", 1)[1]] = p.description
        corps["properties"] = proprietes
    else:
        corps[champ] = p.description
    return _sans_none(corps)


def envoyer(propositions: list[Proposition], progression, journal, cfg: dict,
            mode: Literal["simulation", "reel"]) -> list[dict]:
    if mode == "reel" and not cfg.get("ecriture_validee"):
        raise ValueError("Écriture réelle verrouillée : l'essai sur un bon de test n'a pas encore été validé.")
    resultats = []
    for p in propositions:
        if journal.deja_ecrit(p.bon_id, p.maj):
            resultats.append({"bon_id": p.bon_id, "resultat": "deja_ecrit", "message": "Déjà écrit dans Progression."})
            continue
        if mode == "simulation":
            resultats.append({"bon_id": p.bon_id, "resultat": "simule", "message": "Rien n'a été écrit (simulation).",
                              "corps": corps_mise_a_jour(p, cfg, None)})
            continue
        try:
            tache = progression.tache_brute(p.bon_id)
            if (tache.get("updated") or "") != p.maj:
                resultats.append({"bon_id": p.bon_id, "resultat": "perime",
                                  "message": "Le bon a été modifié dans Progression depuis l'analyse : à réanalyser."})
                continue
            corps = corps_mise_a_jour(p, cfg, tache)
            progression.mettre_a_jour(p.bon_id, corps)
        except ErreurProgression as e:
            journal.inscrire("echec", p.bon_id, p.maj, {"message": str(e)})
            resultats.append({"bon_id": p.bon_id, "resultat": "echec", "message": str(e)})
            continue
        journal.inscrire("ecrit", p.bon_id, p.maj, {
            "external_ids": [l.external_id for l in p.lignes if l.id is None and l.external_id],
            "description_originale": p.description_originale,
            "description": p.description,
            "corps": corps,
        })
        resultats.append({"bon_id": p.bon_id, "resultat": "ecrit", "message": "Écrit dans Progression."})
    return resultats
