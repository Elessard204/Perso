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
- **Transport** : un seul par technicien et par jour sur le bon. Un aller-retour au magasin n'en ajoute pas : la
  ligne de transport en trop est retirée (Hugo peut la remettre). Un trajet inscrit à 0 min compte quand même (le
  technicien s'est déplacé). Au-delà de 60 min, l'excédent passe en main-d'œuvre, sur la dernière ligne non modifiée
  du technicien (alerte : possible oubli de changer le statut). Le même immeuble le même jour sur deux bons est
  signalé (transport en double).
- **Entrées de travail de moins d'une minute** (clic par erreur) : ignorées pour le blocage « Facturer » et pour
  l'alerte « transport manquant ».
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
  l'alerte « transport manquant » tombe; la valeur totale fait foi. Quand Hugo supprime une ligne dans Progression,
  ses entrées perdent leur lien : sur un bon qui a une ligne modifiée à la main, ces entrées ne bloquent pas (cliquer
  « Facturer » recréerait les lignes en double).
- **Salaire fixe** (case dans Règles; Harry) : transport à 1, la route n'est jamais ajoutée en main-d'œuvre.
- **Bon d'information** : toutes les lignes à 0 $ (ménage au forfait Immoblox, refacturé par la comptabilité).
  Aucune correction ni alerte de facturation.
- **Produit au forfait** (liste dans Règles; « Bacs ordures / recyclage », 95 $ par semaine) : pas d'alerte « heures
  non facturées », « transport manquant » ni rabais.
- **Taux de base des techniciens** : pour estimer la rentabilité (avec charges, vacances et fériés). Inscrits le
  17 novembre 2026 à partir de la liste de paie, seulement dans le `regles.toml` de SharePoint, jamais dans Git :
  ce fichier ne doit plus être écrasé par la version du dépôt. Hugo les modifie dans Règles au besoin.

### Ajustements après les premiers résultats réels (17 novembre 2026, 32 bons, vraie IA)

Sur les 28 factures lues, extraction et majoration de 15 % exactes. Corrections : description du matériel
limitée aux articles (fournisseur, numéro et SKU dans la colonne Origine); ligne « Matériel acheté » à 0 $ du
technicien remplacée par la facture; date jour/mois inversée remise à l'endroit; alertes « facture incomplète »
(sans sous-total), « facture sans numéro » et « facture dans le futur »; « S/o », « Nou » = pas d'achat; tant que
« Facturer » n'est pas cliqué, seul le blocage s'affiche; notes texte et vidéos jointes ignorées sans alerte;
consignes de rédaction resserrées (pas de demande transformée en travail fait, pas de description des photos,
pas de formule creuse); raison courte pour les photos (coût). Question pour Hugo : les reçus de stationnement
se refacturent-ils ?

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

- entrées de temps pas encore envoyées à la facture, sur un bon sans ligne modifiée à la main (cliquer « Facturer »,
  puis réanalyser);
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

## 9. Jarvis (assistant) et journal d'améliorations

Bouton « Jarvis » dans le bandeau, et « Pourquoi ? » à côté de chaque alerte de la fiche. L'assistant
(`assistant.py`) répond aux questions sur l'usage et les règles à partir de `assistant_guide.md`, des règles en
vigueur (sans les taux des employés) et, quand une fiche est ouverte, du contexte du bon : lignes, règle qui a
produit chaque valeur, alertes, entrées de temps. Il explique et conseille; il ne modifie jamais un bon ni les
règles, et dit quand la réponse n'est pas dans ses sources. Même modèle que le reste de l'outil; le guide et
les règles sont mis en cache entre les questions (environ 2 à 5 cents par question). Chaque question et sa
réponse sont notées dans `_logiciel/questions/` (hors Git) et affichées dans l'onglet Historique : celles qui
reviennent montrent où une règle ou l'outil n'est pas clair. `assistant_guide.md` se met à jour à chaque
changement de règle.

Jarvis tutoie. En mode solution (question d'amélioration, alerte inutile, cas non prévu), il part du cas réel,
propose deux ou trois options avec avantage et risque, vérifie si l'idée est déjà notée et suggère de la noter.
Le bouton « Recommander une amélioration » fait rédiger par Jarvis un brouillon (titre, problème, cas,
solutions) que l'utilisateur vérifie avant d'enregistrer. Onglet Améliorations : la liste, un statut (Nouvelle,
À discuter, Retenue, Écartée, Faite) et une note par recommandation, export Excel pour les revues avec Éric,
Hugo et Claude. Journal par personne dans `_logiciel/recommandations/` (hors Git). L'outil « apprend » par ce
cycle : chaque décision retenue modifie l'outil ou les règles et s'ajoute à la section « Décisions prises » du
guide de Jarvis; Jarvis voit aussi les 40 dernières recommandations et leur statut.

## 10. Acceptation

En simulation sur un mois de bons déjà facturés par Hugo, comparer les propositions de l'outil avec ce qu'il a
réellement envoyé (lignes de matériel, heures, transports, alertes). Passage au mode réel quand l'écart est jugé
acceptable par la direction et Hugo.

**Essai sur octobre 2026 (17 novembre).** 154 bons transférés, reconstitués tels qu'après « Facturer », passés dans
l'outil (lecture seule, IA simulée : matériel et description non évalués). Corrections apportées : un transport par
technicien et par jour, entrées de travail de moins d'une minute ignorées, fusion faite dans Progression sans
blocage. Résultat sur les 115 bons facturés à l'heure : 46 identiques à Hugo, 10 à 0,25 h près (Hugo laisse parfois
quelques minutes sans arrondir), 9 où Hugo ajoute un transport signalé par l'outil, et environ 50 où Hugo s'appuie sur
de l'information absente des feuilles de temps : rabais et fusions (25 bons), heures ajoutées (19), aide qui n'a pas
poinçonné sur le bon (5 bons, 4 636 $). Les 7 bons de bacs et les 32 bons à 0 $ passent sans alerte. Sur les bons tels
que facturés par Hugo, l'outil ne change que 3 lignes (excédent de transport) et en bloque 6 (temps non facturé).
