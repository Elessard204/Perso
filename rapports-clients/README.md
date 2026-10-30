# Rapports clients mensuels

Cet outil prépare l'envoi mensuel des rapports financiers aux clients à partir des exports Hopem. Il lit l'Excel des clients et associe chaque PDF exporté à son entité légale. Il bloque tout client à qui il manque un rapport, puis fusionne un PDF par entité (avec des signets pour chaque rapport) et prépare un courriel par client. Ce courriel part de finance@progim.com, avec le gestionnaire et les copies fixes en cc.

**L'outil n'envoie jamais rien lui-même.** En mode `simulation` (par défaut), il produit les PDF, un aperçu `.eml` de chaque courriel et un rapport de contrôle. En mode `brouillons`, il crée en plus les brouillons dans la boîte finance@. L'équipe les révise et clique Envoyer.

## Déroulement d'un mois

1. Exporter les rapports de Hopem dans un dossier du mois, par exemple `Rapports clients/2026-10/` sur SharePoint (synchronisé par OneDrive), sans renommer les fichiers.
2. Lancer l'outil :
   ```
   python envoi_rapports.py --mois 2026-10 --exports "<dossier du mois>" --clients "<Excel des clients>"
   ```
3. Ouvrir `sortie/2026-10/rapport.html`. Il montre les clients prêts, les clients bloqués avec la raison, et les fichiers non reconnus. Corriger ce qui bloque (export manquant, Excel à jour), puis relancer.
4. Quand tout est vert, relancer avec `--mode brouillons` et réviser les brouillons dans Outlook.

## L'Excel des clients

Il compte deux onglets. **Clients** a une ligne par client qui reçoit un courriel : `code_client`, `nom_client`, `nom_contact`, `courriel_a` et `courriel_cc` (plusieurs adresses séparées par `;`), `gestionnaire_nom`, `gestionnaire_courriel`, `langue` (FR/EN) et `actif` (Oui/Non). **Entites** a une ligne par entité légale Hopem : `code_entite` (le code tel qu'il apparaît dans les noms de fichiers Hopem), `nom_entite`, `code_client`, une colonne Oui/Non par rapport requis et `actif`. Un client avec trois entités reçoit un seul courriel avec trois PDF.

## Les contrôles qui bloquent un client

Un client est bloqué dans les cas suivants : un rapport coché dans l'Excel est absent du dossier, ou un rapport reçu n'est pas coché; deux fichiers existent pour le même rapport; une adresse courriel est invalide ou le courriel du gestionnaire manque; le code de l'entité n'apparaît pas dans le texte de la première page d'un PDF (fichier mal nommé ou mauvaise entité). Ce dernier contrôle protège contre le pire scénario : envoyer les états financiers d'un client à un autre.

## Ce qui se règle sans toucher au code

`config.toml` contient l'expéditeur, les copies fixes, l'objet du courriel, l'ordre des rapports dans le PDF et la façon de reconnaître un fichier Hopem par son nom (`motif`). Les textes des courriels sont dans `modeles/courriel_fr.html` et `modeles/courriel_en.html`.

## Essayer avec des données fictives

```
pip install -r requirements.txt
python demo/generer_demo.py
python envoi_rapports.py --mois 2026-10 --exports demo/exports/2026-10 --clients demo/clients_demo.xlsx
```

La démo contient volontairement un bilan manquant, un PDF qui porte le nom d'une entité mais le contenu d'une autre, un courriel invalide, un client inactif et deux fichiers non reconnus.

## Brancher Outlook (mode brouillons)

Il faut une application inscrite dans Entra ID, avec la permission d'application Microsoft Graph `Mail.ReadWrite` et le consentement administrateur. Limite ensuite cette application à la seule boîte finance@progim.com avec une stratégie d'accès d'application Exchange (`New-ApplicationAccessPolicy`), sinon elle pourrait écrire dans toutes les boîtes de l'organisation. Remplis `tenant_id` et `client_id` dans `config.toml`, et définis le secret dans la variable d'environnement `GRAPH_CLIENT_SECRET`. Ne l'écris jamais dans un fichier du repo.

## À confirmer avec de vrais exemples

Le format des noms de fichiers Hopem (`motif` dans `config.toml`) est une hypothèse, tout comme l'adresse courriel de Maxime. Il faut aussi savoir si le gestionnaire est le même pour toutes les entités d'un client, ou s'il varie par immeuble.
