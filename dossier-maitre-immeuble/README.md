# Dossier maître de l'immeuble

Gabarit Excel de Gestion Progim : un fichier par immeuble géré, déposé dans le dossier SharePoint de l'immeuble.
Il sert à trois moments : l'intégration d'un nouveau client, la tenue à jour par l'équipe et la passation
d'un gestionnaire à un autre. Le mode d'emploi complet est dans le premier onglet.

- `Dossier maitre immeuble - GABARIT.xlsx` : le gabarit à copier.
- `generer_gabarit.py` : régénère le gabarit (`python generer_gabarit.py [sortie.xlsx]`). Faire évoluer le gabarit
  dans ce script plutôt que dans le fichier.

Onglets : Fiche (identification, propriétaire et mandat, équipe, accès, tableau de bord), Intégration (69 éléments à
obtenir du propriétaire, du gestionnaire sortant ou en visite, avec suivi et relances), Connaissances (questions guides
pour recueillir le savoir de l'équipe), Calendrier annuel, Unités et baux, Assurances, Taxes, Contrats, Entretien,
Équipements, Travaux, Contacts, Documents, Journal (mises à jour et liste de passation), Paramètres.
