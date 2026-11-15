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


import hashlib
import io
import urllib.error

import pytest


def octets_roue(fichiers):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for chemin, contenu in fichiers.items():
            z.writestr(chemin, contenu)
    return tampon.getvalue()


def manifeste(dossier, entrees):
    texte = "".join(f'[[roue]]\nnom = "{n}"\nurl = "https://exemple.test/{n}"\nsha256 = "{s}"\n\n' for n, s in entrees)
    (dossier / "roues.toml").write_text(texte, encoding="utf-8")
    return dossier / "roues.toml"


class Reseau:
    def __init__(self, contenus):
        self.contenus, self.appels = contenus, []

    def __call__(self, url, timeout=None):
        self.appels.append(url)
        if url not in self.contenus:
            raise urllib.error.URLError("hors ligne")
        return io.BytesIO(self.contenus[url])


def test_telecharge_selon_le_manifeste(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    data = octets_roue({"tele_mod/__init__.py": "OK = True\n"})
    m = manifeste(tmp_path, [("tele_mod-1.0-py3-none-any.whl", hashlib.sha256(data).hexdigest())])
    reseau = Reseau({"https://exemple.test/tele_mod-1.0-py3-none-any.whl": data})
    cible = preparer(tmp_path / "absent", tmp_path / "profil", manifeste=m, ouvrir=reseau)
    import tele_mod
    assert tele_mod.OK and str(cible) == sys.path[0]
    preparer(tmp_path / "absent", tmp_path / "profil", manifeste=m, ouvrir=reseau)
    assert len(reseau.appels) == 1   # déjà téléchargé : rien à refaire


def test_empreinte_incorrecte_refusee(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    m = manifeste(tmp_path, [("x-1.0-py3-none-any.whl", "0" * 64)])
    reseau = Reseau({"https://exemple.test/x-1.0-py3-none-any.whl": octets_roue({"x/__init__.py": ""})})
    with pytest.raises(RuntimeError, match="empreinte"):
        preparer(tmp_path / "absent", tmp_path / "profil", manifeste=m, ouvrir=reseau)
    assert not list((tmp_path / "profil").glob("modules-*/x"))


def test_reseau_indisponible_message_clair(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    m = manifeste(tmp_path, [("x-1.0-py3-none-any.whl", "0" * 64)])
    with pytest.raises(RuntimeError, match="télécharger"):
        preparer(tmp_path / "absent", tmp_path / "profil", manifeste=m, ouvrir=Reseau({}))


def test_manifeste_reel_coherent():
    import tomllib
    from conftest import LOGICIEL
    roues = tomllib.loads((LOGICIEL / "roues.toml").read_text(encoding="utf-8"))["roue"]
    assert len(roues) == 16 and all(r["url"].startswith("https://files.pythonhosted.org/") for r in roues)
    assert all(len(r["sha256"]) == 64 for r in roues)
    assert any(r["nom"].startswith("anthropic-2.8.0") for r in roues)
