"""Correction et résumé de la description des travaux par Claude, avec contrôle anti-invention."""

from __future__ import annotations

import base64
import re

from claude_client import demander_json
from modele import Alerte

SCHEMA = {
    "type": "object",
    "properties": {
        "texte": {"type": "string"},
        "ajouts_photos": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["texte", "ajouts_photos"],
    "additionalProperties": False,
}

SYSTEME = """Tu révises la « Note technicien » d'un bon de service, le texte qui décrit au client les travaux faits,
sur la facture d'une entreprise de gestion immobilière au Québec.

Tu reçois la demande de départ (rédigée par le bureau), la note du technicien et, s'il y en a, les photos du bon.
- Corrige l'orthographe, la grammaire et la syntaxe : français professionnel, clair et sobre, au passé
  (ce qui a été fait).
- Si la note est confuse ou décousue, résume-la en quelques phrases simples.
- Si la note est vide ou trop pauvre, rédige une description à partir de la demande et des photos.
- Tu peux préciser un détail clairement visible sur une photo (modèle, matériau, emplacement), mais chaque
  détail tiré d'une photo doit aussi être recopié tel quel dans « ajouts_photos ».
- N'invente jamais un travail, une pièce, une quantité ou un constat qui n'est ni dans la note, ni dans la
  demande, ni visible sur les photos. Dans le doute, reste vague plutôt que d'inventer.
- Garde intacts les emplacements, équipements, marques, numéros de modèle, quantités et mesures.
- Si la note est une demande, une question ou un besoin de conseil (« besoin d'un plombier pour… »), ne la
  transforme pas en travail fait : reformule-la telle quelle, en français correct.
- Décris les travaux, jamais les photos : pas de « a été photographié » ni de description de ce qu'on voit sur
  une photo.
- Pas de formule creuse (« selon la demande », « tel que demandé », « conformément à la demande ») et pas de
  détail sans intérêt pour le client (température lue, nom d'une personne, marque d'un équipement non touché).
- Pas de salutation, pas de signature, pas de Markdown : seulement la description.

Réponds avec le texte dans « texte » et la liste des détails tirés des photos dans « ajouts_photos »
(liste vide s'il n'y en a pas)."""

TYPES_PHOTOS = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_PHOTOS = 4
TAILLE_MAX_PHOTO = 5 * 1024 * 1024

# 1 000 ou 1000, 2,5 ou 2.5
NOMBRE = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def _nombres(texte: str) -> list[str]:
    vus: list[str] = []
    for brut in NOMBRE.findall(texte or ""):
        valeur = re.sub(r"[   ]", "", brut).replace(",", ".")
        normal = f"{float(valeur):g}"
        if normal not in vus:
            vus.append(normal)
    return vus


def nombres_absents(original: str, propose: str) -> list[str]:
    """Nombres du texte proposé qui n'apparaissent pas dans l'original."""
    dans_original = set(_nombres(original))
    return [n for n in _nombres(propose) if n not in dans_original]


def rediger(texte: str, client, cfg: dict, photos: list[tuple[str, bytes]] | None = None,
            demande: str = "") -> tuple[str, list[Alerte]]:
    texte = texte or ""
    utilisables = [(m.lower(), c) for m, c in (photos or [])
                   if m.lower() in TYPES_PHOTOS and len(c) <= TAILLE_MAX_PHOTO][:MAX_PHOTOS]
    if not texte.strip() and not utilisables:
        return "", []
    contenu = [{"type": "image", "source": {"type": "base64", "media_type": m,
                                             "data": base64.standard_b64encode(c).decode("ascii")}}
               for m, c in utilisables]
    contenu.append({"type": "text", "text": f"Demande de départ :\n{demande or '(aucune)'}\n\n"
                                            f"Note du technicien :\n{texte or '(vide)'}"})
    resultat = demander_json(client, cfg, contenu, SCHEMA, SYSTEME)
    propose = ((resultat or {}).get("texte") or "").strip()
    if not propose:
        return texte, [Alerte("redaction_echec", "La description n'a pas pu être révisée; texte original conservé.")]
    alertes = []
    if not texte.strip():
        alertes.append(Alerte("description_creee", "Le technicien n'a rien écrit : description proposée à partir de "
                                                   "la demande et des photos, à vérifier."))
    ajouts = [a for a in (resultat.get("ajouts_photos") or []) if isinstance(a, str) and a.strip()]
    if ajouts:
        alertes.append(Alerte("description_enrichie",
                              "Détails ajoutés d'après les photos, à vérifier : " + " · ".join(ajouts) + "."))
    absents = nombres_absents(f"{texte}\n{demande}\n{' '.join(ajouts)}", propose)
    if absents:
        alertes.append(Alerte(
            "redaction_chiffre",
            f"La description révisée contient des nombres absents du texte du technicien : {', '.join(absents)}."))
    return propose, alertes
