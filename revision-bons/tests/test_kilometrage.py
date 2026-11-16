import json
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from cartes import ErreurCartes
from conftest import LOGICIEL
from demo.faux_services import FaussesCartes, FausseProgression, FauxClaude
from journal import Journal
from kilometrage import Kilometrage
from regles import charger_regles

CFG = {"modele": "x", "effort": "low"}
DEBUT, FIN = date(2026, 10, 25), date(2026, 11, 7)
R = charger_regles(LOGICIEL / "regles.toml")
TECHS = {
    "Luc Tremblay": {"code_postal": "H1A 1A1", "paye_km": True},
    "Max Roy": {"code_postal": "H2B 2B2", "paye_km": True},
}


class CartesEspionnes(FaussesCartes):
    def __init__(self, echec_distance_au: int | None = None, introuvables: tuple = ()):
        self.geocodages: list[str] = []
        self.distances = 0
        self.echec_distance_au = echec_distance_au
        self.introuvables = introuvables

    def geocoder(self, code_postal):
        self.geocodages.append(code_postal)
        if code_postal in self.introuvables:
            return None
        return super().geocoder(code_postal)

    def distance_km(self, a, b):
        self.distances += 1
        if self.echec_distance_au is not None and self.distances >= self.echec_distance_au:
            raise ErreurCartes("Google Maps ne répond pas.")
        return super().distance_km(a, b)


def _km(tmp_path, cartes=None, client=None):
    journal = Journal(tmp_path / "journal", "Hugo")
    return Kilometrage(FausseProgression(), cartes or CartesEspionnes(), client or FauxClaude(), CFG,
                       tmp_path / "kilometrage", journal)


def _ligne(resultat, nom):
    return next(l for l in resultat["techniciens"] if l["nom"] == nom)


def _evenements(tmp_path, nom):
    return [e for e in Journal(tmp_path / "journal", "Hugo").historique() if e["evenement"] == nom]


def test_calcul_periode_demo(tmp_path):
    km = _km(tmp_path)
    messages = []
    assert km.calculer(DEBUT, FIN, TECHS, messages.append) is None
    fichier = tmp_path / "kilometrage" / "2026-10-25.json"
    donnees = json.loads(fichier.read_text(encoding="utf-8"))
    assert donnees["statut"] == "brouillon" and donnees["revision"] == 0 and donnees["ajustements"] == {}
    assert set(donnees["base"]["techniciens"]) == {"Luc Tremblay", "Max Roy"}   # Sam Côté : hors période
    jour = donnees["base"]["techniciens"]["Luc Tremblay"]["jours"][0]
    assert jour["jour"] == "2026-11-03" and jour["domicile"] is True and jour["minutes"] == 205
    assert jour["arrets"] == [{"code": "BS-2001", "tache_id": 2001}]
    assert [t["de"] for t in jour["troncons"]] == ["domicile", "BS-2001"]
    assert messages

    resultat = km.periode(DEBUT, TECHS, R)
    json.dumps(resultat)
    assert resultat["statut"] == "brouillon" and resultat["debut"] == "2026-10-25"
    luc = _ligne(resultat, "Luc Tremblay")
    assert luc["km_a_payer"] > 0 and luc["paie"] is True
    assert luc["montant"] == round(luc["km_a_payer"] * 0.61, 2)
    assert {b["code"] for b in luc["bons"]} == {"BS-2001", "BS-2002"}


def test_periode_sans_base(tmp_path):
    assert _km(tmp_path).periode(DEBUT, TECHS, R) is None


def test_ajuster_sans_rappeler_google(tmp_path):
    cartes = CartesEspionnes()
    km = _km(tmp_path, cartes)
    km.calculer(DEBUT, FIN, TECHS)
    avant = _ligne(km.periode(DEBUT, TECHS, R), "Luc Tremblay")
    cartes.distances, cartes.geocodages = 0, []

    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 12.5, "Hugo")
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-04", True, 0, "Hugo")
    luc = _ligne(km.periode(DEBUT, TECHS, R), "Luc Tremblay")
    assert cartes.distances == 0 and cartes.geocodages == []
    km_04 = next(d["km"] for d in avant["details"] if d["jour"] == "2026-11-04")
    assert luc["km_magasin"] == 12.5
    assert luc["km_a_payer"] == round(avant["km_a_payer"] + 12.5 - km_04, 1)

    evenements = _evenements(tmp_path, "km_ajustement")
    assert len(evenements) == 2
    details = next(e["details"] for e in evenements if e["details"]["jour"] == "2026-11-03")
    assert details == {"periode": "2026-10-25", "technicien": "Luc Tremblay", "jour": "2026-11-03",
                       "avant": {"uhaul": False, "magasin_km": 0.0}, "apres": {"uhaul": False, "magasin_km": 12.5}}
    assert all(e["bon_id"] == 0 and e["maj"] == "" for e in evenements)


def test_ajuster_borne_magasin(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    for mauvais in (-1, 500.5, float("nan")):
        with pytest.raises(ValueError):
            km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, mauvais, "Hugo")
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 500, "Hugo")
    assert _evenements(tmp_path, "km_ajustement")


def test_periode_validee_figee(tmp_path):
    cartes = CartesEspionnes()
    km = _km(tmp_path, cartes)
    km.calculer(DEBUT, FIN, TECHS)
    valide = km.valider(DEBUT, TECHS, R, "Hugo")
    assert valide["statut"] == "valide" and valide["valide_par"] == "Hugo" and valide["revision"] == 0
    assert valide["valide_le"]
    fige = km.periode(DEBUT, TECHS, R)
    assert fige == valide
    json.dumps(fige)

    autres_techs = {**TECHS, "Luc Tremblay": {"code_postal": "J4W 3J9", "paye_km": True}}
    fichier = tmp_path / "kilometrage" / "2026-10-25.json"
    contenu = fichier.read_bytes()
    cartes.distances = 0
    assert km.calculer(DEBUT, FIN, autres_techs) is None
    assert cartes.distances == 0 and fichier.read_bytes() == contenu
    assert km.periode(DEBUT, autres_techs, replace(R, km_taux=1.0)) == fige
    with pytest.raises(ValueError, match="Période validée : la rouvrir avant de modifier."):
        km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", True, 0, "Hugo")

    (evenement,) = _evenements(tmp_path, "km_validation")
    assert evenement["details"] == {"periode": "2026-10-25", "total_km": fige["total_km"],
                                    "total_montant": fige["total_montant"], "revision": 0}


def test_rouvrir_exige_raison(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    km.valider(DEBUT, TECHS, R, "Hugo")
    for raison in ("", "   ", "oups"):
        with pytest.raises(ValueError):
            km.rouvrir(DEBUT, raison, "Hugo")
    assert km.periode(DEBUT, TECHS, R)["statut"] == "valide"

    km.rouvrir(DEBUT, "erreur de Hugo", "Hugo")
    resultat = km.periode(DEBUT, TECHS, R)
    assert resultat["statut"] == "brouillon" and resultat["revision"] == 1
    donnees = json.loads((tmp_path / "kilometrage" / "2026-10-25.json").read_text(encoding="utf-8"))
    assert donnees["instantane"] is None and donnees["statut"] == "brouillon" and donnees["revision"] == 1
    (evenement,) = _evenements(tmp_path, "km_reouverture")
    assert evenement["details"] == {"periode": "2026-10-25", "raison": "erreur de Hugo", "revision": 1}

    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", True, 0, "Hugo")   # de nouveau modifiable
    assert km.valider(DEBUT, TECHS, R, "Hugo")["revision"] == 1


def test_erreur_google_pas_de_base_partielle(tmp_path):
    km = _km(tmp_path, CartesEspionnes(echec_distance_au=3))
    with pytest.raises(ErreurCartes):
        km.calculer(DEBUT, FIN, TECHS)
    assert not list(tmp_path.glob("kilometrage/*"))   # ni fichier de période, ni fichier .tmp


def test_erreur_au_recalcul_laisse_le_fichier_intact(tmp_path):
    _km(tmp_path).calculer(DEBUT, FIN, TECHS)
    km = _km(tmp_path)
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 4, "Hugo")
    fichier = tmp_path / "kilometrage" / "2026-10-25.json"
    contenu = fichier.read_bytes()

    with pytest.raises(ErreurCartes):
        _km(tmp_path, CartesEspionnes(echec_distance_au=3)).calculer(DEBUT, FIN, TECHS)
    assert fichier.read_bytes() == contenu

    class ClaudeEnPanne:
        beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(
            RuntimeError("API indisponible"))))

    with pytest.raises(RuntimeError):
        _km(tmp_path, client=ClaudeEnPanne()).calculer(DEBUT, FIN, TECHS)
    assert fichier.read_bytes() == contenu


def test_recalcul_garde_les_ajustements(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 7, "Hugo")
    km.calculer(DEBUT, FIN, TECHS)
    assert _ligne(km.periode(DEBUT, TECHS, R), "Luc Tremblay")["km_magasin"] == 7


def test_technicien_sans_code_postal_a_configurer(tmp_path):
    cartes = CartesEspionnes()
    km = _km(tmp_path, cartes)
    techs = {"Luc Tremblay": TECHS["Luc Tremblay"], "Max Roy": {"code_postal": "", "paye_km": True}}
    km.calculer(DEBUT, FIN, techs)
    assert cartes.geocodages == ["H1A 1A1"]
    resultat = km.periode(DEBUT, techs, R)
    max_roy = _ligne(resultat, "Max Roy")
    assert max_roy["statut"] == "a_configurer" and max_roy["montant"] is None
    assert all(d["domicile"] is False for d in max_roy["details"])
    assert _ligne(resultat, "Luc Tremblay")["montant"] is not None

    sous_traitant = {**TECHS, "Max Roy": {"code_postal": "H2B 2B2", "paye_km": False}}
    cartes.geocodages = []
    km.calculer(DEBUT, FIN, sous_traitant)
    assert cartes.geocodages == ["H1A 1A1"]
    assert _ligne(km.periode(DEBUT, sous_traitant, R), "Max Roy")["statut"] == "sous_traitant"


def test_code_postal_introuvable_a_verifier(tmp_path):
    km = _km(tmp_path, CartesEspionnes(introuvables=("H2B 2B2",)))
    km.calculer(DEBUT, FIN, TECHS)
    resultat = km.periode(DEBUT, TECHS, R)
    max_roy = _ligne(resultat, "Max Roy")
    assert max_roy["details"]
    for jour in max_roy["details"]:
        assert jour["domicile"] is False
        assert any("code postal introuvable" in note for note in jour["a_verifier"])
    # Pas payé comme un trajet normal : à configurer, sans montant ni écart, avec la note sur la ligne.
    assert (max_roy["statut"], max_roy["montant"], max_roy["ecart"], max_roy["paie"]) == (
        "a_configurer", None, None, False)
    assert max_roy["note"] == "code postal introuvable"
    assert max_roy["jours_a_verifier"] == len(max_roy["details"])
    luc = _ligne(resultat, "Luc Tremblay")
    assert luc["note"] is None and resultat["total_montant"] == luc["montant"]
    with pytest.raises(ValueError, match="À configurer avant de valider : Max Roy"):
        km.valider(DEBUT, TECHS, R, "Hugo")


def test_config_changee_depuis_le_calcul_recalcul_requis(tmp_path):
    km = _km(tmp_path)
    sans_code = {**TECHS, "Max Roy": {"code_postal": "", "paye_km": True}}
    km.calculer(DEBUT, FIN, sans_code)

    # Hugo saisit le code postal de Max sans recalculer : pas de montant sur des distances sans domicile.
    resultat = km.periode(DEBUT, TECHS, R)
    max_roy, luc = _ligne(resultat, "Max Roy"), _ligne(resultat, "Luc Tremblay")
    assert max_roy["statut"] == "recalcul_requis" and max_roy["montant"] is None
    assert max_roy["ecart"] is None and max_roy["paie"] is False and max_roy["km_a_payer"] == 0.0
    assert resultat["total_km"] == luc["km_a_payer"] and resultat["total_montant"] == luc["montant"]
    with pytest.raises(ValueError, match="Recalcul requis pour : Max Roy — recalculer la période avant de valider."):
        km.valider(DEBUT, TECHS, R, "Hugo")
    assert km.periode(DEBUT, TECHS, R)["statut"] == "brouillon"

    # Code corrigé pour un technicien déjà admissible : même chose.
    corrige = {**TECHS, "Luc Tremblay": {"code_postal": "J4W 3J9", "paye_km": True}}
    assert _ligne(km.periode(DEBUT, corrige, R), "Luc Tremblay")["statut"] == "recalcul_requis"
    # Devenu sous-traitant : aucun montant de toute façon, pas besoin de recalcul.
    sous_traitant = {**sans_code, "Max Roy": {"code_postal": "", "paye_km": False}}
    assert _ligne(km.periode(DEBUT, sous_traitant, R), "Max Roy")["statut"] == "sous_traitant"

    km.calculer(DEBUT, FIN, TECHS)
    resultat = km.periode(DEBUT, TECHS, R)
    assert _ligne(resultat, "Max Roy")["montant"] > 0
    assert km.valider(DEBUT, TECHS, R, "Hugo")["statut"] == "valide"


def test_code_introuvable_puis_corrige_recalcul_requis(tmp_path):
    km = _km(tmp_path, CartesEspionnes(introuvables=("H2B 2B2",)))
    km.calculer(DEBUT, FIN, TECHS)
    assert _ligne(km.periode(DEBUT, TECHS, R), "Max Roy")["statut"] != "recalcul_requis"
    corrige = {**TECHS, "Max Roy": {"code_postal": "H2B 2B3", "paye_km": True}}
    max_roy = _ligne(km.periode(DEBUT, corrige, R), "Max Roy")
    assert max_roy["statut"] == "recalcul_requis" and max_roy["note"] is None


def test_validation_pendant_le_calcul_gardee(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    autre = _km(tmp_path)

    def valider_pendant(message):
        if message.startswith("Calcul des distances"):
            autre.valider(DEBUT, TECHS, R, "Hugo")

    assert km.calculer(DEBUT, FIN, TECHS, valider_pendant) is None
    fige = km.periode(DEBUT, TECHS, R)
    assert fige["statut"] == "valide" and fige["valide_par"] == "Hugo"
    donnees = json.loads((tmp_path / "kilometrage" / "2026-10-25.json").read_text(encoding="utf-8"))
    assert donnees["instantane"] is not None


def test_ajustement_pendant_le_calcul_garde(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)

    def ajuster_pendant(message):
        if message.startswith("Calcul des distances"):
            km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 9, "Hugo")

    km.calculer(DEBUT, FIN, TECHS, ajuster_pendant)
    assert _ligne(km.periode(DEBUT, TECHS, R), "Luc Tremblay")["km_magasin"] == 9


def test_reouverture_garde_le_taux_de_la_validation(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    plus_cher = replace(R, km_taux=0.70, km_seuil_ecart=99.0)
    assert km.periode(DEBUT, TECHS, plus_cher)["taux"] == 0.70      # jamais validée : taux actuel
    valide = km.valider(DEBUT, TECHS, R, "Hugo")
    assert valide["taux"] == 0.61
    donnees = json.loads((tmp_path / "kilometrage" / "2026-10-25.json").read_text(encoding="utf-8"))
    assert (donnees["taux"], donnees["seuil_km"]) == (0.61, R.km_seuil_ecart)

    km.rouvrir(DEBUT, "erreur de Hugo", "Hugo")                    # le taux a changé entre-temps
    rouverte = km.periode(DEBUT, TECHS, plus_cher)
    assert rouverte["taux"] == 0.61 and rouverte["seuil_km"] == R.km_seuil_ecart
    for nom in TECHS:
        assert _ligne(rouverte, nom)["montant"] == _ligne(valide, nom)["montant"]
    assert rouverte["total_montant"] == valide["total_montant"]
    km.calculer(DEBUT, FIN, TECHS)                                  # même après un recalcul
    assert km.periode(DEBUT, TECHS, plus_cher)["taux"] == 0.61
    assert km.valider(DEBUT, TECHS, plus_cher, "Hugo")["taux"] == 0.61


def test_validation_refusee_si_technicien_a_configurer(tmp_path):
    km = _km(tmp_path)
    techs = {"Luc Tremblay": TECHS["Luc Tremblay"]}                # Max Roy jamais configuré
    km.calculer(DEBUT, FIN, techs)
    message = ("À configurer avant de valider : Max Roy — inscrire le code postal ou décocher "
               "« Employé Progim » (sous-traitant).")
    with pytest.raises(ValueError) as erreur:
        km.valider(DEBUT, techs, R, "Hugo")
    assert str(erreur.value) == message
    sans_code = {**techs, "Max Roy": {"code_postal": "", "paye_km": True}}
    with pytest.raises(ValueError, match="À configurer avant de valider : Max Roy"):
        km.valider(DEBUT, sans_code, R, "Hugo")
    assert km.periode(DEBUT, techs, R)["statut"] == "brouillon" and not _evenements(tmp_path, "km_validation")
    sous_traitant = {**techs, "Max Roy": {"code_postal": "", "paye_km": False}}
    assert km.valider(DEBUT, sous_traitant, R, "Hugo")["statut"] == "valide"


def test_jours_a_verifier_par_technicien(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    for ligne in km.periode(DEBUT, TECHS, R)["techniciens"]:
        assert ligne["jours_a_verifier"] == sum(1 for d in ligne["details"] if d["a_verifier"])


def test_pas_de_distances_pour_les_techniciens_non_admissibles(tmp_path):
    cartes = CartesEspionnes()
    km = _km(tmp_path, cartes)
    techs = {"Luc Tremblay": {"code_postal": "", "paye_km": False}, "Max Roy": {"code_postal": "", "paye_km": True}}
    km.calculer(DEBUT, FIN, techs)                                  # Max a une journée à plusieurs arrêts
    assert cartes.distances == 0 and cartes.geocodages == []
    base = json.loads((tmp_path / "kilometrage" / "2026-10-25.json").read_text(encoding="utf-8"))["base"]
    for tech in base["techniciens"].values():
        assert tech["jours"] and all(j["km"] == 0.0 and j["troncons"] == [] and j["arrets"] for j in tech["jours"])
    km.calculer(DEBUT, FIN, TECHS)                                  # configurés plus tard : recalculés
    assert cartes.distances > 0


def test_erreur_google_dit_quel_technicien_et_quel_jour(tmp_path):
    km = _km(tmp_path, CartesEspionnes(echec_distance_au=3))       # 3e tronçon : Luc, 2e journée
    with pytest.raises(ErreurCartes) as erreur:
        km.calculer(DEBUT, FIN, TECHS)
    assert str(erreur.value) == "Google Maps ne répond pas. (technicien Luc Tremblay, jour 2026-11-04, bons BS-2002)"


def test_magasin_arrondi_au_dixieme(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 12.34, "Hugo")
    luc = _ligne(km.periode(DEBUT, TECHS, R), "Luc Tremblay")
    assert luc["km_magasin"] == 12.3
    assert next(d for d in luc["details"] if d["jour"] == "2026-11-03")["magasin_km"] == 12.3
    (evenement,) = _evenements(tmp_path, "km_ajustement")
    assert evenement["details"]["apres"] == {"uhaul": False, "magasin_km": 12.3}
    km.ajuster(DEBUT, "Luc Tremblay", "2026-11-03", False, 12.31, "Hugo")   # même valeur arrondie : rien
    assert len(_evenements(tmp_path, "km_ajustement")) == 1


def test_date_du_calcul_dans_la_periode(tmp_path):
    km = _km(tmp_path)
    km.calculer(DEBUT, FIN, TECHS)
    donnees = json.loads((tmp_path / "kilometrage" / "2026-10-25.json").read_text(encoding="utf-8"))
    brouillon = km.periode(DEBUT, TECHS, R)
    assert brouillon["calcule_le"] == donnees["base"]["calcule_le"] and brouillon["calcule_le"]
    assert km.valider(DEBUT, TECHS, R, "Hugo")["calcule_le"] == brouillon["calcule_le"]
