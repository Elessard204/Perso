"""Faux Progression et faux Claude pour essayer l'outil sans réseau ni clé (mode --demo).

Six bons fictifs couvrent les cas à voir : facture + photo, même facture jointe deux fois,
photo illisible, journée de plus de 12 h, bon sans heures, facture dont le total ne balance pas.
"""

from __future__ import annotations

import json
import math
import re
import struct
import zlib
from datetime import date, timedelta
from types import SimpleNamespace

from progression import bon_depuis_json

CLIENTS = ["Gestion Fictive inc.", "Immeubles Démo SENC", "Habitations Exemple ltée"]


def _png(couleur: tuple[int, int, int], largeur: int = 320, hauteur: int = 200) -> bytes:
    def morceau(type_: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", zlib.crc32(type_ + donnees))
    ligne = bytes([0]) + bytes(couleur) * largeur
    return (bytes([0x89]) + b"PNG\r\n" + bytes([0x1A]) + b"\n" + morceau(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0))
            + morceau(b"IDAT", zlib.compress(ligne * hauteur)) + morceau(b"IEND", b""))


def _pdf(lignes_texte: list[str]) -> bytes:
    texte = " ".join(f"({t.replace('(', '').replace(')', '')}) Tj T*" for t in lignes_texte)
    flux = f"BT /F1 12 Tf 14 TL 50 750 Td {texte} ET".encode("latin-1", "replace")
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    sortie, positions = b"%PDF-1.4\n", []
    for i, objet in enumerate(objets, start=1):
        positions.append(len(sortie))
        sortie += b"%d 0 obj\n" % i + objet + b"\nendobj\n"
    debut_xref = len(sortie)
    sortie += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    sortie += b"".join(b"%010d 00000 n \n" % p for p in positions)
    sortie += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, debut_xref)
    return sortie


FACTURES = {
    "facture_rona_A-1.pdf": {"genre": "facture", "raison": "Reçu de quincaillerie Rona.", "fournisseur": "Rona",
                             "numero": "A-1", "date": "2026-11-02", "sous_total": 31.48,
                             "lignes": [{"description": "Robinet de cuisine", "quantite": 1, "prix_unitaire": 24.98},
                                        {"description": "Raccord 1/2 po", "quantite": 2, "prix_unitaire": 3.25}]},
    "facture_bmr_778.pdf": {"genre": "facture", "raison": "Facture BMR.", "fournisseur": "BMR", "numero": "778",
                            "date": "2026-11-05", "sous_total": 60.00,
                            "lignes": [{"description": "Disjoncteur 15 A", "quantite": 2, "prix_unitaire": 18.50},
                                       {"description": "Boîte électrique", "quantite": 1, "prix_unitaire": 9.75}]},
}
PHOTO = {"genre": "photo", "raison": "Photo des travaux.", "fournisseur": "", "numero": "", "date": "",
         "sous_total": None, "lignes": []}

DESCRIPTIONS = {
    "changer robinet cuisine fuite sous lavabo, posé 2 raccord":
        "Remplacement du robinet de cuisine qui fuyait sous l'évier et pose de 2 raccords.",
    "fuite reglé meme chose que hier":
        "Réparation de la fuite, suite de l'intervention de la veille.",
    "inspection toiture photo jointe":
        "Inspection de la toiture; photo jointe au bon.",
    "urgence degat deau sous sol pompé eau toute la nuit":
        "Intervention d'urgence pour un dégât d'eau au sous-sol : pompage de l'eau durant la nuit.",
    "a faire":
        "Travaux à compléter.",
    "remplacé 2 disjoncteur panneau + boite":
        "Remplacement de 2 disjoncteurs au panneau électrique et d'une boîte électrique.",
    "peinture cage escalier":
        "Peinture de la cage d'escalier.",
}

# Le champ « Achat » du technicien et le type de chaque bon.
ACHATS = {1: "Robinet cuisine", 3: "Silicone", 6: "Non"}
TYPES = {1: "Appel de service", 2: "Appel de service", 3: "Maintenance", 4: "Maintenance", 5: "Appel de service",
         6: "Maintenance", 7: "Maintenance"}
IMMEUBLES = {1: 701, 2: 702, 3: 703, 4: 704, 5: 705, 6: 706, 7: 704}   # le bon 7 est dans le même immeuble que le 4
# Une position fictive (autour de Montréal) par immeuble, et le « Km » écrit par les techniciens.
POSITIONS = {701: (45.5017, -73.5673), 702: (45.5311, -73.6003), 703: (45.4765, -73.5844),
             704: (45.5588, -73.5512), 705: (45.4420, -73.6150), 706: (45.6070, -73.6420)}
KM_ECRITS = {1: "35 km", 2: "30 pour les deux jours", 3: "", 4: "52", 5: "12 km", 6: "", 7: "18,5 km"}


def _tache(n: int, note: str, pieces: list[tuple[int, str, str]], travail: list[tuple[str, str, str]],
           jour: int | None = None, prix_heure: float = 65.0, inventaire_vide: bool = False,
           non_facturee: bool = False) -> tuple[dict, list[dict]]:
    """travail : (technicien, durée du transport, durée du travail). Les lignes sont celles que crée
    « Facturer » : une par entrée de temps, aux taux par défaut de Progression (65 $/h, 50 $ le transport)."""
    jour = jour or n + 2
    items, entrees = [], []
    for k, (tech, transport, duree) in enumerate(travail):
        it_t, it_mo = 2000 + n * 10 + 2 * k, 2000 + n * 10 + 2 * k + 1
        items.append({"id": it_t, "label": f"Transport (En route, {tech})", "description": "", "quantity": 1.0,
                      "price": 50.0, "product": {"label": "Transport"}})
        heures = round(sum(int(x) * f for x, f in zip(re.findall(r"(\d+)", duree.replace("PT", "")), (1, 1 / 60))
                       ) if "H" in duree else int(re.findall(r"\d+", duree)[0]) / 60, 4)
        items.append({"id": it_mo, "label": f"Main d'oeuvre (En cours, {tech})", "description": "", "quantity": heures,
                      "price": prix_heure, "product": {"label": "Main d'oeuvre"}})
        entrees.append({"id": 30000 + n * 10 + 2 * k, "duration": transport, "start": f"2026-11-{jour:02d}T08:00:00-05:00",
                        "activity": {"label": "En route"}, "averageHourlyCost": 28.0, "humanResource": {"label": tech},
                        "item": {"id": it_t}, "task": {"id": 2000 + n, "code": f"BS-{2000 + n}"}})
        entrees.append({"id": 30000 + n * 10 + 2 * k + 1, "duration": duree, "start": f"2026-11-{jour:02d}T09:00:00-05:00",
                        "activity": {"label": "En cours"}, "averageHourlyCost": 28.0, "humanResource": {"label": tech},
                        "item": {"id": it_mo}, "task": {"id": 2000 + n, "code": f"BS-{2000 + n}"}})
    if inventaire_vide:
        items.append({"id": 2000 + n * 10 + 9, "label": "Matériel", "description": "", "quantity": 1.0, "price": 0.0,
                      "product": {"label": "Matériel en inventaire"}})
    if non_facturee:
        entrees.append({"id": 30000 + n * 10 + 9, "duration": "PT45M", "start": f"2026-11-{jour:02d}T14:00:00-05:00",
                        "activity": {"label": "En cours"}, "averageHourlyCost": 28.0, "humanResource": {"label": "Max Roy"},
                        "item": None, "task": {"id": 2000 + n, "code": f"BS-{2000 + n}"}})
    tache = {
        "id": 2000 + n, "code": f"BS-{2000 + n}", "summary": "", "rv": f"2026-11-{jour:02d}T08:00:00-05:00",
        "updated": f"2026-11-{jour:02d}T17:00:00-05:00", "description": f"Intervention demandée au logement {n}.",
        "type": {"label": TYPES[n]}, "client": {"id": IMMEUBLES[n], "label": CLIENTS[n % len(CLIENTS)]},
        "location": {"id": n, "label": f"Logement {n}"},
        "clientAddress": {"address": f"{100 + n} rue Fictive", "position": {
            "latitude": POSITIONS[IMMEUBLES[n]][0], "longitude": POSITIONS[IMMEUBLES[n]][1]}},
        "currentState": {"label": "Terminé", "logicId": 600},
        "properties": {"info.notes": note, "info.achat": ACHATS.get(n, ""),
                       "info.km": KM_ECRITS.get(n, "")},
        "itemList": {"items": items},
        "attachments": [{"id": pid, "name": nom, "contentType": mime} for pid, nom, mime in pieces],
    }
    return tache, entrees


def _jeu() -> dict[int, tuple[dict, list[dict]]]:
    bons = [
        _tache(1, "changer robinet cuisine fuite sous lavabo, posé 2 raccord",
               [(9101, "IMG_2041.png", "image/png"), (9102, "facture_rona_A-1.pdf", "application/pdf")],
               [("Luc Tremblay", "PT1H20M", "PT2H5M")]),
        _tache(2, "fuite reglé meme chose que hier",
               [(9201, "facture_rona_A-1.pdf", "application/pdf"), (9202, "facture_rona_A-1 (copie).pdf", "application/pdf")],
               [("Luc Tremblay", "PT25M", "PT40M")]),
        _tache(3, "inspection toiture photo jointe",
               [(9301, "toiture.png", "image/png"), (9302, "IMG_8812.heic", "image/heic")],
               [("Max Roy", "PT30M", "PT1H")]),
        _tache(4, "urgence degat deau sous sol pompé eau toute la nuit",
               [(9401, "sous-sol.png", "image/png")],
               [("Max Roy", "PT30M", "PT12H30M")]),
        _tache(5, "a faire", [(9501, "avant.png", "image/png")], [], inventaire_vide=True),
        _tache(6, "remplacé 2 disjoncteur panneau + boite",
               [(9601, "facture_bmr_778.pdf", "application/pdf"), (9602, "panneau.png", "image/png")],
               [("Luc Tremblay", "PT20M", "PT1H10M"), ("Sam Côté", "PT20M", "PT50M")]),
        _tache(7, "peinture cage escalier", [(9701, "escalier.png", "image/png")],
               [("Max Roy", "PT15M", "PT3H")], jour=6, prix_heure=85.0, non_facturee=True),
    ]
    return {t["id"]: (t, e) for t, e in bons}


class FausseProgression:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        self.taches = _jeu()
        self.ecrits: list[tuple[int, dict]] = []

    def _piece(self, piece_id: int) -> tuple[str, str]:
        for tache, _ in self.taches.values():
            for a in tache["attachments"]:
                if a["id"] == piece_id:
                    return a["name"], a["contentType"]
        raise KeyError(piece_id)

    def lister_bons(self, logic_ids: str, type_tache: str, rv: str) -> list[dict]:
        return [{"id": t["id"], "code": t["code"], "client": t["client"], "rv": t["rv"]} for t, _ in self.taches.values()]

    def lire_bon(self, identifiant: int):
        tache, entrees = self.taches[identifiant]
        return bon_depuis_json(tache, entrees, self.cfg)

    def tache_brute(self, identifiant: int) -> dict:
        return self.taches[identifiant][0]

    def lire_tache(self, identifiant: int) -> tuple[dict, list[dict]]:
        tache, entrees = self.taches[identifiant]
        return tache, entrees

    def entrees_periode(self, debut: date, fin: date) -> list[dict]:
        """Les entrées du jeu de démo dans [debut - 1 jour, fin + 1 jour], au format /timeEntry/list."""
        bas, haut = (debut - timedelta(days=1)).isoformat(), (fin + timedelta(days=1)).isoformat()
        return [
            {k: e[k] for k in ("id", "humanResource", "start", "duration", "activity", "task")}
            for _, entrees in self.taches.values() for e in entrees
            if bas <= e["start"][:10] <= haut
        ]

    def telecharger_piece(self, piece_id: int) -> bytes:
        nom, mime = self._piece(piece_id)
        if mime == "application/pdf":
            f = FACTURES.get(nom.replace(" (copie)", ""), {})
            return _pdf([f"FACTURE {f.get('fournisseur', '')} no {f.get('numero', '')}"]
                        + [f"{l['quantite']} x {l['description']} {l['prix_unitaire']:.2f} $" for l in f.get("lignes", [])])
        if mime == "image/png":
            return _png((90 + piece_id % 120, 120, 150))
        return bytes(3) + b" ftypheic"

    def bon_avec_ligne(self, external_id: str) -> int | None:
        for identifiant, corps in self.ecrits:
            if any(i.get("externalId") == external_id for i in corps["itemList"]["items"]):
                return identifiant
        return None

    def mettre_a_jour(self, identifiant: int, corps: dict) -> dict:
        self.ecrits.append((identifiant, corps))
        return {}


class FaussesCartes:
    """Même interface que cartes.Cartes, sans réseau ni clé, et toujours les mêmes résultats."""

    def geocoder(self, code_postal: str) -> tuple[float, float] | None:
        n = sum(int(c) for c in code_postal if c.isdigit())
        return (round(45.45 + n / 100, 5), round(-73.45 - n / 100, 5))

    def distance_km(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        """Distance à vol d'oiseau (haversine) × 1,3, arrondie à 0,1 km."""
        if (round(a[0], 5), round(a[1], 5)) == (round(b[0], 5), round(b[1], 5)):
            return 0.0
        p1, p2 = math.radians(a[0]), math.radians(b[0])
        dp, dl = p2 - p1, math.radians(b[1] - a[1])
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return round(6371.0 * 2 * math.asin(math.sqrt(h)) * 1.3, 1)


class FauxClaude:
    """Répond comme Claude, selon le nom de la pièce ou le texte du technicien."""

    def __init__(self):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        textes = [b["text"] for b in kwargs["messages"][0]["content"] if b.get("type") == "text"]
        consigne = textes[-1] if textes else ""
        if "Kilométrage inscrit" in consigne:
            reponse = {"km": 52, "confiance": "haute"}
        elif "Note du technicien :" in consigne:
            original = consigne.split("Note du technicien :\n", 1)[1].strip()
            reponse = {"texte": DESCRIPTIONS.get(original, original.capitalize()), "ajouts_photos": []}
        else:
            nom = consigne.split("«", 1)[1].split("»", 1)[0].strip() if "«" in consigne else ""
            reponse = FACTURES.get(nom.replace(" (copie)", ""), PHOTO)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(reponse, ensure_ascii=False))])
