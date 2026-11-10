import json
from pathlib import Path

from inspecter import rapport_inspection
from progression import Progression
from test_progression import ENTREES, TACHE, FauxHttp


def test_rapport_lecture_seule_et_complet():
    http = FauxHttp([[TACHE], TACHE, ENTREES])
    texte = rapport_inspection(Progression("c", ouvrir=http), nombre=10)
    assert all(r.get_method() == "GET" for r in http.requetes)
    for attendu in ["BS-1001", "logicId=600", "description:", "properties.notesTech:",
                    "MO-PLOMB", "quantity=2.0833", "unitCost=40.0", "Luc Tremblay", "80 min", "item=501",
                    "facture_rona.pdf", "application/pdf"]:
        assert attendu in texte, attendu


def test_aucune_ecriture_dans_le_script():
    source = (Path(__file__).parent.parent / "_logiciel" / "inspecter.py").read_text(encoding="utf-8")
    assert "mettre_a_jour" not in source and '"POST"' not in source
