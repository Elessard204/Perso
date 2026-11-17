"""Règles de Hugo pour les lignes générées par « Facturer » : transport, main-d'œuvre, tarifs, rentabilité.

Fonctions pures, sans réseau. Elles travaillent sur les lignes que Progression crée quand on clique
« Facturer » dans l'onglet Feuille de temps du bon (une ligne par entrée de temps).
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal

from modele import Alerte, Bon, Ligne
from regles import Regles, argent_fr, cents, heures_fr

ACTIVITE_TRANSPORT = "en route"
ACTIVITE_MAIN_OEUVRE = "en cours"
MINUTES_MIN = 1.0   # une entrée de travail de moins d'une minute (clic par erreur) ne compte pas comme travail.
# Un trajet compte toujours, même à 0 min : le technicien s'est déplacé (Hugo facture alors le transport).


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


TOLERANCE_HEURES = 0.01   # 36 s : écart d'arrondi entre une ligne de « Facturer » et ses entrées


def bon_informatif(bon: Bon) -> bool:
    """Toutes les lignes à 0 $ : bon joint pour information (ex. ménage au forfait facturé par la comptabilité)."""
    return (any(classer(l) in ("transport", "main_oeuvre") for l in bon.lignes)
            and all(abs(l.prix) < 0.005 for l in bon.lignes))


def bon_forfait(bon: Bon, r: Regles) -> bool:
    """Le bon contient un produit forfaitaire inscrit dans Règles (ex. bacs à 95 $ par semaine)."""
    produits = [p.strip().lower() for p in r.produits_forfait if p.strip()]
    return any(p in f"{l.produit or ''} {l.libelle or ''}".lower() for l in bon.lignes for p in produits)


def lignes_ajustees(bon: Bon) -> set[int]:
    """Lignes de main-d'œuvre modifiées à la main (journées fusionnées, rabais) : l'outil n'y touche plus.

    Une ligne créée par « Facturer » vaut le temps de ses entrées; arrondie au 0,25 h, c'est encore l'outil.
    Une ligne sans entrée liée a été ajoutée à la main.
    """
    minutes: dict[int, float] = defaultdict(float)
    for e in bon.entrees:
        if e.ligne_id is not None:
            minutes[e.ligne_id] += e.minutes
    ajustees = set()
    for l in bon.lignes:
        if classer(l) != "main_oeuvre" or l.id is None:
            continue
        if l.id not in minutes:
            ajustees.add(l.id)
            continue
        cree = minutes[l.id] / 60
        if abs(l.quantite - cree) > TOLERANCE_HEURES and abs(l.quantite - arrondir_quart(cree)) > TOLERANCE_HEURES:
            ajustees.add(l.id)
    return ajustees


def ajuster_heures_transport(bon: Bon, r: Regles) -> tuple[list[Ligne], dict[str, str], list[Alerte]]:
    lignes = [replace(l) for l in bon.lignes]
    par_id = {l.id: l for l in lignes if l.id is not None}
    origine: dict[str, str] = {}
    alertes: list[Alerte] = []
    forfait = bon_forfait(bon, r)

    # Entrées pas encore envoyées à la facture. Si Hugo a déjà fusionné des journées dans Progression (ligne
    # modifiée ou ajoutée à la main), les entrées de la ligne supprimée ont perdu leur lien : cliquer « Facturer »
    # recréerait ces lignes en double. La valeur totale fait foi (evaluer_rabais).
    non_facturees = [e for e in bon.entrees if e.ligne_id is None and e.minutes >= MINUTES_MIN]
    if non_facturees and not forfait and not lignes_ajustees(bon):
        alertes.append(Alerte("heures_non_facturees",
                              f"{len(non_facturees)} entrée(s) de temps pas encore envoyée(s) à la facture : cliquer sur "
                              "« Facturer » dans l'onglet Feuille de temps du bon, puis réanalyser.", bloquante=True))
    if bon_informatif(bon):
        return lignes, origine, alertes   # rien à facturer : aucune correction, aucune alerte de facturation

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

    # Transport : un seul par technicien et par jour sur le bon (un aller-retour au magasin n'en ajoute pas). Une
    # ligne dont les trajets sont déjà couverts passe à 0 et est retirée à l'analyse.
    trajets: dict[int, set] = defaultdict(set)
    liees: set[int] = set()
    for e in bon.entrees:
        if _activite(e) == "transport" and e.ligne_id is not None:
            liees.add(e.ligne_id)
            trajets[e.ligne_id].add((e.technicien, e.jour))
    couverts: set = set()
    for l in lignes:
        if classer(l) != "transport" or l.id is None:
            continue
        cible, raison = 1.0, "Transport : quantité 1"
        if l.id in liees:
            if trajets[l.id] <= couverts:
                tech, jour = sorted(trajets[l.id], key=str)[0]
                cible, raison = 0.0, f"Déjà un transport pour {tech} le {jour or '?'} : un seul transport par jour (retiré)"
            couverts |= trajets[l.id]
        if l.quantite != cible:
            origine[str(l.id)] = (origine.get(str(l.id), "") + " · " if str(l.id) in origine else "") + raison
            l.quantite = cible

    # Lignes de main-d'œuvre de chaque technicien, et celles qu'Hugo a modifiées à la main.
    ajustees = lignes_ajustees(bon)
    lignes_mo_par_tech: dict[str, list[int]] = defaultdict(list)
    for e in bon.entrees:
        if _activite(e) == "main_oeuvre" and e.ligne_id in par_id and e.ligne_id not in lignes_mo_par_tech[e.technicien]:
            lignes_mo_par_tech[e.technicien].append(e.ligne_id)

    # Transport : l'excédent au-delà du maximum passe en main-d'œuvre, sur la dernière ligne non modifiée du
    # technicien. Si toutes ses lignes ont été modifiées à la main, Hugo en a déjà tenu compte : la comparaison
    # avec la valeur du temps inscrit (evaluer_rabais) s'en charge.
    ajouts: dict[int, float] = defaultdict(float)
    for e in bon.entrees:
        if _activite(e) != "transport" or e.minutes <= r.transport_max_minutes or e.technicien in r.salaire_fixe:
            continue
        minutes = e.minutes - r.transport_max_minutes
        cibles = [i for i in lignes_mo_par_tech.get(e.technicien, []) if i not in ajustees]
        if cibles:
            ajouts[cibles[-1]] += minutes / 60
            alertes.append(Alerte("transport_long",
                                  f"Transport de {e.technicien} de {heures_fr(e.minutes / 60)} h le {e.jour or '?'} : "
                                  f"l'excédent passe en main-d'œuvre. Vérifier que ce n'est pas un oubli de changer le "
                                  "statut à « Travaux commencés ».", ligne_id=cibles[-1]))
        elif not lignes_mo_par_tech.get(e.technicien) and not forfait:
            alertes.append(Alerte("excedent_sans_main_oeuvre",
                                  f"{heures_fr(minutes / 60)} h d'excédent de transport de {e.technicien} le "
                                  f"{e.jour or '?'} sans ligne de main-d'œuvre où les ajouter : à facturer à la main."))

    # Main-d'œuvre : chaque ligne non modifiée au 0,25 h supérieur, excédent de transport compris.
    for l in lignes:
        if classer(l) != "main_oeuvre" or l.id is None or l.id in ajustees:
            continue
        cible = arrondir_quart(l.quantite + ajouts.get(l.id, 0))
        if cible > l.quantite + 1e-9:
            raison = f"Arrondi au 0,25 h supérieur : {heures_fr(cible)} h"
            if ajouts.get(l.id):
                raison += f" (dont {heures_fr(ajouts[l.id])} h d'excédent de transport)"
            origine[str(l.id)] = (origine[str(l.id)] + " · " if str(l.id) in origine else "") + raison
            l.quantite = round(cible, 4)

    # Une journée de travail sans aucun transport facturé. Sur un bon dont des journées ont été fusionnées
    # (ligne modifiée ou retirée), le transport est souvent sur la journée fusionnée : la valeur totale fait foi.
    fusionne = bool(ajustees) or any(e.ligne_id is not None and e.ligne_id not in par_id for e in bon.entrees)
    if not forfait and not fusionne:
        jours_travail = {(e.technicien, e.jour) for e in bon.entrees
                         if _activite(e) == "main_oeuvre" and e.minutes >= MINUTES_MIN}
        jours_transport = {(e.technicien, e.jour) for e in bon.entrees if _activite(e) == "transport"}
        for tech, jour in sorted(jours_travail - jours_transport, key=str):
            alertes.append(Alerte("transport_manquant", f"{tech} a travaillé le {jour or '?'} sans transport inscrit : "
                                                        "vérifier s'il manque un transport à facturer."))
    return lignes, origine, alertes


def valeur_du_temps(bon: Bon, r: Regles) -> Decimal | None:
    """Ce que vaudrait le temps inscrit avec les règles : main-d'œuvre par technicien et par jour au 0,25 h
    supérieur (excédent de transport compris, sauf salaire fixe), un transport par technicien et par jour."""
    tarif = _tarif_attendu(bon.type_bon, r)
    if tarif is None:
        return None
    heures: dict[tuple, Decimal] = defaultdict(Decimal)
    trajets: set = set()
    for e in bon.entrees:
        cle = (e.technicien, e.jour)
        if _activite(e) == "main_oeuvre":
            heures[cle] += Decimal(str(e.minutes)) / 60
        elif _activite(e) == "transport":
            trajets.add(cle)
            if e.minutes > r.transport_max_minutes and e.technicien not in r.salaire_fixe:
                heures[cle] += Decimal(str(e.minutes - r.transport_max_minutes)) / 60
    mo = sum((Decimal(str(arrondir_quart(float(h)))) for h in heures.values()), Decimal(0))
    return mo * Decimal(str(tarif["heure"])) + len(trajets) * Decimal(str(tarif["transport"]))


def evaluer_rabais(bon: Bon, lignes: list[Ligne], r: Regles) -> tuple[dict, list[Alerte]]:
    """Main-d'œuvre et transport facturés sous la valeur du temps inscrit : rabais à confirmer (non bloquant).

    Les journées fusionnées par Hugo gardent la même valeur (2 visites de 2 h -> 4,75 h et un transport) et ne
    sont donc pas signalées. Bons au forfait et bons informatifs à 0 $ : rien à comparer.
    """
    if bon_informatif(bon) or bon_forfait(bon, r):
        return {}, []
    valeur = valeur_du_temps(bon, r)
    if valeur is None:
        return {}, []
    facture = sum((Decimal(str(l.quantite)) * Decimal(str(l.prix)) for l in lignes
                   if classer(l) in ("transport", "main_oeuvre")), Decimal(0))
    ecart = cents(valeur - facture)
    if ecart <= r.seuil_rabais:
        return {}, []
    rabais = {"montant": ecart, "valeur_temps": cents(valeur), "facture": cents(facture), "raison": ""}
    return rabais, [Alerte("rabais", f"Main-d'œuvre et transport facturés {argent_fr(facture)}, alors que le temps "
                                     f"inscrit vaut {argent_fr(valeur)} : rabais de {argent_fr(ecart)}. Si c'est voulu, "
                                     "inscrire la raison (facultatif) : elle sera gardée dans le relevé des rabais.")]


def cout_horaire(e, r: Regles | None) -> float | None:
    """Coût horaire chargé : celui de Progression (déjà chargé), sinon le taux de base inscrit dans Règles
    (ou le taux moyen) multiplié par les charges."""
    if e.cout_horaire is not None:
        return e.cout_horaire
    if r is None:
        return None
    base = r.couts_techniciens.get(e.technicien) or r.cout_horaire_defaut
    return base * r.facteur_charges if base else None


def estimer_marge(bon: Bon, lignes: list[Ligne], retirees: list[int], r: Regles | None = None) -> dict:
    """Revenu facturé contre coût : temps des techniciens à leur coût horaire, plus le matériel au coût.

    Si le coût d'un technicien est inconnu, la marge n'est pas calculée : mieux vaut « inconnue » qu'un faux 100 %.
    Les frais fixes (gestion, administration, logiciels, bureau) ne sont pas comptés.
    """
    gardees = [l for l in lignes if l.id not in set(retirees)]
    revenu = cents(sum(l.quantite * l.prix for l in gardees))
    sans_cout = sorted({e.technicien for e in bon.entrees if e.minutes > 0 and cout_horaire(e, r) is None})
    # En décimal, minutes × taux avant la division par 60 : 45 min × 36,90 $ = 27,675 $ exactement.
    cout_temps = sum((Decimal(str(e.minutes)) * Decimal(str(cout_horaire(e, r) or 0)) for e in bon.entrees),
                     Decimal(0)) / 60
    cout_materiel = sum((Decimal(str(l.cout_unitaire or 0)) * Decimal(str(l.quantite)) for l in gardees
                         if classer(l) not in ("transport", "main_oeuvre")), Decimal(0))
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
