from datetime import timedelta
from pathlib import Path

from conftest import J, LOGICIEL
from modele import EntreeTemps, Facture, LigneFacture
from regles import (
    arrondir_minutes,
    charger_regles,
    garde_fous_facture,
    garde_fous_temps,
    heures_facturees,
    lignes_materiel,
    prix_avec_marge,
)

R = charger_regles(LOGICIEL / "regles.toml")


def codes(alertes):
    return [a.code for a in alertes]


def test_regles_toml():
    assert (R.pas_minutes, R.marge, R.regle_transports) == (15, 0.10, "conserver")
    assert (R.ecart_sous_total, R.jours_max_facture, R.montant_max_ligne, R.heures_max_jour) == (0.05, 30, 1000.00, 12)


def test_arrondi():
    assert arrondir_minutes(125) == 135   # 2 h 05 -> 2 h 15
    assert arrondir_minutes(135) == 135   # 2 h 15 reste
    assert arrondir_minutes(1) == 15
    assert arrondir_minutes(0) == 0


def test_arrondi_par_technicien_et_non_sur_le_total():
    e = [EntreeTemps(1, "Luc", J, 65, 10), EntreeTemps(2, "Max", J, 65, 11)]
    assert heures_facturees(e, 15) == {"Luc": 1.25, "Max": 1.25}   # 2 h 30, pas 2 h 15


def test_arrondi_sur_total_du_technicien():
    e = [EntreeTemps(1, "Luc", J, 50, 10), EntreeTemps(2, "Luc", J, 20, 10)]
    assert heures_facturees(e, 15) == {"Luc": 1.25}   # 70 min -> 75


def test_marge():
    assert prix_avec_marge(12.34, 0.10) == 13.57
    assert prix_avec_marge(100.00, 0.10) == 110.00


def test_lignes_materiel_cout_et_prix():
    f = Facture("Rona", "A-1", J, 20.0, [LigneFacture("Vis", 2, 10.0)])
    [l] = lignes_materiel(f, 0.10)
    assert (l.cout_unitaire, l.prix, l.quantite) == (10.0, 11.0, 2)
    assert l.external_id == "rona|A-1|1"
    assert l.id is None


def test_facture_conforme_sans_alerte():
    f = Facture("Rona", "A-1", J, 20.0, [LigneFacture("Vis", 2, 10.0)])
    assert garde_fous_facture(f, J, R) == []


def test_ecart_sous_total():
    f = Facture("Rona", "A-1", J, 25.0, [LigneFacture("Vis", 2, 10.0)])
    [a] = garde_fous_facture(f, J, R)
    assert a.code == "ecart_sous_total" and "20,00 $" in a.message and "25,00 $" in a.message


def test_ecart_dans_la_tolerance():
    f = Facture("Rona", "A-1", J, 20.05, [LigneFacture("Vis", 2, 10.0)])
    assert garde_fous_facture(f, J, R) == []


def test_facture_ancienne():
    f = Facture("Rona", "A-1", J - timedelta(days=31), 20.0, [LigneFacture("Vis", 2, 10.0)])
    assert codes(garde_fous_facture(f, J, R)) == ["facture_ancienne"]
    f30 = Facture("Rona", "A-1", J - timedelta(days=30), 20.0, [LigneFacture("Vis", 2, 10.0)])
    assert garde_fous_facture(f30, J, R) == []


def test_ligne_elevee():
    f = Facture("Rona", "A-1", J, 1000.01, [LigneFacture("Chauffe-eau", 1, 1000.01)])
    [a] = garde_fous_facture(f, J, R)
    assert a.code == "ligne_elevee" and "1 000,00 $" in a.message


def test_plus_12h():
    e = [EntreeTemps(1, "Luc", J, 12 * 60 + 1, 10)]
    alertes = garde_fous_temps(e, R)
    assert codes(alertes) == ["plus_12h"]
    assert "12,02 h" in alertes[0].message and "12 h" in alertes[0].message
    assert not alertes[0].bloquante
    assert garde_fous_temps([EntreeTemps(1, "Luc", J, 12 * 60, 10)], R) == []


def test_sans_heures_bloquant():
    [a] = garde_fous_temps([], R)
    assert (a.code, a.bloquante) == ("sans_heures", True)


from regles import garde_fou_achat


def test_achat_declare_sans_facture():
    [a] = garde_fou_achat("Robinet cuisine", nb_factures=0)
    assert (a.code, a.bloquante) == ("achat_sans_facture", False) and "Robinet cuisine" in a.message


def test_montant_declare_sans_facture():
    assert [a.code for a in garde_fou_achat("61.13", 0)] == ["achat_sans_facture"]


def test_facture_sans_achat_declare():
    [a] = garde_fou_achat("Non", nb_factures=1)
    assert (a.code, a.bloquante) == ("facture_sans_achat", False)


def test_achat_coherent_ou_champ_vide():
    assert garde_fou_achat("Robinet cuisine", 1) == []
    assert garde_fou_achat("non ", 0) == []
    assert garde_fou_achat("", 0) == [] and garde_fou_achat("", 2) == []   # champ non rempli : rien à comparer
