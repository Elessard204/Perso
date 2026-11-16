import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_logiciel"))

from excel import ecrire_xlsx, export_periode, h_mm  # noqa: E402

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _lignes(z, n):
    racine = ET.fromstring(z.read(f"xl/worksheets/sheet{n}.xml"))
    lignes = []
    for r in racine.iter(f"{{{NS['m']}}}row"):
        ligne = []
        for c in r:
            if c.get("t") == "inlineStr":
                ligne.append("".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t")))
            else:
                v = c.find("m:v", NS)
                ligne.append(float(v.text) if v is not None else None)
        lignes.append(ligne)
    return lignes


def _jour(j, km, minutes_, codes=("B1",)):
    return {"jour": j, "arrets": [{"code": c, "tache_id": 1} for c in codes], "km": km, "uhaul": False,
            "magasin_km": 0.0, "km_paye": km, "a_verifier": [], "minutes": minutes_}


def _periode():
    return {
        "debut": "2026-11-08", "fin": "2026-11-21", "taux": 0.61, "seuil_km": 10, "statut": "valide",
        "revision": 1, "valide_par": "Hugo", "valide_le": "2026-11-23",
        "techniciens": [
            {"nom": "Toufik", "paie": False, "statut": "sous_traitant", "minutes_par_jour": {"2026-11-10": 60},
             "minutes_total": 60, "km_a_payer": 0.0, "montant": None, "details": []},
            {"nom": "Vadim", "paie": True, "statut": "ok",
             "minutes_par_jour": {"2026-11-10": 300, "2026-11-11": 240, "2026-11-17": 120},
             "minutes_total": 660, "km_a_payer": 112.0, "montant": 68.32,
             "details": [_jour("2026-11-10", 60.0, 300, ("B1", "B2")), _jour("2026-11-11", 52.0, 240),
                         _jour("2026-11-17", 0.0, 120)]},
        ],
    }


def test_xlsx_valide():
    contenu = ecrire_xlsx({"Sommaire": [["Nom", "Km"], ["Vadim & fils <test>", 112.5]]})
    z = zipfile.ZipFile(io.BytesIO(contenu))
    assert "xl/worksheets/sheet1.xml" in z.namelist() and "[Content_Types].xml" in z.namelist()
    feuille = z.read("xl/worksheets/sheet1.xml").decode()
    assert "Vadim &amp; fils &lt;test&gt;" in feuille and "<v>112.5</v>" in feuille
    for nom in z.namelist():
        ET.fromstring(z.read(nom))
    types = z.read("[Content_Types].xml").decode()
    for p in ("/xl/workbook.xml", "/xl/worksheets/sheet1.xml", "/xl/styles.xml"):
        assert p in types


def test_nom_feuille_tronque():
    z = zipfile.ZipFile(io.BytesIO(ecrire_xlsx({"x" * 40: [["a"]]})))
    assert 'name="' + "x" * 31 + '"' in z.read("xl/workbook.xml").decode()


def test_export_feuille_de_temps():
    contenu, nom = export_periode(_periode())
    assert nom == "Feuille de temps et km 2026-11-08 au 2026-11-21 (revise 1).xlsx"
    z = zipfile.ZipFile(io.BytesIO(contenu))
    wb = z.read("xl/workbook.xml").decode()
    for n in ("Semaine du 2026-11-08", "Semaine du 2026-11-15", "Détail"):
        assert f'name="{n}"' in wb
    s1 = _lignes(z, 1)
    assert s1[0][0] == "Semaine du 2026-11-08 - 2026-11-14"
    assert s1[1] == ["Ressource humaine", "Dim.", "Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Total",
                     "Km à payer", "Montant km ($)"]
    vadim = next(r for r in s1 if r[0] == "Vadim")
    assert vadim[3] == "5:00" and vadim[4] == "4:00" and vadim[1] == "0:00" and vadim[8] == "9:00"
    assert vadim[9] == 112 and vadim[10] == 68.32
    assert all(r[0] != "Toufik" for r in s1) and s1[-1][0] == "Total"
    s2 = _lignes(z, 2)
    vadim2 = next(r for r in s2 if r[0] == "Vadim")
    assert vadim2[3] == "2:00" and vadim2[9] == 0
    detail = _lignes(z, 3)
    assert detail[0] == ["Technicien", "Jour", "Trajet", "Km calculé", "Uhaul", "Km magasin", "Km payé",
                         "À vérifier"]
    assert detail[1][2] == "B1 → B2"


def test_export_brouillon_sans_revision():
    p = _periode()
    p.update(statut="brouillon", revision=0)
    _, nom = export_periode(p)
    assert nom == "Feuille de temps et km 2026-11-08 au 2026-11-21.xlsx"


def test_h_mm():
    assert [h_mm(m) for m in (0, 59.6, 405, 404.6, 600)] == ["0:00", "1:00", "6:45", "6:45", "10:00"]
