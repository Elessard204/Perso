# Rapports clients mensuels

Cet outil prépare l'envoi mensuel des rapports financiers aux clients. Sabrina télécharge déjà de Hopem un PDF combiné par entité (« Rapports mensuels Sept 2026_05401.pdf ») dans `ÉTATS FINANCIERS/1_CLIENTS/<mois>`. L'outil prend le relais à partir de là.

Il associe chaque PDF à son entité grâce aux 5 derniers chiffres (05401 = 54.1). Il vérifie ensuite le contenu du PDF et regroupe les entités qui ont les mêmes destinataires. Il prépare enfin un courriel par client, qui part de finance@progim.com avec le gestionnaire et la direction en cc.

**L'outil n'envoie jamais rien lui-même.** En mode `simulation` (par défaut), il produit un aperçu `.eml` de chaque courriel et un rapport de contrôle. En mode `brouillons`, il crée en plus les brouillons dans la boîte finance@, que l'équipe révise et envoie.

## Déroulement d'un mois

1. Avant de télécharger les rapports de Hopem, sortir la liste des périodes à extraire. Chaque entité a sa propre fin d'exercice, donc septembre est la période 9 pour une fin en décembre, la période 5 pour une fin en avril, etc.
   ```
   python envoi_rapports.py --mois 2026-09 --clients clients_rapports.xlsx
   ```
2. Télécharger les rapports de Hopem comme d'habitude, sans changer les noms de fichiers.
3. Lancer l'outil sur le dossier du mois :
   ```
   python envoi_rapports.py --mois 2026-09 --clients clients_rapports.xlsx --exports "<...>/1_CLIENTS/09-septembre 2026"
   ```
4. Ouvrir `sortie/2026-09/rapport.html`. Il montre les courriels prêts, ceux qui sont bloqués avec la raison, les fichiers non reconnus et les entités sans envoi ce mois-ci. Corriger ce qui bloque, puis relancer.
5. Quand tout est vert, relancer avec `--mode brouillons` et réviser les brouillons dans Outlook.

## Les contrôles

Un courriel est bloqué si une de ses entités est dans un des cas suivants :

- aucun PDF dans le dossier, ou deux PDF pour la même entité;
- le nom du fichier n'est pas celui du mois envoyé;
- le PDF ne contient pas le bilan ou l'état des résultats;
- le bilan n'est pas au dernier jour du mois;
- la période de l'état des résultats ne correspond pas à la fin d'exercice de l'Excel;
- le nom du propriétaire imprimé en haut du PDF n'est pas celui de la colonne `nom_hopem`.

Ce dernier contrôle protège contre le pire scénario : un PDF enregistré sous le mauvais numéro, qui partirait chez le mauvais client. Tant que `nom_hopem` est vide, l'outil affiche le nom trouvé dans le PDF pour qu'on l'inscrive, sans bloquer.

Un courriel est aussi bloqué si une adresse courriel est invalide.

## L'Excel des clients

Il est créé à partir du fichier de suivi actuel par `importer_excel.py` (voir plus bas) et compte trois onglets.

- **Clients** : une ligne par courriel envoyé, avec `code_client`, `nom_client`, `nom_contact` (pour « Bonjour Julie », facultatif), `courriel_clients`, `courriel_direction` (vide = `direction_defaut` de `config.toml`), `langue` et `actif`.
- **Entites** : une ligne par entité Hopem, avec `code_entite` (54.1), `nom_entite`, `nom_hopem`, `code_client`, `fin_exercice` (mois de 1 à 12), `frequence` (mensuel, trimestriel, semestriel ou annuel), `gestionnaire`, `courriel_gestionnaire` (facultatif, remplace celui de l'onglet Gestionnaires), `actif`, `notes` et `immeubles`.
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
