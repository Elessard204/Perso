# Rapports clients mensuels

Cet outil prépare l'envoi mensuel des rapports financiers aux clients. Sabrina télécharge déjà de Hopem un PDF combiné par entité (« Rapports mensuels Sept 2026_05401.pdf ») dans `ÉTATS FINANCIERS/1_CLIENTS/<mois>`. L'outil prend le relais à partir de là.

Il associe chaque PDF à son entité grâce aux 5 derniers chiffres (05401 = 54.1). Il vérifie ensuite le contenu du PDF et regroupe les entités qui ont les mêmes destinataires. Il prépare enfin un courriel par client, qui part de finance@progim.com avec le gestionnaire et la direction en cc.

**L'outil n'envoie jamais rien lui-même.** En mode `simulation` (par défaut), il produit un aperçu `.eml` de chaque courriel et un rapport de contrôle. En mode `brouillons`, il crée en plus les brouillons dans la boîte finance@, que l'équipe révise et envoie.

## Utilisation par l'équipe

Double-cliquer sur **Rapports clients.bat**. La première fois, il installe les modules nécessaires (environ une minute), puis ouvre la fenêtre de l'outil. Le mois proposé est le dernier mois terminé.

1. **Étape 1 – Voir les périodes à extraire.** Avant de télécharger les rapports de Hopem : chaque entité a sa propre fin d'exercice, donc septembre est la période 9 pour une fin en décembre, la période 5 pour une fin en avril, etc.
2. Télécharger les rapports de Hopem comme d'habitude dans `ÉTATS FINANCIERS/1_CLIENTS/<mois>`, sans changer les noms. La première fois, choisir ce dossier avec « Choisir… » : les mois suivants, l'outil le retrouve seul.
3. **Étape 2 – Vérifier les rapports et préparer les courriels.** Le rapport de contrôle s'ouvre : courriels prêts, courriels bloqués avec la raison, fichiers non reconnus, entités sans envoi ce mois-ci. Corriger ce qui bloque (Excel ou dossier) et recommencer l'étape 2.
4. **Étape 3 – Créer les brouillons dans Outlook** (une fois la connexion à Outlook configurée). Réviser chaque brouillon dans la boîte finance@ et l'envoyer.

Les aperçus `.eml` des courriels sont dans `sortie/<mois>/apercus` (bouton « Ouvrir les aperçus de courriels »).

## En ligne de commande

```
python envoi_rapports.py --mois 2026-09 --clients clients_rapports.xlsx
python envoi_rapports.py --mois 2026-09 --clients clients_rapports.xlsx --exports "<...>/1_CLIENTS/09-septembre 2026" --completer
python envoi_rapports.py --mois 2026-09 --clients clients_rapports.xlsx --exports ... --mode brouillons
```

## Les contrôles

Un courriel est bloqué si une de ses entités est dans un des cas suivants :

- aucun PDF dans le dossier, ou deux PDF pour la même entité;
- le nom du fichier n'est pas celui du mois envoyé;
- un élément coché dans l'Excel manque : un rapport absent du PDF Hopem (bilan, sommaire, transactions par compte...), ou une pièce additionnelle absente du dossier (factures...);
- le bilan n'est pas au dernier jour du mois;
- la période de l'état des résultats ne correspond pas à la fin d'exercice de l'Excel;
- le nom du propriétaire imprimé en haut du PDF n'est pas celui de la colonne `nom_entite`.

Ce dernier contrôle protège contre le pire scénario : un PDF enregistré sous le mauvais numéro, qui partirait chez le mauvais client. Tant que `nom_entite` est vide, l'outil affiche le nom trouvé dans le PDF sans bloquer. L'option `--completer` écrit une copie de l'Excel (`..._complete.xlsx`) où les noms vides d'entités et de clients sont remplis à partir des PDF du mois. Il reste à la réviser une fois, puis à la garder comme Excel de référence.

Un courriel est aussi bloqué si une adresse courriel est invalide.

## L'Excel des clients

Il est créé à partir du fichier de suivi actuel par `importer_excel.py` (voir plus bas) et compte trois onglets.

- **Clients** : une ligne par courriel envoyé, avec `code_client`, `nom_client` (le propriétaire, utilisé dans l'objet), `nom_contact` (pour « Bonjour Julie », facultatif), `courriel_clients`, `courriel_direction` (vide = `direction_defaut` de `config.toml`), `langue` et `actif`.
- **Entites** : une ligne par entité Hopem, avec `code_entite` (54.1), `nom_entite` (nom légal tel qu'imprimé par Hopem), `immeubles` (adresses), `code_client`, `fin_exercice` (mois de 1 à 12), `frequence` (mensuel, trimestriel, semestriel ou annuel), `gestionnaire`, `courriel_gestionnaire` (facultatif, remplace celui de l'onglet Gestionnaires), `actif`, une case Oui/Non par élément à inclure (`bilan`, `etat_resultats`, `sommaire_transactions`, `transactions_par_compte`, `liste_depots`, `comptes_a_recevoir`, `liste_cheques`, `factures`) et `notes`, affichée comme consigne dans le rapport de contrôle. La liste des éléments et leurs titres Hopem se modifient dans `config.toml`.

Les pièces additionnelles, comme les factures, sont des PDF séparés dans le même dossier, dont le nom se termine par le numéro de l'entité (« Factures Sept 2026_14001.pdf »). Elles ne sont jointes que si leur case est cochée.
- **Gestionnaires** : le prénom tel qu'écrit dans l'onglet Entites et son courriel.

Plusieurs adresses vont dans une même cellule, séparées par `;`. Un client avec trois entités reçoit un seul courriel avec trois PDF.

## Convertir le fichier de suivi actuel

```
python importer_excel.py --source "Clients contrôle mensuel.xlsx" --sortie clients_rapports.xlsx
```

Le script lit le dernier onglet mensuel, ou celui passé avec `--onglet`. Il regroupe sous un même client les entités qui ont exactement les mêmes courriels clients. Il déduit la fréquence des notes (« trimestriellement », « Bi-Annuel ») et ajoute un onglet « A verifier » avec tout ce qui demande un jugement humain.

## Essayer avec des données fictives

```
pip install -r requirements.txt
python demo/generer_demo.py
python envoi_rapports.py --mois 2026-10 --exports demo/exports/2026-10 --clients demo/clients_demo.xlsx
```

## Brancher Outlook (mode brouillons)

Il faut une application inscrite dans Entra ID, avec la permission d'application Microsoft Graph `Mail.ReadWrite` et le consentement administrateur. Limite ensuite cette application à la seule boîte finance@progim.com avec une stratégie d'accès d'application Exchange (`New-ApplicationAccessPolicy`), sinon elle pourrait écrire dans toutes les boîtes de l'organisation. Remplis `tenant_id` et `client_id` dans `config.toml`, et définis le secret dans la variable d'environnement `GRAPH_CLIENT_SECRET`. Ne l'écris jamais dans un fichier du repo.

## Confidentialité

Les fichiers Excel, PDF et `.eml` sont exclus du repo par `.gitignore`. Les vraies données restent dans OneDrive/SharePoint.
