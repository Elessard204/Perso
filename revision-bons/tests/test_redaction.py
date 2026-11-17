import json

from redaction import nombres_absents, rediger
from test_pieces_jointes import FauxClaude

CFG = {"modele": "claude-opus-5-5", "effort": "medium"}


def reponse(texte):
    return FauxClaude(json.dumps({"texte": texte, "ajouts_photos": []}))


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


def reponse_v2(texte, ajouts=()):
    return FauxClaude(json.dumps({"texte": texte, "ajouts_photos": list(ajouts)}))


PHOTO = ("image/jpeg", b"\xff\xd8 photo")


def test_photos_et_demande_envoyees():
    c = reponse_v2("Remplacement du détecteur de fumée.")
    rediger("Détecteur de fumme", c, CFG, photos=[PHOTO, PHOTO], demande="Détecteur à remplacer au 3e")
    contenu = c.appels[0]["messages"][0]["content"]
    assert [b["type"] for b in contenu] == ["image", "image", "text"]
    assert "Détecteur à remplacer au 3e" in contenu[-1]["text"] and "Détecteur de fumme" in contenu[-1]["text"]


def test_au_plus_quatre_photos_legeres():
    c = reponse_v2("x")
    grosse = ("image/jpeg", b"0" * (5 * 1024 * 1024 + 1))
    rediger("texte", c, CFG, photos=[PHOTO] * 6 + [grosse, ("image/heic", b"x")])
    assert sum(1 for b in c.appels[0]["messages"][0]["content"] if b["type"] == "image") == 4


def test_ajouts_des_photos_signales():
    texte, alertes = rediger("Détecteur de fumme",
                             reponse_v2("Remplacé le détecteur de fumée à pile lithium 10 ans.", ["pile lithium 10 ans"]),
                             CFG, photos=[PHOTO])
    codes = [a.code for a in alertes]
    assert "description_enrichie" in codes and "pile lithium 10 ans" in alertes[codes.index("description_enrichie")].message


def test_note_vide_description_creee_a_partir_des_photos():
    texte, alertes = rediger("", reponse_v2("Réparation du plafond.", ["plafond réparé"]), CFG, photos=[PHOTO],
                             demande="Plafond à réparer")
    assert texte == "Réparation du plafond." and "description_creee" in [a.code for a in alertes]


def test_nombre_de_la_demande_accepte():
    _, alertes = rediger("posé détecteur", reponse_v2("Pose de 3 détecteurs."), CFG, demande="Installer 3 détecteurs")
    assert "redaction_chiffre" not in [a.code for a in alertes]


def test_consignes_tirees_de_l_essai_reel():
    from redaction import SYSTEME
    for consigne in ("ne la\n  transforme pas en travail fait", "jamais les photos", "formule creuse"):
        assert consigne in SYSTEME


def test_pas_de_point_double_dans_l_alerte():
    import json
    from types import SimpleNamespace
    from redaction import rediger
    rep = {"texte": "Fenêtre colmatée.", "ajouts_photos": ["Fenêtre à battant."]}
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **k: SimpleNamespace(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(rep))]))))
    _, alertes = rediger("fenetre colmate", client, {"modele": "x", "effort": "medium"})
    message = next(a.message for a in alertes if a.code == "description_enrichie")
    assert ".." not in message and message.endswith("Fenêtre à battant.")
