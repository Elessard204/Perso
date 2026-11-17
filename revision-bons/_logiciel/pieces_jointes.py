"""Classement des pièces jointes (facture / photo) et extraction des factures par Claude."""

from __future__ import annotations

import base64
from datetime import date

from claude_client import demander_json
from modele import AnalysePiece, Facture, LigneFacture, PieceJointe



def _refus_de_la_piece() -> tuple:
    """Erreurs du SDK propres à une pièce (inutile de réessayer).

    Le SDK de Claude compte des milliers de fichiers : il n'est chargé qu'à la première analyse, jamais à
    l'ouverture de l'outil (sinon la page met de longues secondes à s'ouvrir sur un poste Windows).
    """
    try:
        import anthropic
    except ImportError:  # mode démo sans le module
        return ()
    return (anthropic.BadRequestError, anthropic.RequestTooLargeError, anthropic.UnprocessableEntityError)

TYPES_LISIBLES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}
TAILLE_MAX = 22 * 1024 * 1024        # PDF : la requête à l'API est limitée à 32 Mo une fois encodée
TAILLE_MAX_IMAGE = 5 * 1024 * 1024   # limite de l'API par image

NOMBRE_OU_NUL = {"anyOf": [{"type": "number"}, {"type": "null"}]}
SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string", "enum": ["facture", "photo", "incertain"]},
        "raison": {"type": "string"},
        "fournisseur": {"type": "string"},
        "numero": {"type": "string"},
        "date": {"type": "string"},
        "sous_total": NOMBRE_OU_NUL,
        "lignes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantite": {"type": "number"},
                    "prix_unitaire": {"type": "number"},
                },
                "required": ["description", "quantite", "prix_unitaire"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["genre", "raison", "fournisseur", "numero", "date", "sous_total", "lignes"],
    "additionalProperties": False,
}

SYSTEME = """Tu tries les pièces jointes des bons de service d'une entreprise de gestion immobilière au Québec.
Les techniciens joignent des photos de chantier et des factures d'achat de matériel.

Classe la pièce :
- « facture » : une facture ou un reçu d'achat de matériel (quincaillerie, plomberie, électricité, etc.);
- « photo » : une photo de chantier, de travaux, d'équipement ou de lieux, avant ou après les travaux;
- « incertain » : un document flou, coupé, illisible ou d'un autre genre.

Pour une facture, extrais le fournisseur, le numéro de facture, la date (AAAA-MM-JJ, chaîne vide si absente),
le sous-total avant taxes (null s'il n'est pas imprimé) et chaque ligne de matériel avec sa quantité et son
prix unitaire AVANT taxes. Garde les écofrais, consignes et frais de livraison comme des lignes
(ils sont refacturés). Ignore seulement la TPS et la TVQ. Le sous-total est le montant avant taxes,
frais compris, rabais déduits.
Ne devine jamais un montant illisible : si un prix ou une quantité ne se lit pas clairement, classe la pièce
« incertain » et explique pourquoi dans « raison ».
Pour une photo ou une pièce incertaine, laisse fournisseur, numéro et date vides, sous_total null, lignes vide.
« raison » : en français, quelques mots pour une photo (au plus 10, ex. « Photo de chantier : mur réparé »),
une courte phrase pour une facture ou une pièce incertaine."""


def _incertain(piece: PieceJointe, raison: str) -> AnalysePiece:
    return AnalysePiece(piece.id, "incertain", None, raison)


def _date(texte: str) -> date | None:
    try:
        return date.fromisoformat(texte) if texte else None
    except ValueError:
        return None


def analyser_piece(piece: PieceJointe, contenu: bytes, client, cfg: dict) -> AnalysePiece:
    type_mime = (piece.type_mime or "").lower()
    if type_mime.startswith(("text/", "video/")):
        # Note écrite ou vidéo jointe au bon : jamais une facture, inutile de la signaler.
        return AnalysePiece(piece.id, "photo", None, f"Note ou vidéo jointe ({type_mime.split(';')[0]}) : pas une facture.")
    if type_mime not in TYPES_LISIBLES:
        return _incertain(piece, f"Format non lisible ({piece.type_mime or 'inconnu'})")
    limite = TAILLE_MAX if type_mime == "application/pdf" else TAILLE_MAX_IMAGE
    if len(contenu) > limite:
        return _incertain(piece, f"Fichier trop gros pour l'analyse ({len(contenu) / (1024 * 1024):.1f} Mo) : "
                                 "le vérifier dans Progression.")

    donnees = base64.standard_b64encode(contenu).decode("ascii")
    genre_bloc = "document" if type_mime == "application/pdf" else "image"
    bloc = {"type": genre_bloc, "source": {"type": "base64", "media_type": type_mime, "data": donnees}}
    texte = {"type": "text", "text": f"Pièce jointe « {piece.nom} ». Classe-la et extrais la facture s'il y a lieu."}

    try:
        resultat = demander_json(client, cfg, [bloc, texte], SCHEMA, SYSTEME)
    except Exception as e:
        # PDF protégé ou corrompu, image refusée : propre à cette pièce, inutile de réessayer.
        # Les erreurs temporaires (429, 5xx, réseau) remontent : le bon reste « à analyser ».
        if not isinstance(e, _refus_de_la_piece()):
            raise
        return _incertain(piece, "Pièce refusée par l'IA (fichier protégé, corrompu ou trop lourd).")
    if resultat is None:
        return _incertain(piece, "L'IA n'a pas pu lire cette pièce (réponse refusée ou invalide).")

    genre = resultat.get("genre")
    raison = resultat.get("raison") or ""
    if genre == "photo":
        return AnalysePiece(piece.id, "photo", None, raison)
    if genre != "facture":
        return _incertain(piece, raison or "Classement incertain.")
    try:
        lignes = [
            LigneFacture(str(l["description"]), float(l["quantite"]), float(l["prix_unitaire"]))
            for l in resultat.get("lignes") or []
        ]
        sous_total = resultat.get("sous_total")
        sous_total = float(sous_total) if sous_total is not None else None
    except (KeyError, TypeError, ValueError):
        return _incertain(piece, "Montants de la facture illisibles.")
    if not lignes:
        return _incertain(piece, "Facture reconnue, mais aucune ligne de matériel lisible.")
    facture = Facture(
        fournisseur=(resultat.get("fournisseur") or "").strip() or "Fournisseur inconnu",
        numero=(resultat.get("numero") or "").strip() or f"piece-{piece.id}",
        date=_date(resultat.get("date") or ""),
        sous_total=sous_total,
        lignes=lignes,
    )
    return AnalysePiece(piece.id, "facture", facture, raison)
