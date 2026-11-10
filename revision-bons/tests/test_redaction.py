import json

from redaction import nombres_absents, rediger
from test_pieces_jointes import FauxClaude

CFG = {"modele": "claude-opus-5-5", "effort": "medium"}


def reponse(texte):
    return FauxClaude(json.dumps({"texte": texte}))


def test_nombres_absents():
    assert nombres_absents("changé 2 robinets", "Remplacement de 3 robinets") == ["3"]
    assert nombres_absents("tuyau 2,5 po", "tuyau de 2.5 po") == []
    assert nombres_absents("posé 2 raccord", "Pose de deux raccords") == []
    assert nombres_absents("1 000 pi", "1000 pi") == []


def test_redaction_normale():
    c = reponse("Remplacement du robinet de cuisine et pose de 2 raccords.")
    texte, alertes = rediger("changer robinet cuisine, posé 2 raccord", c, CFG)
    assert texte == "Remplacement du robinet de cuisine et pose de 2 raccords."
    assert alertes == []
    assert c.appels[0]["model"] == "claude-opus-5-5"


def test_redaction_invente_un_nombre():
    texte, alertes = rediger("changé robinet", reponse("Remplacement de 3 robinets."), CFG)
    assert texte == "Remplacement de 3 robinets."
    assert [(a.code, a.bloquante) for a in alertes] == [("redaction_chiffre", False)]
    assert "3" in alertes[0].message


def test_texte_vide():
    c = reponse("ne devrait pas servir")
    assert rediger("   ", c, CFG) == ("", [])
    assert c.appels == []


def test_refus():
    texte, alertes = rediger("changé robinet", FauxClaude(stop_reason="refusal"), CFG)
    assert texte == "changé robinet"
    assert [a.code for a in alertes] == ["redaction_echec"]


def test_reponse_vide_garde_l_original():
    texte, alertes = rediger("changé robinet", reponse("  "), CFG)
    assert texte == "changé robinet" and [a.code for a in alertes] == ["redaction_echec"]
