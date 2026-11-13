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


# Champs d'une ligne que Progression calcule ou attribue : jamais renvoyés.
LECTURE_SEULE = {"id", "uid", "url", "total", "cost", "margin", "profit", "unitProfit", "created", "updated", "removed"}


def _nouvelle_ligne(ligne: Ligne, cfg: dict) -> dict:
    item = {nom: getattr(ligne, attribut) for attribut, nom in CHAMPS}
    item["externalId"] = ligne.external_id
    if cfg.get("produit_materiel"):
        item["product"] = {"code": cfg["produit_materiel"]}
    return item


def _ligne_existante(ligne: Ligne, brute: dict, cfg: dict) -> dict:
    """La ligne telle que Progression l'a renvoyée (tous ses champs), avec seulement nos changements par-dessus."""
    item = {k: v for k, v in brute.items() if k not in LECTURE_SEULE}
    lue = bon_depuis_json({"id": 0, "itemList": {"items": [brute]}}, [], cfg).lignes[0]
    for attribut, nom in CHAMPS:
        if getattr(ligne, attribut) != getattr(lue, attribut):
            item[nom] = getattr(ligne, attribut)
    return item


def corps_mise_a_jour(p: Proposition, cfg: dict, tache: dict | None,
                      lignes_avant: list[Ligne] | None = None) -> dict:
    """Description révisée + liste COMPLÈTE des lignes.

    Progression supprime toutes les lignes du bon et les recrée à partir de la liste reçue
    (confirmé par Progression le 2026-11-11). Chaque ligne existante est donc renvoyée au complet,
    et une ligne existante absente de la proposition est refusée : elle serait effacée.
    """
    if tache is not None:
        brutes = {i.get("id"): i for i in (tache.get("itemList") or {}).get("items") or [] if i.get("id") is not None}
        manquantes = [i for i in brutes if i not in {l.id for l in p.lignes}]
        if manquantes:
            raise ValueError(f"Ligne(s) {', '.join(map(str, manquantes))} du bon absente(s) de la proposition : "
                             "l'écriture les effacerait.")
        items = []
        for l in p.lignes:
            if l.id is None:
                items.append(_nouvelle_ligne(l, cfg))
            elif l.id in brutes:
                items.append(_ligne_existante(l, brutes[l.id], cfg))
            else:
                raise ValueError(f"Ligne {l.id} introuvable dans le bon actuel : réanalyser le bon.")
    else:
        # Simulation sans réseau : on montre ce qu'on connaît des lignes.
        items = []
        for l in p.lignes:
            item = _nouvelle_ligne(l, cfg) if l.id is None else {nom: getattr(l, a) for a, nom in CHAMPS}
            if l.id is not None and l.produit:
                item["product"] = {"code": l.produit}
            if l.id is not None and l.external_id:
                item["externalId"] = l.external_id
            items.append(item)
    corps: dict = {"itemList": {"items": items}}
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
        except (ErreurProgression, ValueError) as e:
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
