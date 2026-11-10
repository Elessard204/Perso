"""Construit et écrit les mises à jour approuvées dans Progression (simulation par défaut)."""

from __future__ import annotations

from typing import Literal

from modele import Ligne, Proposition
from progression import ErreurProgression, bon_depuis_json

# Champs d'une ligne que l'outil peut modifier, et leur nom dans l'API.
CHAMPS = (("libelle", "label"), ("description", "description"), ("quantite", "quantity"),
          ("prix", "price"), ("cout_unitaire", "unitCost"))


def _sans_none(objet):
    """Progression efface une donnée reçue à null : on retire toute clé à None."""
    if isinstance(objet, dict):
        return {k: _sans_none(v) for k, v in objet.items() if v is not None}
    if isinstance(objet, list):
        return [_sans_none(v) for v in objet]
    return objet


def _item(ligne: Ligne, avant: Ligne | None, cfg: dict) -> dict:
    if ligne.id is not None and avant is not None:
        # Ligne existante : seulement son id et ce qui a changé, pour ne rien réécrire d'autre.
        item = {"id": ligne.id}
        for attribut, nom in CHAMPS:
            if getattr(ligne, attribut) != getattr(avant, attribut):
                item[nom] = getattr(ligne, attribut)
        return item
    item = {"id": ligne.id, **{nom: getattr(ligne, attribut) for attribut, nom in CHAMPS}}
    if ligne.id is None:
        item["externalId"] = ligne.external_id
        if cfg.get("produit_materiel"):
            item["product"] = {"code": cfg["produit_materiel"]}
    return item


def corps_mise_a_jour(p: Proposition, cfg: dict, tache: dict | None,
                      lignes_avant: list[Ligne] | None = None) -> dict:
    """Description révisée + liste COMPLÈTE des lignes (existantes avec leur id, nouvelles sans id)."""
    if lignes_avant is None and tache is not None:
        lignes_avant = bon_depuis_json(tache, [], cfg).lignes
    avant = {l.id: l for l in lignes_avant or [] if l.id is not None}
    corps: dict = {"itemList": {"items": [_item(l, avant.get(l.id), cfg) for l in p.lignes]}}
    champ = cfg.get("champ_description") or "description"
    if champ.startswith("properties."):
        # On renvoie tous les champs personnalisés existants pour ne rien écraser.
        proprietes = dict((tache or {}).get("properties") or {})
        proprietes[champ.split(".", 1)[1]] = p.description
        corps["properties"] = proprietes
    else:
        corps[champ] = p.description
    return _sans_none(corps)


def _nouvelles(p: Proposition) -> list[str]:
    return [l.external_id for l in p.lignes if l.id is None and l.external_id]


def _doublon(p: Proposition, journal, progression, envoyees: dict[str, int]) -> str | None:
    """Message si une nouvelle facture de ce bon est déjà ailleurs, sinon None."""
    refacturees = journal.factures_refacturees()
    for external_id in _nouvelles(p):
        cle = external_id.rsplit("|", 1)[0]
        autre = refacturees.get(cle)
        if autre in (None, p.bon_id):
            autre = envoyees.get(cle)
        if autre in (None, p.bon_id) and progression is not None:
            autre = progression.bon_avec_ligne(external_id)
        if autre not in (None, p.bon_id):
            return f"Facture {cle.replace('|', ' ')} déjà refacturée dans le bon {autre} : rien n'a été écrit."
    return None


def envoyer(propositions: list[Proposition], progression, journal, cfg: dict,
            mode: Literal["simulation", "reel"], originaux: dict[int, list[Ligne]] | None = None) -> list[dict]:
    if mode == "reel" and not cfg.get("ecriture_validee"):
        raise ValueError("Écriture réelle verrouillée : l'essai sur un bon de test n'a pas encore été validé.")
    resultats = []
    envoyees: dict[str, int] = {}  # factures de ce lot déjà écrites (ou simulées), pour les doublons du lot

    def retenir(p):
        for external_id in _nouvelles(p):
            envoyees.setdefault(external_id.rsplit("|", 1)[0], p.bon_id)

    for p in propositions:
        if not p.maj:
            resultats.append({"bon_id": p.bon_id, "resultat": "echec",
                              "message": "Date de modification du bon inconnue : écriture refusée par prudence."})
            continue
        if journal.deja_ecrit(p.bon_id, p.maj):
            resultats.append({"bon_id": p.bon_id, "resultat": "deja_ecrit", "message": "Déjà écrit dans Progression."})
            continue
        if mode == "simulation":
            doublon = _doublon(p, journal, None, envoyees)
            if doublon:
                resultats.append({"bon_id": p.bon_id, "resultat": "doublon", "message": doublon})
                continue
            retenir(p)
            resultats.append({"bon_id": p.bon_id, "resultat": "simule", "message": "Rien n'a été écrit (simulation).",
                              "corps": corps_mise_a_jour(p, cfg, None, (originaux or {}).get(p.bon_id))})
            continue
        try:
            tache = progression.tache_brute(p.bon_id)
            if (tache.get("updated") or "") != p.maj:
                resultats.append({"bon_id": p.bon_id, "resultat": "perime",
                                  "message": "Le bon a été modifié dans Progression depuis l'analyse : à réanalyser."})
                continue
            doublon = _doublon(p, journal, progression, envoyees)
            if doublon:
                resultats.append({"bon_id": p.bon_id, "resultat": "doublon", "message": doublon})
                continue
            corps = corps_mise_a_jour(p, cfg, tache)
            progression.mettre_a_jour(p.bon_id, corps)
        except ErreurProgression as e:
            journal.inscrire("echec", p.bon_id, p.maj, {"message": str(e)})
            resultats.append({"bon_id": p.bon_id, "resultat": "echec", "message": str(e)})
            continue
        try:
            maj_apres = progression.tache_brute(p.bon_id).get("updated") or ""
        except ErreurProgression:
            maj_apres = ""
        retenir(p)
        journal.inscrire("ecrit", p.bon_id, p.maj, {
            "external_ids": _nouvelles(p),
            "maj_apres": maj_apres,
            "description_originale": p.description_originale,
            "description": p.description,
            "lignes_avant": [l.__dict__ for l in bon_depuis_json(tache, [], cfg).lignes],
            "corps": corps,
        })
        resultats.append({"bon_id": p.bon_id, "resultat": "ecrit", "message": "Écrit dans Progression."})
    return resultats
