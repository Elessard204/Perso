"""Profil de la personne (dossier ProgimRevisionBons du profil Windows) : techniciens et codes postaux, jamais partagés."""

from __future__ import annotations

import json
import re
from pathlib import Path

import cles

_CODE_POSTAL = re.compile(r"^[A-Z]\d[A-Z]\d[A-Z]\d$")


def dossier() -> Path:
    return cles.fichier().parent


def _fichier() -> Path:
    return dossier() / "techniciens.json"


def normaliser_code_postal(texte: str) -> str | None:
    """« j4w3j9 » -> « J4W 3J9 »; None si ce n'est pas un code postal canadien complet."""
    brut = re.sub(r"[\s" + chr(0xA0) + "]", "", texte or "").upper()
    if not _CODE_POSTAL.match(brut):
        return None
    return f"{brut[:3]} {brut[3:]}"


def lire_techniciens() -> dict[str, dict]:
    try:
        donnees = json.loads(_fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(donnees, dict):
        return {}
    return {
        nom: {"code_postal": str(v.get("code_postal") or ""), "paye_km": bool(v.get("paye_km"))}
        for nom, v in donnees.items() if isinstance(nom, str) and isinstance(v, dict)
    }


def ecrire_techniciens(techniciens: dict[str, dict]) -> dict[str, dict]:
    propres: dict[str, dict] = {}
    for nom, v in techniciens.items():
        nom = str(nom).strip()
        if not nom or len(nom) > 80:
            raise ValueError(f"Nom de technicien invalide : {nom[:40]!r}")
        brut = str(v.get("code_postal") or "").strip()
        code = normaliser_code_postal(brut) if brut else ""
        if code is None:
            raise ValueError(f"Code postal invalide pour {nom} : {brut}")
        propres[nom] = {"code_postal": code, "paye_km": bool(v.get("paye_km"))}
    f = _fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(propres, indent=2, ensure_ascii=False), encoding="utf-8")
    return propres
