import copy

import pytest

from essai_ecriture import essai_ecriture
from test_progression import TACHE

CLIENT_TEST = "Client TEST Progim"
CFG = {"champ_description": "description"}


class FausseProgression:
    """Simule POST /task/{id}/update. « remplace » est le comportement confirmé par Progression :
    toutes les lignes sont supprimées puis recréées (nouveaux ids) à partir de la liste reçue."""

    def __init__(self, client=CLIENT_TEST, comportement="remplace"):
        self.tache = copy.deepcopy(TACHE)
        self.tache["client"] = {"label": client}
        self.tache["properties"] = {"notesTech": "vieux", "autre": "à garder"}
        self.tache["itemList"]["items"][1].update({"taxable": False, "rebate": 5})
        self.comportement = comportement
        self.ecrits = []
        self.prochain_id = 7000

    def tache_brute(self, identifiant):
        return copy.deepcopy(self.tache)

    def _recreer(self, item):
        self.prochain_id += 1
        nouveau = dict(item, id=self.prochain_id, total=item.get("quantity", 0) * item.get("price", 0))
        if self.comportement == "perd_external_id":
            nouveau.pop("externalId", None)
        if self.comportement == "perd_produit":
            nouveau.pop("product", None)
        return nouveau

    def mettre_a_jour(self, identifiant, corps):
        self.ecrits.append(copy.deepcopy(corps))
        recrees = [self._recreer(i) for i in corps["itemList"]["items"]]
        if self.comportement == "ajoute":
            self.tache["itemList"]["items"] += recrees
        else:
            self.tache["itemList"]["items"] = recrees
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


def test_comportement_reel_de_progression_valide():
    r = essai_ecriture(FausseProgression(), 1001, CLIENT_TEST, CFG)
    assert r["valide"] is True, r["message"]
    assert r["lignes_avant"] == 2 and r["lignes_apres"] == 3


def test_champ_perdu_a_la_recreation_detecte():
    r = essai_ecriture(FausseProgression(comportement="perd_produit"), 1001, CLIENT_TEST, CFG)
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
    assert premiere["quantity"] == 3.0833 and premiere["label"] == "Main-d'œuvre" and "id" not in premiere
    assert prog.ecrits[0]["itemList"]["items"][1]["taxable"] is False   # champs inconnus de l'outil conservés


def test_properties_conservees():
    cfg = {"champ_description": "properties.notesTech"}
    assert essai_ecriture(FausseProgression(), 1001, CLIENT_TEST, cfg)["valide"] is True
    r = essai_ecriture(FausseProgression(comportement="ecrase_properties"), 1001, CLIENT_TEST, cfg)
    assert r["valide"] is False and "properties" in r["message"]
