import runpy
import sys

from conftest import LOGICIEL


def test_prepare_les_modules_puis_ouvre_l_interface(monkeypatch):
    appels = []
    import dependances
    monkeypatch.setattr(dependances, "preparer", lambda roues, manifeste=None: appels.append(("preparer", roues.name, manifeste.name)))
    vrai_run_path = runpy.run_path
    monkeypatch.setattr(runpy, "run_path", lambda chemin, run_name=None: appels.append(("ouvrir", chemin.rsplit("/", 1)[-1].rsplit("\\", 1)[-1], run_name)))
    monkeypatch.setattr(sys, "platform", "win32")
    vrai_run_path(str(LOGICIEL / "demarrer.py"), run_name="__main__")
    assert appels == [("preparer", "roues", "roues.toml"), ("ouvrir", "interface.py", "__main__")]


def test_interface_ne_prepare_plus_elle_meme():
    assert "dependances" not in (LOGICIEL / "interface.py").read_text(encoding="utf-8")


def test_cache_de_python_dans_le_profil(monkeypatch, tmp_path):
    # Le lanceur passe -B (rien d'écrit dans OneDrive) : sans cache ailleurs, chaque lancement recompile tout le SDK.
    import dependances
    monkeypatch.setattr(dependances, "preparer", lambda roues, manifeste=None: None)
    monkeypatch.setattr(dependances, "dossier_profil", lambda: tmp_path / "profil")
    vrai_run_path = runpy.run_path
    monkeypatch.setattr(runpy, "run_path", lambda chemin, run_name=None: None)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(sys, "pycache_prefix", None)
    vrai_run_path(str(LOGICIEL / "demarrer.py"), run_name="__main__")
    assert sys.dont_write_bytecode is False
    assert sys.pycache_prefix == str(tmp_path / "profil" / "pycache")
