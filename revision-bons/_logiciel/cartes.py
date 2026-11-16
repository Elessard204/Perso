"""Client Google Maps (géocodage et distances routières) avec cache local. Lecture seule."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

URL_GEOCODAGE = "https://maps.googleapis.com/maps/api/geocode/json"
URL_ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
ESSAIS = 5  # quand Google demande de ralentir (429)

MSG_CLE = "Clé Google refusée ou API non activée : vérifier la clé dans l'onglet Règles."
MSG_RESEAU = "Google Maps ne répond pas. Vérifier la connexion Internet et réessayer."


class ErreurCartes(Exception):
    """Erreur de Google Maps, avec un message lisible par l'équipe."""


def _cle_point(p: tuple[float, float]) -> str:
    return f"{round(p[0], 5):.5f},{round(p[1], 5):.5f}"


class Cartes:
    def __init__(self, cle: str, fichier_cache: Path, ouvrir=urllib.request.urlopen, dormir=time.sleep):
        self.cle = cle
        self.fichier = Path(fichier_cache)
        self.ouvrir = ouvrir
        self.dormir = dormir
        self.cache = self._lire_cache()

    def _lire_cache(self) -> dict:
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
            geo, dist = donnees["geo"], donnees["dist"]
            if isinstance(geo, dict) and isinstance(dist, dict):
                return {"geo": geo, "dist": dist}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return {"geo": {}, "dist": {}}

    def _ecrire_cache(self) -> None:
        try:
            self.fichier.parent.mkdir(parents=True, exist_ok=True)
            temporaire = self.fichier.with_name(self.fichier.name + ".tmp")
            temporaire.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
            os.replace(temporaire, self.fichier)
        except OSError as e:
            raise ErreurCartes(f"Impossible d'écrire le cache des distances ({self.fichier}).") from e

    def _appel(self, requete: urllib.request.Request) -> dict:
        for essai in range(ESSAIS):
            try:
                with self.ouvrir(requete, timeout=30) as reponse:
                    texte = reponse.read().decode("utf-8")
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    if essai == ESSAIS - 1:
                        raise ErreurCartes(
                            "Google Maps reçoit trop de demandes : réessayer dans quelques minutes.") from e
                    self.dormir(2 ** essai)
                    continue
                if e.code in (400, 403):
                    raise ErreurCartes(MSG_CLE) from e
                raise ErreurCartes(f"Google Maps a répondu une erreur {e.code}.") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                raise ErreurCartes(MSG_RESEAU) from e
        try:
            return json.loads(texte) if texte.strip() else {}
        except ValueError as e:
            raise ErreurCartes("Google Maps a renvoyé une réponse illisible.") from e

    def geocoder(self, code_postal: str) -> tuple[float, float] | None:
        code = code_postal.strip().upper()
        if code in self.cache["geo"]:
            valeur = self.cache["geo"][code]
            return (valeur[0], valeur[1]) if valeur else None
        url = URL_GEOCODAGE + "?" + urllib.parse.urlencode(
            {"address": code, "components": "country:CA", "key": self.cle})
        reponse = self._appel(urllib.request.Request(url, method="GET"))
        statut = reponse.get("status")
        if statut == "OK":
            lieu = reponse["results"][0]["geometry"]["location"]
            position = (lieu["lat"], lieu["lng"])
            self.cache["geo"][code] = [position[0], position[1]]
        elif statut == "ZERO_RESULTS":
            position = None
            self.cache["geo"][code] = None
        else:
            raise ErreurCartes(f"Google Maps : {reponse.get('error_message') or statut}")
        self._ecrire_cache()
        return position

    def distance_km(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        cle_a, cle_b = _cle_point(a), _cle_point(b)
        if cle_a == cle_b:
            return 0.0
        cle = f"{cle_a}>{cle_b}"
        if cle in self.cache["dist"]:
            return self.cache["dist"][cle]

        def point(p):
            return {"location": {"latLng": {"latitude": p[0], "longitude": p[1]}}}
        corps = {"origin": point(a), "destination": point(b),
                 "travelMode": "DRIVE", "routingPreference": "TRAFFIC_UNAWARE"}
        requete = urllib.request.Request(URL_ROUTES, data=json.dumps(corps).encode("utf-8"), method="POST", headers={
            "X-Goog-Api-Key": self.cle,
            "X-Goog-FieldMask": "routes.distanceMeters",
            "Content-Type": "application/json",
        })
        routes = self._appel(requete).get("routes") or []
        if not routes or "distanceMeters" not in routes[0]:
            raise ErreurCartes("Aucun trajet routier trouvé entre ces deux endroits.")
        km = round(routes[0]["distanceMeters"] / 1000, 1)
        self.cache["dist"][cle] = km
        self._ecrire_cache()
        return km
