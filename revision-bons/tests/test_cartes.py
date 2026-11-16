import io
import json
import urllib.error

import pytest

from cartes import Cartes, ErreurCartes
from demo.faux_services import FaussesCartes

A = (45.5, -73.5)
B = (45.6, -73.6)


class FauxHttp:
    """Remplace urllib.request.urlopen : enregistre les requêtes, renvoie des réponses prévues."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.requetes = []

    def __call__(self, requete, timeout=None):
        self.requetes.append({
            "methode": requete.get_method(),
            "url": requete.full_url,
            "entetes": {k.lower(): v for k, v in requete.header_items()},
            "corps": json.loads(requete.data) if requete.data else None,
        })
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(json.dumps(r).encode("utf-8"))


def erreur_http(code):
    return urllib.error.HTTPError("https://exemple.test", code, "erreur", {}, io.BytesIO(b"{}"))


REPONSE_GEO = {"status": "OK", "results": [{"geometry": {"location": {"lat": 45.47, "lng": -73.46}}}]}


def cartes(tmp_path, reponses, dormir=None):
    http = FauxHttp(reponses)
    pauses = []
    c = Cartes("cle-test", tmp_path / "profil" / "cartes.json", ouvrir=http,
               dormir=dormir or pauses.append)
    return c, http, pauses


def test_geocoder_et_cache(tmp_path):
    c, http, _ = cartes(tmp_path, [REPONSE_GEO])
    pos = c.geocoder("H2X 1Y4")
    assert pos == (45.47, -73.46) and len(http.requetes) == 1
    r = http.requetes[0]
    assert r["methode"] == "GET"
    assert r["url"].startswith("https://maps.googleapis.com/maps/api/geocode/json?")
    assert "components=country%3ACA" in r["url"] or "components=country:CA" in r["url"]
    assert "key=cle-test" in r["url"]
    # nouvelle instance, même cache : aucune requête
    c2, http2, _ = cartes(tmp_path, [])
    assert c2.geocoder("H2X 1Y4") == (45.47, -73.46)
    assert http2.requetes == []


def test_distance_routes_api(tmp_path):
    c, http, _ = cartes(tmp_path, [{"routes": [{"distanceMeters": 12345}]}])
    assert c.distance_km(A, B) == 12.3
    r = http.requetes[0]
    assert r["methode"] == "POST"
    assert r["url"] == "https://routes.googleapis.com/directions/v2:computeRoutes"
    assert r["entetes"]["x-goog-api-key"] == "cle-test"
    assert r["entetes"]["x-goog-fieldmask"] == "routes.distanceMeters"
    assert r["entetes"]["content-type"] == "application/json"
    assert r["corps"] == {
        "origin": {"location": {"latLng": {"latitude": 45.5, "longitude": -73.5}}},
        "destination": {"location": {"latLng": {"latitude": 45.6, "longitude": -73.6}}},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
    }
    # même point : 0.0 sans requête
    assert c.distance_km(A, (45.500001, -73.500001)) == 0.0
    assert len(http.requetes) == 1
    # résultat en cache
    assert c.distance_km(A, B) == 12.3
    assert len(http.requetes) == 1


def test_aucune_route(tmp_path):
    c, _, _ = cartes(tmp_path, [{}])
    with pytest.raises(ErreurCartes, match="Aucun trajet routier trouvé"):
        c.distance_km(A, B)


def test_429_reessaie(tmp_path):
    c, http, pauses = cartes(tmp_path, [erreur_http(429), REPONSE_GEO])
    assert c.geocoder("H2X 1Y4") == (45.47, -73.46)
    assert pauses == [1] and len(http.requetes) == 2


def test_429_abandonne_apres_cinq_essais(tmp_path):
    c, http, pauses = cartes(tmp_path, [erreur_http(429)] * 5)
    with pytest.raises(ErreurCartes):
        c.geocoder("H2X 1Y4")
    assert len(http.requetes) == 5 and pauses == [1, 2, 4, 8]


def test_cle_refusee(tmp_path):
    for code in (400, 403):
        c, _, _ = cartes(tmp_path, [erreur_http(code)])
        with pytest.raises(ErreurCartes) as e:
            c.geocoder("H2X 1Y4")
        assert "Clé Google" in str(e.value)


def test_statut_geocodage_refuse(tmp_path):
    c, _, _ = cartes(tmp_path, [{"status": "REQUEST_DENIED", "error_message": "API key invalide", "results": []}])
    with pytest.raises(ErreurCartes, match="Google Maps : API key invalide"):
        c.geocoder("H2X 1Y4")


def test_zero_results(tmp_path):
    c, http, _ = cartes(tmp_path, [{"status": "ZERO_RESULTS", "results": []}])
    assert c.geocoder("Z9Z 9Z9") is None
    # le « introuvable » est aussi mis en cache
    assert c.geocoder("Z9Z 9Z9") is None
    assert len(http.requetes) == 1


def test_reseau_en_panne(tmp_path):
    for exc in (urllib.error.URLError("hors ligne"), TimeoutError()):
        c, _, _ = cartes(tmp_path, [exc])
        with pytest.raises(ErreurCartes, match="Google Maps ne répond pas"):
            c.geocoder("H2X 1Y4")


def test_valeur_gardee_apres_panne(tmp_path):
    c, _, _ = cartes(tmp_path, [REPONSE_GEO, urllib.error.URLError("hors ligne")])
    c.geocoder("H2X 1Y4")
    with pytest.raises(ErreurCartes):
        c.geocoder("H3Z 2Y7")
    c2, http2, _ = cartes(tmp_path, [])
    assert c2.geocoder("H2X 1Y4") == (45.47, -73.46)
    assert http2.requetes == []


def test_cache_corrompu_ignore(tmp_path):
    fichier = tmp_path / "profil" / "cartes.json"
    fichier.parent.mkdir()
    fichier.write_text("{pas du json", encoding="utf-8")
    c, http, _ = cartes(tmp_path, [REPONSE_GEO])
    assert c.geocoder("H2X 1Y4") == (45.47, -73.46)
    assert json.loads(fichier.read_text(encoding="utf-8"))["geo"]["H2X 1Y4"] == [45.47, -73.46]


def test_fausses_cartes():
    f = FaussesCartes()
    a = f.geocoder("H2X 1Y4")
    b = f.geocoder("J4B 5C6")
    assert a == f.geocoder("H2X 1Y4") and a != b
    assert f.distance_km(a, a) == 0.0
    d = f.distance_km(a, b)
    assert d > 0 and d == f.distance_km(b, a)
