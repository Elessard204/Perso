import json
import shutil
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import LOGICIEL
from interface import Application, ErreurDemande, Serveur, creer_gestionnaire, doit_arreter


@pytest.fixture
def site(tmp_path):
    shutil.copy(LOGICIEL / "regles.toml", tmp_path / "regles.toml")
    app = Application(LOGICIEL, demo=True, personne="hugo", donnees=tmp_path / "donnees",
                      chemin_regles=tmp_path / "regles.toml")
    serveur = Serveur(("127.0.0.1", 0), creer_gestionnaire(app))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{serveur.server_address[1]}"

    def appel(chemin, corps=None, entetes=None):
        donnees = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(base + chemin, data=donnees, method="POST" if corps is not None else "GET",
                                     headers={"Content-Type": "application/json", "X-Jeton": app.jeton,
                                              **(entetes or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    appel.base = base
    appel.app = app
    yield appel
    serveur.shutdown()


def charger_et_analyser(appel):
    code, liste = appel("/charger", {"debut": "2026-11-01", "fin": "2026-11-30"})
    assert code == 200 and liste["bons"]
    ids = [b["id"] for b in liste["bons"]]
    appel("/analyser", {"bon_ids": ids})
    attendre(appel)
    _, liste = appel("/bons")
    return {b["code"]: b for b in liste["bons"]}


def test_page_et_etat_sans_cles(site):
    code, etat = site("/etat")
    assert code == 200 and etat["demo"] is True and etat["mode_reel_permis"] is False
    assert set(etat["cles"]) == {"progression", "claude"}
    assert all(isinstance(v, bool) for v in etat["cles"].values())


def test_charger_analyser_ouvrir(site):
    bons = charger_et_analyser(site)
    assert {b["statut"] for b in bons.values()} <= {"pret", "a_verifier", "bloque"}
    bon = next(iter(bons.values()))
    code, detail = site(f"/bon/{bon['id']}")
    assert code == 200
    assert detail["proposition"]["description"] and detail["bon"]["description"]
    assert detail["pieces"]


def test_approuver_refuse_un_bon_bloque(site):
    bons = charger_et_analyser(site)
    bloque = next(b for b in bons.values() if b["statut"] == "bloque")
    code, r = site("/approuver", {"bon_ids": [bloque["id"]]})
    assert code == 400 and "bloqué" in r["erreur"]


def test_modifier_puis_approuver_puis_simuler(site):
    bons = charger_et_analyser(site)
    bon = next(b for b in bons.values() if b["statut"] != "bloque")
    code, _ = site(f"/bon/{bon['id']}/modifier", {"champ": "description", "valeur": "Texte de Hugo."})
    assert code == 200
    _, detail = site(f"/bon/{bon['id']}")
    assert detail["proposition"]["description"] == "Texte de Hugo."
    assert site("/approuver", {"bon_ids": [bon["id"]]})[0] == 200
    code, r = site("/envoyer", {"mode": "simulation"})
    assert code == 200 and [x["resultat"] for x in r["resultats"]] == ["simule"]


def test_modifier_quantite_ligne(site):
    bons = charger_et_analyser(site)
    bon = next(iter(bons.values()))
    assert site(f"/bon/{bon['id']}/modifier", {"champ": "ligne:0:quantite", "valeur": "3,5"})[0] == 200
    _, detail = site(f"/bon/{bon['id']}")
    assert detail["proposition"]["lignes"][0]["quantite"] == 3.5
    assert "hugo" in detail["proposition"]["origine"][str(detail["proposition"]["lignes"][0]["id"])]


def test_envoi_reel_verrouille(site):
    bons = charger_et_analyser(site)
    bon = next(b for b in bons.values() if b["statut"] != "bloque")
    site("/approuver", {"bon_ids": [bon["id"]]})
    code, r = site("/envoyer", {"mode": "reel"})
    assert code == 400 and "verrouillée" in r["erreur"]


def test_regles_aller_retour(site):
    code, r = site("/regles")
    assert code == 200 and r["marge"] == 0.10 and r["pas_minutes"] == 15
    assert site("/regles", {**r, "montant_max_ligne": 1500})[0] == 200
    _, r2 = site("/regles")
    assert (r2["marge"], r2["montant_max_ligne"]) == (0.10, 1500)


def test_regles_invalides_refusees(site):
    _, r = site("/regles")
    code, err = site("/regles", {**r, "marge": "beaucoup"})
    assert code == 400 and err["erreur"]


def test_historique_apres_approbation(site):
    bons = charger_et_analyser(site)
    bon = next(b for b in bons.values() if b["statut"] != "bloque")
    site("/approuver", {"bon_ids": [bon["id"]]})
    _, h = site("/historique")
    assert h["evenements"][0]["evenement"] == "approuve"


def test_piece_servie(site):
    bons = charger_et_analyser(site)
    _, detail = site(f"/bon/{next(iter(bons.values()))['id']}")
    pid = detail["pieces"][0]["id"]
    with urllib.request.urlopen(site.base + f"/piece/{pid}?jeton={site.app.jeton}", timeout=10) as r:
        assert r.status == 200 and r.headers["Content-Type"] in ("application/pdf", "image/png")
        assert r.read()


def test_page_html(site):
    with urllib.request.urlopen(site.base + "/", timeout=10) as r:
        page = r.read().decode("utf-8")
    assert "Révision des bons" in page and "À réviser" in page and "Règles" in page and "Historique" in page


def test_raison_montre_l_alerte_la_plus_importante(site):
    bons = charger_et_analyser(site)
    assert "Facture" in bons["BS-2002"]["raison"]          # bloquante avant le transport
    assert "Aucune heure" in bons["BS-2005"]["raison"]
    assert "transport" not in bons["BS-2003"]["raison"].lower()   # pièce illisible avant le transport



def test_page_contient_le_jeton(site):
    with urllib.request.urlopen(site.base + "/", timeout=10) as r:
        assert site.app.jeton in r.read().decode("utf-8")


def test_sans_jeton_refuse(site):
    assert site("/approuver", {"bon_ids": []}, {"X-Jeton": "faux"})[0] == 403
    assert site("/bons", None, {"X-Jeton": ""})[0] == 403


def test_host_etranger_refuse(site):
    assert site("/bons", None, {"Host": "evil.example:80"})[0] == 403


def test_origin_etrangere_refusee(site):
    assert site("/approuver", {"bon_ids": []}, {"Origin": "http://evil.example"})[0] == 403


def test_doublon_entre_deux_bons_du_lot(site):
    bons = charger_et_analyser(site)
    _, detail = site(f"/bon/{bons['BS-2002']['id']}")
    assert "facture_autre_bon" in [a["code"] for a in detail["proposition"]["alertes"]]
    _, detail = site(f"/bon/{bons['BS-2001']['id']}")
    assert "facture_autre_bon" not in [a["code"] for a in detail["proposition"]["alertes"]]


def test_charger_refuse_pendant_une_analyse(site):
    site.app.progres["en_cours"] = True
    code, r = site("/charger", {"debut": "2026-11-01", "fin": "2026-11-30"})
    assert code == 400 and "en cours" in r["erreur"]


def test_envoi_refuse_pendant_un_autre_envoi(site):
    bons = charger_et_analyser(site)
    bon = next(b for b in bons.values() if b["statut"] != "bloque")
    site("/approuver", {"bon_ids": [bon["id"]]})
    site.app.envoi_en_cours = True
    code, r = site("/envoyer", {"mode": "simulation"})
    assert code == 400 and "en cours" in r["erreur"]


@pytest.mark.parametrize("champ,valeur", [("marge", 10), ("marge", "nan"), ("marge", "inf"),
                                           ("regle_transports", "autre"), ("pas_minutes", 0)])
def test_regles_hors_bornes(site, champ, valeur):
    _, r = site("/regles")
    assert site("/regles", {**r, champ: valeur})[0] == 400


def test_forcer_reanalyse(site):
    bons = charger_et_analyser(site)
    bon_id = bons["BS-2001"]["id"]
    [fichier] = (site.app.cache).glob(f"{bon_id}_*.json")
    contenu = json.loads(fichier.read_text(encoding="utf-8"))
    contenu["description"] = "VIEUX CACHE"
    fichier.write_text(json.dumps(contenu), encoding="utf-8")
    site("/analyser", {"bon_ids": [bon_id], "forcer": False}); attendre(site)
    assert site(f"/bon/{bon_id}")[1]["proposition"]["description"] == "VIEUX CACHE"
    site("/analyser", {"bon_ids": [bon_id], "forcer": True}); attendre(site)
    assert site(f"/bon/{bon_id}")[1]["proposition"]["description"] != "VIEUX CACHE"


def test_bon_deja_envoye_reconnu_apres_redemarrage(site):
    from demo.faux_services import FausseProgression
    maj = FausseProgression().tache_brute(2001)["updated"]
    site.app.journal.inscrire("ecrit", 2001, "avant", {"maj_apres": maj})
    bons = charger_et_analyser(site)
    assert bons["BS-2001"]["statut"] == "envoye"


def test_arret_automatique_jamais_pendant_le_travail(tmp_path):
    app = Application(LOGICIEL, demo=True, personne="hugo", donnees=tmp_path)
    assert doit_arreter(app, inactif_depuis=301) is True
    assert doit_arreter(app, inactif_depuis=120) is False
    app.progres["en_cours"] = True
    assert doit_arreter(app, inactif_depuis=3600) is False


def test_configuration_vide_refusee_hors_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = Application(LOGICIEL, demo=False, personne="hugo", donnees=tmp_path)
    with pytest.raises(ErreurDemande, match="config.toml"):
        app.charger("2026-11-01", "2026-11-30")


def attendre(appel):
    for _ in range(200):
        if not appel("/progres")[1]["en_cours"]:
            return
        time.sleep(0.05)
