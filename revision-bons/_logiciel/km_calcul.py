"""Calcul pur du kilométrage des techniciens : périodes, journées, km d'une journée, totaux.

Aucune entrée-sortie ni réseau : les distances sont fournies par l'appelant.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from progression import minutes_iso
from regles import cents

_NBSP = chr(0xA0)
_RE_KM = re.compile(
    r"^\s*(\d{1,3}(?:[ " + _NBSP + r"]\d{3})*|\d+)(?:[.,](\d+))?\s*(?:km)?\s*$", re.IGNORECASE)
_SANS_BON = "entrée sans bon"


def periode_contenant(jour: date, reference: date) -> tuple[date, date]:
    """Période de 14 jours (début = reference + 14*k) qui contient `jour`."""
    k = (jour - reference).days // 14
    debut = reference + timedelta(days=14 * k)
    return debut, debut + timedelta(days=13)


def periodes_proposees(aujourdhui: date, reference: date, nombre: int = 4) -> list[tuple[date, date]]:
    """La période courante puis les précédentes."""
    debut, fin = periode_contenant(aujourdhui, reference)
    return [(debut - timedelta(days=14 * i), fin - timedelta(days=14 * i)) for i in range(nombre)]


@dataclass
class Arret:
    tache_id: int
    code: str
    lat: float | None
    lng: float | None


@dataclass
class Journee:
    technicien: str
    jour: date
    arrets: list[Arret] = field(default_factory=list)
    a_verifier: list[str] = field(default_factory=list)
    minutes: float = 0.0


def _position(tache: dict | None) -> tuple[float, float] | None:
    for cle in ("clientAddress", "locationAddress"):
        pos = ((tache or {}).get(cle) or {}).get("position") or {}
        lat, lng = pos.get("latitude"), pos.get("longitude")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    return None


def _cle(arret: Arret) -> tuple:
    return arret.tache_id, round(arret.lat, 5), round(arret.lng, 5)


def journees(entrees: list[dict], taches: dict[int, dict], debut: date, fin: date) -> list[Journee]:
    """Regroupe les entrées de temps par technicien et par jour (date du champ `start`)."""
    retenues = []
    for e in entrees:
        start = e.get("start") or ""
        try:
            jour = date.fromisoformat(start[:10])
        except ValueError:
            continue
        if debut <= jour <= fin:
            retenues.append((((e.get("humanResource") or {}).get("label") or ""), jour, start, e))
    retenues.sort(key=lambda r: (r[0], r[1], r[2]))

    resultat: dict[tuple[str, date], Journee] = {}
    for tech, jour, _start, e in retenues:
        j = resultat.setdefault((tech, jour), Journee(tech, jour))
        j.minutes += minutes_iso(e.get("duration") or "")
        tache = e.get("task") or {}
        tache_id = tache.get("id")
        code = tache.get("code") or ""
        pos = _position(taches.get(tache_id)) if tache_id is not None else None
        if pos is None:
            msg = f"{code or _SANS_BON} : immeuble sans position GPS"
            if msg not in j.a_verifier:
                j.a_verifier.append(msg)
            continue
        arret = Arret(tache_id, code, pos[0], pos[1])
        if not j.arrets or _cle(j.arrets[-1]) != _cle(arret):
            j.arrets.append(arret)
    return [resultat[k] for k in sorted(resultat)]


def km_journee(domicile: tuple[float, float] | None, arrets: list[Arret],
               distance: Callable[[tuple, tuple], float]) -> tuple[float, list[dict]]:
    """Km de domicile → arrêts → domicile, et la liste des tronçons."""
    points = [(a.code, (a.lat, a.lng)) for a in arrets if a.lat is not None and a.lng is not None]
    if not points:
        return 0.0, []
    if domicile is not None:
        points = [("domicile", tuple(domicile))] + points + [("domicile", tuple(domicile))]
    troncons = []
    for (de, p1), (a, p2) in zip(points, points[1:]):
        troncons.append({"de": de, "a": a, "km": distance(p1, p2)})
    return round(sum(t["km"] for t in troncons), 1), troncons


def lire_km_simple(texte: str) -> float | None:
    """Un seul nombre avec unité facultative (« 60km », « 12,5 km », « 1 200 km »), sinon None."""
    m = _RE_KM.match(texte or "")
    if not m:
        return None
    entier = re.sub(r"[ " + _NBSP + "]", "", m.group(1))
    return float(entier + ("." + m.group(2) if m.group(2) else ""))


def totaliser(base: dict, ajustements: dict, taux: float, seuil: float,
              techniciens: dict[str, dict]) -> dict:
    """Totaux par technicien et pour la période (format envoyé à la page et à l'export)."""
    lignes = []
    total_km = 0.0
    total_montant = 0.0
    for nom in sorted(base.get("techniciens", {})):
        donnees = base["techniciens"][nom]
        config = techniciens.get(nom)
        if config is not None and not config.get("paye_km"):
            statut_fixe = "sous_traitant"
        elif config is None or not (config.get("code_postal") or "").strip():
            statut_fixe = "a_configurer"
        else:
            statut_fixe = None
        paie = statut_fixe is None

        details = []
        minutes_par_jour: dict[str, float] = {}
        km_calcule = km_magasin = km_a_payer = 0.0
        for jour in donnees.get("jours", []):
            aj = ajustements.get(f"{nom}|{jour['jour']}") or {}
            uhaul = bool(aj.get("uhaul"))
            magasin = float(aj.get("magasin_km") or 0)
            km_paye = 0.0 if uhaul else jour.get("km", 0.0) + magasin
            details.append({**jour, "uhaul": uhaul, "magasin_km": magasin, "km_paye": round(km_paye, 1)})
            minutes_par_jour[jour["jour"]] = minutes_par_jour.get(jour["jour"], 0.0) + jour.get("minutes", 0.0)
            km_calcule += jour.get("km", 0.0)
            if not uhaul:
                km_magasin += magasin
            km_a_payer += km_paye
        bons = donnees.get("bons", [])
        km_declare = round(sum(b.get("km", 0.0) * b.get("part", 1.0) for b in bons if b.get("statut") == "ok"), 1)
        a_declare = any(b.get("statut") == "ok" for b in bons)

        if paie:
            km_a_payer = round(km_a_payer, 1)
            montant = cents(km_a_payer * taux)
            ecart = round(km_declare - km_a_payer, 1)
            if not a_declare:
                statut = "non_declare"
            elif abs(ecart) > seuil:
                statut = "ecart"
            else:
                statut = "ok"
            total_km += km_a_payer
            total_montant += montant
        else:
            km_a_payer, montant, ecart, statut = 0.0, None, None, statut_fixe

        lignes.append({
            "nom": nom, "jours": len(details), "km_calcule": round(km_calcule, 1),
            "km_magasin": round(km_magasin, 1), "km_a_payer": km_a_payer, "montant": montant,
            "km_declare": km_declare, "ecart": ecart, "statut": statut, "paie": paie,
            "minutes_par_jour": minutes_par_jour, "minutes_total": sum(minutes_par_jour.values()),
            "details": details, "bons": bons,
        })
    return {"debut": base.get("debut"), "fin": base.get("fin"), "taux": taux, "seuil_km": seuil,
            "techniciens": lignes, "total_km": round(total_km, 1), "total_montant": cents(total_montant)}
