import copy
from dataclasses import replace

from conftest import LOGICIEL
from facturation import (ajuster_heures_transport, arrondir_quart, classer, estimer_marge, alertes_marge,
                         evaluer_rabais, lignes_ajustees)
from modele import EntreeTemps, Ligne
from progression import bon_depuis_json
from regles import charger_regles
from test_progression import ENTREES, TACHE

R = charger_regles(LOGICIEL / "regles.toml")


def bon(type_bon="Appel de service", **modifs):
    b = bon_depuis_json(copy.deepcopy(TACHE), copy.deepcopy(ENTREES), {"champ_description": "description"})
    b.type_bon = type_bon
    for k, v in modifs.items():
        setattr(b, k, v)
    return b


def codes(alertes):
    return [a.code for a in alertes]


def ligne(lignes, id_):
    return next(l for l in lignes if l.id == id_)


def test_regles_v2():
    assert (R.marge, R.pas_minutes, R.transport_max_minutes, R.regle_transports) == (0.15, 15, 60, "un_par_visite")
    assert R.tarifs["Maintenance"] == {"service": "SELP", "heure": 45.0, "transport": 40.0}
    assert R.tarifs["Rénovation"] == {"service": "SRP", "heure": 85.0, "transport": 50.0}
    assert R.tarif_progression == "Appel de service"
    assert (R.salaire_fixe, R.produits_forfait, R.seuil_rabais) == ([], [], 50.0)


def test_classer():
    assert classer(Ligne(1, "Transport (En route, Luc)", "", 1, 50, produit="Transport")) == "transport"
    assert classer(Ligne(1, "Main d'oeuvre (En cours)", "", 1, 65, produit="Main d'oeuvre")) == "main_oeuvre"
    assert classer(Ligne(1, "Matériel", "", 0, 0, produit="Matériel en inventaire")) == "inventaire"
    assert classer(Ligne(1, "Matériel acheté", "", 1, 10, produit="Matériel acheté")) == "materiel"
    assert classer(Ligne(1, "Autre chose", "", 1, 10)) == "autre"


def test_arrondir_quart():
    assert arrondir_quart(2.0833) == 2.25
    assert arrondir_quart(2.25) == 2.25
    assert arrondir_quart(0.1) == 0.25
    assert arrondir_quart(0) == 0


def test_transport_a_un_et_excedent_en_main_d_oeuvre():
    lignes, origine, alertes = ajuster_heures_transport(bon(), R)
    assert ligne(lignes, 502).quantite == 1
    # main-d'œuvre 2 h 05 + 20 min d'excédent de transport = 2 h 25 -> 2,5
    assert ligne(lignes, 501).quantite == 2.5
    assert "transport_long" in codes(alertes)
    assert "transport" in origine["502"].lower() and "excédent" in origine["501"]


def test_arrondi_par_ligne_sans_excedent():
    b = bon()
    b.entrees[0].minutes = 50   # transport court
    lignes, _, alertes = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).quantite == 2.25 and "transport_long" not in codes(alertes)


def test_ligne_deja_ronde_inchangee():
    b = bon()
    b.entrees[0].minutes = 50   # pas d'excédent de transport
    b.lignes[0].quantite = 3.0
    lignes, origine, _ = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).quantite == 3.0 and "501" not in origine


def test_minimum_un_quart_d_heure():
    b = bon()
    b.entrees = [EntreeTemps(1, "Luc", None, 4, 501, "En cours"), EntreeTemps(2, "Luc", None, 10, 502, "En route")]
    b.lignes[0].quantite = 0.0667
    lignes, _, _ = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).quantite == 0.25


def test_tarifs_maintenance_appliques():
    lignes, origine, alertes = ajuster_heures_transport(bon("Maintenance"), R)
    assert (ligne(lignes, 501).prix, ligne(lignes, 502).prix) == (45.0, 40.0)
    assert "SELP" in origine["501"]
    assert "tarif_non_standard" not in codes(alertes)


def test_tarif_srp_garde_et_signale():
    b = bon()
    b.lignes[0].prix = 85.0
    lignes, _, alertes = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).prix == 85.0
    assert "tarif_non_standard" in codes(alertes) and "SRP" in next(a.message for a in alertes if a.code == "tarif_non_standard")


def test_renovation_taux_par_defaut_corrige():
    """Progression met le taux SMMP par défaut : sur un bon Rénovation, il devient le taux SRP."""
    lignes, origine, alertes = ajuster_heures_transport(bon("Rénovation"), R)
    assert (ligne(lignes, 501).prix, ligne(lignes, 502).prix) == (85.0, 50.0)
    assert "SRP" in origine["501"]
    assert "tarif_non_standard" not in codes(alertes)


def test_taux_choisi_a_la_main_signale_pas_corrige():
    """Un taux autre que celui par défaut de Progression a été choisi par quelqu'un : on le garde et on signale."""
    b = bon()
    b.lignes[0].prix = 45.0      # taux SELP sur un appel de service
    lignes, _, alertes = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).prix == 45.0
    assert "tarif_non_standard" in codes(alertes)


def test_type_sans_tarif():
    _, _, alertes = ajuster_heures_transport(bon("Inspection"), R)
    assert "type_sans_tarif" in codes(alertes)


def test_heures_non_facturees_bloquant():
    b = bon()
    b.entrees[2].ligne_id = None
    _, _, alertes = ajuster_heures_transport(b, R)
    a = next(a for a in alertes if a.code == "heures_non_facturees")
    assert a.bloquante and "Facturer" in a.message


def test_transport_manquant():
    b = bon()
    b.entrees = [e for e in b.entrees if e.activite != "En route"]
    _, _, alertes = ajuster_heures_transport(b, R)
    assert "transport_manquant" in codes(alertes)


def test_excedent_sans_main_d_oeuvre():
    b = bon()
    b.entrees = [b.entrees[0]]
    b.lignes = [b.lignes[1]]
    _, _, alertes = ajuster_heures_transport(b, R)
    assert "excedent_sans_main_oeuvre" in codes(alertes)


def test_ligne_modifiee_a_la_main_pas_touchee():
    """Journées fusionnées par Hugo : la ligne ne correspond plus au temps de « Facturer », l'outil n'y touche plus."""
    b = bon()
    b.lignes[0].quantite = 4.75
    lignes, origine, alertes = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).quantite == 4.75 and "501" not in origine
    assert "transport_long" not in codes(alertes) and "excedent_sans_main_oeuvre" not in codes(alertes)


def test_ligne_arrondie_par_l_outil_reste_a_l_outil():
    b = bon()
    assert lignes_ajustees(b) == set()
    b.lignes[0].quantite = 2.25          # 2 h 05 arrondies au 0,25 : c'est encore la ligne de « Facturer »
    assert lignes_ajustees(b) == set()
    b.lignes[0].quantite = 2.5
    assert lignes_ajustees(b) == {501}


def test_ligne_ajoutee_a_la_main_pas_touchee():
    b = bon()
    b.lignes.append(Ligne(503, "Main d'oeuvre (journée du 2)", "", 1.6, 65.0, produit="Main d'oeuvre"))
    lignes, _, _ = ajuster_heures_transport(b, R)
    assert 503 in lignes_ajustees(b) and ligne(lignes, 503).quantite == 1.6
    assert ligne(lignes, 501).quantite == 2.5     # l'excédent va sur la ligne de « Facturer »


def test_journee_fusionnee_pas_de_transport_manquant():
    b = bon()
    b.entrees = [e for e in b.entrees if e.activite != "En route"]
    b.lignes[0].quantite = 4.75
    _, _, alertes = ajuster_heures_transport(b, R)
    assert "transport_manquant" not in codes(alertes)


def test_ligne_retiree_compte_comme_fusion():
    b = bon()
    b.entrees = [e for e in b.entrees if e.activite != "En route"]
    b.entrees[1].ligne_id = 999            # ligne créée par « Facturer » puis retirée par Hugo
    _, _, alertes = ajuster_heures_transport(b, R)
    assert "transport_manquant" not in codes(alertes)


def test_salaire_fixe_route_jamais_en_main_d_oeuvre():
    r = replace(R, salaire_fixe=["Luc Tremblay"])
    lignes, _, alertes = ajuster_heures_transport(bon(), r)
    assert ligne(lignes, 501).quantite == 2.25 and ligne(lignes, 502).quantite == 1
    assert "transport_long" not in codes(alertes)


def test_bon_informatif_a_zero_sans_correction():
    b = bon("Maintenance")
    for l in b.lignes:
        l.prix = 0.0
    lignes, origine, alertes = ajuster_heures_transport(b, R)
    assert [(l.quantite, l.prix) for l in lignes] == [(l.quantite, 0.0) for l in b.lignes]
    assert origine == {} and alertes == []
    assert evaluer_rabais(b, lignes, R) == ({}, [])


def test_bon_au_forfait_heures_non_facturees_acceptees():
    r = replace(R, produits_forfait=["Bacs"])
    b = bon()
    b.lignes.append(Ligne(504, "Sortie des bacs", "", 4, 95.0, produit="Bacs"))
    b.entrees[2].ligne_id = None
    _, _, alertes = ajuster_heures_transport(b, r)
    assert "heures_non_facturees" not in codes(alertes)
    assert "heures_non_facturees" in codes(ajuster_heures_transport(b, R)[2])   # sans la règle : bloqué
    assert evaluer_rabais(b, b.lignes, r) == ({}, [])


def test_pas_de_rabais_quand_l_outil_corrige():
    b = bon()
    lignes, _, _ = ajuster_heures_transport(b, R)
    assert evaluer_rabais(b, lignes, R) == ({}, [])   # 2,5 h × 65 + 50 = 212,50 des deux côtés


def test_rabais_signale_avec_montant():
    b = bon()
    b.lignes[0].quantite = 1.0                        # Hugo ramène la main-d'œuvre à 1 h
    lignes, _, _ = ajuster_heures_transport(b, R)
    rabais, alertes = evaluer_rabais(b, lignes, R)
    assert rabais == {"montant": 97.5, "valeur_temps": 212.5, "facture": 115.0, "raison": ""}
    assert codes(alertes) == ["rabais"] and not alertes[0].bloquante and "97,50 $" in alertes[0].message
    assert evaluer_rabais(b, lignes, replace(R, seuil_rabais=100.0)) == ({}, [])


def test_fusion_a_valeur_egale_pas_de_rabais():
    """Deux visites de 2 h fusionnées en 4,75 h et un transport : 358,75 $ contre 360 $, sous le seuil."""
    from datetime import date
    b = bon()
    b.entrees = [EntreeTemps(1, "Luc", date(2026, 11, 3), 30, 502, "En route"),
                 EntreeTemps(2, "Luc", date(2026, 11, 3), 120, 501, "En cours"),
                 EntreeTemps(3, "Luc", date(2026, 11, 5), 30, 998, "En route"),
                 EntreeTemps(4, "Luc", date(2026, 11, 5), 120, 999, "En cours")]
    b.lignes[0].quantite = 4.75
    lignes, _, alertes = ajuster_heures_transport(b, R)
    assert ligne(lignes, 501).quantite == 4.75 and "transport_manquant" not in codes(alertes)
    assert evaluer_rabais(b, lignes, R) == ({}, [])


def test_marge_et_bon_a_perte():
    b = bon()
    lignes, _, _ = ajuster_heures_transport(b, R)
    m = estimer_marge(b, lignes, [])
    # revenu : 2,5 h × 65 + 1 × 50 = 212,50 ; coût : (80 + 80 + 45) min × 30 $/h = 102,50
    assert (m["revenu"], m["cout"], m["cout_complet"]) == (212.5, 102.5, True)
    assert round(m["marge"], 3) == round((212.5 - 102.5) / 212.5, 3)
    assert alertes_marge(m, R) == []
    perte = dict(m, revenu=90.0, marge=(90 - 102.5) / 90)
    assert codes(alertes_marge(perte, R)) == ["bon_a_perte"]
    assert codes(alertes_marge(dict(m, revenu=0.0, marge=None), R)) == ["bon_sans_revenu"]


def test_marge_cout_inconnu_pas_de_fausse_marge():
    """Sans coût horaire nulle part, pas de marge à 100 % trompeuse : marge inconnue, pas d'alerte de perte."""
    b = bon()
    for e in b.entrees:
        e.cout_horaire = None
    m = estimer_marge(b, b.lignes, [], R)
    assert m["cout_complet"] is False and m["marge"] is None
    assert m["sans_cout"] == ["Luc Tremblay"]
    assert alertes_marge(dict(m, revenu=10.0), R) == []


def test_marge_taux_inscrit_dans_les_regles():
    """Le taux inscrit par Hugo pour le technicien remplace un coût absent de Progression."""
    b = bon()
    for e in b.entrees:
        e.cout_horaire = None
    r = replace(R, couts_techniciens={"Luc Tremblay": 30.0})
    lignes, _, _ = ajuster_heures_transport(b, r)
    m = estimer_marge(b, lignes, [], r)
    # (80 + 80 + 45) min × 30 $ × 1,23 = 126,075 $ -> 126,08 $ (demi vers le haut)
    assert (m["cout"], m["cout_complet"], m["sans_cout"]) == (126.08, True, [])


def test_marge_taux_par_defaut():
    b = bon()
    for e in b.entrees:
        e.cout_horaire = None
    r = replace(R, cout_horaire_defaut=30.0, couts_techniciens={"Autre": 99.0})
    lignes, _, _ = ajuster_heures_transport(b, r)
    assert estimer_marge(b, lignes, [], r)["cout"] == 126.08


def test_cout_charge_depuis_taux_de_base():
    b = bon()
    for e in b.entrees:
        e.cout_horaire = None
    r = replace(R, couts_techniciens={"Luc Tremblay": 30.0})
    assert r.facteur_charges == 1.23          # DAS 12 % + vacances 6 % + fériés 5 %
    lignes, _, _ = ajuster_heures_transport(b, r)
    # (80 + 80 + 45) min × 30 $ × 1,23 = 126,08 $
    assert estimer_marge(b, lignes, [], r)["cout"] == 126.08
