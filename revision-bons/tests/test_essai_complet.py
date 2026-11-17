from types import SimpleNamespace

import essai_complet


def test_compteur_additionne_les_jetons_et_estime_le_cout():
    class Client:
        beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: SimpleNamespace(
            usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000, cache_creation_input_tokens=0,
                                  cache_read_input_tokens=1_000_000))))
    c = essai_complet.Compteur(Client())
    c.beta.messages.create(model="x")
    c.beta.messages.create(model="x")
    assert c.appels == 2 and c.jetons["entree"] == 2_000_000
    assert round(c.cout(), 2) == round(2 * 4.0 + 0.2 * 20.0 + 2 * 0.20, 2)


def test_essai_en_lecture_seule():
    # L'essai ne doit jamais écrire dans Progression ni appeler l'envoi.
    source = (essai_complet.ICI / "essai_complet.py").read_text(encoding="utf-8")
    for interdit in ("mettre_a_jour", "envoyer(", "essai_ecriture", "approuver("):
        assert interdit not in source
