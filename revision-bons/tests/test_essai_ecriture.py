import copy

import pytest

from essai_ecriture import essai_ecriture
from test_progression import TACHE

CLIENT_TEST = "Client TEST Progim"
CFG = {"champ_description": "description"}


class FausseProgression:
    """Simule plusieurs comportements possibles de POST /task/{id}/update sur itemList."""

    def __init__(self, client=CLIENT_TEST, comportement="fusionne"):
        self.tache = copy.deepcopy(TACHE)
        self.tache["client"] = {"label": client}
        self.tache["properties"] = {"notesTech": "vieux", "autre": "à garder"}
        self.comportement = comportement
        self.ecrits = []

    def tache_brute(self, identifiant):
        return copy.deepcopy(self.tache)

    def mettre_a_jour(self, identifiant, corps):
        self.ecrits.append(copy.deepcopy(corps))
        envoyes = corps["itemList"]["items"]
        actuels = self.tache["itemList"]["items"]
        if self.comportement == "remplace":
            self.tache["itemList"]["items"] = [dict(i, id=i.get("id") or 999) for i in envoyes]
        elif self.comportement == "ajoute":
            actuels += [dict(i, id=i.get("id") or 999) for i in envoyes]
        else:
            par_id = {i["id"]: i for i in actuels}
            for i in envoyes:
                if i.get("id") in par_id:
                    par_id[i["id"]].update(i)
                else:
                    nouveau = dict(i, id=999)
                    if self.comportement == "perd_external_id":
                        nouveau.pop("externalId", None)
                    actuels.append(nouveau)
        if "properties" in corps:
            if self.comportement == "ecrase_properties":
                self.tache["properties"] = {k: v for k, v in corps["properties"].items() if k == "notesTech"}
            else:
                self.tache["properties"] = corps["properties"]
        if "description" in corps:
            self.tache["description"] = corps["description"]
        return {}


def test_refuse_un_vrai_client():
    prog = FausseProgression(client="Gestion Fictive inc.")
    with pytest.raises(ValueError, match="client de test"):
        essai_ecriture(prog, 1001, CLIENT_TEST, CFG)
    assert prog.ecrits == []


def test_fusion_valide():
    r = essai_ecriture(FausseProgression("Client TEST Progim", "fusionne"), 1001, CLIENT_TEST, CFG)
    assert r["valide"] is True, r["message"]
    assert r["lignes_avant"] == 2 and r["lignes_apres"] == 3


def test_remplacement_qui_efface_des_champs_detecte():
    r = essai_ecriture(FausseProgression(comportement="remplace"), 1001, CLIENT_TEST, CFG)
    assert r["valide"] is False and "modifié" in r["message"]


def test_ajout_en_double_detecte():
    r = essai_ecriture(FausseProgression(comportement="ajoute"), 1001, CLIENT_TEST, CFG)
    assert r["valide"] is False and "double" in r["message"]


def test_external_id_perdu_detecte():
    r = essai_ecriture(FausseProgression(comportement="perd_external_id"), 1001, CLIENT_TEST, CFG)
    assert r["valide"] is False and "externalId" in r["message"]


def test_quantite_modifiee_sur_ligne_existante():
    prog = FausseProgression()
    essai_ecriture(prog, 1001, CLIENT_TEST, CFG)
    premiere = prog.ecrits[0]["itemList"]["items"][0]
    assert premiere == {"id": 501, "quantity": 3.0833}


def test_properties_conservees():
    cfg = {"champ_description": "properties.notesTech"}
    assert essai_ecriture(FausseProgression(), 1001, CLIENT_TEST, cfg)["valide"] is True
    r = essai_ecriture(FausseProgression(comportement="ecrase_properties"), 1001, CLIENT_TEST, cfg)
    assert r["valide"] is False and "properties" in r["message"]
