"""Essai d'écriture sur UN bon de test, avant de déverrouiller l'écriture réelle.

Usage : python essai_ecriture.py --bon <id> --client-test "<nom exact du client fictif>"
Ajoute une ligne « Essai révision » au bon de test en renvoyant la liste complète des lignes,
relit le bon et vérifie que les lignes d'origine sont toujours là, sans doublon.
Refuse tout bon dont le client n'est pas le client de test.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path

import cles
from envoi import corps_mise_a_jour
from modele import Ligne, Proposition
from progression import ErreurProgression, Progression, bon_depuis_json

ICI = Path(__file__).resolve().parent


def essai_ecriture(prog, bon_id: int, client_test: str) -> dict:
    tache = prog.tache_brute(bon_id)
    client = ((tache.get("client") or {}).get("label") or "").strip()
    if client != client_test.strip():
        raise ValueError(f"Le bon {bon_id} appartient à « {client} », pas au client de test : essai refusé.")
    bon = bon_depuis_json(tache, [], {})
    avant = [l.id for l in bon.lignes]
    essai = Ligne(None, "Essai révision", "Ligne d'essai de l'outil de révision des bons", 1, 0.01, 0.01, None,
                  f"essai-revision|{datetime.now():%Y%m%d%H%M%S}")
    p = Proposition(bon_id, bon.maj, bon.description, bon.description, bon.lignes + [essai])
    prog.mettre_a_jour(bon_id, corps_mise_a_jour(p, {"champ_description": "description"}, tache))
    apres = [it.get("id") for it in (prog.tache_brute(bon_id).get("itemList") or {}).get("items") or []]
    doublons = [i for i, n in Counter(apres).items() if n > 1]
    manquantes = [i for i in avant if i not in apres]
    valide = not doublons and not manquantes and len(apres) == len(avant) + 1
    if valide:
        message = "Essai réussi : lignes d'origine conservées, une seule ligne ajoutée. On peut passer ecriture_validee = true."
    elif doublons or len(apres) > len(avant) + 1:
        message = "Échec : des lignes ont été mises en double. Ne pas déverrouiller l'écriture; revoir envoi.corps_mise_a_jour."
    else:
        message = f"Échec : lignes d'origine disparues ({manquantes}). Ne pas déverrouiller l'écriture."
    return {"valide": valide, "lignes_avant": len(avant), "lignes_apres": len(apres), "message": message}


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
        resultat = essai_ecriture(Progression(cle, cfg["base"], cfg=cfg), args.bon, args.client_test)
    except (ValueError, ErreurProgression) as e:
        print(e)
        return 1
    print(f"Lignes avant : {resultat['lignes_avant']}, après : {resultat['lignes_apres']}")
    print(resultat["message"])
    return 0 if resultat["valide"] else 1


if __name__ == "__main__":
    sys.exit(main())
