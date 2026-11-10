# Révision des bons de service

Outil local qui prépare la facturation des bons de service Progression Live. Il récupère les bons terminés,
classe leurs pièces jointes (facture ou photo) et lit les factures avec Claude. Il propose ensuite les lignes de
matériel au coût plus 10 %, arrondit les heures facturées de chaque technicien au quart d'heure supérieur et
réécrit la description des travaux. Hugo révise, approuve, puis l'outil écrit les corrections dans Progression.

Design : `docs/superpowers/specs/2026-11-10-revision-bons-design.md`.
Plan : `docs/superpowers/plans/2026-11-10-revision-bons.md`.

## Utilisation

Double-cliquer sur `Révision des bons.bat` (même Python portable que les autres outils Progim). Pour essayer
sans clé ni réseau : `Essai (démo).bat`, ou `python _logiciel/interface.py --demo`.

**L'outil n'écrit jamais rien sans approbation.** Le mode simulation est le mode par défaut. L'écriture réelle
reste verrouillée tant que `ecriture_validee = false` dans `_logiciel/config.toml`. On la déverrouille seulement
après l'essai sur un bon de test (tâche 10 du plan).

## Mise en service

1. Obtenir la clé API Progression (forfait Premium, soutien Progression) et une clé API Claude
   (console.anthropic.com). Les inscrire dans l'onglet Règles, section Connexions. Elles sont gardées dans
   `%APPDATA%\ProgimRevisionBons\cles.json`.
2. `python _logiciel/inspecter.py --nombre 10` : inspection en lecture seule de vrais bons. Le rapport
   `_logiciel/cache/inspection.txt` sert à remplir les champs vides de `config.toml` (état à facturer, type de
   tâche, champ de la description, produits transport et matériel).
3. Essai d'écriture sur un bon de test, puis `ecriture_validee = true`.

Le module `anthropic` doit être présent dans Python portable. Le `.bat` tente de l'installer avec pip à la
première utilisation. Sinon, l'ajouter au `python_portable.zip` :
`python -m pip install "anthropic>=2.8" --target <dossier du Python portable>\Lib\site-packages`.

## Organisation

| Fichier | Rôle |
|---|---|
| `modele.py` | Données : bon, lignes, pièces, factures, proposition |
| `regles.py` + `regles.toml` | Arrondi, marge, garde-fous (fonctions pures) |
| `progression.py` | Seul module qui parle à l'API Progression |
| `claude_client.py`, `pieces_jointes.py`, `redaction.py` | Seuls modules qui appellent Claude (`claude-opus-5-5`, effort `medium`, relève automatique si un modèle refuse) |
| `analyse.py` | Assemble la proposition d'un bon (cache par bon et date de modification) |
| `journal.py` | Historique partagé, un fichier par personne dans `_logiciel/journal/` |
| `envoi.py` | Construit et écrit les mises à jour (jamais de `null`, jamais les entrées de temps) |
| `interface.py` + `interface.html` | Serveur local et page (onglets À réviser, Règles, Historique) |
| `demo/faux_services.py` | Faux Progression et faux Claude pour le mode démo |

## Tests

```
pip install pytest "anthropic>=2.8"
cd revision-bons && python -m pytest -q
```

## Confidentialité

Les pièces jointes et les descriptions sont envoyées à l'API de Claude pour l'analyse. Clés, caches, journaux et
pièces jointes restent hors du dépôt (`.gitignore`).
