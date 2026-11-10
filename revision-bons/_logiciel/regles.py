"""Règles de facturation : fonctions pures, sans réseau. Paramètres dans regles.toml."""

from __future__ import annotations

import math
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from modele import Alerte, EntreeTemps, Facture, Ligne


@dataclass
class Regles:
    pas_minutes: int
    marge: float
    refacturer_taxes: bool
    regle_transports: str
    ecart_sous_total: float
    jours_max_facture: int
    montant_max_ligne: float
    heures_max_jour: float


def charger_regles(chemin: Path) -> Regles:
    d = tomllib.loads(Path(chemin).read_text(encoding="utf-8"))
    g = d["garde_fous"]
    return Regles(
        pas_minutes=int(d["heures"]["pas_minutes"]),
        marge=float(d["materiel"]["marge"]),
        refacturer_taxes=bool(d["materiel"].get("refacturer_taxes", False)),
        regle_transports=str(d["transports"]["regle"]),
        ecart_sous_total=float(g["ecart_sous_total"]),
        jours_max_facture=int(g["jours_max_facture"]),
        montant_max_ligne=float(g["montant_max_ligne"]),
        heures_max_jour=float(g["heures_max_jour"]),
    )


def cents(montant: float) -> float:
    return float(Decimal(str(montant)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def heures_fr(heures: float) -> str:
    """12.5 -> « 12,50 », 12.0 -> « 12 »."""
    texte = f"{heures:.2f}".replace(".", ",")
    return texte[:-3] if texte.endswith(",00") else texte


def argent_fr(montant: float) -> str:
    """1000.5 -> « 1 000,50 $ »."""
    return f"{cents(montant):,.2f} $".replace(",", " ").replace(".", ",")


def arrondir_minutes(minutes: float, pas: int = 15) -> int:
    """Arrondit au pas supérieur : 125 -> 135, 135 reste 135, 14 min 40 s -> 15."""
    return math.ceil(round(minutes, 6) / pas) * pas


def heures_facturees(entrees: list[EntreeTemps], pas: int) -> dict[str, float]:
    """Heures facturées par technicien : son total du bon, arrondi au pas supérieur."""
    totaux: dict[str, float] = defaultdict(float)
    for e in entrees:
        totaux[e.technicien] += e.minutes
    return {tech: arrondir_minutes(m, pas) / 60 for tech, m in totaux.items()}


def prix_avec_marge(cout: float, marge: float) -> float:
    return cents(Decimal(str(cout)) * (1 + Decimal(str(marge))))


def lignes_materiel(facture: Facture, marge: float) -> list[Ligne]:
    lignes = []
    for i, lf in enumerate(facture.lignes, start=1):
        lignes.append(Ligne(
            id=None,
            libelle=lf.description,
            description=f"{facture.fournisseur} – facture {facture.numero}",
            quantite=lf.quantite,
            prix=prix_avec_marge(lf.prix_unitaire, marge),
            cout_unitaire=lf.prix_unitaire,
            external_id=f"{facture.cle}|{i}",
        ))
    return lignes


def garde_fous_facture(facture: Facture, date_bon: date | None, r: Regles) -> list[Alerte]:
    alertes = []
    nom = f"{facture.fournisseur} {facture.numero}"
    if facture.sous_total is not None:
        total = sum(Decimal(str(l.quantite)) * Decimal(str(l.prix_unitaire)) for l in facture.lignes)
        ecart = abs(total - Decimal(str(facture.sous_total)))
        if ecart > Decimal(str(r.ecart_sous_total)):
            alertes.append(Alerte(
                "ecart_sous_total",
                f"Facture {nom} : les lignes totalisent {argent_fr(total)}, "
                f"le sous-total imprimé est {argent_fr(facture.sous_total)}."))
    if facture.date and date_bon and abs((date_bon - facture.date).days) > r.jours_max_facture:
        alertes.append(Alerte(
            "facture_ancienne",
            f"Facture {nom} datée du {facture.date:%Y-%m-%d}, à plus de "
            f"{r.jours_max_facture} jours du bon."))
    for l in facture.lignes:
        if l.quantite * l.prix_unitaire > r.montant_max_ligne:
            alertes.append(Alerte(
                "ligne_elevee",
                f"Facture {nom} : « {l.description} » dépasse {argent_fr(r.montant_max_ligne)}."))
    return alertes


def garde_fous_temps(entrees: list[EntreeTemps], r: Regles) -> list[Alerte]:
    if not entrees:
        return [Alerte("sans_heures", "Aucune heure inscrite sur ce bon.", bloquante=True)]
    par_jour: dict[tuple[str, date | None], float] = defaultdict(float)
    for e in entrees:
        par_jour[(e.technicien, e.jour)] += e.minutes
    return [
        Alerte("plus_12h", f"{tech} a {heures_fr(m / 60)} h le {jour}, plus de {heures_fr(r.heures_max_jour)} h.")
        for (tech, jour), m in par_jour.items()
        if m > r.heures_max_jour * 60
    ]
