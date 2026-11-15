"""Modules Python livrés avec l'outil (dossier « roues ») et décompressés au premier lancement.

Le Python portable de Progim n'a pas pip : les modules du SDK de Claude, compilés pour Windows 64 bits et
Python 3.12, sont fournis en fichiers .whl (des archives zip) et décompressés avec la bibliothèque standard
dans le profil Windows de la personne. Une nouvelle série de roues crée un nouveau dossier.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path


def dossier_profil() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "ProgimRevisionBons"


def preparer(roues: Path, profil: Path | None = None) -> Path | None:
    """Décompresse les roues au besoin et ajoute leur dossier en tête du chemin des modules."""
    fichiers = sorted(Path(roues).glob("*.whl"))
    if not fichiers:
        return None
    empreinte = hashlib.sha1("|".join(f"{f.name}:{f.stat().st_size}" for f in fichiers).encode()).hexdigest()[:10]
    cible = Path(profil or dossier_profil()) / f"modules-{empreinte}"
    if not (cible / ".complet").exists():
        temporaire = cible.with_name(cible.name + ".tmp")
        shutil.rmtree(temporaire, ignore_errors=True)
        temporaire.mkdir(parents=True)
        for f in fichiers:
            with zipfile.ZipFile(f) as z:
                z.extractall(temporaire)
        (temporaire / ".complet").write_text("ok", encoding="utf-8")
        shutil.rmtree(cible, ignore_errors=True)
        temporaire.rename(cible)
    if str(cible) not in sys.path:
        sys.path.insert(0, str(cible))
    return cible
