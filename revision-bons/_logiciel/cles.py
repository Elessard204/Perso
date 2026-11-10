"""Clés API de la personne, gardées dans son profil Windows (jamais dans le dossier partagé)."""

from __future__ import annotations

import json
import os
from pathlib import Path

NOMS = ("progression", "claude")


def fichier() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "ProgimRevisionBons" / "cles.json"


def lire() -> dict[str, str]:
    try:
        donnees = json.loads(fichier().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in donnees.items() if k in NOMS and isinstance(v, str) and v}


def ecrire(progression: str | None, claude: str | None) -> None:
    """Enregistre les clés fournies; None laisse la clé existante en place."""
    actuelles = lire()
    for nom, valeur in (("progression", progression), ("claude", claude)):
        if valeur is not None:
            actuelles[nom] = valeur.strip()
    f = fichier()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(actuelles, indent=2), encoding="utf-8")


def etat() -> dict[str, bool]:
    """Seulement « configurée ou non » : la page ne reçoit jamais la clé elle-même."""
    actuelles = lire()
    return {nom: bool(actuelles.get(nom)) for nom in NOMS}
