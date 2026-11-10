"""Faux Progression et faux Claude pour essayer l'outil sans réseau ni clé (mode --demo).

Six bons fictifs couvrent les cas à voir : facture + photo, même facture jointe deux fois,
photo illisible, journée de plus de 12 h, bon sans heures, facture dont le total ne balance pas.
"""

from __future__ import annotations

import json
import struct
import zlib
from types import SimpleNamespace

from progression import bon_depuis_json

CLIENTS = ["Gestion Fictive inc.", "Immeubles Démo SENC", "Habitations Exemple ltée"]


def _png(couleur: tuple[int, int, int], largeur: int = 320, hauteur: int = 200) -> bytes:
    def morceau(type_: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", zlib.crc32(type_ + donnees))
    ligne = b"\x00" + bytes(couleur) * largeur
    return (b"\x89PNG\r\n\x1a\n" + morceau(b"IHDR", struct.pack(">IIBBBBB", largeur, hauteur, 8, 2, 0, 0, 0))
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
}


ACHATS = {3: "Silicone", 6: "Non", 1: "Robinet cuisine"}   # champ « Achat » du technicien


def _tache(n: int, description: str, pieces: list[tuple[int, str, str]], heures: list[tuple[str, int, str]],
           items_mo: list[tuple[int, str, float]]) -> tuple[dict, list[dict]]:
    tache = {
        "id": 2000 + n, "code": f"BS-{2000 + n}", "label": description[:30],
        "rv": f"2026-11-{n + 2:02d}T08:00:00-05:00", "updated": f"2026-11-{n + 2:02d}T17:00:00-05:00",
        "description": description, "client": {"label": CLIENTS[n % len(CLIENTS)]},
        "currentState": {"label": "Complété", "logicId": 600},
        "properties": {"info": {"achat": ACHATS.get(n, "")}},
        "itemList": {"items": [
            *({"id": i, "label": "Main-d'œuvre", "description": tech, "quantity": q, "price": 95.0, "unitCost": 40.0,
               "product": {"code": "MO"}} for i, tech, q in items_mo),
            {"id": 2000 + n * 10 + 9, "label": "Transport", "description": "", "quantity": 1, "price": 45.0,
             "product": {"code": "TRANSPORT"}},
        ]},
        "attachments": [{"id": pid, "name": nom, "contentType": mime} for pid, nom, mime in pieces],
    }
    entrees = [
        {"id": 2000 + n * 100 + i, "duration": duree, "start": f"2026-11-{n + 2:02d}T08:00:00-05:00",
         "humanResource": {"label": tech}, "item": {"id": next((i_ for i_, t, _ in items_mo if t == tech), None)}}
        for i, (tech, _, duree) in enumerate(heures)
    ]
    return tache, entrees


def _jeu() -> dict[int, tuple[dict, list[dict]]]:
    bons = [
        _tache(1, "changer robinet cuisine fuite sous lavabo, posé 2 raccord",
               [(9101, "IMG_2041.png", "image/png"), (9102, "facture_rona_A-1.pdf", "application/pdf")],
               [("Luc Tremblay", 0, "PT2H5M")], [(2011, "Luc Tremblay", 2.0833)]),
        _tache(2, "fuite reglé meme chose que hier",
               [(9201, "facture_rona_A-1.pdf", "application/pdf"), (9202, "facture_rona_A-1 (copie).pdf", "application/pdf")],
               [("Luc Tremblay", 0, "PT40M")], [(2021, "Luc Tremblay", 0.6667)]),
        _tache(3, "inspection toiture photo jointe",
               [(9301, "toiture.png", "image/png"), (9302, "IMG_8812.heic", "image/heic")],
               [("Max Roy", 0, "PT1H")], [(2031, "Max Roy", 1.0)]),
        _tache(4, "urgence degat deau sous sol pompé eau toute la nuit",
               [(9401, "sous-sol.png", "image/png")],
               [("Max Roy", 0, "PT12H30M")], [(2041, "Max Roy", 12.5)]),
        _tache(5, "a faire", [(9501, "avant.png", "image/png")], [], []),
        _tache(6, "remplacé 2 disjoncteur panneau + boite",
               [(9601, "facture_bmr_778.pdf", "application/pdf"), (9602, "panneau.png", "image/png")],
               [("Luc Tremblay", 0, "PT1H10M"), ("Sam Côté", 0, "PT50M")],
               [(2061, "Luc Tremblay", 1.1667), (2062, "Sam Côté", 0.8333)]),
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

    def telecharger_piece(self, piece_id: int) -> bytes:
        nom, mime = self._piece(piece_id)
        if mime == "application/pdf":
            f = FACTURES.get(nom.replace(" (copie)", ""), {})
            return _pdf([f"FACTURE {f.get('fournisseur', '')} no {f.get('numero', '')}"]
                        + [f"{l['quantite']} x {l['description']} {l['prix_unitaire']:.2f} $" for l in f.get("lignes", [])])
        if mime == "image/png":
            return _png((90 + piece_id % 120, 120, 150))
        return b"\x00\x00\x00 ftypheic"

    def bon_avec_ligne(self, external_id: str) -> int | None:
        for identifiant, corps in self.ecrits:
            if any(i.get("externalId") == external_id for i in corps["itemList"]["items"]):
                return identifiant
        return None

    def mettre_a_jour(self, identifiant: int, corps: dict) -> dict:
        self.ecrits.append((identifiant, corps))
        return {}


class FauxClaude:
    """Répond comme Claude, selon le nom de la pièce ou le texte du technicien."""

    def __init__(self):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        textes = [b["text"] for b in kwargs["messages"][0]["content"] if b.get("type") == "text"]
        consigne = textes[-1] if textes else ""
        if consigne.startswith("Description du technicien"):
            original = consigne.split("\n\n", 1)[1]
            reponse = {"texte": DESCRIPTIONS.get(original, original.capitalize())}
        else:
            nom = consigne.split("«", 1)[1].split("»", 1)[0].strip() if "«" in consigne else ""
            reponse = FACTURES.get(nom.replace(" (copie)", ""), PHOTO)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(reponse, ensure_ascii=False))])
