import copy

import pytest

from essai_ecriture import essai_ecriture
from test_progression import TACHE

CLIENT_TEST = "Client TEST Progim"


class FausseProgression:
    """Simule deux comportements possibles de Progression pour itemList."""

    def __init__(self, client=CLIENT_TEST, comportement="remplace"):
        self.tache = copy.deepcopy(TACHE)
        self.tache["client"] = {"label": client}
        self.comportement = comportement
        self.ecrits = []

    def tache_brute(self, identifiant):
        return copy.deepcopy(self.tache)

    def mettre_a_jour(self, identifiant, corps):
        self.ecrits.append(corps)
        envoyes = corps["itemList"]["items"]
        if self.comportement == "remplace":
            self.tache["itemList"]["items"] = [dict(i, id=i.get("id") or 999) for i in envoyes]
        elif self.comportement == "ajoute":
            self.tache["itemList"]["items"] += [dict(i, id=i.get("id") or 999) for i in envoyes]
        return {}


def test_refuse_un_vrai_client():
    prog = FausseProgression(client="Gestion Fictive inc.")
    with pytest.raises(ValueError, match="client de test"):
        essai_ecriture(prog, 1001, CLIENT_TEST)
    assert prog.ecrits == []


def test_comportement_remplace_valide():
    r = essai_ecriture(FausseProgression(comportement="remplace"), 1001, CLIENT_TEST)
    assert r["valide"] is True
    assert r["lignes_avant"] == 2 and r["lignes_apres"] == 3


def test_comportement_ajoute_detecte_les_doublons():
    r = essai_ecriture(FausseProgression(comportement="ajoute"), 1001, CLIENT_TEST)
    assert r["valide"] is False and "double" in r["message"]


def test_ligne_d_essai_marquee():
    prog = FausseProgression()
    essai_ecriture(prog, 1001, CLIENT_TEST)
    nouvelle = prog.ecrits[0]["itemList"]["items"][-1]
    assert nouvelle["externalId"].startswith("essai-revision|") and "id" not in nouvelle
    assert [i["id"] for i in prog.ecrits[0]["itemList"]["items"][:2]] == [501, 502]
