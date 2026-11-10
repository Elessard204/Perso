"""Correction et résumé de la description des travaux par Claude, avec contrôle anti-invention."""

from __future__ import annotations

import re

from claude_client import demander_json
from modele import Alerte

SCHEMA = {
    "type": "object",
    "properties": {"texte": {"type": "string"}},
    "required": ["texte"],
    "additionalProperties": False,
}

SYSTEME = """Tu révises la description des travaux écrite par un technicien sur un bon de service, avant
qu'elle soit envoyée au client sur la facture d'une entreprise de gestion immobilière au Québec.

- Corrige l'orthographe, la grammaire et la syntaxe pour obtenir un français professionnel, clair et sobre.
- Si le texte est confus ou décousu, résume-le en quelques phrases simples qui décrivent les travaux faits.
- N'ajoute jamais un travail, une pièce, une quantité, une mesure ou un constat que le technicien n'a pas écrit.
- Garde intacts les emplacements, équipements, marques, numéros de modèle, quantités et mesures.
- Écris dans la même langue que l'original (français ou anglais).
- Pas de salutation, pas de signature, pas de mise en forme Markdown : seulement la description.

Réponds avec le texte révisé dans le champ « texte »."""

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


def rediger(texte: str, client, cfg: dict) -> tuple[str, list[Alerte]]:
    if not (texte or "").strip():
        return "", []
    resultat = demander_json(
        client, cfg, [{"type": "text", "text": f"Description du technicien :\n\n{texte}"}], SCHEMA, SYSTEME)
    propose = ((resultat or {}).get("texte") or "").strip()
    if not propose:
        return texte, [Alerte("redaction_echec", "La description n'a pas pu être révisée; texte original conservé.")]
    absents = nombres_absents(texte, propose)
    if absents:
        return propose, [Alerte(
            "redaction_chiffre",
            f"La description révisée contient des nombres absents du texte du technicien : {', '.join(absents)}.")]
    return propose, []
