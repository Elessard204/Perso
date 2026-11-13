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
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import cles
from envoi import corps_mise_a_jour
from modele import Ligne, Proposition
from progression import ErreurProgression, Progression, bon_depuis_json

ICI = Path(__file__).resolve().parent


CALCULES = {"total", "cost", "margin", "profit", "unitProfit", "created", "updated", "url", "removed"}


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

    # Progression recrée toutes les lignes (nouveaux ids) : on compare le contenu, pas les ids.
    items_avant, items_apres = _items(avant), _items(apres)
    net = lambda i: {k: v for k, v in i.items() if k not in CALCULES | {"id", "uid"}}
    attendus = [net(i) for i in items_avant]
    if attendus:
        attendus[0]["quantity"] = lignes[0].quantite
    restants = [net(i) for i in items_apres]
    problemes = []
    if len(items_apres) > len(items_avant) + 1:
        problemes.append("des lignes ont été mises en double")
    for original, attendu in zip(items_avant, attendus):
        if attendu in restants:
            restants.remove(attendu)
            continue
        proche = next((r for r in restants if r.get("label") == attendu.get("label")), None)
        if proche is None:
            problemes.append(f"la ligne « {original.get('label')} » a disparu")
        else:
            differents = sorted(k for k in set(attendu) | set(proche) if attendu.get(k) != proche.get(k))
            problemes.append(f"la ligne « {original.get('label')} » a été modifié au-delà de la demande "
                             f"({', '.join(differents)})")
            restants.remove(proche)
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
