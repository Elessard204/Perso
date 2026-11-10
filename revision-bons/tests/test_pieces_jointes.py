import json
from types import SimpleNamespace

from modele import PieceJointe
from pieces_jointes import analyser_piece

CFG = {"modele": "claude-opus-5-5", "effort": "medium"}
FACTURE_JSON = {
    "genre": "facture", "raison": "Reçu Rona", "fournisseur": "Rona", "numero": "A-1",
    "date": "2026-11-02", "sous_total": 20.0,
    "lignes": [{"description": "Vis", "quantite": 2, "prix_unitaire": 10.0}],
}


class FauxClaude:
    def __init__(self, texte=None, stop_reason="end_turn"):
        self.appels = []
        self.texte = json.dumps(FACTURE_JSON) if texte is None else texte
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.appels.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=self.texte)])


def bloc(client):
    return client.appels[0]["messages"][0]["content"][0]


def test_pdf_envoye_comme_document():
    c = FauxClaude()
    analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"%PDF" * 40, c, CFG)
    b = bloc(c)
    assert b["type"] == "document" and b["source"]["media_type"] == "application/pdf"
    assert "\n" not in b["source"]["data"]


def test_image_envoyee_comme_image():
    c = FauxClaude()
    analyser_piece(PieceJointe(1, "p.jpg", "image/jpeg"), b"\xff\xd8jpeg", c, CFG)
    assert bloc(c)["type"] == "image" and bloc(c)["source"]["media_type"] == "image/jpeg"


def test_facture_extraite():
    a = analyser_piece(PieceJointe(7, "f.pdf", "application/pdf"), b"%PDF", FauxClaude(), CFG)
    assert (a.piece_id, a.genre) == (7, "facture")
    assert (a.facture.fournisseur, a.facture.numero, str(a.facture.date), a.facture.sous_total) == ("Rona", "A-1", "2026-11-02", 20.0)
    assert [(l.description, l.quantite, l.prix_unitaire) for l in a.facture.lignes] == [("Vis", 2, 10.0)]


def test_photo():
    texte = json.dumps({**FACTURE_JSON, "genre": "photo", "raison": "Photo du lavabo", "lignes": []})
    a = analyser_piece(PieceJointe(1, "p.jpg", "image/jpeg"), b"x", FauxClaude(texte), CFG)
    assert (a.genre, a.facture) == ("photo", None)


def test_facture_sans_lignes_devient_incertaine():
    texte = json.dumps({**FACTURE_JSON, "lignes": []})
    a = analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"x", FauxClaude(texte), CFG)
    assert a.genre == "incertain"


def test_type_non_lisible():
    c = FauxClaude()
    a = analyser_piece(PieceJointe(1, "IMG.heic", "image/heic"), b"x", c, CFG)
    assert (a.genre, a.raison) == ("incertain", "Format non lisible (image/heic)")
    assert c.appels == []


def test_trop_gros():
    c = FauxClaude()
    a = analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"0" * (31 * 1024 * 1024), c, CFG)
    assert a.genre == "incertain" and "trop gros" in a.raison
    assert c.appels == []


def test_refus():
    a = analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"x", FauxClaude(stop_reason="refusal"), CFG)
    assert a.genre == "incertain" and a.raison


def test_json_invalide():
    a = analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"x", FauxClaude("pas du json"), CFG)
    assert a.genre == "incertain"


def test_parametres_api():
    c = FauxClaude()
    analyser_piece(PieceJointe(1, "f.pdf", "application/pdf"), b"x", c, CFG)
    k = c.appels[0]
    assert k["model"] == "claude-opus-5-5"
    assert k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
    assert k["output_config"]["effort"] == "medium"
    assert k["output_config"]["format"]["type"] == "json_schema"
