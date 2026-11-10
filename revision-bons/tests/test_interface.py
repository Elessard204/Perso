import json
import shutil
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import LOGICIEL
from interface import Application, Serveur, creer_gestionnaire


@pytest.fixture
def site(tmp_path):
    shutil.copy(LOGICIEL / "regles.toml", tmp_path / "regles.toml")
    app = Application(LOGICIEL, demo=True, personne="hugo", donnees=tmp_path / "donnees",
                      chemin_regles=tmp_path / "regles.toml")
    serveur = Serveur(("127.0.0.1", 0), creer_gestionnaire(app))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{serveur.server_address[1]}"

    def appel(chemin, corps=None):
        donnees = json.dumps(corps).encode() if corps is not None else None
        req = urllib.request.Request(base + chemin, data=donnees, method="POST" if corps is not None else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    appel.base = base
    yield appel
    serveur.shutdown()


def charger_et_analyser(appel):
    code, liste = appel("/charger", {"debut": "2026-11-01", "fin": "2026-11-30"})
    assert code == 200 and liste["bons"]
    ids = [b["id"] for b in liste["bons"]]
    appel("/analyser", {"bon_ids": ids})
    for _ in range(200):
        _, p = appel("/progres")
        if not p["en_cours"]:
            break
        time.sleep(0.05)
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
    with urllib.request.urlopen(site.base + f"/piece/{pid}", timeout=10) as r:
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
