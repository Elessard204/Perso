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
    ligne_materiel,
    prix_avec_marge,
)

R = charger_regles(LOGICIEL / "regles.toml")


def codes(alertes):
    return [a.code for a in alertes]


def test_regles_toml():
    assert (R.pas_minutes, R.marge, R.regle_transports) == (15, 0.15, "un_par_visite")
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


def test_une_ligne_par_facture_sous_total_plus_marge():
    f = Facture("Rona", "A-1", J, 31.48, [LigneFacture("Robinet de cuisine", 1, 24.98), LigneFacture("Raccord 1/2 po", 2, 3.25)])
    l = ligne_materiel(f, 0.15)
    assert (l.id, l.quantite, l.cout_unitaire, l.prix) == (None, 1, 31.48, 36.2)   # 31,48 × 1,15 = 36,20
    assert l.libelle == "Matériel acheté" and l.produit == "Matériel acheté"
    assert l.description == "Rona – facture A-1 : Robinet de cuisine (1), Raccord 1/2 po (2)"
    assert l.external_id == "rona|A-1|1"


def test_sans_sous_total_imprime_on_additionne_les_lignes():
    f = Facture("BMR", "9", J, None, [LigneFacture("Vis", 2, 10.0), LigneFacture("Écofrais", 1, 0.5)])
    assert ligne_materiel(f, 0.15).cout_unitaire == 20.5


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


def test_achat_facture_en_inventaire_sans_facture_accepte():
    """Le matériel en inventaire n'a jamais de facture : Hugo l'estime selon le travail."""
    assert garde_fou_achat("Silicone", 0, en_inventaire=True) == []


def test_regles_kilometrage():
    from datetime import date
    r = charger_regles(LOGICIEL / "regles.toml")
    assert (r.km_taux, r.km_seuil_ecart, r.km_debut_reference) == (0.61, 10.0, date(2026, 11, 8))


def test_montant_km_arrondi_demi_superieur_exact():
    from regles import montant_km
    assert 17.5 * 0.61 < 10.675                       # le produit en virgule flottante tombe sous la demie
    assert montant_km(17.5, 0.61) == 10.68
    assert montant_km(0.5, 0.61) == 0.31 and montant_km(0, 0.61) == 0.0


def test_charges_de_la_paie_progim():
    # Chiffres de la paie : vacances 6 % pour tous, fériés 5 %, DAS 12 %.
    from regles import Regles, cents
    assert (R.charges_das, R.charges_vacances, R.charges_feries) == (0.12, 0.06, 0.05)
    defaut = Regles(15, 0.15, False, "un_par_visite", 0.05, 30, 1000.0, 12)
    assert (defaut.charges_das, defaut.charges_vacances, defaut.charges_feries) == (0.12, 0.06, 0.05)
    assert R.facteur_charges == 1.23
    assert cents(35 * R.facteur_charges) == 43.05     # 35 $/h × 1,23 = 43,05 $


def test_charges_par_defaut_sans_section_couts(tmp_path):
    texte = (LOGICIEL / "regles.toml").read_text(encoding="utf-8")
    debut = texte.index("[couts]")
    fin = texte.index("[garde_fous]")
    (tmp_path / "r.toml").write_text(texte[:debut] + texte[fin:], encoding="utf-8")
    r = charger_regles(tmp_path / "r.toml")
    assert (r.charges_das, r.charges_vacances, r.charges_feries) == (0.12, 0.06, 0.05)
