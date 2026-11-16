from datetime import date
from km_calcul import (Arret, journees, km_journee, lire_km_simple, periode_contenant, periodes_proposees, totaliser)

REF = date(2026, 11, 8)

def test_periode_contenant():
    assert periode_contenant(date(2026, 11, 8), REF) == (date(2026, 11, 8), date(2026, 11, 21))
    assert periode_contenant(date(2026, 11, 21), REF) == (date(2026, 11, 8), date(2026, 11, 21))
    assert periode_contenant(date(2026, 11, 22), REF) == (date(2026, 11, 22), date(2026, 12, 5))
    assert periode_contenant(date(2026, 11, 7), REF) == (date(2026, 10, 25), date(2026, 11, 7))
    assert periodes_proposees(date(2026, 11, 16), REF, 2) == [(date(2026, 11, 8), date(2026, 11, 21)),
                                                              (date(2026, 10, 25), date(2026, 11, 7))]

def _e(tech, start, tache_id, code):
    return {"humanResource": {"label": tech}, "start": start, "task": {"id": tache_id, "code": code}, "duration": "PT30M"}

def _t(lat, lng):
    return {"clientAddress": {"position": {"latitude": lat, "longitude": lng}}}

def test_journees_ordre_et_fusion():
    entrees = [_e("V", "2026-11-10T13:00:00-05", 2, "B"), _e("V", "2026-11-10T08:00:00-05", 1, "A"),
               _e("V", "2026-11-10T09:00:00-05", 1, "A"), _e("V", "2026-11-10T15:00:00-05", 1, "A")]
    [j] = journees(entrees, {1: _t(45.5, -73.5), 2: _t(45.6, -73.6)}, date(2026, 11, 8), date(2026, 11, 21))
    assert [a.code for a in j.arrets] == ["A", "B", "A"] and j.a_verifier == []
    assert j.minutes == 4 * 30.0          # chaque entrée _e dure PT30M

def test_jour_selon_horodatage_local():
    entrees = [_e("V", "2026-11-21T23:30:00-05", 1, "A"), _e("V", "2026-11-22T07:00:00-05", 1, "A")]
    jours = journees(entrees, {1: _t(45.5, -73.5)}, date(2026, 11, 8), date(2026, 11, 21))
    assert [j.jour for j in jours] == [date(2026, 11, 21)]

def test_journee_sans_position_a_verifier():
    [j] = journees([_e("V", "2026-11-10T08:00:00-05", 3, "C")], {3: {}}, date(2026, 11, 8), date(2026, 11, 21))
    assert j.arrets == [] and "C" in j.a_verifier[0]
    assert km_journee((45.4, -73.4), j.arrets, lambda a, b: 99.0) == (0.0, [])

def test_km_journee_domicile_aller_retour():
    arrets = [Arret(1, "A", 45.5, -73.5), Arret(2, "B", 45.6, -73.6)]
    km, troncons = km_journee((45.4, -73.4), arrets, lambda a, b: 10.0)
    assert km == 30.0 and [(t["de"], t["a"]) for t in troncons] == [("domicile", "A"), ("A", "B"), ("B", "domicile")]
    assert km_journee(None, arrets, lambda a, b: 10.0)[0] == 10.0

def test_lire_km_simple():
    assert [lire_km_simple(t) for t in ("60km", "25 KM", "49", "12,5 km", "1 200 km", "", "52 pour les deux jours",
                                         "+14km achat + 6km")] == [60, 25, 49, 12.5, 1200, None, None, None]

def test_entree_sans_tache_compte_les_minutes():
    e = {"humanResource": {"label": "V"}, "start": "2026-11-10T08:00:00-05", "task": None, "duration": "PT1H"}
    [j] = journees([e], {}, date(2026, 11, 8), date(2026, 11, 21))
    assert j.minutes == 60.0 and j.arrets == [] and j.a_verifier == ["entrée sans bon : immeuble sans position GPS"]

def _base():
    return {"debut": "2026-11-08", "fin": "2026-11-21", "techniciens": {
        "Vadim": {"jours": [{"jour": "2026-11-10", "arrets": [], "troncons": [], "km": 100.0, "a_verifier": [], "domicile": True, "minutes": 300.0},
                            {"jour": "2026-11-11", "arrets": [], "troncons": [], "km": 50.0, "a_verifier": [], "domicile": True, "minutes": 240.0}],
                  "bons": [{"code": "A", "texte": "200", "km": 200.0, "statut": "ok", "part": 1.0}]},
        "Hugo": {"jours": [{"jour": "2026-11-10", "arrets": [], "troncons": [], "km": 20.0, "a_verifier": [], "domicile": False, "minutes": 60.0}],
                 "bons": []}}}

def test_totaliser_ecart_uhaul_magasin_et_admissibilite():
    techs = {"Vadim": {"code_postal": "H1A 1A1", "paye_km": True}}
    p = totaliser(_base(), {"Vadim|2026-11-11": {"uhaul": True, "magasin_km": 0}, "Vadim|2026-11-10": {"uhaul": False, "magasin_km": 12}},
                  0.61, 10.0, techs)
    v = next(t for t in p["techniciens"] if t["nom"] == "Vadim")
    assert (v["km_calcule"], v["km_magasin"], v["km_a_payer"], v["montant"]) == (150.0, 12.0, 112.0, 68.32)
    assert (v["km_declare"], v["ecart"], v["statut"]) == (200.0, 88.0, "ecart")
    h = next(t for t in p["techniciens"] if t["nom"] == "Hugo")
    assert (h["statut"], h["montant"], h["paie"]) == ("a_configurer", None, False)
    p2 = totaliser(_base(), {}, 0.61, 10.0, {**techs, "Hugo": {"code_postal": "", "paye_km": False}})
    assert next(t for t in p2["techniciens"] if t["nom"] == "Hugo")["statut"] == "sous_traitant"
    assert v["minutes_par_jour"] == {"2026-11-10": 300.0, "2026-11-11": 240.0} and v["minutes_total"] == 540.0
    assert p["total_montant"] == 68.32

def test_totaliser_seuil_et_non_declare():
    techs = {"Vadim": {"code_postal": "H1A 1A1", "paye_km": True}}
    base = _base(); base["techniciens"]["Vadim"]["bons"][0]["km"] = 155.0
    assert next(t for t in totaliser(base, {}, 0.61, 10.0, techs)["techniciens"] if t["nom"] == "Vadim")["statut"] == "ok"
    base["techniciens"]["Vadim"]["bons"][0]["statut"] = "vide"
    assert next(t for t in totaliser(base, {}, 0.61, 10.0, techs)["techniciens"] if t["nom"] == "Vadim")["statut"] == "non_declare"


def test_montant_arrondi_demi_superieur():
    base = {"debut": "2026-11-08", "fin": "2026-11-21", "techniciens": {"Vadim": {"jours": [
        {"jour": "2026-11-10", "arrets": [], "troncons": [], "km": 0.5, "a_verifier": [], "domicile": True, "minutes": 0.0}],
        "bons": []}}}
    p = totaliser(base, {}, 0.61, 10.0, {"Vadim": {"code_postal": "H2X 1Y4", "paye_km": True}})
    assert p["techniciens"][0]["montant"] == 0.31 and p["total_montant"] == 0.31


def _base_un_jour(km, a_verifier=(), **tech):
    return {"debut": "2026-11-08", "fin": "2026-11-21", "techniciens": {"Vadim": {"jours": [
        {"jour": "2026-11-10", "arrets": [], "troncons": [], "km": km, "a_verifier": list(a_verifier),
         "domicile": True, "minutes": 0.0}], "bons": [], **tech}}}


def test_montant_demi_superieur_sur_le_produit_exact():
    p = totaliser(_base_un_jour(17.5), {}, 0.61, 10.0, {"Vadim": {"code_postal": "H2X 1Y4", "paye_km": True}})
    assert p["techniciens"][0]["montant"] == 10.68 and p["total_montant"] == 10.68


def test_jours_a_verifier_et_note():
    base = _base_un_jour(10.0, ["BS-1 : immeuble sans position GPS"])
    base["techniciens"]["Vadim"]["jours"].append({"jour": "2026-11-11", "arrets": [], "troncons": [], "km": 5.0,
                                                  "a_verifier": [], "domicile": True, "minutes": 0.0})
    v = totaliser(base, {}, 0.61, 10.0, {"Vadim": {"code_postal": "H2X 1Y4", "paye_km": True}})["techniciens"][0]
    assert v["jours_a_verifier"] == 1 and v["note"] is None and v["paie"] is True


def test_code_postal_introuvable_a_configurer():
    base = _base_un_jour(10.0, code_introuvable=True)
    p = totaliser(base, {}, 0.61, 10.0, {"Vadim": {"code_postal": "H2X 1Y4", "paye_km": True}})
    v = p["techniciens"][0]
    assert (v["statut"], v["montant"], v["ecart"], v["paie"]) == ("a_configurer", None, None, False)
    assert v["note"] == "code postal introuvable" and p["total_montant"] == 0.0
    # Devenu sous-traitant : la note ne sert plus.
    s = totaliser(base, {}, 0.61, 10.0, {"Vadim": {"code_postal": "H2X 1Y4", "paye_km": False}})["techniciens"][0]
    assert s["statut"] == "sous_traitant" and s["note"] is None
