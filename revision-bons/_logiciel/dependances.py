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
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


def dossier_profil() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "ProgimRevisionBons"


def telecharger(manifeste: Path, dossier: Path, ouvrir=urllib.request.urlopen) -> list[Path]:
    """Télécharge les roues du manifeste qui manquent, en vérifiant l'empreinte sha256 de chacune."""
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = []
    for roue in tomllib.loads(Path(manifeste).read_text(encoding="utf-8"))["roue"]:
        chemin = dossier / roue["nom"]
        if not chemin.exists() or hashlib.sha256(chemin.read_bytes()).hexdigest() != roue["sha256"]:
            try:
                with ouvrir(roue["url"], timeout=120) as reponse:
                    contenu = reponse.read()
            except (urllib.error.URLError, OSError) as e:
                raise RuntimeError(f"Impossible de télécharger {roue['nom']} : vérifier la connexion Internet "
                                   "et relancer l'outil.") from e
            if hashlib.sha256(contenu).hexdigest() != roue["sha256"]:
                raise RuntimeError(f"{roue['nom']} : empreinte inattendue, fichier refusé par sécurité.")
            chemin.write_bytes(contenu)
        fichiers.append(chemin)
    return fichiers


def preparer(roues: Path, profil: Path | None = None, manifeste: Path | None = None,
             ouvrir=urllib.request.urlopen) -> Path | None:
    """Décompresse les roues au besoin et ajoute leur dossier en tête du chemin des modules.

    Les roues viennent du dossier « roues » s'il en contient, sinon elles sont téléchargées selon le manifeste
    (roues.toml) dans le profil Windows de la personne.
    """
    profil = Path(profil or dossier_profil())
    fichiers = sorted(Path(roues).glob("*.whl"))
    if not fichiers and manifeste is not None and Path(manifeste).exists():
        fichiers = telecharger(manifeste, profil / "roues", ouvrir)
    if not fichiers:
        return None
    empreinte = hashlib.sha1("|".join(f"{f.name}:{f.stat().st_size}" for f in fichiers).encode()).hexdigest()[:10]
    cible = profil / f"modules-{empreinte}"
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
