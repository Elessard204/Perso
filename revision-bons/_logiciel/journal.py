"""Historique partagé : un fichier par personne, lus ensemble (comme le suivi des rapports clients)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


class Journal:
    def __init__(self, dossier: Path, personne: str):
        self.dossier = Path(dossier)
        self.personne = personne

    def inscrire(self, evenement: str, bon_id: int, maj: str, details: dict) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        ligne = {
            "horodatage": datetime.now().astimezone().isoformat(timespec="microseconds"),
            "personne": self.personne,
            "evenement": evenement,
            "bon_id": bon_id,
            "maj": maj,
            "details": details,
        }
        with open(self.dossier / f"{self.personne}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")

    def _tous(self) -> list[dict]:
        evenements = []
        for fichier in sorted(self.dossier.glob("*.jsonl")):
            for ligne in fichier.read_text(encoding="utf-8").splitlines():
                try:
                    evenements.append(json.loads(ligne))
                except ValueError:
                    continue
        return sorted(evenements, key=lambda e: e.get("horodatage", ""))

    def historique(self, limite: int = 200) -> list[dict]:
        return list(reversed(self._tous()))[:limite]

    def deja_ecrit(self, bon_id: int, maj: str) -> bool:
        """Vrai si ce bon, dans cet état, a déjà été écrit (date d'avant ou d'après l'écriture)."""
        if not maj:
            return False
        return any(
            e["evenement"] == "ecrit" and e["bon_id"] == bon_id
            and maj in (e["maj"], (e.get("details") or {}).get("maj_apres"))
            for e in self._tous())

    def factures_refacturees(self) -> dict[str, int]:
        """« fournisseur|numéro » -> bon où la facture a déjà été refacturée."""
        factures: dict[str, int] = {}
        for e in self._tous():
            if e["evenement"] != "ecrit":
                continue
            for external_id in (e.get("details") or {}).get("external_ids") or []:
                factures.setdefault(external_id.rsplit("|", 1)[0], e["bon_id"])
        return factures
