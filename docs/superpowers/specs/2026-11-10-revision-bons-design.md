# Révision des bons de service : design

Version consolidée au 17 novembre 2026. Ce document décrit l'outil tel qu'il est, avec les règles confirmées par Hugo
(questionnaire du 14 novembre, cas à valider du 16 novembre). Le module de kilométrage a son propre document :
`2026-11-16-kilometrage-design.md`.

## 1. Le but

Avant la facturation, Hugo ouvrait chaque bon Progression Live et le corrigeait à la main : trier les pièces jointes
(factures ou photos), saisir le matériel des factures, arrondir les heures, ajuster les transports, corriger la
description. Le but est de le faire passer de la saisie au contrôle : l'outil prépare tout selon les règles, Hugo
ne traite que les exceptions qui demandent son jugement. Les garde-fous assurent que rien n'est oublié et que tout
respecte les règles.

## 2. Flux réel dans Progression

Le technicien passe le bon à « Terminé ». Hugo clique « Facturer » dans l'onglet Feuille de temps : Progression crée
une ligne par entrée de temps (activité « En route » → ligne Transport, « En cours » → ligne Main d'oeuvre). L'API
n'a pas d'équivalent à ce bouton : l'outil travaille après ce clic et bloque un bon dont des entrées de temps ne
sont liées à aucune ligne. Ensuite Hugo passe le bon à « Prêt à facturer », puis au 1er du mois à « Transférer au
système comptable » (logicId 700). Ces changements d'état restent faits par Hugo pour l'instant.

## 3. Règles de facturation

Toutes sont visibles et réglables dans l'onglet Règles (`_logiciel/regles.toml`).

- **Main-d'œuvre** : chaque ligne au 0,25 h supérieur, minimum 0,25 h; jamais réduite. Les entrées de temps (paie)
  ne sont jamais modifiées.
- **Transport** : quantité 1 par entrée « En route ». Au-delà de 60 min, l'excédent passe en main-d'œuvre, sur la
  dernière ligne non modifiée du technicien (alerte : possible oubli de changer le statut). Un seul transport par
  immeuble et par jour.
- **Tarifs selon le type de bon** : Appel de service = SMMP (65 $/h, 50 $ le transport); Maintenance = SELP (45 $/h,
  40 $). SRP (rénovations, 85 $/h, 50 $) n'est jamais appliqué automatiquement. Seul le taux que Progression met par
  défaut est corrigé; tout autre taux a été choisi par quelqu'un : il est gardé et signalé s'il est hors grille.
- **Matériel acheté** : une ligne par facture, quantité 1, articles en description, prix = sous-total avant taxes
  (écofrais, consignes et livraison compris) + 15 %. Une ligne « Matériel acheté » vide existante est réutilisée;
  une ligne vide inutile est retirée. Chaque ligne porte un `externalId` (`fournisseur|numéro`) pour empêcher qu'une
  facture soit refacturée deux fois.
- **Matériel en inventaire** : prix estimé par Hugo. Une ligne à 0 $ veut dire qu'il n'y a pas de matériel. Un achat
  déclaré et facturé en inventaire n'a jamais de facture : pas d'alerte « achat sans facture ».
- **Description** : le champ réécrit est la « Note technicien » (`properties.info.notes`). L'IA corrige ou résume
  sans inventer, garde quantités, emplacements, équipements et numéros de modèle, et s'appuie sur la demande de
  départ et les photos; chaque détail tiré d'une photo est signalé « à vérifier ». Les notes internes restent pour
  le bureau.
- **Journées fusionnées** : Hugo regroupe parfois plusieurs visites sur une ligne en gardant la même valeur (deux
  visites de 2 h → 4,75 h et un transport). Une ligne de main-d'œuvre dont la quantité ne correspond ni au temps
  créé par « Facturer » ni à ce temps arrondi au 0,25 h (tolérance 0,01 h), ou qui n'a aucune entrée liée, est une
  ligne modifiée à la main : l'outil n'y touche plus (ni arrondi, ni excédent de transport). Sur un bon fusionné,
  l'alerte « transport manquant » tombe; la valeur totale fait foi.
- **Salaire fixe** (case dans Règles; Harry) : transport à 1, la route n'est jamais ajoutée en main-d'œuvre.
- **Bon d'information** : toutes les lignes à 0 $ (ménage au forfait Immoblox, refacturé par la comptabilité).
  Aucune correction ni alerte de facturation.
- **Produit au forfait** (liste dans Règles; « Bacs ordures / recyclage », 95 $ par semaine) : pas d'alerte « heures
  non facturées », « transport manquant » ni rabais.
- **Taux de base des techniciens** : inscrits par Hugo dans Règles, pour estimer la rentabilité (avec charges,
  vacances et fériés).

## 4. Garde-fous

Ils passent le bon « À vérifier », avec la raison :

- tarif hors grille pour le type de bon, ou type sans tarif;
- transport long (excédent ajouté en main-d'œuvre), transport manquant, transport en double (même technicien, même
  immeuble, même jour), excédent sans ligne de main-d'œuvre où l'ajouter;
- rabais : main-d'œuvre et transport facturés sous la valeur du temps inscrit de plus du seuil (50 $). Hugo peut
  inscrire une raison; le relevé des rabais est dans l'onglet Historique;
- rentabilité : bon sans revenu, à perte ou sous la marge minimale;
- facture : total des lignes ≠ sous-total (écart > 0,05 $), date à plus de 30 jours du bon, ligne > 1 000 $, pièce
  jointe incertaine;
- champ « Achat » du technicien contredit par les pièces jointes (achat déclaré sans facture, ou « Non » avec une
  facture);
- plus de 12 h pour un technicien dans une journée;
- description créée ou enrichie par l'IA (à vérifier), ou révision impossible (original gardé).

Ils bloquent le bon :

- entrées de temps pas encore envoyées à la facture (cliquer « Facturer », puis réanalyser);
- bon sans aucune heure;
- même facture jointe deux fois au bon, ou déjà refacturée dans un autre bon (journal local + `externalId` dans
  Progression).

## 5. Ce qui reste manuel (jugement d'Hugo)

Le clic « Facturer » et les changements d'état dans Progression; le prix du matériel en inventaire; les journées
fusionnées et les rabais (l'outil les reconnaît et les signale); les plafonds de soumission; la refacturation à un
locataire; les minuteries oubliées (corrigées par Hugo dans Progression, jamais réduites par l'outil).

## 6. API Progression

Adresse propre à Progim : `https://progim.progressionlive.com/server/rest`, authentification
`Authorization: Bearer <clé>`.

| Besoin | Route |
|---|---|
| Lister les bons | `GET /task/list` (`logicId`, `type`, `rv`; 500 résultats par page) |
| Lire un bon | `GET /task/{id}`, entrées de temps `GET /task/{id}/timeEntries` |
| Pièces jointes | `GET /task/attachment/{id}` (base64) |
| Produits | `GET /product/list` : Main d'oeuvre, Transport, Matériel acheté, Matériel en inventaire, Bacs ordures / recyclage, Chauffe-eau |
| Écrire | `POST /task/{id}/update` |
| Retrouver une facture déjà refacturée | `GET /task/list?itemExternalId=` |

Règles d'intégration : ne jamais envoyer `null` (efface la donnée), filtrer plutôt que tout lire. Réponse de
Progression (11 novembre 2026) : la liste de lignes reçue par `update` REMPLACE toutes les lignes (nouveaux ids,
totaux et taxes recalculés). L'outil renvoie donc chaque ligne existante au complet, et une ligne existante absente
de la proposition bloque l'écriture.

## 7. Architecture

Outil local, même modèle que « Rapports clients » : Python portable lancé par un `.bat`, serveur local avec jeton,
interface dans le navigateur, design Progim. Dossier partagé SharePoint « Révision des bons ».

| Module | Rôle |
|---|---|
| `progression.py` | Seul module qui parle à Progression |
| `claude_client.py`, `pieces_jointes.py`, `redaction.py` | Seuls modules qui appellent Claude : classement et lecture des factures, révision de la description |
| `regles.py`, `facturation.py` | Règles et garde-fous, fonctions pures sans réseau |
| `analyse.py` | Assemble la proposition d'un bon (cache par bon, date de modification et règles) |
| `envoi.py` | Construit et écrit les mises à jour |
| `journal.py` | Historique partagé, un fichier JSONL par personne |
| `kilometrage.py`, `km_calcul.py`, `km_declare.py`, `cartes.py`, `excel.py` | Module de kilométrage |
| `interface.py` + `interface.html` | Serveur et page : À réviser, Kilométrage, Règles, Historique |

Les clés API sont dans le profil Windows de la personne, jamais dans le dossier partagé ni dans le dépôt. Pièces
jointes et textes envoyés à l'API Claude (pas d'entraînement sur ces données). Clés, caches et journaux exclus du
dépôt.

## 8. Écriture dans Progression

Rien n'est écrit sans l'approbation d'Hugo. Le mode simulation est le mode par défaut. En réel, l'outil relit le
bon, vérifie qu'il n'a pas changé depuis l'analyse (sinon retour « À vérifier »), écrit, puis inscrit au journal.
L'écriture réelle reste verrouillée (`ecriture_validee = false`) jusqu'à l'essai dans l'environnement de test de
Progression, à partir du 27 novembre 2026, avec Hugo. À y vérifier : qu'une ligne générée par une entrée de temps
garde son lien une fois recréée.

## 9. Acceptation

En simulation sur un mois de bons déjà facturés par Hugo, comparer les propositions de l'outil avec ce qu'il a
réellement envoyé (lignes de matériel, heures, transports, alertes). Passage au mode réel quand l'écart est jugé
acceptable par la direction et Hugo.
