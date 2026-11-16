import json
from datetime import date
from types import SimpleNamespace

from km_declare import bons_du_technicien, interpreter_km

CFG = {"modele": "m", "effort": "low"}


class FauxClient:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.appels.append(kw)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.reponse))])


def test_texte_simple_sans_ia():
    client = FauxClient({"km": 1, "confiance": "haute"})
    assert interpreter_km("60km", client, CFG, {}) == (60.0, "ok")
    assert client.appels == []


def test_texte_ambigu_par_ia():
    client = FauxClient({"km": 52, "confiance": "haute"})
    cache = {}
    texte = "aller 26 retour 26"
    assert interpreter_km(texte, client, CFG, cache) == (52.0, "ok")
    assert len(client.appels) == 1
    contenu = client.appels[0]["messages"][0]["content"]
    assert "Kilométrage inscrit" in contenu[-1]["text"] and "«" + texte + "»" in contenu[-1]["text"]
    assert interpreter_km(texte, client, CFG, cache) == (52.0, "ok")
    assert len(client.appels) == 1


def test_ia_peu_sure():
    client = FauxClient({"km": 20, "confiance": "basse"})
    assert interpreter_km("environ 20 ou 30", client, CFG, {}) == (20.0, "a_verifier")


def test_ia_sans_total():
    client = FauxClient({"km": None, "confiance": "haute"})
    assert interpreter_km("voir plus haut", client, CFG, {}) == (None, "a_verifier")


def test_texte_vide():
    client = FauxClient({"km": 1, "confiance": "haute"})
    assert interpreter_km("  ", client, CFG, {}) == (None, "vide")
    assert client.appels == []


def _e(tech, start):
    return {"humanResource": {"label": tech}, "start": start}


def test_bon_partage_et_prorata():
    client = FauxClient({"km": 52, "confiance": "haute"})
    taches = {
        1: {"code": "A-1", "properties": {"info.km": "30 km"}},
        2: {"code": "B-2", "properties": {"info.km": "40"}},
        3: {"code": "C-3", "properties": {}},
    }
    entrees = {
        1: [_e("V", "2026-11-09T08:00:00-05:00"), _e("F", "2026-11-09T09:00:00-05:00")],
        2: [_e("V", "2026-11-20T08:00:00-05:00"), _e("V", "2026-11-21T08:00:00-05:00"),
            _e("V", "2026-11-25T08:00:00-05:00")],
        3: [_e("F", "2026-11-10T08:00:00-05:00")],
    }
    bons = bons_du_technicien("V", entrees, taches, date(2026, 11, 8), date(2026, 11, 21), client, CFG, {})
    par_id = {b["tache_id"]: b for b in bons}
    assert set(par_id) == {1, 2}
    assert par_id[1]["statut"] == "partage" and par_id[1]["km"] == 30.0 and par_id[1]["part"] == 1.0
    assert par_id[2]["statut"] == "ok" and par_id[2]["km"] == 40.0
    assert par_id[2]["part"] == round(2 / 3, 4)
    assert par_id[2]["code"] == "B-2" and par_id[2]["texte"] == "40"
