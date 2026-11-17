# Révision des bons de service

Outil local qui prépare la facturation des bons de service Progression Live. Il récupère les bons terminés,
classe leurs pièces jointes (facture ou photo) et lit les factures avec Claude. Il applique ensuite les règles de
facturation (matériel au sous-total plus 15 %, main-d'œuvre au 0,25 h, transport, tarifs selon le type de bon),
réécrit la description et signale les exceptions. Hugo révise, approuve, puis l'outil écrit les corrections dans
Progression. Un onglet calcule aussi le kilométrage des techniciens pour la paie.

Design : `docs/superpowers/specs/2026-11-10-revision-bons-design.md` (règles et garde-fous) et
`docs/superpowers/specs/2026-11-16-kilometrage-design.md`. Mode d'emploi d'Hugo : `LISEZ-MOI.txt`.

## Utilisation

Double-cliquer sur `Révision des bons.bat` (même Python portable que les autres outils Progim). Pour essayer
sans clé ni réseau : `Essai (démo).bat`, ou `python _logiciel/interface.py --demo`.

**L'outil n'écrit jamais rien sans approbation.** Le mode simulation est le mode par défaut. L'écriture réelle
reste verrouillée tant que `ecriture_validee = false` dans `_logiciel/config.toml`. On la déverrouille seulement
après l'essai dans l'environnement de test de Progression.

## Mise en service

1. Obtenir la clé API Progression (forfait Premium, soutien Progression) et une clé API Claude
   (console.anthropic.com). Les inscrire dans l'onglet Règles, section Connexions. Elles sont gardées dans
   `%APPDATA%\ProgimRevisionBons\cles.json`.
2. `config.toml` est rempli (inspection du 10 novembre 2026). Au besoin, `python _logiciel/inspecter.py
   --nombre 10` refait une inspection en lecture seule de vrais bons (`_logiciel/cache/inspection.txt`).
3. Essai d'écriture dans l'environnement de test (`essai_ecriture.py`), puis `ecriture_validee = true`.

Le Python portable de Progim n'a pas pip. Au premier lancement, `dependances.py` télécharge depuis PyPI les
modules du SDK de Claude pour Windows 64 bits / Python 3.12 listés dans `_logiciel/roues.toml`, vérifie
l'empreinte sha256 de chacun, puis les décompresse dans `%LOCALAPPDATA%\ProgimRevisionBons`. Un dossier
`_logiciel/roues` contenant des `.whl` est utilisé à la place s'il existe (poste sans Internet).

## Organisation

| Fichier | Rôle |
|---|---|
| `modele.py` | Données : bon, lignes, pièces, factures, proposition |
| `regles.py` + `regles.toml`, `facturation.py` | Règles de facturation et garde-fous (fonctions pures) |
| `progression.py` | Seul module qui parle à l'API Progression |
| `claude_client.py`, `pieces_jointes.py`, `redaction.py` | Seuls modules qui appellent Claude (`claude-opus-5-5`, effort `medium`, relève automatique si un modèle refuse) |
| `analyse.py` | Assemble la proposition d'un bon (cache par bon et date de modification) |
| `journal.py` | Historique partagé, un fichier par personne dans `_logiciel/journal/` |
| `envoi.py` | Construit et écrit les mises à jour (jamais de `null`, jamais les entrées de temps) |
| `assistant.py` + `assistant_guide.md` | Jarvis, l'assistant : répond aux questions sur l'usage et les règles avec le contexte du bon ouvert, aide à trouver des améliorations et rédige les recommandations du journal d'améliorations; ne modifie rien. **Mettre `assistant_guide.md` à jour à chaque changement de règle (section « Décisions prises »).** Questions dans `_logiciel/questions/`, recommandations dans `_logiciel/recommandations/` |
| `kilometrage.py`, `km_calcul.py`, `km_declare.py`, `cartes.py`, `excel.py` | Kilométrage des techniciens et export Excel |
| `interface.py` + `interface.html` | Serveur local et page (onglets À réviser, Kilométrage, Règles, Historique) |
| `demo/faux_services.py` | Faux Progression et faux Claude pour le mode démo |

## Tests

```
pip install pytest "anthropic>=2.8"
cd revision-bons && python -m pytest -q
```

## Confidentialité

Les pièces jointes et les descriptions sont envoyées à l'API de Claude pour l'analyse. Clés, caches, journaux et
pièces jointes restent hors du dépôt (`.gitignore`).
