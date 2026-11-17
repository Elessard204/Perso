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
    assert set(etat["cles"]) == {"progression", "claude", "google"}
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
    assert code == 200 and r["marge"] == 0.15 and r["pas_minutes"] == 15
    assert site("/regles", {**r, "montant_max_ligne": 1500, "transport_max_minutes": 45})[0] == 200
    _, r2 = site("/regles")
    assert (r2["marge"], r2["montant_max_ligne"], r2["transport_max_minutes"]) == (0.15, 1500, 45)
    assert r2["tarifs"]["Maintenance"]["heure"] == 45.0 and r2["tarifs"]["Rénovation"]["heure"] == 85.0  # tarifs conservés


def test_couts_horaires_des_techniciens(site):
    _, r = site("/regles")
    assert r["cout_horaire_defaut"] == 0.0 and r["couts_techniciens"] == {}
    code, r2 = site("/regles", {**r, "cout_horaire_defaut": "32,50",
                                "couts_techniciens": {"Harry Charlette": "35", "  ": "20", "Vide": ""}})
    assert code == 200
    assert r2["cout_horaire_defaut"] == 32.5 and r2["couts_techniciens"] == {"Harry Charlette": 35.0}
    assert r2["tarifs"]["Maintenance"]["heure"] == 45.0          # tarifs toujours conservés
    code, r3 = site("/regles", {**r2, "charges_feries": "0,042", "charges_das": "0,11"})
    assert code == 200 and r3["charges_feries"] == 0.042 and r3["charges_das"] == 0.11
    assert site("/regles", {**r3, "charges_das": "0,9"})[0] == 400
    assert site("/regles", {**r2, "couts_techniciens": {"Harry Charlette": "-3"}})[0] == 400
    assert site("/regles", {**r2, "couts_techniciens": ["pas", "un", "dict"]})[0] == 400


def test_techniciens_connus_proposes(site):
    charger_et_analyser(site)
    _, r = site("/regles")
    assert r["techniciens_connus"] and all(isinstance(t, str) and t for t in r["techniciens_connus"])


def test_salaire_fixe_forfaits_et_seuil_rabais(site):
    _, r = site("/regles")
    code, r2 = site("/regles", {**r, "salaire_fixe": ["Harry Charlette", " ", "Harry Charlette"],
                                "produits_forfait": "Bacs,  Ménage commun ,", "seuil_rabais": "75"})
    assert code == 200
    assert r2["salaire_fixe"] == ["Harry Charlette"] and r2["produits_forfait"] == ["Bacs", "Ménage commun"]
    assert r2["seuil_rabais"] == 75.0 and r2["tarifs"]["Maintenance"]["heure"] == 45.0
    assert site("/regles", {**r2, "salaire_fixe": {"pas": "une liste"}})[0] == 400
    assert site("/regles", {**r2, "seuil_rabais": "-1"})[0] == 400


def test_rabais_raison_et_releve(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    _, d = site(f"/bon/{bon['id']}")
    assert not d["proposition"]["rabais"]
    i = next(i for i, l in enumerate(d["proposition"]["lignes"]) if l["libelle"].startswith("Main"))
    code, d = site(f"/bon/{bon['id']}/modifier", {"champ": f"ligne:{i}:quantite", "valeur": "0,25"})
    assert code == 200 and d["proposition"]["rabais"]["montant"] > 50
    assert "rabais" in [a["code"] for a in d["proposition"]["alertes"]]
    code, d = site(f"/bon/{bon['id']}/modifier", {"champ": "raison_rabais", "valeur": "  Ramené au devis  "})
    assert code == 200 and d["proposition"]["rabais"]["raison"] == "Ramené au devis"
    assert site("/approuver", {"bon_ids": [bon["id"]]})[0] == 200
    _, h = site("/historique")
    [x] = h["rabais"]
    assert (x["code"], x["raison"]) == ("BS-2001", "Ramené au devis") and x["montant"] == d["proposition"]["rabais"]["montant"]
    site(f"/bon/{bon['id']}/modifier", {"champ": "raison_rabais", "valeur": "Client plafonné"})
    assert site("/bons")[1]["bons"][[b["code"] for b in site("/bons")[1]["bons"]].index("BS-2001")]["approuve"]
    assert site("/historique")[1]["rabais"][0]["raison"] == "Client plafonné"   # raison ajoutée après approbation
    autre = next(b for b in bons.values() if b["statut"] != "bloque" and b["code"] != "BS-2001")
    assert site(f"/bon/{autre['id']}/modifier", {"champ": "raison_rabais", "valeur": "x"})[0] == 400


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
    assert 'data-vue="kilometrage"' in page and "Seuil d'écart" in page
    assert "Vacances (0,06 chez Progim)" in page and "Fériés (0,05 chez Progim)" in page


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
                                           ("regle_transports", "autre"), ("pas_minutes", 0),
                                           ("transport_max_minutes", 0), ("marge_minimum", 2)])
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
    import shutil
    monkeypatch.setenv("APPDATA", str(tmp_path))
    logiciel = tmp_path / "logiciel"
    shutil.copytree(LOGICIEL, logiciel, ignore=shutil.ignore_patterns("demo", "cache", "journal", "__pycache__"))
    cfg = (logiciel / "config.toml").read_text(encoding="utf-8")
    (logiciel / "config.toml").write_text(cfg.replace('logic_ids_a_facturer = "600"', 'logic_ids_a_facturer = ""'),
                                          encoding="utf-8")
    app = Application(logiciel, demo=False, personne="hugo", donnees=tmp_path)
    with pytest.raises(ErreurDemande, match="config.toml"):
        app.charger("2026-11-01", "2026-11-30")


def test_type_de_bon_facultatif(tmp_path, monkeypatch):
    # Hugo traite les deux types (Maintenance et Appel de service) : sans type, on charge tous les bons terminés.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = Application(LOGICIEL, demo=False, personne="hugo", donnees=tmp_path)
    with pytest.raises(ErreurDemande, match="Clés manquantes"):   # passe la vérification de configuration
        app.charger("2026-11-01", "2026-11-30")


def test_nom_de_la_personne_garde_ses_accents():
    from interface import nom_personne
    assert nom_personne("ÉricLessard") == "ÉricLessard"
    assert nom_personne("hugo.b") == "hugo.b"
    assert nom_personne("a/b:c") == "a_b_c"

def attendre(appel):
    for _ in range(200):
        if not appel("/progres")[1]["en_cours"]:
            return
        time.sleep(0.05)


def test_garde_fou_achat_en_demo(site):
    bons = charger_et_analyser(site)
    _, detail = site(f"/bon/{bons['BS-2003']['id']}")
    assert detail["bon"]["achat"] == "Silicone"
    assert "achat_sans_facture" in [a["code"] for a in detail["proposition"]["alertes"]]
    _, detail = site(f"/bon/{bons['BS-2006']['id']}")
    assert "facture_sans_achat" in [a["code"] for a in detail["proposition"]["alertes"]]


def _codes(site, bons, code):
    return [a["code"] for a in site(f"/bon/{bons[code]['id']}")[1]["proposition"]["alertes"]]


def test_garde_fous_v2_en_demo(site):
    bons = charger_et_analyser(site)
    assert "transport_double" in _codes(site, bons, "BS-2007")          # même immeuble, même jour que BS-2004
    assert "transport_double" not in _codes(site, bons, "BS-2004")
    assert "tarif_non_standard" in _codes(site, bons, "BS-2007")         # 85 $/h (SRP) sur une maintenance
    assert "heures_non_facturees" in _codes(site, bons, "BS-2007") and bons["BS-2007"]["statut"] == "bloque"
    assert "inventaire_a_zero" not in _codes(site, bons, "BS-2005")       # 0 $ en inventaire = aucun matériel
    assert "transport_long" in _codes(site, bons, "BS-2001")
    _, d = site(f"/bon/{bons['BS-2003']['id']}")
    prix = {l["libelle"].split(" ")[0]: l["prix"] for l in d["proposition"]["lignes"]}
    assert prix == {"Transport": 40.0, "Main": 45.0}                    # tarifs SELP appliqués à une maintenance
    assert d["proposition"]["marge"]["revenu"] > 0


def test_regles_kilometrage_survivent_a_la_reecriture(site):
    _, r = site("/regles")
    assert r["km_debut_reference"] == "2026-11-08" and r["km_taux"] == 0.61
    assert site("/regles", {**r, "marge": 0.2})[0] == 200
    _, r2 = site("/regles")
    assert (r2["km_debut_reference"], r2["km_taux"], r2["km_seuil_ecart"]) == ("2026-11-08", 0.61, 10.0)


# ---------- kilométrage ----------
DEBUT_KM = "2026-10-25"
TECHS_KM = {"Luc Tremblay": {"code_postal": "h1a 1a1", "paye_km": True},
            "Max Roy": {"code_postal": "H2B 2B2", "paye_km": True}}


@pytest.fixture
def km_site(site, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return site


def attendre_km(appel):
    for _ in range(200):
        if not appel("/km/progres")[1]["en_cours"]:
            return appel("/km/progres")[1]
        time.sleep(0.05)


def reglages_km(appel, techniciens=None):
    return appel("/km/reglages", {"taux": "0,61", "seuil_km": 15, "debut_reference": "2026-11-08",
                                  "techniciens": TECHS_KM if techniciens is None else techniciens})


def calculer_km(appel):
    assert reglages_km(appel)[0] == 200
    code, _ = appel("/km/calculer", {"debut": DEBUT_KM})
    assert code == 200
    assert "terminé" in attendre_km(appel)["message"]


def telecharger(site, chemin):
    req = urllib.request.Request(site.base + chemin, headers={"X-Jeton": site.app.jeton})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_km_reglages_aller_retour(km_site, tmp_path):
    code, r = reglages_km(km_site)
    assert code == 200
    code, lus = km_site("/km/reglages")
    assert code == 200
    assert lus["taux"] == 0.61 and lus["seuil_km"] == 15 and lus["debut_reference"] == "2026-11-08"
    assert lus["techniciens"]["Luc Tremblay"] == {"code_postal": "H1A 1A1", "paye_km": True}
    assert "google" not in json.dumps(lus).lower()
    texte = (tmp_path / "regles.toml").read_text(encoding="utf-8")
    assert "[kilometrage]" in texte and "seuil_ecart_km = 15" in texte
    assert "[tarifs" in texte   # les autres sections sont conservées


def test_km_reglages_invalides(km_site):
    base = {"taux": 0.61, "seuil_km": 10, "debut_reference": "2026-11-08", "techniciens": {}}
    assert km_site("/km/reglages", {**base, "debut_reference": "2026-11-09"})[0] == 400   # un lundi
    assert km_site("/km/reglages", {**base, "taux": 9})[0] == 400
    assert km_site("/km/reglages", {**base, "seuil_km": 5000})[0] == 400
    code, r = km_site("/km/reglages", {**base, "techniciens": {"Luc": {"code_postal": "J4W", "paye_km": True}}})
    assert code == 400 and "J4W" in r["erreur"]
    assert km_site("/km/reglages", {**base, "techniciens": {"Luc": "x"}})[0] == 400
    assert km_site("/km/reglages", {**base, "techniciens": ["Luc"]})[0] == 400


def test_km_periodes(km_site):
    code, r = km_site("/km/periodes")
    assert code == 200 and len(r["periodes"]) == 4
    assert r["periodes"][0] == {"debut": "2026-10-25", "fin": "2026-11-07",
                                "libelle": "du dim. 25 octobre au sam. 7 novembre 2026"}
    assert r["periodes"][1]["libelle"] == "du dim. 11 au sam. 24 octobre 2026"


def test_km_calcul_et_periode(km_site):
    assert km_site(f"/km/periode?debut={DEBUT_KM}")[1] == {"periode": None}
    assert km_site("/km/calculer", {"debut": "2026-10-26"})[0] == 400   # pas un début de période
    calculer_km(km_site)
    code, r = km_site(f"/km/periode?debut={DEBUT_KM}")
    assert code == 200 and r["periode"]["techniciens"]
    code, r = km_site("/km/reglages")
    assert r["techniciens_connus"] == []
    km_site("/km/reglages", {"taux": 0.61, "seuil_km": 10, "debut_reference": "2026-11-08", "techniciens": {}})
    assert set(km_site("/km/reglages")[1]["techniciens_connus"]) >= {"Luc Tremblay"}


def test_km_calcul_refuse_si_occupe_et_erreur_lisible(km_site):
    km_site.app.progres["en_cours"] = True
    code, r = km_site("/km/calculer", {"debut": DEBUT_KM})
    km_site.app.progres["en_cours"] = False
    assert code == 400 and "en cours" in r["erreur"]


def test_km_ajuster_valider_exporter(km_site):
    calculer_km(km_site)
    periode = km_site(f"/km/periode?debut={DEBUT_KM}")[1]["periode"]
    luc = next(t for t in periode["techniciens"] if t["nom"] == "Luc Tremblay")
    jour = luc["details"][0]["jour"]
    code, r = km_site("/km/ajuster", {"debut": DEBUT_KM, "technicien": "Luc Tremblay", "jour": jour,
                                      "uhaul": False, "magasin_km": 12})
    assert code == 200
    luc = next(t for t in r["periode"]["techniciens"] if t["nom"] == "Luc Tremblay")
    assert luc["km_magasin"] == 12
    assert km_site("/km/ajuster", {"debut": DEBUT_KM, "technicien": "Luc Tremblay", "jour": jour,
                                   "uhaul": False, "magasin_km": "abc"})[0] == 400
    code, _, corps = telecharger(km_site, f"/km/export?debut={DEBUT_KM}")
    assert code == 400 and "Valider la période" in json.loads(corps)["erreur"]
    code, r = km_site("/km/valider", {"debut": DEBUT_KM})
    assert code == 200 and r["periode"]["statut"] == "valide"
    code, entetes, corps = telecharger(km_site, f"/km/export?debut={DEBUT_KM}")
    assert code == 200 and corps[:2] == b"PK"
    assert entetes["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert entetes["Content-Disposition"].startswith("attachment; filename*=UTF-8''")
    assert km_site("/km/ajuster", {"debut": DEBUT_KM, "technicien": "Luc Tremblay", "jour": jour,
                                   "uhaul": True, "magasin_km": 0})[0] == 400


def test_km_rouvrir(km_site):
    calculer_km(km_site)
    km_site("/km/valider", {"debut": DEBUT_KM})
    code, r = km_site("/km/rouvrir", {"debut": DEBUT_KM, "raison": ""})
    assert code == 400
    code, r = km_site("/km/rouvrir", {"debut": DEBUT_KM, "raison": "Oubli d'une journée"})
    assert code == 200 and r["periode"]["statut"] == "brouillon" and r["periode"]["revision"] == 1


def test_km_sans_jeton_refuse(site):
    req = urllib.request.Request(site.base + f"/km/periode?debut={DEBUT_KM}")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 403


def test_cles_accepte_google(km_site):
    code, etat = km_site("/cles", {"google": "AIza-fausse"})
    assert code == 200 and etat["cles"]["google"] is True


def test_periodes_km_dans_le_profil_en_mode_reel(tmp_path, monkeypatch):
    # Les fichiers de période contiennent les codes postaux : jamais dans le dossier partagé (SharePoint).
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    reel = Application(LOGICIEL, demo=False, personne="hugo", donnees=tmp_path / "partage")
    assert reel.km().dossier == tmp_path / "appdata" / "ProgimRevisionBons" / "kilometrage"
    demo = Application(LOGICIEL, demo=True, personne="hugo", donnees=tmp_path / "demo")
    assert demo.km().dossier == tmp_path / "demo" / "kilometrage"


def test_km_reglages_inscrits_au_journal_sans_codes_postaux(km_site):
    assert reglages_km(km_site)[0] == 200
    modifies = {"Luc Tremblay": {"code_postal": "H1A 1A2", "paye_km": True},
                "Max Roy": {"code_postal": "H2B 2B2", "paye_km": False}}
    assert km_site("/km/reglages", {"taux": "0,65", "seuil_km": 15, "debut_reference": "2026-11-22",
                                    "techniciens": modifies})[0] == 200
    assert km_site("/km/reglages", {"taux": "0,65", "seuil_km": 15, "debut_reference": "2026-11-22",
                                    "techniciens": modifies})[0] == 200          # rien de changé : pas de ligne
    evenements = [e for e in km_site("/historique")[1]["evenements"] if e["evenement"] == "km_reglages"]
    assert len(evenements) == 2
    dernier = evenements[0]
    assert dernier["bon_id"] == 0 and dernier["maj"] == "" and dernier["personne"] == "hugo"
    d = dernier["details"]
    assert d["avant"] == {"taux": 0.61, "seuil_km": 15.0, "debut_reference": "2026-11-08"}
    assert d["apres"] == {"taux": 0.65, "seuil_km": 15.0, "debut_reference": "2026-11-22"}
    assert d["techniciens"] == {
        "Luc Tremblay": {"paye_km_avant": True, "paye_km_apres": True, "code_postal_modifie": "oui"},
        "Max Roy": {"paye_km_avant": True, "paye_km_apres": False, "code_postal_modifie": "non"}}
    premier = evenements[1]["details"]["techniciens"]
    assert premier["Luc Tremblay"] == {"paye_km_avant": None, "paye_km_apres": True, "code_postal_modifie": "oui"}
    texte = json.dumps(evenements, ensure_ascii=False).upper()
    for code in ("H1A", "H2B", "1A1", "1A2", "2B2"):
        assert code not in texte


def test_transport_long_disparait_quand_hugo_modifie_la_ligne(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    _, d = site(f"/bon/{bon['id']}")
    [alerte] = [a for a in d["proposition"]["alertes"] if a["code"] == "transport_long"]
    lignes = d["proposition"]["lignes"]
    cible = next(i for i, l in enumerate(lignes) if l["id"] == alerte["ligne_id"])
    autre = next(i for i, l in enumerate(lignes) if i != cible)
    _, d = site(f"/bon/{bon['id']}/modifier", {"champ": f"ligne:{autre}:libelle", "valeur": "Autre texte"})
    assert "transport_long" in [a["code"] for a in d["proposition"]["alertes"]]   # autre ligne : l'alerte reste
    _, d = site(f"/bon/{bon['id']}/modifier", {"champ": f"ligne:{cible}:quantite", "valeur": "3"})
    assert "transport_long" not in [a["code"] for a in d["proposition"]["alertes"]]
    _, d = site(f"/bon/{bon['id']}")                                               # gardé dans le cache
    assert "transport_long" not in [a["code"] for a in d["proposition"]["alertes"]]


def test_ligne_retiree_revient_si_hugo_lui_donne_une_quantite(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    p = site.app.bons[bon["id"]]["proposition"]
    i, l = next((i, l) for i, l in enumerate(p.lignes) if l.libelle.startswith("Transport"))
    l.quantite = 0.0
    p.lignes_retirees = [l.id]
    _, d = site(f"/bon/{bon['id']}/modifier", {"champ": f"ligne:{i}:quantite", "valeur": "1"})
    assert l.id not in d["proposition"]["lignes_retirees"]


def test_assistant_repond_avec_le_bon_et_consigne_la_question(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    code, r = site("/assistant", {"question": "Pourquoi ce transport ?", "bon_id": bon["id"]})
    assert code == 200 and "BS-2001" in r["reponse"]
    code, r2 = site("/assistant", {"question": "Et l'arrondi ?", "bon_id": bon["id"],
                                   "historique": [{"question": "Pourquoi ce transport ?", "reponse": r["reponse"]}]})
    assert code == 200
    _, h = site("/historique")
    assert [q["details"]["question"] for q in h["questions"]] == ["Et l'arrondi ?", "Pourquoi ce transport ?"]
    assert h["questions"][0]["details"]["code"] == "BS-2001"
    assert all(e["evenement"] != "question" for e in h["evenements"])     # le journal des bons reste à part


def test_assistant_sans_bon_et_validations(site):
    code, r = site("/assistant", {"question": "Comment charger les bons ?"})
    assert code == 200 and r["reponse"]
    assert site("/assistant", {"question": "   "})[0] == 400
    assert site("/assistant", {"question": "x" * 2001})[0] == 400
    assert site("/assistant", {"question": "?", "historique": "pas une liste"})[0] == 400


def test_assistant_ne_modifie_rien(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    avant = site(f"/bon/{bon['id']}")[1]
    site("/assistant", {"question": "Approuve ce bon et mets 10 h.", "bon_id": bon["id"]})
    apres = site(f"/bon/{bon['id']}")[1]
    assert avant["proposition"] == apres["proposition"] and avant["liste"]["approuve"] == apres["liste"]["approuve"]


def test_recommandations_brouillon_enregistrement_statut_export(site):
    bons = charger_et_analyser(site)
    bon = bons["BS-2001"]
    code, b = site("/recommandation/brouillon", {"bon_id": bon["id"],
                                                 "historique": [{"question": "Q", "reponse": "R"}]})
    assert code == 200 and b["titre"] and isinstance(b["solutions"], list) and "BS-2001" in b["cas"]
    code, r = site("/recommandation", {"titre": "Transport du magasin", "probleme": "Deux trajets le même jour.",
                                      "cas": "BS-2001", "solutions": ["Un seul transport", ""], "bon_id": bon["id"]})
    assert code == 200
    [reco] = r["recommandations"]
    assert (reco["titre"], reco["statut"], reco["solutions"], reco["code"]) == (
        "Transport du magasin", "nouvelle", ["Un seul transport"], "BS-2001")
    code, r = site("/recommandation/statut", {"id": reco["id"], "statut": "retenue", "note": "On le fait."})
    assert code == 200 and (r["recommandations"][0]["statut"], r["recommandations"][0]["note"]) == ("retenue", "On le fait.")
    assert site("/recommandations")[1]["recommandations"][0]["statut"] == "retenue"
    assert site("/recommandation/statut", {"id": reco["id"], "statut": "bidon"})[0] == 400
    assert site("/recommandation/statut", {"id": "inconnu", "statut": "faite"})[0] == 400
    assert site("/recommandation", {"titre": "  ", "probleme": "x"})[0] == 400
    assert site("/recommandation", {"titre": "x", "solutions": {"pas": "une liste"}})[0] == 400
    code, entetes, corps = telecharger(site, "/recommandations/export")
    assert code == 200 and corps[:2] == b"PK" and "attachment" in entetes["Content-Disposition"]


def test_brouillon_sans_conversation_est_vide(site):
    code, b = site("/recommandation/brouillon", {"historique": []})
    assert code == 200 and b == {"titre": "", "probleme": "", "cas": "", "solutions": []}


def test_analyser_sans_bon_coche_ne_fait_rien(site):
    # Essai d'Éric le 17 novembre : « Analyser » sans rien cocher analysait toute la période (et coûtait).
    code, liste = site("/charger", {"debut": "2026-11-01", "fin": "2026-11-30"})
    assert code == 200
    code, r = site("/analyser", {"bon_ids": []})
    assert code == 400 and "Cocher" in r["erreur"]
    assert all(b["statut"] == "a_analyser" for b in site("/bons")[1]["bons"])


def test_reanalyser_seulement_les_bons_demandes(site, monkeypatch):
    import interface
    bons = charger_et_analyser(site)
    effaces = []
    monkeypatch.setattr(interface, "effacer_cache", lambda cache, bon_id: effaces.append(bon_id))
    ids = [bons["BS-2001"]["id"], bons["BS-2003"]["id"]]
    site("/analyser", {"bon_ids": ids, "forcer_ids": [ids[0]]})
    attendre(site)
    assert effaces == [ids[0]]
