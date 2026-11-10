"""Essai d'écriture sur UN bon de test, avant de déverrouiller l'écriture réelle.

Usage : python essai_ecriture.py --bon <id> --client-test "<nom exact du client fictif>"
Écrit sur le bon de test exactement comme l'outil le fera : +1 sur la quantité de la première ligne
et une ligne « Essai révision ». Relit le bon et vérifie que rien d'autre n'a changé (aucune ligne
perdue, doublée ou altérée, externalId conservé, properties intactes).
Refuse tout bon dont le client n'est pas le client de test.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import cles
from envoi import corps_mise_a_jour
from modele import Ligne, Proposition
from progression import ErreurProgression, Progression, bon_depuis_json

ICI = Path(__file__).resolve().parent


CALCULES = {"total", "cost", "margin", "profit", "unitProfit", "created", "updated", "url"}


def _items(tache: dict) -> list[dict]:
    return (tache.get("itemList") or {}).get("items") or []


def essai_ecriture(prog, bon_id: int, client_test: str, cfg: dict) -> dict:
    """Écrit sur le bon de test exactement comme l'outil le fera, puis vérifie tout ce qui a changé."""
    avant = prog.tache_brute(bon_id)
    client = ((avant.get("client") or {}).get("label") or "").strip()
    if client != client_test.strip():
        raise ValueError(f"Le bon {bon_id} appartient à « {client} », pas au client de test : essai refusé.")
    bon = bon_depuis_json(avant, [], cfg)
    lignes = [replace(l) for l in bon.lignes]
    if lignes:
        lignes[0].quantite = round(lignes[0].quantite + 1, 4)   # on vérifie aussi la modification d'une ligne
    essai = Ligne(None, "Essai révision", "Ligne d'essai de l'outil de révision des bons", 1, 0.01, 0.01, None,
                  f"essai-revision|{datetime.now():%Y%m%d%H%M%S}")
    p = Proposition(bon_id, bon.maj, bon.description, bon.description, lignes + [essai])
    prog.mettre_a_jour(bon_id, corps_mise_a_jour(p, cfg, avant))
    apres = prog.tache_brute(bon_id)

    items_avant, items_apres = _items(avant), _items(apres)
    ids = [i.get("id") for i in items_apres]
    problemes = []
    if [i for i, n in Counter(ids).items() if n > 1] or len(items_apres) > len(items_avant) + 1:
        problemes.append("des lignes ont été mises en double")
    par_id = {i.get("id"): i for i in items_apres}
    for n, original in enumerate(items_avant):
        actuel = par_id.get(original.get("id"))
        if actuel is None:
            problemes.append(f"la ligne {original.get('id')} a disparu")
            continue
        attendu = dict(original, quantity=lignes[0].quantite) if n == 0 else original
        differents = sorted(k for k in set(attendu) | set(actuel)
                            if k not in CALCULES and attendu.get(k) != actuel.get(k))
        if differents:
            problemes.append(f"la ligne {original.get('id')} a été modifié au-delà de la demande ({', '.join(differents)})")
    if not any(i.get("externalId") == essai.external_id for i in items_apres):
        problemes.append("l'externalId de la nouvelle ligne n'a pas été conservé")
    champ = cfg.get("champ_description") or "description"
    if champ.startswith("properties."):
        nom = champ.split(".", 1)[1]
        perdues = [k for k, v in (avant.get("properties") or {}).items()
                   if k != nom and (apres.get("properties") or {}).get(k) != v]
        if perdues:
            problemes.append(f"des properties ont été écrasées ({', '.join(perdues)})")

    valide = not problemes
    message = ("Essai réussi : lignes d'origine intactes, quantité modifiée, une seule ligne ajoutée avec son "
               "externalId. On peut passer ecriture_validee = true."
               if valide else "Échec : " + "; ".join(problemes) + ". Ne pas déverrouiller l'écriture.")
    return {"valide": valide, "lignes_avant": len(items_avant), "lignes_apres": len(items_apres), "message": message}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bon", type=int, required=True)
    parser.add_argument("--client-test", required=True)
    args = parser.parse_args()
    cle = cles.lire().get("progression")
    if not cle:
        print(f"Aucune clé Progression dans {cles.fichier()}.")
        return 1
    cfg = tomllib.loads((ICI / "config.toml").read_text(encoding="utf-8"))["progression"]
    try:
        resultat = essai_ecriture(Progression(cle, cfg["base"], cfg=cfg), args.bon, args.client_test, cfg)
    except (ValueError, ErreurProgression) as e:
        print(e)
        return 1
    print(f"Lignes avant : {resultat['lignes_avant']}, après : {resultat['lignes_apres']}")
    print(resultat["message"])
    return 0 if resultat["valide"] else 1


if __name__ == "__main__":
    sys.exit(main())
