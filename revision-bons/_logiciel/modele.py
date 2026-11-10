"""Données manipulées par l'outil : un bon de service, ses pièces et la proposition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class EntreeTemps:
    """Temps réel d'un technicien (feuille de temps). Jamais modifié par l'outil."""
    id: int
    technicien: str
    jour: date | None
    minutes: float  # exactes (secondes comprises)
    ligne_id: int | None  # ligne facturable générée à partir de cette entrée


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

    @property
    def statut(self) -> Literal["pret", "a_verifier", "bloque"]:
        if any(a.bloquante for a in self.alertes):
            return "bloque"
        if self.alertes:
            return "a_verifier"
        return "pret"
