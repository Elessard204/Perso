# Dossier maître de l'immeuble — Modèle Progim

Gabarit Excel : un fichier par immeuble géré, déposé dans le dossier SharePoint de l'immeuble. C'est la source de
connaissance principale de l'immeuble : rempli à l'intégration d'un nouveau mandat, tenu à jour par le gestionnaire et
l'équipe, utilisable par un remplaçant ou lors d'une passation. Le mode d'emploi et les règles de gouvernance sont
dans le premier onglet.

- `Dossier maitre immeuble - GABARIT.xlsx` : le gabarit à copier.
- `generer_gabarit.py` : régénère le gabarit (`python generer_gabarit.py [sortie.xlsx]`). Faire évoluer le gabarit
  dans ce script plutôt que dans le fichier.

## Correspondance avec le modèle en 38 sections

| Onglet | Sections du modèle |
|---|---|
| Résumé | 36 (calculé à partir des autres onglets) et tableau de bord des échéances |
| Fiche | 1, 2, 3, 5, 14, 22 |
| Vision | 4, 10 (particularités locatives), 11, 12 |
| Finances | 6, 7, 8 |
| Bâtiment | 16, 20, procédures d'urgence |
| Intégration | 5 (documents reçus, informations manquantes) |
| Plan 90 jours | 31, 32 |
| Unités, Dossiers | 10, 13 |
| Assurances, Taxes, Contrats | 9, 8, 15 et 21 |
| Entretien, Équipements, Projets, Sinistres | 17, 16, 18, 19 |
| Exceptions, Décisions, Risques, Opportunités | 24, 25, 26, 27 |
| KPI | 28 (à l'échelle de l'immeuble) |
| Actions | 37, 38 |
| Documents | 23 |
| Journal | 34 et liste de passation |
| Mode d'emploi | Objectif, 33, 35 |

Les sections 29 et 30 (revues hebdomadaire et mensuelle) se font à l'échelle du portefeuille, hors du dossier d'immeuble.
