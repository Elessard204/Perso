import sys
import zipfile

from dependances import preparer


def roue(dossier, nom, fichiers):
    with zipfile.ZipFile(dossier / nom, "w") as z:
        for chemin, contenu in fichiers.items():
            z.writestr(chemin, contenu)


def test_decompresse_puis_ajoute_au_chemin(tmp_path, monkeypatch):
    roues, profil = tmp_path / "roues", tmp_path / "profil"
    roues.mkdir()
    roue(roues, "abc_mod-1.0-py3-none-any.whl", {"abc_mod/__init__.py": "VALEUR = 42\n"})
    monkeypatch.setattr(sys, "path", list(sys.path))
    cible = preparer(roues, profil)
    assert (cible / "abc_mod" / "__init__.py").exists() and str(cible) == sys.path[0]
    import abc_mod
    assert abc_mod.VALEUR == 42


def test_deja_decompresse_rien_a_refaire(tmp_path, monkeypatch):
    roues, profil = tmp_path / "roues", tmp_path / "profil"
    roues.mkdir()
    roue(roues, "x-1.0-py3-none-any.whl", {"x/__init__.py": ""})
    monkeypatch.setattr(sys, "path", list(sys.path))
    cible = preparer(roues, profil)
    (cible / "x" / "__init__.py").write_text("# touché")
    assert preparer(roues, profil) == cible
    assert (cible / "x" / "__init__.py").read_text() == "# touché"   # pas redécompressé


def test_nouvelle_version_nouveau_dossier(tmp_path, monkeypatch):
    roues, profil = tmp_path / "roues", tmp_path / "profil"
    roues.mkdir()
    roue(roues, "x-1.0-py3-none-any.whl", {"x/__init__.py": ""})
    monkeypatch.setattr(sys, "path", list(sys.path))
    a = preparer(roues, profil)
    roue(roues, "y-2.0-py3-none-any.whl", {"y/__init__.py": ""})
    assert preparer(roues, profil) != a


def test_sans_roues_ne_fait_rien(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    assert preparer(tmp_path / "absent", tmp_path / "profil") is None


def test_roues_reelles_presentes():
    from conftest import LOGICIEL
    noms = sorted(p.name for p in (LOGICIEL / "roues").glob("*.whl"))
    assert any(n.startswith("anthropic-") for n in noms)
    assert any("pydantic_core" in n and "cp312-win_amd64" in n for n in noms)
