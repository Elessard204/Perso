"""Point de départ de l'outil : prépare les modules de l'IA au besoin, puis ouvre l'interface."""

import runpy
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

if sys.platform == "win32":
    # Python portable sans pip : les modules du SDK de Claude sont téléchargés et vérifiés au premier lancement.
    import dependances

    print("Vérification des modules de l'IA (le premier lancement peut prendre une minute)...")
    try:
        dependances.preparer(ICI / "roues", manifeste=ICI / "roues.toml")
    except RuntimeError as erreur:
        print(f"Module de l'IA indisponible : {erreur}")

runpy.run_path(str(ICI / "interface.py"), run_name="__main__")
