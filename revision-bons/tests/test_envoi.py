import copy
import json

import pytest

from envoi import corps_mise_a_jour, envoyer
from journal import Journal
from modele import Ligne, Proposition
from progression import ErreurProgression, Progression
from test_progression import TACHE, FauxHttp

CFG = {"champ_description": "description", "produit_materiel": "MAT", "ecriture_validee": True}
CFG_VERROU = {**CFG, "ecriture_validee": False}


def proposition(bon_id=1001, maj=TACHE["updated"]):
    return Proposition(
        bon_id=bon_id, maj=maj, description="Remplacement du robinet.", description_originale="changer robinet",
        lignes=[
            Ligne(501, "Main-d'œuvre", "Luc", 2.25, 95.0, 40.0, "MO-PLOMB", None),
            Ligne(502, "Transport", "", 1, 45.0, None, "TRANSPORT", None),
            Ligne(None, "Vis", "Rona – facture A-1", 2, 11.0, 10.0, None, "rona|A-1|1"),
        ])


def valeurs(objet):
    if isinstance(objet, dict):
        for v in objet.values():
            yield from valeurs(v)
    elif isinstance(objet, list):
        for v in objet:
            yield from valeurs(v)
    else:
        yield objet


class FauxProgression:
    def __init__(self, maj=TACHE["updated"], erreur_sur=()):
        self.maj = maj
        self.erreur_sur = set(erreur_sur)
        self.ecrits = []
        self.porteurs = {}

    def tache_brute(self, identifiant):
        maj = "apres-ecriture" if any(i == identifiant for i, _ in self.ecrits) else self.maj
        return {**copy.deepcopy(TACHE), "id": identifiant, "updated": maj}

    def bon_avec_ligne(self, external_id):
        return self.porteurs.get(external_id)

    def mettre_a_jour(self, identifiant, corps):
        if identifiant in self.erreur_sur:
            raise ErreurProgression("Progression a répondu une erreur 500.")
        self.ecrits.append((identifiant, corps))
        return {}


def test_aucun_none():
    assert None not in list(valeurs(corps_mise_a_jour(proposition(), CFG, TACHE)))


# Progression REMPLACE toutes les lignes par la liste reçue (confirmé par Progression le 2026-11-11) :
# chaque ligne existante doit donc être renvoyée au complet, sans ses champs en lecture seule.

def test_liste_complete_sans_ids():
    items = corps_mise_a_jour(proposition(), CFG, TACHE)["itemList"]["items"]
    assert len(items) == 3 and not any("id" in i for i in items)


def test_ligne_existante_renvoyee_au_complet_avec_nos_changements():
    items = corps_mise_a_jour(proposition(), CFG, TACHE)["itemList"]["items"]
    assert items[0] == {"label": "Main-d'œuvre", "description": "Luc", "quantity": 2.25, "price": 95.0,
                        "unitCost": 40.0, "product": {"id": 9, "label": "MO-PLOMB", "code": "MO-PLOMB"}}
    assert items[1] == {"label": "Transport", "description": "", "quantity": 1, "price": 45.0,
                        "product": {"id": 10, "label": "TRANSPORT", "code": "TRANSPORT"}}


def test_champs_inconnus_de_l_outil_conserves():
    tache = copy.deepcopy(TACHE)
    tache["itemList"]["items"][1].update({"taxable": False, "rebate": 5, "type": {"id": 3}, "externalId": "erp-77",
                                          "taxConfig": {"id": 2}, "properties": {"x": 1}, "quantityConfirmed": 1})
    item = corps_mise_a_jour(proposition(), CFG, tache)["itemList"]["items"][1]
    assert (item["taxable"], item["rebate"], item["type"], item["externalId"], item["taxConfig"],
            item["properties"], item["quantityConfirmed"]) == (False, 5, {"id": 3}, "erp-77", {"id": 2}, {"x": 1}, 1)


def test_champs_en_lecture_seule_retires():
    tache = copy.deepcopy(TACHE)
    tache["itemList"]["items"][0].update({"total": 1, "cost": 2, "margin": 3, "profit": 4, "unitProfit": 5,
                                          "url": "u", "uid": "x", "created": "c", "updated": "m", "removed": None})
    item = corps_mise_a_jour(proposition(), CFG, tache)["itemList"]["items"][0]
    assert not {"id", "total", "cost", "margin", "profit", "unitProfit", "url", "uid", "created", "updated",
                "removed"} & set(item)


def test_prix_nul_dans_progression_jamais_renvoye_a_zero():
    tache = copy.deepcopy(TACHE)
    tache["itemList"]["items"][1]["price"] = None
    p = proposition()
    p.lignes[1].prix = 0.0   # valeur lue comme 0 faute de prix
    item = corps_mise_a_jour(p, CFG, tache)["itemList"]["items"][1]
    assert "price" not in item


def test_ligne_supprimee_par_l_outil_jamais():
    # Une ligne existante absente de la proposition serait effacée par le remplacement : refusé.
    p = proposition()
    p.lignes = p.lignes[1:]
    with pytest.raises(ValueError, match="501"):
        corps_mise_a_jour(p, CFG, TACHE)


def test_external_id_sur_nouvelles_lignes():
    nouvelle = corps_mise_a_jour(proposition(), CFG, TACHE)["itemList"]["items"][2]
    assert nouvelle == {"label": "Vis", "description": "Rona – facture A-1", "quantity": 2, "price": 11.0,
                        "unitCost": 10.0, "externalId": "rona|A-1|1", "product": {"code": "MAT"}}


def test_sans_produit_materiel():
    nouvelle = corps_mise_a_jour(proposition(), {**CFG, "produit_materiel": ""}, TACHE)["itemList"]["items"][2]
    assert "product" not in nouvelle


def test_description_dans_champ_description():
    assert corps_mise_a_jour(proposition(), CFG, TACHE)["description"] == "Remplacement du robinet."


def test_description_dans_properties_garde_les_autres_champs():
    tache = {**TACHE, "properties": {"notesTech": "vieux", "autre": "à garder"}}
    corps = corps_mise_a_jour(proposition(), {**CFG, "champ_description": "properties.notesTech"}, tache)
    assert corps["properties"] == {"notesTech": "Remplacement du robinet.", "autre": "à garder"}
    assert "description" not in corps


def test_simulation_n_ecrit_rien(tmp_path):
    prog = FauxProgression()
    [r] = envoyer([proposition()], prog, Journal(tmp_path, "hugo"), CFG_VERROU, "simulation")
    assert r["resultat"] == "simule" and prog.ecrits == []
    assert r["corps"]["itemList"]["items"][2]["externalId"] == "rona|A-1|1"


def test_reel_refuse_sans_validation(tmp_path):
    prog = FauxProgression()
    with pytest.raises(ValueError, match="verrouillée"):
        envoyer([proposition()], prog, Journal(tmp_path, "hugo"), CFG_VERROU, "reel")
    assert prog.ecrits == []


def test_reel_ecrit_et_journalise(tmp_path):
    prog, j = FauxProgression(), Journal(tmp_path, "hugo")
    [r] = envoyer([proposition()], prog, j, CFG, "reel")
    assert r["resultat"] == "ecrit" and prog.ecrits[0][0] == 1001
    assert j.deja_ecrit(1001, TACHE["updated"])
    assert j.factures_refacturees() == {"rona|A-1": 1001}
    assert j.historique()[0]["details"]["description_originale"] == "changer robinet"


def test_bon_perime(tmp_path):
    prog = FauxProgression(maj="2026-11-04T09:00:00-05:00")
    [r] = envoyer([proposition()], prog, Journal(tmp_path, "hugo"), CFG, "reel")
    assert r["resultat"] == "perime" and prog.ecrits == []


def test_reprise_apres_coupure(tmp_path):
    j = Journal(tmp_path, "hugo")
    j.inscrire("ecrit", 1, TACHE["updated"], {})
    prog = FauxProgression(erreur_sur={2})
    r = envoyer([proposition(1), proposition(2), proposition(3)], prog, j, CFG, "reel")
    assert [x["resultat"] for x in r] == ["deja_ecrit", "echec", "ecrit"]
    assert [i for i, _ in prog.ecrits] == [3]
    assert any(e["evenement"] == "echec" and e["bon_id"] == 2 for e in j.historique())


def test_jamais_timeentry(tmp_path):
    http = FauxHttp([TACHE, [], {}, TACHE])
    envoyer([proposition()], Progression("c", ouvrir=http), Journal(tmp_path, "hugo"), CFG, "reel")
    assert http.requetes and not any("timeEntr" in r.full_url for r in http.requetes)
    assert [r.get_method() for r in http.requetes] == ["GET", "GET", "POST", "GET"]


def test_date_de_modification_absente_refusee(tmp_path):
    prog = FauxProgression(maj="")
    [r] = envoyer([proposition(maj="")], prog, Journal(tmp_path, "hugo"), CFG, "reel")
    assert r["resultat"] == "echec" and prog.ecrits == []


def test_doublon_journal_au_moment_de_l_envoi(tmp_path):
    j = Journal(tmp_path, "hugo")
    j.inscrire("ecrit", 777, "m", {"external_ids": ["rona|A-1|1"]})
    prog = FauxProgression()
    [r] = envoyer([proposition()], prog, j, CFG, "reel")
    assert r["resultat"] == "doublon" and "777" in r["message"] and prog.ecrits == []


def test_doublon_progression_au_moment_de_l_envoi(tmp_path):
    prog = FauxProgression()
    prog.porteurs = {"rona|A-1|1": 888}
    [r] = envoyer([proposition()], prog, Journal(tmp_path, "hugo"), CFG, "reel")
    assert r["resultat"] == "doublon" and prog.ecrits == []


def test_meme_facture_deux_bons_du_meme_envoi(tmp_path):
    prog = FauxProgression()
    r = envoyer([proposition(1), proposition(2)], prog, Journal(tmp_path, "hugo"), CFG, "reel")
    assert [x["resultat"] for x in r] == ["ecrit", "doublon"]


def test_doublon_signale_en_simulation(tmp_path):
    r = envoyer([proposition(1), proposition(2)], FauxProgression(), Journal(tmp_path, "hugo"), CFG, "simulation")
    assert [x["resultat"] for x in r] == ["simule", "doublon"]


def test_date_apres_ecriture_journalisee(tmp_path):
    j = Journal(tmp_path, "hugo")
    envoyer([proposition()], FauxProgression(), j, CFG, "reel")
    assert j.historique()[0]["details"]["maj_apres"] == "apres-ecriture"
    assert j.deja_ecrit(1001, "apres-ecriture")


def test_simulation_avec_lignes_originales(tmp_path):
    originaux = {1001: proposition().lignes[:2]}
    [r] = envoyer([proposition()], FauxProgression(), Journal(tmp_path, "hugo"), CFG, "simulation", originaux)
    assert r["corps"]["itemList"]["items"][1]["label"] == "Transport" and "id" not in r["corps"]["itemList"]["items"][1]
