"""Données manipulées par l'outil : un bon de service, ses pièces et la proposition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


@dataclass
class EntreeTemps:
    """Temps réel d'un technicien (feuille de temps). Jamais modifié par l'outil."""
    id: int
    technicien: str
    jour: date | None
    minutes: float  # exactes (secondes comprises)
    ligne_id: int | None  # ligne facturable générée par « Facturer » à partir de cette entrée
    activite: str = ""  # « En route » (transport) ou « En cours » (main-d'œuvre)
    debut: datetime | None = None
    cout_horaire: float | None = None  # coût horaire moyen du technicien


@dataclass
class Ligne:
    """Ligne facturable du bon (main-d'œuvre, transport, matériel)."""
    id: int | None
    libelle: str
    description: str
    quantite: float
    prix: float
    cout_unitaire: float | None = None
    produit: str | None = None
    external_id: str | None = None


@dataclass
class PieceJointe:
    id: int
    nom: str
    type_mime: str


@dataclass
class LigneFacture:
    description: str
    quantite: float
    prix_unitaire: float  # avant taxes


@dataclass
class Facture:
    fournisseur: str
    numero: str
    date: date | None
    sous_total: float | None
    lignes: list[LigneFacture] = field(default_factory=list)

    @property
    def cle(self) -> str:
        """Identifie la facture d'un bon à l'autre : « fournisseur|numéro »."""
        return f"{self.fournisseur.lower().strip()}|{self.numero.strip()}"


@dataclass
class AnalysePiece:
    piece_id: int
    genre: Literal["facture", "photo", "incertain"]
    facture: Facture | None
    raison: str


@dataclass
class Bon:
    id: int
    code: str
    client: str
    date_rv: date | None
    maj: str  # champ « updated » de Progression, pour détecter un bon modifié
    description: str
    entrees: list[EntreeTemps] = field(default_factory=list)
    lignes: list[Ligne] = field(default_factory=list)
    pieces: list[PieceJointe] = field(default_factory=list)
    achat: str = ""  # champ « Achat » rempli par le technicien (ex. « Non », « Robinet cuisine », « 61.13 »)
    type_bon: str = ""  # « Appel de service » ou « Maintenance » : détermine les tarifs
    lieu: str = ""  # « client/location » : sert à repérer un transport en double dans le même immeuble
    lieu_libelle: str = ""
    demande: str = ""  # sommaire et description rédigés au départ (contexte pour la réécriture)


@dataclass
class Alerte:
    code: str
    message: str
    bloquante: bool = False


@dataclass
class Proposition:
    bon_id: int
    maj: str
    description: str
    description_originale: str
    lignes: list[Ligne] = field(default_factory=list)
    analyses: list[AnalysePiece] = field(default_factory=list)
    alertes: list[Alerte] = field(default_factory=list)
    origine: dict[str, str] = field(default_factory=dict)
    lignes_retirees: list[int] = field(default_factory=list)  # lignes vides que l'écriture supprime
    marge: dict = field(default_factory=dict)  # {"revenu", "cout", "marge", "cout_complet"}

    @property
    def statut(self) -> Literal["pret", "a_verifier", "bloque"]:
        if any(a.bloquante for a in self.alertes):
            return "bloque"
        if self.alertes:
            return "a_verifier"
        return "pret"
