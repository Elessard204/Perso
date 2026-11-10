import json

import cles


def test_ecrire_puis_lire(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert cles.lire() == {}
    cles.ecrire(progression="p-1", claude=None)
    cles.ecrire(progression=None, claude="c-2")   # None = ne pas toucher
    assert cles.lire() == {"progression": "p-1", "claude": "c-2"}
    assert (tmp_path / "ProgimRevisionBons" / "cles.json").exists()


def test_fichier_corrompu(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    (tmp_path / "ProgimRevisionBons").mkdir()
    (tmp_path / "ProgimRevisionBons" / "cles.json").write_text("{pas du json")
    assert cles.lire() == {}


def test_etat_ne_revele_pas_les_cles(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cles.ecrire(progression="secret-p", claude=None)
    assert cles.etat() == {"progression": True, "claude": False}
    assert "secret" not in json.dumps(cles.etat())
