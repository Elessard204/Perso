import base64
import io
import json
import urllib.error
from pathlib import Path

import pytest

from progression import ErreurProgression, Progression, bon_depuis_json, minutes_iso

DONNEES = Path(__file__).parent / "donnees"
TACHE = json.loads((DONNEES / "tache_exemple.json").read_text(encoding="utf-8"))
ENTREES = json.loads((DONNEES / "entrees_exemple.json").read_text(encoding="utf-8"))
CFG = {"champ_description": "description"}


class FauxHttp:
    """Remplace urllib.request.urlopen : enregistre les requêtes, renvoie des réponses prévues."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.requetes = []

    def __call__(self, requete, timeout=None):
        self.requetes.append(requete)
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(json.dumps(r).encode("utf-8"))


def test_entete_bearer():
    http = FauxHttp([TACHE, ENTREES])
    Progression("cle-test", ouvrir=http).lire_bon(1001)
    for r in http.requetes:
        assert r.get_header("Authorization") == "Bearer cle-test"
        assert "apiKey" not in r.full_url


def test_lister_pagine():
    page1 = [{"id": i} for i in range(500)]
    page2 = [{"id": 500}]
    http = FauxHttp([page1, page2])
    taches = Progression("c", ouvrir=http).lister_bons("600", "BS", "2026-11-01,2026-11-30")
    assert len(taches) == 501
    urls = [r.full_url for r in http.requetes]
    assert "startResult=0" in urls[0] and "startResult=500" in urls[1]
    assert "logicId=600" in urls[0] and "maxResults=500" in urls[0]


def test_lister_accepte_une_enveloppe():
    http = FauxHttp([{"data": [{"id": 1}]}])
    assert Progression("c", ouvrir=http).lister_bons("600", "", "") == [{"id": 1}]


def test_minutes_iso():
    assert minutes_iso("PT1H20M") == 80
    assert minutes_iso("PT45M") == 45
    assert minutes_iso("PT2H") == 120
    assert minutes_iso("PT1H0M30S") == 60.5   # secondes exactes; l arrondi se fait sur le total
    assert minutes_iso("") == 0


def test_bon_depuis_json():
    bon = bon_depuis_json(TACHE, ENTREES, CFG)
    assert (bon.id, bon.code, bon.client, bon.maj) == (1001, "BS-1001", "Gestion Fictive inc.", "2026-11-03T16:42:10-05:00")
    assert bon.description.startswith("changer robinet")
    assert [(e.technicien, e.minutes, e.ligne_id) for e in bon.entrees] == [("Luc Tremblay", 80, 501), ("Luc Tremblay", 45, 501)]
    assert str(bon.entrees[0].jour) == "2026-11-03"
    mo = bon.lignes[0]
    assert (mo.id, mo.quantite, mo.prix, mo.cout_unitaire, mo.produit) == (501, 2.0833, 95.0, 40.0, "MO-PLOMB")
    assert bon.lignes[1].cout_unitaire is None
    assert [(p.id, p.type_mime) for p in bon.pieces] == [(9001, "image/jpeg"), (9002, "application/pdf")]


def test_description_dans_properties():
    bon = bon_depuis_json(TACHE, ENTREES, {"champ_description": "properties.notesTech"})
    assert bon.description == "texte du technicien dans un champ perso"


def test_telecharger_piece():
    contenu = b"%PDF-1.4 faux"
    http = FauxHttp([{"id": 9002, "data": base64.b64encode(contenu).decode()}])
    assert Progression("c", ouvrir=http).telecharger_piece(9002) == contenu
    assert http.requetes[0].full_url.endswith("/task/attachment/9002")


def test_mettre_a_jour_poste_json():
    http = FauxHttp([{}])
    Progression("c", ouvrir=http).mettre_a_jour(1001, {"description": "x"})
    r = http.requetes[0]
    assert r.get_method() == "POST" and r.full_url.endswith("/task/1001/update")
    assert json.loads(r.data) == {"description": "x"}


def test_erreur_401():
    err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(b""))
    with pytest.raises(ErreurProgression, match="Clé Progression refusée"):
        Progression("c", ouvrir=FauxHttp([err])).lire_bon(1)


def test_erreur_reseau():
    with pytest.raises(ErreurProgression, match="Progression ne répond pas"):
        Progression("c", ouvrir=FauxHttp([urllib.error.URLError("timeout")])).lire_bon(1)


def test_tache_brute_une_seule_requete_get():
    http = FauxHttp([TACHE])
    assert Progression("c", ouvrir=http).tache_brute(1001)["updated"] == TACHE["updated"]
    assert [(r.get_method(), r.full_url.rsplit("/rest", 1)[1]) for r in http.requetes] == [("GET", "/task/1001")]


def test_minutes_exactes_et_decimales():
    assert minutes_iso("PT7M20S") == pytest.approx(7 + 1 / 3)
    assert minutes_iso("PT1.5H") == 90


def test_secondes_additionnees_avant_arrondi():
    from regles import heures_facturees
    entrees = [{"id": i, "duration": "PT7M20S", "start": "2026-11-03T08:00:00", "humanResource": {"label": "Luc"},
                "item": {"id": 501}} for i in (1, 2)]
    bon = bon_depuis_json(TACHE, entrees, CFG)
    assert heures_facturees(bon.entrees, 15) == {"Luc": 0.25}   # 14 min 40 s -> 15 min, pas 30


def test_piece_base64_invalide():
    http = FauxHttp([{"id": 1, "data": "pas du base64!!!"}])
    with pytest.raises(ErreurProgression, match="illisible"):
        Progression("c", ouvrir=http).telecharger_piece(1)


def test_bon_avec_ligne():
    http = FauxHttp([[{"id": 77}], []])
    p = Progression("c", ouvrir=http)
    assert p.bon_avec_ligne("rona|A-1|1") == 77
    assert p.bon_avec_ligne("bmr|9|1") is None
    assert "itemExternalId=rona%7CA-1%7C1" in http.requetes[0].full_url


def _erreur_429(attente="0"):
    return urllib.error.HTTPError("u", 429, "Too Many Requests", {"Retry-After": attente}, io.BytesIO(b""))


def test_429_attend_puis_reessaie():
    pauses = []
    http = FauxHttp([_erreur_429("2"), TACHE])
    p = Progression("c", ouvrir=http, dormir=pauses.append)
    assert p.tache_brute(1001)["id"] == 1001
    assert pauses == [2.0] and len(http.requetes) == 2


def test_429_sans_retry_after_attente_croissante():
    pauses = []
    http = FauxHttp([_erreur_429(""), _erreur_429(""), TACHE])
    Progression("c", ouvrir=http, dormir=pauses.append).tache_brute(1001)
    assert pauses == [2.0, 4.0]


def test_429_abandon_apres_plusieurs_essais():
    http = FauxHttp([_erreur_429() for _ in range(6)])
    with pytest.raises(ErreurProgression, match="trop de demandes"):
        Progression("c", ouvrir=http, dormir=lambda s: None).tache_brute(1001)


def test_champ_achat_lu():
    tache = {**TACHE, "properties": {"info": {"achat": "Robinet cuisine"}}}
    bon = bon_depuis_json(tache, ENTREES, {"champ_achat": "properties.info.achat"})
    assert bon.achat == "Robinet cuisine"
    assert bon_depuis_json(TACHE, ENTREES, CFG).achat == ""
