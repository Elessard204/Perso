import cles
import profil
import pytest


def test_normaliser_code_postal():
    assert profil.normaliser_code_postal("j4w3j9") == "J4W 3J9"
    assert profil.normaliser_code_postal(" J4W 3J9 ") == "J4W 3J9"
    assert profil.normaliser_code_postal("J4W") is None
    assert profil.normaliser_code_postal("") is None


def test_techniciens_aller_retour(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    ecrit = profil.ecrire_techniciens({"Vadim Zubco": {"code_postal": "h1a1a1", "paye_km": True},
                                       "Hugo": {"code_postal": "", "paye_km": False}})
    assert ecrit["Vadim Zubco"] == {"code_postal": "H1A 1A1", "paye_km": True}
    assert profil.lire_techniciens() == ecrit
    assert (tmp_path / "ProgimRevisionBons" / "techniciens.json").exists()


def test_techniciens_absent_ou_illisible(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert profil.lire_techniciens() == {}
    (tmp_path / "ProgimRevisionBons").mkdir()
    (tmp_path / "ProgimRevisionBons" / "techniciens.json").write_text("{pas du json", encoding="utf-8")
    assert profil.lire_techniciens() == {}


def test_code_postal_invalide_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    with pytest.raises(ValueError, match="Vadim"):
        profil.ecrire_techniciens({"Vadim": {"code_postal": "J4W", "paye_km": True}})


def test_nom_invalide_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    with pytest.raises(ValueError):
        profil.ecrire_techniciens({"  ": {"code_postal": "", "paye_km": False}})
    with pytest.raises(ValueError):
        profil.ecrire_techniciens({"x" * 81: {"code_postal": "", "paye_km": False}})


def test_cle_google(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cles.ecrire(None, None, google="AIza-test")
    assert cles.lire()["google"] == "AIza-test" and cles.etat()["google"] is True
