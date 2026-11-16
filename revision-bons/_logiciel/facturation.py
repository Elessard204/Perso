"""Règles de Hugo pour les lignes générées par « Facturer » : transport, main-d'œuvre, tarifs, rentabilité.

Fonctions pures, sans réseau. Elles travaillent sur les lignes que Progression crée quand on clique
« Facturer » dans l'onglet Feuille de temps du bon (une ligne par entrée de temps).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace

from modele import Alerte, Bon, Ligne
from regles import Regles, argent_fr, cents, heures_fr

ACTIVITE_TRANSPORT = "en route"
ACTIVITE_MAIN_OEUVRE = "en cours"


def classer(ligne: Ligne) -> str:
    texte = f"{ligne.produit or ''} {ligne.libelle or ''}".lower()
    if "transport" in texte:
        return "transport"
    if "main d" in texte or "main-d" in texte:
        return "main_oeuvre"
    if "inventaire" in texte:
        return "inventaire"
    if "achet" in texte or "matériel" in texte or "materiel" in texte:
        return "materiel"
    return "autre"


def arrondir_quart(heures: float) -> float:
    """Au 0,25 h supérieur, minimum 0,25 dès qu'il y a du temps."""
    if heures <= 0:
        return 0.0
    return max(0.25, math.ceil(round(heures * 4, 6)) / 4)


def _activite(e) -> str:
    a = (e.activite or "").lower()
    if ACTIVITE_TRANSPORT in a:
        return "transport"
    if ACTIVITE_MAIN_OEUVRE in a:
        return "main_oeuvre"
    return "autre"


def _tarif_attendu(type_bon: str, r: Regles) -> dict | None:
    return r.tarifs.get(type_bon)


def _service_du_prix(genre: str, prix: float, r: Regles) -> str | None:
    for nom, t in list(r.tarifs.items()) + list(r.tarifs_autres.items()):
        if abs(t.get(genre, -1) - prix) < 0.005:
            return t.get("service", nom)
    return None


def ajuster_heures_transport(bon: Bon, r: Regles) -> tuple[list[Ligne], dict[str, str], list[Alerte]]:
    lignes = [replace(l) for l in bon.lignes]
    par_id = {l.id: l for l in lignes if l.id is not None}
    origine: dict[str, str] = {}
    alertes: list[Alerte] = []

    non_facturees = [e for e in bon.entrees if e.ligne_id is None]
    if non_facturees:
        alertes.append(Alerte("heures_non_facturees",
                              f"{len(non_facturees)} entrée(s) de temps pas encore envoyée(s) à la facture : cliquer sur "
                              "« Facturer » dans l'onglet Feuille de temps du bon, puis réanalyser.", bloquante=True))

    # Tarifs selon le type de bon (SMMP pour les appels de service, SELP pour la maintenance).
    tarif = _tarif_attendu(bon.type_bon, r)
    if tarif is None and any(classer(l) in ("transport", "main_oeuvre") for l in lignes):
        alertes.append(Alerte("type_sans_tarif", f"Aucun tarif défini pour le type de bon « {bon.type_bon or '?'} » : "
                                                 "vérifier les taux des heures et du transport."))
    # Seul le taux que Progression met par défaut est corrigé : tout autre taux a été choisi par quelqu'un.
    defaut = r.tarifs.get(r.tarif_progression)
    for l in lignes:
        genre = {"main_oeuvre": "heure", "transport": "transport"}.get(classer(l))
        if genre is None or tarif is None or abs(l.prix - tarif[genre]) < 0.005:
            continue
        if defaut is not None and abs(l.prix - defaut[genre]) < 0.005:
            # Taux par défaut de Progression laissé tel quel : on applique celui du type de bon.
            origine[str(l.id)] = f"Tarif {bon.type_bon} ({tarif.get('service', '')}) : {argent_fr(tarif[genre])}"
            l.prix = tarif[genre]
        else:
            service = _service_du_prix(genre, l.prix, r)
            alertes.append(Alerte("tarif_non_standard",
                                  f"« {l.libelle} » est à {argent_fr(l.prix)}"
                                  + (f" (tarif {service})" if service else "")
                                  + f", alors qu'un bon « {bon.type_bon} » est à {argent_fr(tarif[genre])} : à confirmer."))

    # Transport : quantité 1 par entrée; l'excédent au-delà du maximum passe en main-d'œuvre.
    excedent_par_tech: dict[str, float] = defaultdict(float)
    for e in bon.entrees:
        if _activite(e) == "transport" and e.minutes > r.transport_max_minutes:
            excedent_par_tech[e.technicien] += e.minutes - r.transport_max_minutes
            alertes.append(Alerte("transport_long",
                                  f"Transport de {e.technicien} de {heures_fr(e.minutes / 60)} h le {e.jour or '?'} : "
                                  f"l'excédent passe en main-d'œuvre. Vérifier que ce n'est pas un oubli de changer le "
                                  "statut à « Travaux commencés »."))
    for l in lignes:
        if classer(l) == "transport" and l.id is not None and l.quantite != 1:
            origine[str(l.id)] = (origine.get(str(l.id), "") + " · " if str(l.id) in origine else "") + "Transport : quantité 1"
            l.quantite = 1.0

    # Main-d'œuvre : excédent de transport ajouté à la dernière ligne du technicien, puis chaque ligne au 0,25 sup.
    lignes_mo_par_tech: dict[str, list[int]] = defaultdict(list)
    for e in bon.entrees:
        if _activite(e) == "main_oeuvre" and e.ligne_id in par_id and e.ligne_id not in lignes_mo_par_tech[e.technicien]:
            lignes_mo_par_tech[e.technicien].append(e.ligne_id)
    ajouts: dict[int, float] = defaultdict(float)
    for tech, minutes in excedent_par_tech.items():
        if lignes_mo_par_tech.get(tech):
            ajouts[lignes_mo_par_tech[tech][-1]] += minutes / 60
        else:
            alertes.append(Alerte("excedent_sans_main_oeuvre",
                                  f"{heures_fr(minutes / 60)} h d'excédent de transport de {tech} sans ligne de "
                                  "main-d'œuvre où les ajouter : à facturer à la main."))
    for l in lignes:
        if classer(l) != "main_oeuvre" or l.id is None:
            continue
        cible = arrondir_quart(l.quantite + ajouts.get(l.id, 0))
        if cible > l.quantite + 1e-9:
            raison = f"Arrondi au 0,25 h supérieur : {heures_fr(cible)} h"
            if ajouts.get(l.id):
                raison += f" (dont {heures_fr(ajouts[l.id])} h d'excédent de transport)"
            origine[str(l.id)] = (origine[str(l.id)] + " · " if str(l.id) in origine else "") + raison
            l.quantite = round(cible, 4)

    # Une journée de travail sans aucun transport facturé.
    jours_travail = {(e.technicien, e.jour) for e in bon.entrees if _activite(e) == "main_oeuvre"}
    jours_transport = {(e.technicien, e.jour) for e in bon.entrees if _activite(e) == "transport"}
    for tech, jour in sorted(jours_travail - jours_transport, key=str):
        alertes.append(Alerte("transport_manquant", f"{tech} a travaillé le {jour or '?'} sans transport inscrit : "
                                                    "vérifier s'il manque un transport à facturer."))
    return lignes, origine, alertes


def alertes_inventaire(lignes: list[Ligne]) -> list[Alerte]:
    return [Alerte("inventaire_a_zero", f"« {l.libelle} » (matériel en inventaire) est à {argent_fr(l.prix)} × "
                                        f"{l.quantite:g} : compléter le prix ou retirer la ligne.")
            for l in lignes if classer(l) == "inventaire" and (l.quantite == 0 or l.prix == 0)]


def cout_horaire(e, r: Regles | None) -> float | None:
    """Coût horaire du technicien : celui de Progression, sinon celui inscrit dans Règles, sinon le coût moyen."""
    if e.cout_horaire is not None:
        return e.cout_horaire
    if r is None:
        return None
    return r.couts_techniciens.get(e.technicien) or r.cout_horaire_defaut or None


def estimer_marge(bon: Bon, lignes: list[Ligne], retirees: list[int], r: Regles | None = None) -> dict:
    """Revenu facturé contre coût : temps des techniciens à leur coût horaire, plus le matériel au coût.

    Si le coût d'un technicien est inconnu, la marge n'est pas calculée : mieux vaut « inconnue » qu'un faux 100 %.
    Les frais fixes (gestion, administration, logiciels, bureau) ne sont pas comptés.
    """
    gardees = [l for l in lignes if l.id not in set(retirees)]
    revenu = cents(sum(l.quantite * l.prix for l in gardees))
    sans_cout = sorted({e.technicien for e in bon.entrees if e.minutes > 0 and cout_horaire(e, r) is None})
    cout_temps = sum((e.minutes / 60) * (cout_horaire(e, r) or 0) for e in bon.entrees)
    cout_materiel = sum((l.cout_unitaire or 0) * l.quantite for l in gardees
                        if classer(l) not in ("transport", "main_oeuvre"))
    cout = cents(cout_temps + cout_materiel)
    complet = not sans_cout
    return {"revenu": revenu, "cout": cout, "marge": (revenu - cout) / revenu if revenu and complet else None,
            "cout_complet": complet, "sans_cout": sans_cout}


def alertes_marge(m: dict, r: Regles) -> list[Alerte]:
    if not m.get("revenu"):
        return [Alerte("bon_sans_revenu", "Aucun montant facturé sur ce bon : vérifier qu'il ne manque rien.")]
    if m.get("cout_complet", True) and m["revenu"] < m["cout"]:
        return [Alerte("bon_a_perte", f"Bon à perte : {argent_fr(m['revenu'])} facturés pour un coût estimé de "
                                      f"{argent_fr(m['cout'])}.")]
    if r.marge_minimum > 0 and m["marge"] is not None and m["marge"] < r.marge_minimum:
        return [Alerte("marge_faible", f"Marge de {m['marge'] * 100:.0f} %, sous le minimum de "
                                       f"{r.marge_minimum * 100:.0f} %.".replace(".", ","))]
    return []
