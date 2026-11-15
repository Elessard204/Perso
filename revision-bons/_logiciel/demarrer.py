"""Point de départ de l'outil : prépare les modules de l'IA au besoin, puis ouvre l'interface."""

import runpy
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

if sys.platform == "win32":
    # Python portable sans pip : les modules du SDK de Claude sont téléchargés et vérifiés au premier lancement.
    import dependances

    # Le lanceur interdit le cache de Python (option -B) pour ne rien écrire dans OneDrive. On le remet, mais dans le
    # profil Windows : sans lui, chaque lancement retraduit tout le SDK de Claude (long, surtout avec l'antivirus).
    sys.pycache_prefix = str(dependances.dossier_profil() / "pycache")
    sys.dont_write_bytecode = False

    print("Vérification des modules de l'IA (le premier lancement peut prendre une minute)...")
    try:
        dependances.preparer(ICI / "roues", manifeste=ICI / "roues.toml")
    except RuntimeError as erreur:
        print(f"Module de l'IA indisponible : {erreur}")
    print("Ouverture de l'outil (au premier lancement, Python prépare ses fichiers : quelques minutes au plus)...")

runpy.run_path(str(ICI / "interface.py"), run_name="__main__")
