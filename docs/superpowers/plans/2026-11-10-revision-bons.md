# Révision des bons de service : plan de développement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Outil local qui récupère les bons de service Progression terminés, classe et lit les pièces jointes, propose les lignes de matériel (+10 %), arrondit les heures facturées au 15 min par technicien, réécrit la description, puis écrit les corrections approuvées par Hugo.

**Architecture :** Même modèle que `rapports-clients/` : Python portable lancé par un `.bat`, serveur `http.server` local, page `interface.html`. Modules à responsabilité unique : `modele.py` (données), `regles.py` (fonctions pures), `progression.py` (seul module réseau vers Progression), `pieces_jointes.py` et `redaction.py` (seuls modules qui appellent Claude), `analyse.py` (assemble une proposition), `journal.py` (historique), `envoi.py` (construit et écrit les mises à jour).

**Tech Stack :** Python 3.12 (Python portable Progim), bibliothèque standard (`http.server`, `urllib.request`, `tomllib`, `json`, `dataclasses`), SDK `anthropic` >= 2.8, `pytest` (poste de développement seulement).

**Spec :** `docs/superpowers/specs/2026-11-10-revision-bons-design.md`

## Global Constraints

- Tout le code, les messages et l'interface en français; noms de fonctions et variables en français, comme `rapports-clients`.
- Dossier `revision-bons/` : à la racine seulement `Révision des bons.bat` et `LISEZ-MOI.txt`; tout le reste dans `revision-bons/_logiciel/`.
- Arrondi : 15 minutes supérieur, par technicien, sur son temps total dans le bon. Les `TimeEntry` ne sont **jamais** modifiées (aucun appel à `/timeEntry/*/update`).
- Matériel : `unitCost` = prix unitaire avant taxes de la facture; `price` = `unitCost × 1,10` arrondi au cent.
- Progression : `Authorization: Bearer <clé>`, base `https://api.progressionlive.com/server/rest`; ne jamais envoyer de valeur `None`/`null`.
- Claude : modèle `claude-opus-5-5`, `output_config={"effort": "medium", "format": {...json_schema...}}`, client beta avec `betas=["server-side-fallback-2026-07-01"]` et `fallbacks="default"`; vérifier `stop_reason == "refusal"` avant de lire le contenu.
- Clés API dans `%APPDATA%\ProgimRevisionBons\cles.json` (profil Windows), jamais dans le dossier partagé ni dans le dépôt.
- Mode `simulation` par défaut; le mode `reel` reste refusé tant que `[progression] ecriture_validee = false` dans `config.toml` (voir Tâche 10).
- Pièces jointes, caches, journaux, `cles.json`, `python_portable.zip` exclus par `.gitignore`.

## Review Focus

1. **Bon modifié entre l'analyse et l'envoi** (un technicien ajoute une photo) : l'envoi doit refuser et remettre le bon `À vérifier`, jamais écrire une proposition périmée. Test dans Tâche 8.
2. **Même facture jointe à deux bons, ou analysée deux fois** : la deuxième occurrence bloque le bon, aucune ligne en double dans Progression. Tests dans Tâches 6 et 7.
3. **Pièce jointe non lisible** (HEIC, vidéo, PDF protégé, fichier > 30 Mo) : classée `incertain`, bon `À vérifier`, l'analyse des autres pièces continue. Test dans Tâche 4.
4. **Réponse Claude refusée, tronquée ou JSON invalide** : la pièce ou le texte passe `incertain`/inchangé avec une alerte, pas de plantage du lot. Tests dans Tâches 4 et 5.
5. **Coupure au milieu d'un envoi en lot** : la reprise saute les bons déjà écrits (journal) et n'écrit rien en double. Test dans Tâche 8.

---

### Tâche 1 : squelette, modèle de données et moteur de règles

**Files:**
- Create: `revision-bons/_logiciel/modele.py`, `revision-bons/_logiciel/regles.py`, `revision-bons/_logiciel/regles.toml`, `revision-bons/_logiciel/requirements.txt`, `revision-bons/tests/test_regles.py`, `revision-bons/tests/conftest.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces (`modele.py`, dataclasses) :
  - `EntreeTemps(id: int, technicien: str, jour: date, minutes: int, ligne_id: int | None)`
  - `Ligne(id: int | None, libelle: str, description: str, quantite: float, prix: float, cout_unitaire: float | None, produit: str | None, external_id: str | None)`
  - `PieceJointe(id: int, nom: str, type_mime: str)`
  - `LigneFacture(description: str, quantite: float, prix_unitaire: float)`
  - `Facture(fournisseur: str, numero: str, date: date | None, sous_total: float | None, lignes: list[LigneFacture])`
  - `AnalysePiece(piece_id: int, genre: Literal["facture", "photo", "incertain"], facture: Facture | None, raison: str)`
  - `Bon(id: int, code: str, client: str, date_rv: date | None, maj: str, description: str, entrees: list[EntreeTemps], lignes: list[Ligne], pieces: list[PieceJointe])` — `maj` = champ `updated` de Progression
  - `Alerte(code: str, message: str, bloquante: bool)`
  - `Proposition(bon_id: int, maj: str, description: str, description_originale: str, lignes: list[Ligne], analyses: list[AnalysePiece], alertes: list[Alerte], origine: dict[str, str])` avec propriété `statut -> Literal["pret", "a_verifier", "bloque"]` (bloqué si une alerte bloquante, à vérifier si une alerte, sinon prêt)
- Produces (`regles.py`) :
  - `charger_regles(chemin: Path) -> Regles` (dataclass des valeurs de `regles.toml`)
  - `arrondir_minutes(minutes: int, pas: int = 15) -> int`
  - `heures_facturees(entrees: list[EntreeTemps], pas: int) -> dict[str, float]` (technicien → heures arrondies)
  - `prix_avec_marge(cout: float, marge: float) -> float`
  - `lignes_materiel(facture: Facture, marge: float) -> list[Ligne]`
  - `garde_fous_facture(facture: Facture, date_bon: date | None, r: Regles) -> list[Alerte]`
  - `garde_fous_temps(entrees: list[EntreeTemps], r: Regles) -> list[Alerte]`

`regles.toml` contient exactement :

```toml
[heures]
pas_minutes = 15
[materiel]
marge = 0.10
refacturer_taxes = false
[transports]
regle = "conserver"   # seule valeur implémentée; Hugo définira la vraie règle
[garde_fous]
ecart_sous_total = 0.05
jours_max_facture = 30
montant_max_ligne = 1000.00
heures_max_jour = 12
```

- [ ] **Step 1 : tests qui échouent** dans `tests/test_regles.py` :

```python
def test_arrondi():
    assert arrondir_minutes(125) == 135   # 2 h 05 -> 2 h 15
    assert arrondir_minutes(135) == 135   # 2 h 15 reste
    assert arrondir_minutes(1) == 15
    assert arrondir_minutes(0) == 0

def test_arrondi_par_technicien_et_non_sur_le_total():
    e = [EntreeTemps(1, "Luc", J, 65, 10), EntreeTemps(2, "Max", J, 65, 11)]
    assert heures_facturees(e, 15) == {"Luc": 1.25, "Max": 1.25}   # 2 h 30, pas 2 h 15

def test_arrondi_sur_total_du_technicien():
    e = [EntreeTemps(1, "Luc", J, 50, 10), EntreeTemps(2, "Luc", J, 20, 10)]
    assert heures_facturees(e, 15) == {"Luc": 1.25}   # 70 min -> 75

def test_marge():
    assert prix_avec_marge(12.34, 0.10) == 13.57
    assert prix_avec_marge(100.00, 0.10) == 110.00

def test_lignes_materiel_cout_et_prix():
    f = Facture("Rona", "A-1", J, 20.0, [LigneFacture("Vis", 2, 10.0)])
    [l] = lignes_materiel(f, 0.10)
    assert (l.cout_unitaire, l.prix, l.quantite) == (10.0, 11.0, 2)
    assert l.external_id == "rona|A-1|1"

def test_garde_fous_facture():   # un cas par code
    # "ecart_sous_total" (lignes 20,00 vs sous-total 25,00), "facture_ancienne" (31 jours),
    # "ligne_elevee" (1 000,01 $), aucune alerte sur une facture conforme
def test_garde_fous_temps():
    # "plus_12h" pour 12 h 01 un même jour; "sans_heures" bloquante si liste vide
```

`external_id` = `f"{fournisseur.lower().strip()}|{numero.strip()}|{index_1_base}"`.

- [ ] **Step 2 :** `cd revision-bons && python -m pytest tests/test_regles.py -q` → FAIL (modules absents).
- [ ] **Step 3 :** écrire `modele.py`, `regles.py`, `regles.toml`, `requirements.txt` (`anthropic>=2.8`), `tests/conftest.py` (ajoute `_logiciel` au `sys.path`, constante `J = date(2026, 11, 3)`). Arrondi monétaire avec `decimal.Decimal(...).quantize(Decimal("0.01"), ROUND_HALF_UP)`. Ajouter au `.gitignore` : `revision-bons/_logiciel/cache/`, `revision-bons/_logiciel/journal/`, `revision-bons/_logiciel/python_portable.zip`, `cles.json`.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : modèle de données et moteur de règles`.

### Tâche 2 : client Progression et script d'inspection en lecture seule

**Files:**
- Create: `revision-bons/_logiciel/progression.py`, `revision-bons/_logiciel/config.toml`, `revision-bons/_logiciel/inspecter.py`, `revision-bons/tests/test_progression.py`, `revision-bons/tests/donnees/tache_exemple.json`, `revision-bons/tests/donnees/entrees_exemple.json`

**Interfaces:**
- Consumes : `modele.Bon`, `EntreeTemps`, `Ligne`, `PieceJointe`.
- Produces :
  - `class ErreurProgression(Exception)` (message français lisible)
  - `class Progression(cle: str, base: str = BASE, ouvrir=urllib.request.urlopen)` — `ouvrir` injectable pour les tests
  - `.lister_bons(logic_ids: str, type_tache: str, rv: str) -> list[dict]` (pagine `startResult` par 500)
  - `.lire_bon(identifiant: int) -> Bon`
  - `.telecharger_piece(piece_id: int) -> bytes` (décode `data` base64)
  - `.mettre_a_jour(identifiant: int, corps: dict) -> dict`
  - `bon_depuis_json(tache: dict, entrees: list[dict], cfg: dict) -> Bon` (fonction pure)

`config.toml` :

```toml
[progression]
base = "https://api.progressionlive.com/server/rest"
logic_ids_a_facturer = ""     # à remplir après inspection (spec 9.1)
type_tache = ""               # idem
champ_description = "description"   # ou "properties.<nom>" (spec 9.2)
produit_transport = ""        # spec 9.4
produit_materiel = ""         # spec 9.6
ecriture_validee = false      # passe à true seulement après l'essai de la Tâche 10
[claude]
modele = "claude-opus-5-5"
effort = "medium"
```

- [ ] **Step 1 : tests qui échouent** avec un faux `ouvrir` qui enregistre les requêtes et renvoie les fichiers de `tests/donnees/` (construits à la main d'après les schémas `Task`, `TaskItem`, `TimeEntry`, `AttachmentRef` du Swagger) :
  - `test_entete_bearer` : chaque requête porte `Authorization: Bearer cle-test`, jamais `apiKey=` dans l'URL.
  - `test_lister_pagine` : 501 tâches → deux appels avec `startResult=0` puis `500`.
  - `test_bon_depuis_json` : `minutes` calculées depuis `duration` ISO 8601 (`PT1H20M` → 80), `ligne_id` depuis `TimeEntry.item.id`, `cout_unitaire` depuis `unitCost`, `maj` depuis `updated`, description lue selon `champ_description` (cas `description` et cas `properties.notesTech`).
  - `test_telecharger_piece` : décode le base64 de `GET /task/attachment/{id}`.
  - `test_erreur_401` : `ErreurProgression("Clé Progression refusée…")`; `test_erreur_reseau` : message « Progression ne répond pas… ».
- [ ] **Step 2 :** `python -m pytest tests/test_progression.py -q` → FAIL.
- [ ] **Step 3 :** écrire `progression.py` (`urllib.request.Request`, `Accept`/`Content-Type: application/json`, timeout 60 s) et `config.toml`. Écrire `inspecter.py` : lecture seule, prend `--nombre 10`, lit les derniers bons à l'état ≥ 600 (`logicId=600:1000` si accepté, sinon tous puis filtre), et écrit dans `cache/inspection.txt`, pour chaque bon : `currentState`, `type`, champs texte non vides (`description`, `summary`, clés de `properties`), lignes (`label`, `type`, `product`, `quantity`, `price`, `unitCost`), entrées de temps (technicien, durée, `item.id`), pièces jointes (nom, type MIME). Aucune requête autre que `GET`.
- [ ] **Step 4 :** relancer → PASS. Vérifier avec `grep -n "POST\|update" inspecter.py` qu'aucune écriture n'existe dans le script.
- [ ] **Step 5 :** commit `Révision des bons : client Progression et inspection en lecture seule`.

### Tâche 3 : (bloquante, faite dès réception de la clé, avec la direction) inspection des vrais bons

**Files:**
- Modify: `revision-bons/_logiciel/config.toml`, `docs/superpowers/specs/2026-11-10-revision-bons-design.md` (section 9 : réponses)

- [ ] **Step 1 :** enregistrer la clé dans `%APPDATA%\ProgimRevisionBons\cles.json` (`{"progression": "...", "claude": "..."}`), lancer `python inspecter.py --nombre 10`.
- [ ] **Step 2 :** lire `cache/inspection.txt` et remplir `logic_ids_a_facturer`, `type_tache`, `champ_description`, `produit_transport`, `produit_materiel`. Noter dans la spec, section 9, la réponse à chaque point 1-4 et 6, avec l'id d'un bon exemple.
- [ ] **Step 3 :** si les heures facturées ne sont pas liées aux entrées par `TimeEntry.item`, ou si la description n'est dans aucun champ lisible, **arrêter et revoir le design** avant la Tâche 6.
- [ ] **Step 4 :** commit `Révision des bons : configuration d'après les vrais bons` (aucune donnée client dans le commit).

### Tâche 4 : lecture des pièces jointes par Claude

**Files:**
- Create: `revision-bons/_logiciel/claude_client.py`, `revision-bons/_logiciel/pieces_jointes.py`, `revision-bons/tests/test_pieces_jointes.py`

**Interfaces:**
- Consumes : `modele.PieceJointe`, `Facture`, `LigneFacture`, `AnalysePiece`.
- Produces :
  - `claude_client.demander_json(client, cfg: dict, contenu: list[dict], schema: dict, systeme: str) -> dict | None` — `client.beta.messages.create(model=cfg["modele"], max_tokens=16000, betas=["server-side-fallback-2026-07-01"], fallbacks="default", output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": schema}}, system=systeme, messages=[{"role": "user", "content": contenu}])`; renvoie `None` si `stop_reason` vaut `refusal` ou `max_tokens`, ou si le JSON est invalide; laisse passer les erreurs `anthropic.APIConnectionError` / `APIStatusError`.
  - `TYPES_LISIBLES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}`, `TAILLE_MAX = 30 * 1024 * 1024`
  - `analyser_piece(piece: PieceJointe, contenu: bytes, client, cfg: dict) -> AnalysePiece`

Schéma JSON demandé (tous les champs `required`, `additionalProperties: false`) : `genre` (`facture` | `photo` | `incertain`), `raison` (texte court), `fournisseur`, `numero`, `date` (AAAA-MM-JJ ou chaîne vide), `sous_total` (nombre ou `null`), `lignes` (liste de `{description, quantite, prix_unitaire}` avant taxes). Consigne système : une facture ou un reçu d'achat de matériel est `facture`; une photo de chantier, de travaux ou d'équipement est `photo`; un document flou, coupé ou autre est `incertain`; ignorer TPS, TVQ, écofrais et consignes; ne jamais deviner un montant illisible (mettre `incertain`).

- [ ] **Step 1 : tests qui échouent**, avec un faux client dont `beta.messages.create` renvoie une réponse préparée et enregistre ses arguments :
  - `test_pdf_envoye_comme_document` / `test_image_envoyee_comme_image` (bloc `document` vs `image`, base64 sans saut de ligne).
  - `test_facture_extraite` : JSON facture → `AnalysePiece(genre="facture")` avec `Facture` et ses lignes.
  - `test_type_non_lisible` : `image/heic` → `incertain`, raison « Format non lisible (image/heic) », **aucun** appel au client.
  - `test_trop_gros` : 31 Mo → `incertain`, aucun appel.
  - `test_refus_ou_json_invalide` : `stop_reason="refusal"` puis texte non JSON → `incertain` avec raison, pas d'exception.
  - `test_parametres_api` : `model == "claude-opus-5-5"`, `fallbacks == "default"`, `output_config["effort"] == "medium"`.
- [ ] **Step 2 :** `python -m pytest tests/test_pieces_jointes.py -q` → FAIL.
- [ ] **Step 3 :** écrire `claude_client.py` et `pieces_jointes.py`.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : lecture des pièces jointes`.

### Tâche 5 : réécriture de la description

**Files:**
- Create: `revision-bons/_logiciel/redaction.py`, `revision-bons/tests/test_redaction.py`

**Interfaces:**
- Consumes : `claude_client.demander_json`, `modele.Alerte`.
- Produces :
  - `nombres_absents(original: str, propose: str) -> list[str]` (pure : nombres et mesures de `propose` absents de `original`, en normalisant `2,5`/`2.5` et les espaces)
  - `rediger(texte: str, client, cfg: dict) -> tuple[str, list[Alerte]]`

Consigne système : corriger orthographe et syntaxe en français professionnel; si le texte est confus, le résumer clairement; ne jamais ajouter un travail, une pièce, une quantité ou une mesure absents; garder intacts emplacements, équipements, numéros de modèle; même langue que l'original. Schéma : `{"texte": string}`.

- [ ] **Step 1 : tests qui échouent :**
  - `test_nombres_absents` : `nombres_absents("changé 2 robinets", "Remplacement de 3 robinets") == ["3"]`; `nombres_absents("tuyau 2,5 po", "tuyau de 2.5 po") == []`.
  - `test_redaction_normale` : texte proposé renvoyé, aucune alerte.
  - `test_redaction_invente_un_nombre` : alerte `"redaction_chiffre"` non bloquante, et le texte proposé est quand même renvoyé pour que Hugo tranche.
  - `test_texte_vide` : `("", [])` sans appel au client.
  - `test_refus` : texte original renvoyé + alerte `"redaction_echec"`.
- [ ] **Step 2 :** `python -m pytest tests/test_redaction.py -q` → FAIL.
- [ ] **Step 3 :** écrire `redaction.py`.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : réécriture des descriptions`.

### Tâche 6 : journal et historique

**Files:**
- Create: `revision-bons/_logiciel/journal.py`, `revision-bons/tests/test_journal.py`

**Interfaces:**
- Produces :
  - `class Journal(dossier: Path, personne: str)` — un fichier `journal/<personne>.jsonl` par personne (comme le suivi de `rapports-clients`), lecture combinée de tous les fichiers du dossier
  - `.inscrire(evenement: str, bon_id: int, maj: str, details: dict) -> None` (`evenement` ∈ `approuve`, `ecrit`, `echec`; horodatage ISO ajouté)
  - `.deja_ecrit(bon_id: int, maj: str) -> bool`
  - `.factures_refacturees() -> dict[str, int]` (préfixe `fournisseur|numero` → bon_id, à partir des `external_id` des événements `ecrit`)
  - `.historique(limite: int = 200) -> list[dict]` (plus récent d'abord)

- [ ] **Step 1 : tests qui échouent :** inscrire puis relire; deux personnes → historique combiné trié; `deja_ecrit` vrai seulement pour le même `maj`; `factures_refacturees` retrouve `"rona|A-1"` → `42`; une ligne JSON corrompue est ignorée sans planter.
- [ ] **Step 2 :** `python -m pytest tests/test_journal.py -q` → FAIL.
- [ ] **Step 3 :** écrire `journal.py` (ajout en mode `"a"`, `encoding="utf-8"`, une ligne JSON par événement).
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : journal partagé`.

### Tâche 7 : analyse d'un bon (assemblage de la proposition)

**Files:**
- Create: `revision-bons/_logiciel/analyse.py`, `revision-bons/tests/test_analyse.py`

**Interfaces:**
- Consumes : `Progression.lire_bon`, `.telecharger_piece`, `pieces_jointes.analyser_piece`, `redaction.rediger`, `regles.*`, `Journal.factures_refacturees`.
- Produces :
  - `analyser_bon(bon: Bon, progression, client, cfg: dict, r: Regles, journal: Journal, cache: Path) -> Proposition`
  - `ajuster_main_oeuvre(bon: Bon, heures: dict[str, float]) -> tuple[list[Ligne], dict[str, str]]`

Règle d'ajustement (non déterminée par les signatures) : pour chaque technicien, `écart = heures arrondies − somme des quantités des lignes liées à ses entrées (via EntreeTemps.ligne_id)`; ajouter l'écart à la **dernière** de ses lignes; si aucune ligne n'est liée, alerte `"main_oeuvre_introuvable"` et rien n'est changé. Les lignes de matériel existantes sont conservées telles quelles; les nouvelles s'ajoutent à la fin. Transports : `regle = "conserver"` → ligne inchangée + alerte `"transport_a_definir"`. `origine` associe chaque ligne modifiée ou ajoutée à sa règle (`"arrondi 15 min – Luc"`, `"facture Rona A-1, +10 %"`). Cache : `cache/<bon_id>_<maj nettoyé>.json`; si présent, aucun appel Claude.

- [ ] **Step 1 : tests qui échouent**, avec faux Progression / faux client / journal temporaire :
  - `test_arrondi_applique_aux_lignes_pas_aux_entrees` : Luc 2 h 05 sur une ligne de 2,0833 → ligne à 2,25; `bon.entrees` inchangées.
  - `test_ligne_materiel_ajoutee_avec_origine`.
  - `test_photo_ignoree` : aucune ligne ajoutée pour une photo.
  - `test_facture_deja_refacturee_bloque` : `factures_refacturees()` contient `"rona|A-1"` pour un autre bon → alerte bloquante `"facture_doublon"`.
  - `test_meme_facture_deux_fois_dans_le_bon` : deux pièces, même fournisseur et numéro → une seule série de lignes + alerte `"facture_doublon"` bloquante.
  - `test_piece_incertaine_continue` : une pièce `incertain` → alerte `"piece_incertaine"`, les autres pièces sont quand même analysées.
  - `test_cache_evite_claude` : deuxième appel avec le même `maj` → zéro appel au faux client.
  - `test_statut` : aucune alerte → `pret`; alerte non bloquante → `a_verifier`; bloquante → `bloque`.
- [ ] **Step 2 :** `python -m pytest tests/test_analyse.py -q` → FAIL.
- [ ] **Step 3 :** écrire `analyse.py` (sérialisation du cache avec `dataclasses.asdict`, dates en ISO).
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : analyse d'un bon`.

### Tâche 8 : envoi vers Progression (simulation et réel)

**Files:**
- Create: `revision-bons/_logiciel/envoi.py`, `revision-bons/tests/test_envoi.py`

**Interfaces:**
- Consumes : `Proposition`, `Progression.lire_bon` / `.mettre_a_jour`, `Journal`.
- Produces :
  - `corps_mise_a_jour(p: Proposition, cfg: dict) -> dict` (pure)
  - `envoyer(propositions: list[Proposition], progression, journal: Journal, cfg: dict, mode: Literal["simulation", "reel"]) -> list[dict]` (une entrée par bon : `{bon_id, code, resultat: "simule"|"ecrit"|"deja_ecrit"|"perime"|"echec", message}`)

`corps_mise_a_jour` : description dans le champ `champ_description` (`description` ou `properties.<nom>`), et `itemList.items` = **liste complète** (lignes existantes avec leur `id` + nouvelles lignes sans `id`, avec `externalId`), chaque dict nettoyé de toute clé dont la valeur est `None`. On envoie toujours la liste complète, ce qui reste correct si Progression remplace la liste; l'essai de la Tâche 10 confirme le comportement avant tout mode réel.

- [ ] **Step 1 : tests qui échouent :**
  - `test_aucun_none` : parcours récursif du corps, aucune valeur `None`.
  - `test_liste_complete_avec_ids` et `test_external_id_sur_nouvelles_lignes`.
  - `test_description_dans_properties` quand `champ_description = "properties.notesTech"`.
  - `test_simulation_n_ecrit_rien` : zéro appel à `mettre_a_jour`, résultat `simule`.
  - `test_reel_refuse_sans_validation` : `ecriture_validee = false` → `ValueError` avant tout appel réseau.
  - `test_bon_perime` : `lire_bon` renvoie un autre `maj` → résultat `perime`, aucun `mettre_a_jour`.
  - `test_reprise_apres_coupure` : `deja_ecrit` vrai pour le bon 1 → `deja_ecrit`, seul le bon 2 est écrit; une `ErreurProgression` sur le bon 2 → `echec` inscrit au journal, le bon 3 est quand même traité.
  - `test_jamais_timeentry` : aucune URL appelée ne contient `timeEntry`.
- [ ] **Step 2 :** `python -m pytest tests/test_envoi.py -q` → FAIL.
- [ ] **Step 3 :** écrire `envoi.py`; en réel, inscrire `ecrit` avec les `external_id` ajoutés et la description originale.
- [ ] **Step 4 :** relancer → PASS.
- [ ] **Step 5 :** commit `Révision des bons : envoi simulé et réel`.

### Tâche 9 : interface, lanceur et données de démonstration

**Files:**
- Create: `revision-bons/Révision des bons.bat`, `revision-bons/LISEZ-MOI.txt`, `revision-bons/_logiciel/preparer_python.cmd`, `revision-bons/_logiciel/cles.py`, `revision-bons/_logiciel/interface.py`, `revision-bons/_logiciel/interface.html`, `revision-bons/_logiciel/demo/generer_demo.py`, `revision-bons/_logiciel/demo/faux_services.py`, `revision-bons/README.md`, `revision-bons/tests/test_interface.py`

**Interfaces:**
- Consumes : tous les modules précédents.
- Produces :
  - `cles.lire() -> dict[str, str]`, `cles.ecrire(progression: str | None, claude: str | None) -> None` (`%APPDATA%\ProgimRevisionBons\cles.json`; ne renvoie jamais la clé à la page, seulement « configurée / manquante »)
  - Routes JSON de `interface.py` : `GET /etat` (clés configurées, mode, nom de la personne), `POST /charger {rv}`, `POST /analyser {bon_ids}` (traitement en arrière-plan, `GET /progres`), `GET /bon/{id}` (proposition + original), `POST /bon/{id}/modifier {champ, valeur}`, `POST /approuver {bon_ids}`, `POST /envoyer {mode}`, `GET /regles`, `POST /regles` (réécrit `regles.toml`), `GET /historique`, `GET /piece/{id}` (aperçu de la pièce jointe)
  - `interface.py --demo` : remplace Progression et Claude par `demo/faux_services.py` (bons, photos et fausses factures générés par `generer_demo.py`, sans réseau)

L'interface reprend la structure et le design de `rapports-clients/_logiciel/interface.html` (onglets, tableau qui s'arrête au bas de l'écran, logo Progim) avec trois onglets : **À réviser** (liste avec statut et raison, « tout cocher » limité aux bons `pret`, vue côte à côte original / proposition, chaque facture affichée à côté de ses lignes, origine de chaque valeur), **Règles**, **Historique**. Le `.bat` reprend celui de `rapports-clients` et vérifie `import anthropic`; s'il manque : « Il manque le module anthropic dans Python portable. Avertir le responsable TI. »

- [ ] **Step 1 : tests qui échouent** (`test_interface.py`, serveur lancé en `--demo` sur un port libre) : `/etat` ne contient aucune clé; `/charger` puis `/analyser` puis `/bon/{id}` renvoient une proposition; `/approuver` refuse un bon `bloque`; `/envoyer {"mode": "reel"}` refusé tant que `ecriture_validee = false`; `/regles` aller-retour conserve `marge = 0.10`.
- [ ] **Step 2 :** `python -m pytest tests/test_interface.py -q` → FAIL.
- [ ] **Step 3 :** écrire les fichiers.
- [ ] **Step 4 :** relancer toute la suite `python -m pytest -q` → PASS. Lancer `python _logiciel/interface.py --demo`, ouvrir la page avec Playwright, faire une capture des trois onglets et d'un bon ouvert, et la vérifier visuellement.
- [ ] **Step 5 :** commit `Révision des bons : interface, lanceur et démo`.

### Tâche 10 : (avec la direction) essai d'écriture sur un bon de test, puis acceptation

**Files:**
- Create: `revision-bons/_logiciel/essai_ecriture.py`
- Modify: `revision-bons/_logiciel/config.toml`, spec section 9.5

- [ ] **Step 1 :** dans Progression, la direction crée à la main un bon **de test** (client fictif) avec deux lignes et une photo. `essai_ecriture.py --bon <id>` refuse tout bon dont le client n'est pas celui passé en `--client-test`, ajoute une ligne, relit le bon et affiche si les deux lignes d'origine existent encore.
- [ ] **Step 2 :** si la liste complète a bien été conservée sans doublon, noter la réponse en spec 9.5 et passer `ecriture_validee = true`; sinon arrêter et corriger `corps_mise_a_jour` avant d'aller plus loin.
- [ ] **Step 3 :** acceptation (spec 10) : en simulation sur un mois de bons déjà facturés, produire un tableau de comparaison (classement des pièces, lignes de matériel, heures) entre la proposition et ce que Hugo a envoyé; la direction et Hugo décident du passage en réel.
- [ ] **Step 4 :** commit `Révision des bons : écriture validée sur bon de test`.
