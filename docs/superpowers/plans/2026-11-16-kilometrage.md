# Kilométrage des techniciens — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à l'outil « Révision des bons » un onglet « Kilométrage » qui calcule le km à payer de chaque technicien par période de paie (domicile → immeubles → domicile), affiche le km déclaré à côté avec un seuil d'écart réglable, et exporte un fichier Excel pour Sabrina.

**Architecture:** Calcul pur et testable (`km_calcul.py`) séparé des accès réseau (Progression, Google Maps, Claude). Un orchestrateur (`kilometrage.py`) bâtit une « base » coûteuse (trajets et distances) une seule fois par période, la garde dans un fichier JSON par période, puis applique à chaque modification de Hugo (Uhaul, km magasin) un calcul de totaux pur sans rappeler Google. L'interface existante (`interface.py` + `interface.html`) reçoit de nouvelles routes `/km/...` et un onglet.

**Tech Stack:** Python 3.12 portable sans pip (bibliothèque standard seulement : urllib, json, zipfile, xml), API REST Progression, Google Geocoding API + Routes API (HTTP direct), Claude via `claude_client.demander_json`, pytest, Playwright pour la vérification visuelle.

**Spec:** `docs/superpowers/specs/2026-11-16-kilometrage-design.md` (notes : `2026-11-16-kilometrage-notes.md`)

## Global Constraints

- Aucune écriture dans Progression : lecture seule (`GET` uniquement).
- Aucune nouvelle dépendance : bibliothèque standard Python seulement (le poste de Hugo n'a pas pip). L'Excel est écrit avec `zipfile`.
- Pas de `zoneinfo` (le Python portable Windows n'a pas de base de fuseaux) : le jour d'une entrée est la date de son champ `start` tel que fourni (avec son décalage).
- Taux par défaut 0,61 $/km; seuil d'écart par défaut 10 km par technicien et par période; période de deux semaines du dimanche au samedi; date de référence par défaut 2026-11-08 (un dimanche).
- Codes postaux des techniciens et clé Google : dans le profil Windows (`%APPDATA%\ProgimRevisionBons\`), jamais dans le dossier partagé ni dans Git.
- Code postal accepté : 6 caractères canadiens complets (`A1A 1A1`, espace facultatif à la saisie), enregistré en majuscules avec une espace; un code à 3 caractères est refusé.
- Rien n'est payé à un technicien sans code postal ET sans la case « Employé Progim (sur la paie, payé au km) » cochée. Technicien configuré avec la case décochée = sous-traitant (statut `sous_traitant`, aucun km, exclu de l'export); jamais configuré ou coché sans code postal = `a_configurer` (montant absent).
- Aucune donnée personnelle dans Git : ni taux horaires réels, ni codes postaux réels, ni NAS; les tests utilisent des valeurs fictives.
- Jour coché Uhaul : km du jour = 0.
- Toute validation, réouverture (avec raison), case Uhaul et km magasin est inscrite au journal existant (`Journal.inscrire`, `bon_id=0`, `maj=""`).
- Textes de l'interface en français québécois, même style que l'outil actuel (jetons CSS existants).
- Déploiement : fichiers du dossier `_logiciel` remplacés dans SharePoint (1 Mo max par fichier), comme les versions précédentes; tests exclus du zip.
- Commits sur `claude/optimistic-ptolemy-gwiqj9`, se terminant par les lignes `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` et `Claude-Session: https://claude.ai/code/session_01MzA9xY4GK9uWppKdPadfme`.

## Review Focus

1. Journée dont aucune entrée n'a de position GPS (ou sans tâche) : elle ne doit pas être payée « 0 km » en silence; jour marqué `a_verifier` avec la raison, km domicile→domicile non inventé. → test `test_journee_sans_position_a_verifier` (Task 2).
2. Clé Google absente, refusée (403) ou panne au milieu du calcul : message clair, aucune période partielle enregistrée comme base, mais le cache des distances déjà obtenues est conservé. → tests `test_erreur_google_pas_de_base_partielle` (Task 6) et `test_cle_refusee` (Task 3).
3. Entrée à 23 h 30 un samedi (décalage -05) : appartient au samedi, donc à la période qui finit ce samedi. → test `test_jour_selon_horodatage_local` (Task 2).
4. Hugo change un code postal ou le taux après avoir validé une période : la période validée garde ses chiffres. → test `test_periode_validee_figee` (Task 6).
5. Km déclaré écrit avec virgule ou espace (« 12,5 km », « 1 200 km », « 25 KM ») : lu directement sans l'IA. → test `test_lire_km_simple` (Task 2).

---

### Task 0: Coût chargé à partir du taux de base (outil de révision existant)

**Files:**
- Modify: `revision-bons/_logiciel/regles.toml` (section `[couts]`), `revision-bons/_logiciel/regles.py`, `revision-bons/_logiciel/facturation.py` (`cout_horaire`), `revision-bons/_logiciel/interface.py` (`CHAMPS_REGLES`, `BORNES`), `revision-bons/_logiciel/interface.html` (carte « Coût horaire des techniciens »)
- Test: `revision-bons/tests/test_facturation.py`, `revision-bons/tests/test_interface.py`

**Interfaces:**
- Produces:
  - `regles.toml` `[couts]` : `defaut = 0.0`, `das = 0.12`, `vacances = 0.04`, `feries = 0.042` (+ `[couts.techniciens]` = **taux de base**).
  - `Regles.charges_das: float = 0.12`, `Regles.charges_vacances: float = 0.04`, `Regles.charges_feries: float = 0.042`; `Regles.facteur_charges -> float` (propriété) = `1 + das + vacances + feries`.
  - `facturation.cout_horaire(e, r)` : coût de Progression si présent (déjà chargé), sinon `(taux de base du technicien ou défaut) × r.facteur_charges`, sinon `None`.
  - `CHAMPS_REGLES` gagne `charges_das` / `charges_vacances` / `charges_feries` (section `couts`, clés `das` / `vacances` / `feries`, bornes 0–0,5).
  - Page : la carte devient « Coût horaire des techniciens (taux de base) »; champs « DAS (ex. 0,12) », « Vacances (ex. 0,04; 0,06 après 3 ans) », « Fériés (ex. 0,042 = 11 jours ÷ 260) »; colonne « Taux de base ($/h) » et colonne calculée « Coût chargé »; l'aide « Quoi inclure » est réduite à : taux de base de la liste de paie; DAS, vacances et fériés ajoutés automatiquement; le kilométrage est payé à part; les frais fixes ne sont pas comptés.

- [ ] **Step 1: Write the failing tests**

```python
def test_cout_charge_depuis_taux_de_base():
    b = bon()
    for e in b.entrees:
        e.cout_horaire = None
    r = replace(R, couts_techniciens={"Luc Tremblay": 30.0})
    assert round(r.facteur_charges, 3) == 1.202
    lignes, _, _ = ajuster_heures_transport(b, r)
    # (80 + 80 + 45) min × 30 $ × 1,202 = 123,21 $
    assert abs(estimer_marge(b, lignes, [], r)["cout"] - 123.21) <= 0.01
```
Dans `test_interface.py::test_couts_horaires_des_techniciens`, ajouter : POST `charges_feries: "0,042"` → GET renvoie `0.042`; `charges_das: "0,9"` → 400. Adapter `test_marge_taux_inscrit_dans_les_regles` et `test_marge_taux_par_defaut` (le coût attendu est maintenant multiplié par 1,202 : 123,21).

- [ ] **Step 2: Run** `cd revision-bons && ../.venv/bin/python -m pytest tests -q` → FAIL sur ces tests.
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run** → PASS; vérification Playwright de la carte en démo (champs et colonne « Coût chargé » mise à jour à la saisie).
- [ ] **Step 5: Commit** — `git commit -m "Révision des bons : coût chargé calculé depuis le taux de base (DAS, vacances, fériés)"`

---

### Task 1: Réglages du kilométrage (règles partagées et profil)

**Files:**
- Modify: `revision-bons/_logiciel/regles.toml` (ajouter la section)
- Modify: `revision-bons/_logiciel/regles.py`
- Modify: `revision-bons/_logiciel/cles.py`
- Create: `revision-bons/_logiciel/profil.py`
- Test: `revision-bons/tests/test_profil.py`, `revision-bons/tests/test_regles.py`

**Interfaces:**
- Produces:
  - `regles.toml` : section
    ```toml
    [kilometrage]
    taux = 0.61                      # $ par km
    seuil_ecart_km = 10.0            # écart déclaré / payé signalé au-delà, par technicien et par période
    debut_reference = "2026-11-08"   # un dimanche : début d'une période de paie de deux semaines
    ```
  - `Regles.km_taux: float = 0.61`, `Regles.km_seuil_ecart: float = 10.0`, `Regles.km_debut_reference: date = date(2026, 11, 8)` (lus par `charger_regles`, valeurs par défaut si la section manque).
  - `cles.NOMS = ("progression", "claude", "google")`; `cles.ecrire(progression, claude, google=None)`; `cles.etat()` renvoie aussi `google`.
  - `profil.dossier() -> Path` (même dossier que `cles.fichier().parent`).
  - `profil.normaliser_code_postal(texte: str) -> str | None` : `"j4w3j9"` → `"J4W 3J9"`; `"J4W"` → `None`; `""` → `None`.
  - `profil.lire_techniciens() -> dict[str, dict]` : `{nom: {"code_postal": str, "paye_km": bool}}` depuis `techniciens.json` du profil (`{}` si absent ou illisible).
  - `profil.ecrire_techniciens(techniciens: dict[str, dict]) -> dict[str, dict]` : valide (nom non vide ≤ 80 car., code postal normalisé ou vide), écrit, renvoie ce qui a été écrit; lève `ValueError("Code postal invalide pour <nom> : <texte>")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_profil.py
import profil, cles

def test_normaliser_code_postal():
    assert profil.normaliser_code_postal("j4w3j9") == "J4W 3J9"
    assert profil.normaliser_code_postal(" J4W 3J9 ") == "J4W 3J9"
    assert profil.normaliser_code_postal("J4W") is None
    assert profil.normaliser_code_postal("") is None

def test_techniciens_aller_retour(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    ecrit = profil.ecrire_techniciens({"Vadim Zubco": {"code_postal": "h1a1a1", "paye_km": True},
                                       "Hugo": {"code_postal": "", "paye_km": False}})
    assert ecrit["Vadim Zubco"] == {"code_postal": "H1A 1A1", "paye_km": True}
    assert profil.lire_techniciens() == ecrit
    assert (tmp_path / "ProgimRevisionBons" / "techniciens.json").exists()

def test_code_postal_invalide_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    import pytest
    with pytest.raises(ValueError, match="Vadim"):
        profil.ecrire_techniciens({"Vadim": {"code_postal": "J4W", "paye_km": True}})

def test_cle_google(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cles.ecrire(None, None, google="AIza-test")
    assert cles.lire()["google"] == "AIza-test" and cles.etat()["google"] is True
```

```python
# tests/test_regles.py (ajout)
def test_regles_kilometrage():
    r = charger_regles(LOGICIEL / "regles.toml")
    assert (r.km_taux, r.km_seuil_ecart, r.km_debut_reference) == (0.61, 10.0, date(2026, 11, 8))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd revision-bons && ../.venv/bin/python -m pytest tests/test_profil.py tests/test_regles.py -q`
Expected: FAIL (`ModuleNotFoundError: profil`, `AttributeError: km_taux`).

- [ ] **Step 3: Implement** the section, the three `Regles` fields, `cles` changes and `profil.py` as specified in Interfaces. `profil.dossier()` reuses the `APPDATA` / `~/.config` logic of `cles.fichier()`.

- [ ] **Step 4: Run the whole suite**

Run: `cd revision-bons && ../.venv/bin/python -m pytest tests -q`
Expected: all pass. Update `tests/test_interface.py::test_page_et_etat_sans_cles` to expect `{"progression", "claude", "google"}`.

- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : réglages (taux, seuil, période) et profil des techniciens"`

---

### Task 2: Calcul pur (périodes, journées, km d'une journée, km déclaré simple, totaux)

**Files:**
- Create: `revision-bons/_logiciel/km_calcul.py`
- Test: `revision-bons/tests/test_km_calcul.py`

**Interfaces:**
- Produces (toutes pures, sans réseau) :
  - `periode_contenant(jour: date, reference: date) -> tuple[date, date]` : début = `reference + 14*k` ≤ jour; fin = début + 13 jours.
  - `periodes_proposees(aujourdhui: date, reference: date, nombre: int = 4) -> list[tuple[date, date]]` : la période courante puis les précédentes.
  - `@dataclass Arret: tache_id: int; code: str; lat: float | None; lng: float | None`
  - `@dataclass Journee: technicien: str; jour: date; arrets: list[Arret]; a_verifier: list[str]; minutes: float` (somme des durées de toutes les entrées du jour, `En route` et `En cours`, via `progression.minutes_iso(duration)`).
  - `journees(entrees: list[dict], taches: dict[int, dict], debut: date, fin: date) -> list[Journee]` : `entrees` au format de `/timeEntry/list` (`humanResource.label`, `start`, `task.id`, `task.code`); `taches[id]` = tâche brute (`clientAddress.position.latitude/longitude`, sinon `locationAddress.position`). Jour = `date.fromisoformat(start[:10])`; entrées hors [debut, fin] ignorées; triées par `start`; arrêts consécutifs à la même tâche-position fusionnés (même lat/lng arrondis à 5 décimales); une entrée sans tâche ou sans position n'est pas un arrêt et ajoute à `a_verifier` : `"<code ou 'entrée sans bon'> : immeuble sans position GPS"`.
  - `km_journee(domicile: tuple[float, float] | None, arrets: list[Arret], distance: Callable[[tuple, tuple], float]) -> tuple[float, list[dict]]` : tronçons `{"de": str, "a": str, "km": float}` pour domicile → arrêts → domicile (libellés `"domicile"` et `code`); seulement les arrêts avec position; `domicile=None` → pas de tronçon domicile; aucun arrêt avec position → `(0.0, [])`. Total arrondi à 0,1 km.
  - `lire_km_simple(texte: str) -> float | None` : accepte un seul nombre avec unité facultative (« 60km », « 25 KM », « 49 », « 12,5 km », « 1 200 km ») ; tout autre texte → `None`; vide → `None`.
  - `totaliser(base: dict, ajustements: dict, taux: float, seuil: float, techniciens: dict[str, dict]) -> dict` : voir le format ci-dessous. `ajustements` : `{"<technicien>|<AAAA-MM-JJ>": {"uhaul": bool, "magasin_km": float}}`.

Format de la base (produite par la Task 6, consommée ici) :
```python
base = {"debut": "2026-11-08", "fin": "2026-11-21",
        "techniciens": {"Vadim Zubco": {
            "jours": [{"jour": "2026-11-10", "arrets": [{"code": "AS003195", "tache_id": 1}], "troncons": [...],
                       "km": 132.0, "a_verifier": [], "domicile": True, "minutes": 512.0}],
            "bons": [{"code": "AS003195", "texte": "60km", "km": 60.0, "statut": "ok" | "a_verifier" | "vide" | "partage", "part": 1.0}]}}}
```
Format renvoyé par `totaliser` (envoyé tel quel à la page et à l'export) :
```python
{"debut", "fin", "taux", "seuil_km",
 "techniciens": [{"nom", "jours": int, "km_calcule", "km_magasin", "km_a_payer", "montant": float | None,
                  "km_declare", "ecart": float | None, "statut": "ok" | "ecart" | "non_declare" | "a_configurer" | "sous_traitant",
                  "paie": bool, "minutes_par_jour": {"AAAA-MM-JJ": float}, "minutes_total": float,
                  "details": [<jour de la base> + {"uhaul": bool, "magasin_km": float, "km_paye": float}], "bons": [...]}],
 "total_km", "total_montant"}
```
Règles de `totaliser` : km payé d'un jour = 0 si Uhaul, sinon `km + magasin_km`; `km_declare` = somme `km × part` des bons au statut `ok`; `ecart = km_declare - km_a_payer` (arrondi 0,1); statut `sous_traitant` si le technicien est configuré avec `paye_km` faux (km à payer 0, montant `None`, écart `None`, `paie` faux); `a_configurer` s'il est absent de `techniciens` ou coché sans code postal (montant `None`, écart `None`, `paie` faux); `paie` vrai seulement pour les admissibles; sinon `non_declare` si aucun bon `ok`; sinon `ecart` si `abs(ecart) > seuil`; sinon `ok`. Montant = `round(km_a_payer × taux, 2)`. Techniciens triés par nom.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
from km_calcul import (Arret, journees, km_journee, lire_km_simple, periode_contenant, periodes_proposees, totaliser)

REF = date(2026, 11, 8)

def test_periode_contenant():
    assert periode_contenant(date(2026, 11, 8), REF) == (date(2026, 11, 8), date(2026, 11, 21))
    assert periode_contenant(date(2026, 11, 21), REF) == (date(2026, 11, 8), date(2026, 11, 21))
    assert periode_contenant(date(2026, 11, 22), REF) == (date(2026, 11, 22), date(2026, 12, 5))
    assert periode_contenant(date(2026, 11, 7), REF) == (date(2026, 10, 25), date(2026, 11, 7))
    assert periodes_proposees(date(2026, 11, 16), REF, 2) == [(date(2026, 11, 8), date(2026, 11, 21)),
                                                              (date(2026, 10, 25), date(2026, 11, 7))]

def _e(tech, start, tache_id, code):
    return {"humanResource": {"label": tech}, "start": start, "task": {"id": tache_id, "code": code}, "duration": "PT30M"}

def _t(lat, lng):
    return {"clientAddress": {"position": {"latitude": lat, "longitude": lng}}}

def test_journees_ordre_et_fusion():
    entrees = [_e("V", "2026-11-10T13:00:00-05", 2, "B"), _e("V", "2026-11-10T08:00:00-05", 1, "A"),
               _e("V", "2026-11-10T09:00:00-05", 1, "A"), _e("V", "2026-11-10T15:00:00-05", 1, "A")]
    [j] = journees(entrees, {1: _t(45.5, -73.5), 2: _t(45.6, -73.6)}, date(2026, 11, 8), date(2026, 11, 21))
    assert [a.code for a in j.arrets] == ["A", "B", "A"] and j.a_verifier == []
    assert j.minutes == 4 * 30.0          # chaque entrée _e dure PT30M

def test_jour_selon_horodatage_local():
    entrees = [_e("V", "2026-11-21T23:30:00-05", 1, "A"), _e("V", "2026-11-22T07:00:00-05", 1, "A")]
    jours = journees(entrees, {1: _t(45.5, -73.5)}, date(2026, 11, 8), date(2026, 11, 21))
    assert [j.jour for j in jours] == [date(2026, 11, 21)]

def test_journee_sans_position_a_verifier():
    [j] = journees([_e("V", "2026-11-10T08:00:00-05", 3, "C")], {3: {}}, date(2026, 11, 8), date(2026, 11, 21))
    assert j.arrets == [] and "C" in j.a_verifier[0]
    assert km_journee((45.4, -73.4), j.arrets, lambda a, b: 99.0) == (0.0, [])

def test_km_journee_domicile_aller_retour():
    arrets = [Arret(1, "A", 45.5, -73.5), Arret(2, "B", 45.6, -73.6)]
    km, troncons = km_journee((45.4, -73.4), arrets, lambda a, b: 10.0)
    assert km == 30.0 and [(t["de"], t["a"]) for t in troncons] == [("domicile", "A"), ("A", "B"), ("B", "domicile")]
    assert km_journee(None, arrets, lambda a, b: 10.0)[0] == 10.0

def test_lire_km_simple():
    assert [lire_km_simple(t) for t in ("60km", "25 KM", "49", "12,5 km", "1 200 km", "", "52 pour les deux jours",
                                         "+14km achat + 6km")] == [60, 25, 49, 12.5, 1200, None, None, None]

def _base():
    return {"debut": "2026-11-08", "fin": "2026-11-21", "techniciens": {
        "Vadim": {"jours": [{"jour": "2026-11-10", "arrets": [], "troncons": [], "km": 100.0, "a_verifier": [], "domicile": True, "minutes": 300.0},
                            {"jour": "2026-11-11", "arrets": [], "troncons": [], "km": 50.0, "a_verifier": [], "domicile": True, "minutes": 240.0}],
                  "bons": [{"code": "A", "texte": "200", "km": 200.0, "statut": "ok", "part": 1.0}]},
        "Hugo": {"jours": [{"jour": "2026-11-10", "arrets": [], "troncons": [], "km": 20.0, "a_verifier": [], "domicile": False, "minutes": 60.0}],
                 "bons": []}}}

def test_totaliser_ecart_uhaul_magasin_et_admissibilite():
    techs = {"Vadim": {"code_postal": "H1A 1A1", "paye_km": True}}
    p = totaliser(_base(), {"Vadim|2026-11-11": {"uhaul": True, "magasin_km": 0}, "Vadim|2026-11-10": {"uhaul": False, "magasin_km": 12}},
                  0.61, 10.0, techs)
    v = next(t for t in p["techniciens"] if t["nom"] == "Vadim")
    assert (v["km_calcule"], v["km_magasin"], v["km_a_payer"], v["montant"]) == (150.0, 12.0, 112.0, 68.32)
    assert (v["km_declare"], v["ecart"], v["statut"]) == (200.0, 88.0, "ecart")
    h = next(t for t in p["techniciens"] if t["nom"] == "Hugo")
    assert (h["statut"], h["montant"], h["paie"]) == ("a_configurer", None, False)
    p2 = totaliser(_base(), {}, 0.61, 10.0, {**techs, "Hugo": {"code_postal": "", "paye_km": False}})
    assert next(t for t in p2["techniciens"] if t["nom"] == "Hugo")["statut"] == "sous_traitant"
    assert v["minutes_par_jour"] == {"2026-11-10": 300.0, "2026-11-11": 240.0} and v["minutes_total"] == 540.0
    assert p["total_montant"] == 68.32

def test_totaliser_seuil_et_non_declare():
    techs = {"Vadim": {"code_postal": "H1A 1A1", "paye_km": True}}
    base = _base(); base["techniciens"]["Vadim"]["bons"][0]["km"] = 155.0
    assert next(t for t in totaliser(base, {}, 0.61, 10.0, techs)["techniciens"] if t["nom"] == "Vadim")["statut"] == "ok"
    base["techniciens"]["Vadim"]["bons"][0]["statut"] = "vide"
    assert next(t for t in totaliser(base, {}, 0.61, 10.0, techs)["techniciens"] if t["nom"] == "Vadim")["statut"] == "non_declare"
```

- [ ] **Step 2: Run to verify they fail** — `../.venv/bin/python -m pytest tests/test_km_calcul.py -q` → FAIL (module absent).
- [ ] **Step 3: Implement `km_calcul.py`** per Interfaces (dataclasses, regex for `lire_km_simple`: `^\s*(\d{1,3}(?:[  ]\d{3})*|\d+)(?:[.,](\d+))?\s*(?:km)?\s*$`, insensible à la casse; écrire le caractère insécable avec `chr(0xA0)` dans le code, pas avec une séquence d'échappement — voir Global Constraints sur le déploiement).
- [ ] **Step 4: Run** — `../.venv/bin/python -m pytest tests/test_km_calcul.py -q` → PASS.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : calcul pur (périodes, journées, km, totaux)"`

---

### Task 3: Service de cartes Google (géocodage, distances, cache) et cartes fictives

**Files:**
- Create: `revision-bons/_logiciel/cartes.py`
- Modify: `revision-bons/_logiciel/demo/faux_services.py` (ajouter `FaussesCartes`)
- Test: `revision-bons/tests/test_cartes.py`

**Interfaces:**
- Produces:
  - `class ErreurCartes(Exception)` (message lisible en français).
  - `class Cartes(cle: str, fichier_cache: Path, ouvrir=urllib.request.urlopen, dormir=time.sleep)` :
    - `geocoder(code_postal: str) -> tuple[float, float] | None` : `GET https://maps.googleapis.com/maps/api/geocode/json?address=<code>&components=country:CA&key=<cle>`; `status == "OK"` → `results[0].geometry.location` (`lat`, `lng`); `"ZERO_RESULTS"` → `None`; autre statut → `ErreurCartes(f"Google Maps : {error_message or status}")`.
    - `distance_km(a: tuple[float, float], b: tuple[float, float]) -> float` : même point (5 décimales) → `0.0` sans appel; sinon `POST https://routes.googleapis.com/directions/v2:computeRoutes`, entêtes `X-Goog-Api-Key: <cle>`, `X-Goog-FieldMask: routes.distanceMeters`, `Content-Type: application/json`, corps `{"origin": {"location": {"latLng": {"latitude":…, "longitude":…}}}, "destination": {…}, "travelMode": "DRIVE", "routingPreference": "TRAFFIC_UNAWARE"}`; résultat `routes[0].distanceMeters / 1000` arrondi à 0,1; aucune route → `ErreurCartes("Aucun trajet routier trouvé …")`.
    - HTTP 429 : jusqu'à 5 essais, attente `dormir(2 ** essai)`; HTTP 400/403 → `ErreurCartes("Clé Google refusée ou API non activée : vérifier la clé dans l'onglet Règles.")`.
    - Cache JSON `{"geo": {code: [lat, lng] | null}, "dist": {"lat,lng>lat,lng": km}}` relu à la création, réécrit après chaque nouvelle valeur (une valeur obtenue avant une panne reste en cache).
  - `demo.faux_services.FaussesCartes()` : même interface; `geocoder` renvoie une position fixe dérivée du code (ex. `(45.45 + n/100, -73.45 - n/100)` avec `n` = somme des chiffres); `distance_km` = distance à vol d'oiseau (haversine) × 1,3, arrondie à 0,1.

- [ ] **Step 1: Write the failing tests** (faux `ouvrir` qui enregistre les requêtes et renvoie des réponses JSON préparées; utiliser `urllib.error.HTTPError` pour 429/403)

```python
def test_geocoder_et_cache(tmp_path): ...   # 1er appel interroge Google, 2e appel (nouvelle instance, même cache) n'interroge plus
    # assert pos == (45.47, -73.46) and len(requetes) == 1
def test_distance_routes_api(tmp_path): ...  # vérifie URL computeRoutes, entêtes X-Goog-Api-Key et X-Goog-FieldMask, corps DRIVE
    # réponse {"routes": [{"distanceMeters": 12345}]} -> 12.3 ; même point -> 0.0 sans requête
def test_429_reessaie(tmp_path): ...        # 429 puis 200 -> valeur, dormir appelé une fois
def test_cle_refusee(tmp_path): ...         # 403 -> ErreurCartes dont le message contient "Clé Google"
def test_zero_results(tmp_path): ...        # {"status": "ZERO_RESULTS", "results": []} -> None
def test_fausses_cartes():                  # distance_km(a, a) == 0.0 ; distance > 0 et symétrique
```
Écrire les corps complets de ces tests avec les valeurs ci-dessus.

- [ ] **Step 2: Run to verify they fail** — `../.venv/bin/python -m pytest tests/test_cartes.py -q` → FAIL.
- [ ] **Step 3: Implement `cartes.py` and `FaussesCartes`.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : service Google Maps (géocodage, distances routières, cache)"`

---

### Task 4: Km déclaré (lecture par l'IA des textes ambigus, bons partagés, prorata)

**Files:**
- Create: `revision-bons/_logiciel/km_declare.py`
- Modify: `revision-bons/_logiciel/demo/faux_services.py` (`FauxClaude` répond au schéma du km)
- Test: `revision-bons/tests/test_km_declare.py`

**Interfaces:**
- Consumes: `km_calcul.lire_km_simple`, `claude_client.demander_json(client, cfg, contenu, schema, systeme)`.
- Produces:
  - `SCHEMA_KM = {"type": "object", "properties": {"km": {"type": ["number", "null"]}, "confiance": {"type": "string", "enum": ["haute", "basse"]}}, "required": ["km", "confiance"], "additionalProperties": False}`
  - `interpreter_km(texte: str, client, cfg_claude: dict, cache: dict) -> tuple[float | None, str]` : statut `"vide"` (texte vide), `"ok"` (lecture simple, ou IA avec confiance haute et km non nul), `"a_verifier"` (IA confiance basse, km nul ou réponse `None`). `cache` (dict texte → [km, statut]) évite de redemander le même texte. Message système : le texte est le kilométrage inscrit par un technicien sur un bon; renvoyer le total en km pour ce bon, `null` si aucun total ne peut être déduit, `confiance` basse au moindre doute.
  - `bons_du_technicien(technicien: str, entrees_par_tache: dict[int, list[dict]], taches: dict[int, dict], debut: date, fin: date, client, cfg_claude: dict, cache: dict) -> list[dict]` : un élément par tâche où le technicien a au moins une entrée dans la période : `{"code", "tache_id", "texte", "km", "statut", "part"}`. `entrees_par_tache[id]` = toutes les entrées de la tâche (`/task/{id}/timeEntries`). Si la tâche a des entrées de plus d'un technicien → statut `"partage"`, `km` lu quand même pour affichage, exclu du total par `totaliser`. `part` = jours du technicien sur la tâche dans la période ÷ tous ses jours sur la tâche (1.0 si tout est dans la période).

- [ ] **Step 1: Write the failing tests**

```python
def test_texte_simple_sans_ia(): ...        # "60km" -> (60.0, "ok"), client jamais appelé
def test_texte_ambigu_par_ia(): ...         # faux client renvoie {"km": 52, "confiance": "haute"} -> (52.0, "ok"); 2e appel même texte: client pas rappelé
def test_ia_peu_sure(): ...                 # {"km": 20, "confiance": "basse"} -> (20.0, "a_verifier")
def test_bon_partage_et_prorata(): ...      # tâche avec V et F -> statut "partage" ; tâche de V sur 3 jours dont 2 dans la période -> part == round(2/3, 4)
def test_texte_vide(): ...                  # "" -> (None, "vide")
```
Le faux client imite `client.beta.messages.create(**kw)` et renvoie un objet `stop_reason="end_turn"`, `content=[SimpleNamespace(type="text", text=json.dumps(...))]`, comme `IASimulee` dans les essais existants.

- [ ] **Step 2: Run to verify they fail** → FAIL.
- [ ] **Step 3: Implement `km_declare.py`; étendre `FauxClaude._create` : si le dernier texte contient « Kilométrage inscrit », renvoyer `{"km": 52, "confiance": "haute"}`.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : lecture du km déclaré (IA pour les cas ambigus, bons partagés, prorata)"`

---

### Task 5: Entrées de temps d'une période dans Progression (réel et démo)

**Files:**
- Modify: `revision-bons/_logiciel/progression.py`
- Modify: `revision-bons/_logiciel/demo/faux_services.py`
- Test: `revision-bons/tests/test_progression.py`

**Interfaces:**
- Produces:
  - `Progression.entrees_periode(debut: date, fin: date) -> list[dict]` : `GET /timeEntry/list` avec `start=<debut-1 jour>T00:00:00-05,<fin+1 jour>T23:59:59-05`, `maxResults=500`, pagination par `startResult` jusqu'à une page de moins de 500. (La marge d'un jour compense l'absence de fuseau; `km_calcul.journees` refiltre par date locale.)
  - `FausseProgression.entrees_periode(debut, fin) -> list[dict]` : toutes les entrées du jeu de démo au format `/timeEntry/list` (`humanResource`, `start`, `activity`, `task: {"id", "code"}`).
  - Les tâches de démo reçoivent `clientAddress.position` (une position par immeuble de `IMMEUBLES`) et `properties["info.km"]` (au moins un texte simple, un texte ambigu « 30 pour les deux jours », un vide).
  - `FausseProgression.lire_tache(identifiant) -> tuple[dict, list[dict]]` (même forme que la vraie méthode).

- [ ] **Step 1: Write the failing tests**

```python
def test_entrees_periode_pagine_et_marge(): ...
    # faux ouvrir : 1re page 500 entrées, 2e page 3 -> 503 entrées ; vérifier start=2026-11-07T00:00:00-05,2026-11-22T23:59:59-05
    # et startResult=0 puis 500 dans les URL
def test_fausse_progression_entrees_periode():
    # toutes les entrées ont task.id et humanResource.label ; les tâches ont clientAddress.position
```

- [ ] **Step 2: Run to verify they fail** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run whole suite** — `../.venv/bin/python -m pytest tests -q` → PASS (les tests de la révision des bons ne doivent pas changer).
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : entrées de temps d'une période (Progression et démo)"`

---

### Task 6: Orchestration d'une période (base, ajustements, validation, réouverture)

**Files:**
- Create: `revision-bons/_logiciel/kilometrage.py`
- Test: `revision-bons/tests/test_kilometrage.py`

**Interfaces:**
- Consumes: Tasks 1 à 5 (`profil.lire_techniciens`, `km_calcul.*`, `Cartes`/`FaussesCartes`, `km_declare.bons_du_technicien`, `Progression.entrees_periode`, `tache_brute`, `lire_tache`), `Journal`.
- Produces:
  - `class Kilometrage(progression, cartes, client_ia, cfg_claude: dict, dossier: Path, journal: Journal)`; fichier par période : `dossier / f"{debut}.json"` = `{"base": dict | None, "ajustements": dict, "statut": "brouillon" | "valide", "revision": int, "valide_par": str, "valide_le": str, "instantane": dict | None}`.
  - `calculer(debut: date, fin: date, techniciens: dict, progres: Callable[[str], None] = lambda m: None) -> None` : si la période est validée, ne fait rien; sinon lit les entrées, chaque tâche une fois (`lire_tache`), géocode les codes postaux des techniciens admissibles, calcule `km_journee` par jour (`domicile` = position du code postal, `None` si absent → jour `"domicile": False`), le km déclaré, et enregistre la base. Une `ErreurCartes`, `ErreurProgression` ou erreur de l'IA remonte sans écrire de base (le fichier existant reste intact).
  - `periode(debut: date, techniciens: dict, regles: Regles) -> dict | None` : période validée → `instantane` (avec `"statut": "valide"`, `"revision"`, `"valide_par"`, `"valide_le"`); sinon `km_calcul.totaliser(base, ajustements, regles.km_taux, regles.km_seuil_ecart, techniciens)` + `"statut": "brouillon"`; `None` si aucune base.
  - `ajuster(debut: date, technicien: str, jour: str, uhaul: bool, magasin_km: float, personne: str) -> None` : refusé (`ValueError("Période validée : la rouvrir avant de modifier.")`) si validée; `magasin_km` entre 0 et 500; journal `evenement="km_ajustement"`, détails `{"periode", "technicien", "jour", "avant", "apres"}`.
  - `valider(debut, techniciens, regles, personne) -> dict` : fige `instantane` = `periode(...)` brouillon, `statut="valide"`, journal `km_validation` (`{"periode", "total_km", "total_montant", "revision"}`).
  - `rouvrir(debut, raison: str, personne) -> None` : raison obligatoire (≥ 5 caractères, sinon `ValueError`); `statut="brouillon"`, `revision += 1`, `instantane=None`; journal `km_reouverture` (`{"periode", "raison", "revision"}`).

- [ ] **Step 1: Write the failing tests** (avec `FausseProgression`, `FaussesCartes`, `FauxClaude`, `tmp_path`)

```python
def test_calcul_periode_demo(tmp_path): ...       # base créée; un technicien admissible a km_a_payer > 0 et montant == round(km*0.61, 2)
def test_ajuster_sans_rappeler_google(tmp_path): ...  # cartes espionnes : aucun appel distance_km pendant ajuster + periode; journal contient km_ajustement
def test_periode_validee_figee(tmp_path): ...     # valider, puis changer taux (Regles) et code postal -> periode() identique; ajuster -> ValueError
def test_rouvrir_exige_raison(tmp_path): ...      # rouvrir("") -> ValueError ; rouvrir("erreur de Hugo") -> brouillon, revision 1, journal km_reouverture
def test_erreur_google_pas_de_base_partielle(tmp_path): ...  # cartes qui lèvent ErreurCartes au 3e appel -> exception, fichier période absent
def test_technicien_sans_code_postal_a_configurer(tmp_path): ...  # statut "a_configurer", montant None, aucun géocodage tenté pour lui
```

- [ ] **Step 2: Run to verify they fail** → FAIL.
- [ ] **Step 3: Implement `kilometrage.py`.** Écriture du fichier de période : écrire dans `<fichier>.tmp` puis `os.replace` (atomique, même dossier).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : orchestration d'une période (base, ajustements, validation)"`

---

### Task 7: Export Excel pour Sabrina (sans dépendance)

**Files:**
- Create: `revision-bons/_logiciel/excel.py`
- Test: `revision-bons/tests/test_excel.py`

**Interfaces:**
- Consumes: le dict renvoyé par `Kilometrage.periode` (format `totaliser`).
- Produces:
  - `ecrire_xlsx(feuilles: dict[str, list[list]]) -> bytes` : classeur `.xlsx` minimal écrit avec `zipfile` (`[Content_Types].xml`, `_rels/.rels`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/styles.xml`, `xl/worksheets/sheetN.xml`); nombres en cellules numériques, textes en chaînes en ligne (`t="inlineStr"`), caractères XML échappés; noms de feuilles ≤ 31 caractères.
  - `export_periode(periode: dict) -> tuple[bytes, str]` : nom `f"Feuille de temps et km {debut} au {fin}{' (revise ' + str(revision) + ')' if revision else ''}.xlsx"`. Reprend la feuille de temps hebdomadaire que Hugo envoie à Sabrina : une feuille par semaine nommée `f"Semaine du {dimanche}"`, première ligne `f"Semaine du {dimanche} - {samedi}"` + statut / validé par / le; en-tête `["Ressource humaine", "Dim.", "Lun.", "Mar.", "Mer.", "Jeu.", "Ven.", "Sam.", "Total", "Km à payer", "Montant km ($)"]`; une ligne par technicien dont `paie` est vrai (sous-traitants et « à configurer » exclus), heures au format texte `H:MM` (ex. 405 min → `"6:45"`, 0 → `"0:00"`), km de la semaine = somme des `km_paye` de ses jours, montant = km × taux arrondi au cent; ligne « Total » (heures par jour, km, montant). Feuille « Détail » : `["Technicien", "Jour", "Trajet", "Km calculé", "Uhaul", "Km magasin", "Km payé", "À vérifier"]`, trajet = codes reliés par « → ».
  - `h_mm(minutes: float) -> str` : arrondi à la minute; `404.6` → `"6:45"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_xlsx_valide():
    contenu = ecrire_xlsx({"Sommaire": [["Nom", "Km"], ["Vadim & fils <test>", 112.5]]})
    z = zipfile.ZipFile(io.BytesIO(contenu))
    assert "xl/worksheets/sheet1.xml" in z.namelist() and "[Content_Types].xml" in z.namelist()
    feuille = z.read("xl/worksheets/sheet1.xml").decode()
    assert "Vadim &amp; fils &lt;test&gt;" in feuille and "<v>112.5</v>" in feuille
    ET.fromstring(feuille); ET.fromstring(z.read("xl/workbook.xml"))   # XML bien formé

def test_export_feuille_de_temps():
    # periode validée revision 1 (format totaliser, 2 techniciens : "Vadim" paie=True, "Toufik" sous_traitant)
    # -> nom "Feuille de temps et km 2026-11-08 au 2026-11-21 (revise 1).xlsx"
    # -> 3 feuilles : "Semaine du 2026-11-08", "Semaine du 2026-11-15", "Détail"
    # -> feuille 1 : en-tête exact ci-dessus ; ligne Vadim : Mar. "5:00", Mer. "4:00", Total "9:00", km 112, montant 68.32
    # -> "Toufik" absent des feuilles de semaine ; ligne "Total" présente
def test_h_mm():
    assert [h_mm(m) for m in (0, 59.6, 405, 404.6, 600)] == ["0:00", "1:00", "6:45", "6:45", "10:00"]
```

- [ ] **Step 2: Run to verify they fail** → FAIL.
- [ ] **Step 3: Implement `excel.py`.**
- [ ] **Step 4: Run** → PASS. Vérification manuelle : ouvrir un fichier produit avec LibreOffice (`soffice --headless --convert-to pdf`) et regarder le rendu.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : export Excel de la période"`

---

### Task 8: Routes de l'interface (serveur local)

**Files:**
- Modify: `revision-bons/_logiciel/interface.py`
- Test: `revision-bons/tests/test_interface.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 6, 7; `ErreurDemande`, `_autorise`, jeton existants.
- Produces (méthodes de `Application`, toutes protégées par le jeton) :
  - `cartes()` : démo → `FaussesCartes()`; sinon `Cartes(cles.lire()["google"], profil.dossier() / "cache_cartes.json")`, ou `ErreurDemande("Clé Google manquante : l'inscrire dans l'onglet Règles, section Connexions.")`.
  - `km()` : instance unique de `Kilometrage` (dossier `self.donnees / "kilometrage"`).
  - Routes :
    - `GET /km/periodes` → `{"periodes": [{"debut", "fin", "libelle"}]}` (`periodes_proposees(date.today(), regles.km_debut_reference)`, libellé « du dim. 8 au sam. 21 novembre 2026 »).
    - `POST /km/calculer {"debut": "AAAA-MM-JJ"}` → lance le calcul dans un fil (même modèle que `analyser` : `self.km_progres = {"en_cours", "message"}`; refus si un calcul, une analyse ou un envoi est en cours) ; `debut` doit être un début de période valide sinon `ErreurDemande`.
    - `GET /km/progres` → `self.km_progres`.
    - `GET /km/periode?debut=…` → `Kilometrage.periode(...)` ou `{"periode": None}`.
    - `POST /km/ajuster {"debut", "technicien", "jour", "uhaul", "magasin_km"}` → période recalculée.
    - `POST /km/valider {"debut"}`, `POST /km/rouvrir {"debut", "raison"}` → période.
    - `GET /km/export?debut=…&jeton=…` → fichier `.xlsx` (`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `Content-Disposition: attachment; filename*=UTF-8''<nom encodé>`); refusé si la période n'est pas validée (`ErreurDemande("Valider la période avant d'exporter.")`).
    - `GET /km/reglages` → `{"taux", "seuil_km", "debut_reference", "techniciens": profil.lire_techniciens(), "techniciens_connus": [noms vus dans la dernière période calculée, absents de la liste]}`.
    - `POST /km/reglages {"taux", "seuil_km", "debut_reference", "techniciens"}` → valide (taux 0–5, seuil 0–1000, date de référence = un dimanche), écrit `taux`/`seuil_ecart_km`/`debut_reference` dans `regles.toml` (section `kilometrage`, avec le rédacteur `toml_texte` existant) et les techniciens dans le profil; `ValueError` de `profil` → `ErreurDemande`.
  - `enregistrer_cles(progression, claude, google=None)`; `POST /cles` accepte `google`.

- [ ] **Step 1: Write the failing tests** (fixture `site` existante, mode démo ; rediriger `APPDATA` vers `tmp_path` avec `monkeypatch` pour ne pas toucher au vrai profil)

```python
def test_km_reglages_aller_retour(site, ...): ...     # POST taux "0,61" seuil 15 + un technicien -> GET identique ; regles.toml contient [kilometrage]
def test_km_reglages_invalides(site, ...): ...        # debut_reference un lundi -> 400 ; code postal "J4W" -> 400
def test_km_calcul_et_periode(site, ...): ...         # régler un technicien démo admissible, /km/calculer, attendre, /km/periode -> techniciens non vides
def test_km_ajuster_valider_exporter(site, ...): ...  # ajuster -> km_magasin pris en compte ; export avant validation -> 400 ; valider -> export 200 avec Content-Type xlsx
def test_km_rouvrir(site, ...): ...                   # rouvrir sans raison -> 400 ; avec raison -> statut brouillon, revision 1
def test_km_sans_jeton_refuse(site): ...              # GET /km/periode sans X-Jeton -> 403
```

- [ ] **Step 2: Run to verify they fail** → FAIL.
- [ ] **Step 3: Implement.** Le téléchargement passe par `self.envoyer(200, contenu, type_)` étendu d'un paramètre facultatif `entetes: dict | None` pour `Content-Disposition`.
- [ ] **Step 4: Run whole suite** → PASS.
- [ ] **Step 5: Commit** — `git commit -m "Kilométrage : routes de l'interface"`

---

### Task 9: Onglet « Kilométrage », réglages dans Règles, vérification visuelle et déploiement

**Files:**
- Modify: `revision-bons/_logiciel/interface.html`
- Modify: `docs/superpowers/specs/2026-11-10-revision-bons-design.md` (une ligne : renvoi vers le design kilométrage)
- Test: `revision-bons/tests/test_interface.py::test_page_html` (le texte « Kilométrage » est présent) + vérification Playwright

**Interfaces:**
- Consumes: routes de la Task 8.

- [ ] **Step 1: Write the failing test** — dans `test_page_html`, ajouter `assert 'data-vue="kilometrage"' in page and "Seuil d'écart" in page`. Run → FAIL.
- [ ] **Step 2: Implement the tab** (structure et libellés fixés) :
  - Onglet `<button data-vue="kilometrage">Kilométrage</button>` entre « À réviser » et « Règles »; `montrer()` gère la vue `kilometrage`.
  - Barre : sélecteur de période (`/km/periodes`), bouton « Calculer », avancement (même composant que l'analyse), pastille de statut (Brouillon / Validée, révision n).
  - Tableau : colonnes `Technicien | Jours | Heures | Km calculé | Magasin | Km à payer | Montant | Km déclaré | Écart | Statut`; pastilles : `ok` « Conforme », `ecart` « Écart » (couleur `--bloque`), `non_declare` « Non déclaré », `a_configurer` « À configurer » (lien vers Règles), `sous_traitant` « Sous-traitant » (ligne grisée). Ligne Total.
  - Clic sur une ligne : détail jour par jour (trajet « domicile → AS003195 → AS003258 → domicile », km par tronçon au survol, km du jour, case « Uhaul (jour exclu) », champ « + km magasin », mentions « à vérifier »), puis la liste des bons avec le km déclaré, le statut (« partagé, non attribué », « à vérifier »), et la part au prorata.
  - Boutons « Valider la période » (confirmation), « Rouvrir » (demande la raison), « Exporter Excel » (lien `/km/export?debut=…&jeton=…`, actif seulement si validée).
  - Onglet Règles, nouvelle carte « Kilométrage » : taux ($/km), « Seuil d'écart (km par technicien et par période) » avec l'aide « Hugo peut l'augmenter pour éviter les alertes inutiles », date de début d'une période (un dimanche), tableau `Technicien | Code postal | Employé Progim (sur la paie, payé au km)` (techniciens connus ajoutés vides; case décochée = sous-traitant), bouton « Enregistrer ». Note : « Codes postaux gardés dans votre profil Windows, jamais dans le dossier partagé. »
  - Carte Connexions : champ « Clé API Google Maps » avec son état.
- [ ] **Step 3: Run** `../.venv/bin/python -m pytest tests -q` → PASS.
- [ ] **Step 4: Visual check** — lancer `interface.py --demo --sans-navigateur --sans-arret` dans une copie du dossier (APPDATA temporaire), avec Playwright : régler deux techniciens démo dans Règles, calculer la période du 2026-11-08 (le jeu de démo est en novembre 2026), ouvrir un détail, cocher Uhaul, ajouter 12 km magasin, valider, télécharger l'Excel; captures à 1280 px et 390 px de large; aucune erreur JS; pas de défilement horizontal de page à 390 px.
- [ ] **Step 5: Deploy** — comparer les tailles SharePoint aux versions du dernier commit (`read_resource` du dossier `_logiciel`) pour ne rien écraser de Hugo (surtout `regles.toml`); téléverser les fichiers nouveaux (`km_calcul.py`, `cartes.py`, `km_declare.py`, `kilometrage.py`, `excel.py`, `profil.py`) et remplacer les modifiés, avec `expectedBytes`; reconstruire `docs/Revision-des-bons.zip`.
- [ ] **Step 6: Commit and push** — `git commit -m "Kilométrage : onglet, réglages et déploiement"` puis `git push -u origin claude/optimistic-ptolemy-gwiqj9`.
