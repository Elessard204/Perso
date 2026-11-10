"""Client de l'API REST Progression Live. Seul module qui parle à Progression."""

from __future__ import annotations

import base64
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from modele import Bon, EntreeTemps, Ligne, PieceJointe

BASE = "https://api.progressionlive.com/server/rest"
PAGE = 500  # maximum accepté par /task/list


class ErreurProgression(Exception):
    """Erreur de Progression, avec un message lisible par l'équipe."""


def minutes_iso(duree: str) -> int:
    """Durée ISO 8601 (PT1H20M) en minutes, secondes arrondies à la minute supérieure."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?", duree or "")
    if not m or not duree:
        return 0
    jours, heures, minutes, secondes = (float(x) if x else 0.0 for x in m.groups())
    return math.ceil(jours * 1440 + heures * 60 + minutes + secondes / 60)


def _jour(horodatage: str | None) -> date | None:
    if not horodatage:
        return None
    try:
        return date.fromisoformat(horodatage[:10])
    except ValueError:
        return None


def _libelle(ref) -> str:
    return (ref or {}).get("label") or ""


def lire_champ(tache: dict, champ: str) -> str:
    """Lit « description » ou « properties.notesTech » dans une tâche."""
    valeur = tache
    for partie in champ.split("."):
        valeur = (valeur or {}).get(partie) if isinstance(valeur, dict) else None
    return valeur if isinstance(valeur, str) else ""


def bon_depuis_json(tache: dict, entrees: list[dict], cfg: dict) -> Bon:
    lignes = []
    for it in (tache.get("itemList") or {}).get("items") or []:
        produit = it.get("product") or {}
        lignes.append(Ligne(
            id=it.get("id"),
            libelle=it.get("label") or "",
            description=it.get("description") or "",
            quantite=float(it.get("quantity") or 0),
            prix=float(it.get("price") or 0),
            cout_unitaire=float(it["unitCost"]) if it.get("unitCost") is not None else None,
            produit=produit.get("code") or produit.get("label"),
            external_id=it.get("externalId"),
        ))
    return Bon(
        id=tache["id"],
        code=tache.get("code") or "",
        client=_libelle(tache.get("client")),
        date_rv=_jour(tache.get("rv")),
        maj=tache.get("updated") or "",
        description=lire_champ(tache, cfg.get("champ_description") or "description"),
        entrees=[
            EntreeTemps(
                id=e["id"],
                technicien=_libelle(e.get("humanResource")),
                jour=_jour(e.get("start")),
                minutes=minutes_iso(e.get("duration") or ""),
                ligne_id=(e.get("item") or {}).get("id"),
            )
            for e in entrees
        ],
        lignes=lignes,
        pieces=[
            PieceJointe(id=a["id"], nom=a.get("name") or "", type_mime=a.get("contentType") or "")
            for a in tache.get("attachments") or []
        ],
    )


def _liste(reponse) -> list[dict]:
    """/task/list renvoie une liste; on accepte aussi une enveloppe {"data": [...]}."""
    if isinstance(reponse, list):
        return reponse
    if isinstance(reponse, dict):
        for valeur in reponse.values():
            if isinstance(valeur, list):
                return valeur
    return []


class Progression:
    def __init__(self, cle: str, base: str = BASE, ouvrir=urllib.request.urlopen, cfg: dict | None = None):
        self.cle = cle
        self.base = base.rstrip("/")
        self.ouvrir = ouvrir
        self.cfg = cfg or {}

    def _appel(self, methode: str, chemin: str, params: dict | None = None, corps: dict | None = None):
        url = self.base + chemin
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        donnees = json.dumps(corps).encode("utf-8") if corps is not None else None
        requete = urllib.request.Request(url, data=donnees, method=methode, headers={
            "Authorization": f"Bearer {self.cle}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        try:
            with self.ouvrir(requete, timeout=60) as reponse:
                texte = reponse.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErreurProgression(
                    "Clé Progression refusée ou permissions insuffisantes. "
                    "Vérifier la clé dans les paramètres.") from e
            if e.code == 404:
                raise ErreurProgression(f"Élément introuvable dans Progression ({chemin}).") from e
            raise ErreurProgression(f"Progression a répondu une erreur {e.code} ({chemin}).") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurProgression(
                "Progression ne répond pas. Vérifier la connexion Internet et réessayer.") from e
        return json.loads(texte) if texte.strip() else {}

    def lister_bons(self, logic_ids: str, type_tache: str, rv: str) -> list[dict]:
        taches: list[dict] = []
        debut = 0
        while True:
            page = _liste(self._appel("GET", "/task/list", {
                "logicId": logic_ids, "type": type_tache, "rv": rv,
                "maxResults": PAGE, "startResult": debut,
            }))
            taches.extend(page)
            if len(page) < PAGE:
                return taches
            debut += PAGE

    def lister_recents(self, logic_ids: str, nombre: int) -> list[dict]:
        """Les derniers bons modifiés, pour l'inspection."""
        return _liste(self._appel("GET", "/task/list", {
            "logicId": logic_ids, "order": "updated DESC", "maxResults": nombre, "startResult": 0,
        }))[:nombre]

    def lire_tache(self, identifiant: int) -> tuple[dict, list[dict]]:
        """La tâche et ses entrées de temps, telles que Progression les renvoie."""
        tache = self._appel("GET", f"/task/{identifiant}")
        return tache, _liste(self._appel("GET", f"/task/{identifiant}/timeEntries"))

    def lire_bon(self, identifiant: int) -> Bon:
        tache, entrees = self.lire_tache(identifiant)
        return bon_depuis_json(tache, entrees, self.cfg)

    def telecharger_piece(self, piece_id: int) -> bytes:
        piece = self._appel("GET", f"/task/attachment/{piece_id}")
        return base64.b64decode(piece.get("data") or "")

    def mettre_a_jour(self, identifiant: int, corps: dict) -> dict:
        return self._appel("POST", f"/task/{identifiant}/update", corps=corps)
