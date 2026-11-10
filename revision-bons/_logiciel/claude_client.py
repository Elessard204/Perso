"""Appel à l'API de Claude avec réponse JSON structurée. Seul point d'entrée vers Claude."""

from __future__ import annotations

import json

BETAS = ["server-side-fallback-2026-07-01"]


def creer_client(cle: str):
    import anthropic  # importé ici : les tests et le mode démo n'en ont pas besoin
    return anthropic.Anthropic(api_key=cle)


def demander_json(client, cfg: dict, contenu: list[dict], schema: dict, systeme: str) -> dict | None:
    """Renvoie le JSON demandé, ou None si Claude refuse, coupe sa réponse ou renvoie du JSON invalide.

    Les erreurs réseau et d'API (anthropic.APIConnectionError, APIStatusError) remontent à l'appelant.
    """
    reponse = client.beta.messages.create(
        model=cfg["modele"],
        max_tokens=16000,
        betas=BETAS,
        fallbacks="default",  # si un modèle refuse, un autre modèle Claude prend le relais
        output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}},
        system=systeme,
        messages=[{"role": "user", "content": contenu}],
    )
    if reponse.stop_reason in ("refusal", "max_tokens"):
        return None
    texte = next((b.text for b in reponse.content if getattr(b, "type", "") == "text"), "")
    try:
        donnees = json.loads(texte)
    except ValueError:
        return None
    return donnees if isinstance(donnees, dict) else None
