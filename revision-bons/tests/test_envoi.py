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

    def tache_brute(self, identifiant):
        return {**copy.deepcopy(TACHE), "id": identifiant, "updated": self.maj}

    def mettre_a_jour(self, identifiant, corps):
        if identifiant in self.erreur_sur:
            raise ErreurProgression("Progression a répondu une erreur 500.")
        self.ecrits.append((identifiant, corps))
        return {}


def test_aucun_none():
    assert None not in list(valeurs(corps_mise_a_jour(proposition(), CFG, TACHE)))


def test_liste_complete_avec_ids():
    items = corps_mise_a_jour(proposition(), CFG, TACHE)["itemList"]["items"]
    assert [i.get("id") for i in items] == [501, 502, None]
    assert items[0] == {"id": 501, "label": "Main-d'œuvre", "description": "Luc", "quantity": 2.25,
                        "price": 95.0, "unitCost": 40.0}


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
    http = FauxHttp([TACHE, {}])
    envoyer([proposition()], Progression("c", ouvrir=http), Journal(tmp_path, "hugo"), CFG, "reel")
    assert http.requetes and not any("timeEntr" in r.full_url for r in http.requetes)
    assert [r.get_method() for r in http.requetes] == ["GET", "POST"]
