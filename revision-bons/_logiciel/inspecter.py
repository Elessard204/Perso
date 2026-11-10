"""Inspection en LECTURE SEULE de quelques vrais bons, pour compléter config.toml.

Usage : python inspecter.py --nombre 10
Écrit cache/inspection.txt. Ne modifie rien dans Progression (requêtes GET seulement).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cles
from progression import ErreurProgression, Progression, minutes_iso

ICI = Path(__file__).resolve().parent
ETATS_TERMINES = ">599"   # états 600 et plus = travaux complétés


def _texte(valeur, limite: int = 300) -> str:
    texte = " ".join(str(valeur).split())
    return texte if len(texte) <= limite else texte[:limite] + "…"


def rapport_inspection(prog: Progression, nombre: int) -> str:
    lignes: list[str] = []
    for resume in prog.lister_recents(ETATS_TERMINES, nombre):
        tache, entrees = prog.lire_tache(resume["id"])
        etat = tache.get("currentState") or {}
        type_ = tache.get("type") or {}
        lignes += [
            "=" * 70,
            f"Bon {tache.get('code')} (id {tache.get('id')})  mis à jour {tache.get('updated')}",
            f"État : {etat.get('label')} logicId={etat.get('logicId')}   "
            f"Type : {type_.get('label')} code={type_.get('code')}",
            "-- Champs texte non vides",
        ]
        for champ in ("description", "summary"):
            if tache.get(champ):
                lignes.append(f"  {champ}: {_texte(tache[champ])}")
        for nom, valeur in (tache.get("properties") or {}).items():
            if valeur not in (None, "", [], {}):
                lignes.append(f"  properties.{nom}: {_texte(valeur)}")
        lignes.append("-- Lignes facturables")
        for it in (tache.get("itemList") or {}).get("items") or []:
            produit = it.get("product") or {}
            lignes.append(
                f"  id={it.get('id')} label={_texte(it.get('label'), 60)} "
                f"type={(it.get('type') or {}).get('label')} product={produit.get('code') or produit.get('label')} "
                f"quantity={it.get('quantity')} price={it.get('price')} unitCost={it.get('unitCost')} "
                f"externalId={it.get('externalId')}")
        lignes.append("-- Entrées de temps")
        for e in entrees:
            lignes.append(
                f"  {(e.get('humanResource') or {}).get('label')} : {minutes_iso(e.get('duration') or ''):g} min "
                f"le {(e.get('start') or '')[:10]}  item={(e.get('item') or {}).get('id')}")
        lignes.append("-- Pièces jointes")
        for a in tache.get("attachments") or []:
            lignes.append(f"  id={a.get('id')} {a.get('name')} ({a.get('contentType')})")
    return "\n".join(lignes) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", type=int, default=10)
    args = parser.parse_args()
    cle = cles.lire().get("progression")
    if not cle:
        print(f"Aucune clé Progression dans {cles.fichier()}.")
        return 1
    try:
        texte = rapport_inspection(Progression(cle), args.nombre)
    except ErreurProgression as e:
        print(e)
        return 1
    sortie = ICI / "cache" / "inspection.txt"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(texte, encoding="utf-8")
    print(f"Rapport écrit : {sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
