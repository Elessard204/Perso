# Révision des bons de service avant facturation : design

Date : 2026-11-10
Statut : à relire par la direction avant le plan de développement
Suite : le suivi du kilométrage des techniciens est décrit dans `docs/superpowers/specs/2026-11-16-kilometrage-design.md`.

## 0. Version 2 — règles confirmées par Hugo (questionnaire du 2026-11-14)

Cette section remplace ce qui la contredit plus bas (sections 2, 6 et 7).

- **Flux réel.** Le technicien passe le bon à « Terminé ». Hugo clique « Facturer » dans l'onglet Feuille de
  temps : Progression crée une ligne par entrée de temps (activité « En route » → ligne Transport,
  « En cours » → ligne Main d'oeuvre). L'API n'a pas d'équivalent à ce bouton : l'outil travaille après ce clic
  et bloque un bon dont des entrées de temps ne sont liées à aucune ligne. Ensuite Hugo passe le bon à
  « Prêt à facturer », puis au 1er du mois à « Transférer au système comptable » (logicId 700).
- **Transport** : quantité 1 par entrée; au-delà de 60 min, l'excédent passe en main-d'œuvre (alerte :
  possible oubli de changer le statut).
- **Main-d'œuvre** : chaque ligne au 0,25 h supérieur, minimum 0,25; jamais réduite.
- **Tarifs selon le type de bon** (vérifié sur 80 bons transférés) : Appel de service = SMMP (65 $/h,
  50 $ le transport); Maintenance = SELP (45 $/h, 40 $). SRP (rénovations, 85 $/h, 50 $) n'est jamais appliqué
  automatiquement : un taux hors grille est gardé et signalé. Question en attente : SRP a-t-il son propre type?
- **Matériel acheté** : une ligne par facture, quantité 1, articles en description, prix = sous-total avant
  taxes (écofrais, consignes et livraison compris) + **15 %**. Une ligne « Matériel acheté » vide existante est
  réutilisée; une ligne vide inutile est retirée.
- **Description** : le champ à réviser est la « Note technicien » (`properties.info.notes`, clé à plat).
  L'IA s'appuie aussi sur la demande de départ et sur les photos; chaque détail tiré d'une photo est listé et
  signalé « à vérifier ».
- **Garde-fous ajoutés** (objectif : ne rien oublier de facturer, département autosuffisant) : heures non
  envoyées à la facture (bloquant), transport manquant, transport en double (même technicien, même immeuble,
  même jour), taux non conforme au type, matériel en inventaire à 0 $, rentabilité estimée par bon (revenu
  contre coût horaire des techniciens et coût du matériel; alerte si à perte ou sous la marge minimale). Le
  garde-fou du champ « Achat » est conservé à la demande de la direction.
- **Reste manuel** : prix du matériel en inventaire, fusion d'heures pour certains clients, plafonds de
  soumission, refacturation à un locataire.
- **Prochaine étape envisagée** : calcul automatique du kilométrage de la paie (trajets journaliers par
  technicien), deuxième plus gros irritant de Hugo.

## 1. Le problème

Avant d'envoyer un bon de service Progression Live à la facturation, Hugo
l'ouvre et le corrige à la main, un bon à la fois :

1. il ouvre chaque pièce jointe une par une pour séparer les factures d'achat de
   matériel des photos avant/après;
2. il saisit à la main chaque matériau des factures dans le bon pour le
   refacturer, au coût plus 10 %;
3. il arrondit les heures facturées de chaque technicien au quart d'heure
   supérieur;
4. il ajuste le nombre de transports;
5. il corrige l'orthographe et la syntaxe de la description des travaux, ou la
   résume quand elle est confuse.

L'étape 1-2 est la plus longue. Le but est de faire passer Hugo de la saisie au
contrôle : l'outil prépare tout, Hugo valide.

## 2. Ce qui est décidé

| Sujet | Décision |
|---|---|
| Forme | Outil local, même modèle que « Rapports clients » : Python portable lancé par un `.bat`, serveur local, interface dans le navigateur, design Progim. |
| Arrondi | Au 15 minutes supérieur, **par technicien**, sur son temps total dans le bon (2 h 05 → 2 h 15; 2 h 15 reste 2 h 15; 0 h 01 → 0 h 15). |
| Portée de l'arrondi | **Heures facturées seulement.** Les entrées de temps (feuilles de temps, paie) ne sont jamais modifiées. |
| Matériel | Coût d'achat avant taxes + 10 %. Taxes, écofrais et consignes de la facture fournisseur ignorés par défaut (réglable). |
| Transports | Règle à définir par Hugo. D'ici là, la valeur actuelle est gardée et le bon est signalé. |
| Réécriture | Corriger orthographe et syntaxe; résumer clairement si le texte est confus. Ne jamais inventer un travail; garder intacts quantités, emplacements, équipements, numéros de modèle. |
| Onglet Règles | Toutes les règles et tous les garde-fous visibles; les paramètres (marge, pas d'arrondi, seuils, règle des transports) modifiables. |
| Validation | Rien n'est écrit dans Progression sans approbation de Hugo. Mode simulation par défaut. |
| Passage en facturation | Reste fait par Hugo dans Progression au début; automatisable plus tard. |

## 3. Ce que l'API Progression permet (vérifié dans le Swagger)

Source : `https://api.progressionlive.com/server/rest/spec.json` (OpenAPI 3.0,
201 routes). Authentification par `Authorization: Bearer <clé>`, forfait Premium.

| Besoin | Route / champ | Constat |
|---|---|---|
| Lister les bons terminés | `GET /task/list` avec `logicId`, `type`, `rv`, `updated`, `expand`; 500 résultats max par page (`startResult`) | ✔ |
| Lire un bon | `GET /task/{id}` : `description`, `summary`, `properties` (champs propres au type), `itemList.items[]`, `attachments[]`, `currentState.logicId` | ✔ |
| Pièces jointes | `Task.attachments[]` (nom, type MIME) puis `GET /task/attachment/{id}` : contenu en base64 | ✔ |
| Lignes facturables | `TaskItem` : `label`, `description`, `quantity`, `price`, `unitCost`, `taxable`, `product`, `type` | ✔ `unitCost` = coût, `price` = coût × 1,10; Progression calcule la marge |
| Heures facturées vs paie | `TimeEntry.item` = « ligne générée à la facturation de l'entrée de temps » | ✔ Les heures facturées sont des `TaskItem` distincts des `TimeEntry`. On modifie la quantité de la ligne, jamais l'entrée de temps. |
| Écrire | `POST /task/{id}/update` (« seuls les champs fournis sont modifiés ») | ✔ à confirmer pour `itemList` (voir 9) |
| Statut | `POST /task/{id}/state`, `GET /task/{id}/transitions` | ✔ non utilisé au début |
| Commentaire | `POST /task/{id}/comment/create` | ✔ possible pour laisser une trace dans le bon |

Règles d'intégration de Progression à respecter : ne jamais envoyer de valeur
`null` (efface la donnée), filtrer les requêtes plutôt que tout lire.

## 4. Architecture

Dossier `revision-bons/` à la racine du dépôt, même organisation que
`rapports-clients/` : à la racine seulement `Révision des bons.bat` et la
procédure; le reste dans `_logiciel/`.

Quatre modules indépendants, chacun testable seul :

| Module | Rôle | Dépend de |
|---|---|---|
| `progression.py` | Client de l'API : lister et lire les bons, télécharger les pièces jointes, écrire les corrections. Seul module qui parle à Progression. | clé API |
| `pieces_jointes.py` | Avec Claude : classer chaque pièce jointe (facture / photo / incertain), extraire fournisseur, numéro, date, sous-total et lignes (description, quantité, prix unitaire avant taxes). | clé API Claude |
| `regles.py` | Fonctions pures, sans réseau : arrondi par technicien, prix avec marge, transports, garde-fous. Lit ses paramètres dans `regles.toml`. | rien |
| `redaction.py` | Avec Claude : corriger ou résumer la description; contrôle « aucun chiffre absent de l'original ». | clé API Claude |

`interface.py` + `interface.html` assemblent le tout (serveur local, comme
`rapports-clients`). `journal.py` tient l'historique.

Les clés API (Progression, Claude) sont dans le profil Windows de la personne,
jamais dans le dossier partagé ni dans le dépôt.

## 5. Interface

**À réviser.** Liste des bons de la période avec leur statut : `À analyser`,
`Prêt`, `À vérifier` (avec la raison), `Bloqué`, `Envoyé`. Case « tout cocher »
pour approuver en lot les bons prêts. Au clic sur un bon : original à gauche,
proposition à droite (description, heures facturées par technicien, transports,
lignes de matériel); chaque facture affichée à côté des lignes qu'on en a
tirées; chaque valeur proposée indique la règle qui l'a produite. Tout champ est
modifiable; la modification de Hugo l'emporte toujours.

**Règles.** Les règles et les garde-fous en clair, avec leurs paramètres
modifiables.

**Historique.** Ce qui a été approuvé et écrit dans Progression, par qui, quand,
avec le texte original du technicien et les valeurs avant/après.

## 6. Parcours d'un bon

1. **Récupération** : Hugo choisit une période; `GET /task/list` filtré sur
   l'état « terminé, à facturer » (logicId à confirmer, voir 9). Lecture seule.
2. **Analyse** : téléchargement des pièces jointes dans un dossier temporaire du
   profil; classement et extraction; réécriture; calcul des règles. Barre de
   progression. Résultat mémorisé par bon (clé : id + date `updated`) pour ne
   pas repayer l'analyse.
3. **Révision** par Hugo (section 5).
4. **Envoi** : en simulation, un rapport de ce qui serait écrit. En réel :
   relire le bon, vérifier que `updated` n'a pas changé depuis l'analyse (sinon
   retour en `À vérifier`), puis `POST /task/{id}/update` avec la description et
   les lignes (heures facturées, transports, matériel). Chaque ligne de matériel
   ajoutée porte un `externalId` dérivé de la facture
   (`fournisseur|numéro|ligne`) pour éviter tout doublon. Inscription au journal.

## 7. Garde-fous

Passent le bon en `À vérifier` (seuils modifiables dans Règles) :

- total des lignes extraites ≠ sous-total de la facture (écart > 0,05 $);
- pièce jointe illisible ou classement incertain;
- date de facture à plus de 30 jours de la date du bon;
- ligne de matériel > 1 000 $;
- technicien avec plus de 12 h dans une même journée;
- règle des transports non définie;
- la réécriture contient un nombre ou une unité absents du texte original.
- le technicien déclare un achat (champ « Achat ») mais aucune facture n'est trouvée
  dans les pièces jointes, ou il répond « Non » alors qu'une facture est trouvée
  (champ vide : aucune comparaison).

Bloquent le bon :

- même facture (fournisseur + numéro) déjà refacturée dans un autre bon
  (journal local + `itemExternalId` dans Progression);
- bon sans aucune heure.

## 8. Erreurs et confidentialité

- Progression ou Claude indisponible, clé invalide : message clair, rien n'est
  écrit. Un bon dont l'analyse échoue reste `À analyser` et se relance d'un clic.
- Écriture coupée en cours de lot : chaque bon est écrit séparément et inscrit
  au journal; la reprise saute les bons déjà écrits.
- Pièces jointes et textes envoyés à l'API Claude pour analyse (conditions
  commerciales : pas d'entraînement sur ces données). Clés, pièces jointes,
  journaux et caches exclus du dépôt par `.gitignore`.

## 9. À confirmer avec de vraies données (première étape du développement)

Dès que la clé API est reçue, un script en **lecture seule** inspecte 5 à 10
vrais bons déjà facturés pour confirmer :

1. le `logicId` de l'état « terminé, à facturer » et le type de tâche des bons de
   service;
2. où le technicien écrit sa description (`description`, `summary`, un champ de
   `properties` ou les commentaires);
3. comment les heures facturées apparaissent dans `itemList` (une ligne par
   technicien ou une seule ligne, `type` de la ligne, produit « main-d'œuvre »);
4. comment les transports apparaissent (produit, quantité);
5. ~~le comportement de `POST /task/{id}/update` sur `itemList`~~ **Réponse de
   Progression (2026-11-11) : la liste reçue REMPLACE toutes les lignes.** Le système
   supprime les lignes et recrée la facture (nouveaux ids, totaux et taxes recalculés);
   aucune méthode pour modifier une seule ligne. Conséquence dans l'outil : chaque ligne
   existante est renvoyée au complet (tous ses champs sauf ceux en lecture seule), et une
   ligne existante absente de la proposition bloque l'écriture. Reste à vérifier dans la
   sandbox : qu'une ligne générée à partir d'une entrée de temps garde son lien
   (`TimeEntry.item`) une fois recréée;
6. s'il existe un produit générique « Matériel » à utiliser pour les lignes
   refacturées, et la configuration de taxes à leur appliquer;
7. que l'ajout d'une pièce jointe ou d'une entrée de temps change bien le champ
   `updated` du bon (la protection « bon modifié depuis l'analyse » en dépend);
8. que `GET /task/list?itemExternalId=` retrouve bien un bon par l'externalId
   d'une de ses lignes (détection des factures déjà refacturées).

Le design s'ajuste selon les réponses avant d'écrire le reste.

## 10. Tests et critère d'acceptation

- Tests automatiques de `regles.py` : cas d'arrondi (2 h 05, 2 h 15, 0 h 01,
  plusieurs techniciens), marge 10 % avant taxes, chaque garde-fou.
- Données fictives (bons, photos, fausses factures) pour essayer l'outil sans
  Progression, comme `rapports-clients/_logiciel/demo`.
- **Acceptation** : en simulation sur un mois de bons déjà facturés par Hugo,
  comparer les propositions de l'outil avec ce que Hugo a réellement envoyé
  (classement des pièces jointes, lignes de matériel, heures). Passage au mode
  réel seulement quand l'écart est jugé acceptable par la direction et Hugo.

## 11. Hors de portée (pour l'instant)

Passage automatique à l'état facturé; webhooks; version hébergée multi-postes;
autres irritants Progression. La logique (`regles.py`, `pieces_jointes.py`,
`redaction.py`) est écrite pour être réutilisée telle quelle dans une version
hébergée.

## 12. Réponses d'Hugo aux cas à valider (16 novembre 2026)

Hugo a répondu au document « Cas à valider - Hugo.docx ». Les cas relevés à l'essai à blanc sont presque tous des
choix voulus. L'outil les accepte maintenant au lieu de les signaler.

**Journées fusionnées.** Hugo regroupe parfois plusieurs visites sur une seule ligne de main-d'œuvre. Il garde la même
valeur : deux visites de 2 h deviennent 4,75 h et un transport (50 + 4,75 × 65 = 358,75 $, contre 360 $). Une ligne
de main-d'œuvre qui ne correspond plus au temps créé par « Facturer », ni à ce temps arrondi au 0,25 h, est une ligne
modifiée à la main. Une ligne sans entrée liée l'est aussi. L'outil n'y touche plus : ni arrondi, ni excédent de
transport. Sur un bon fusionné (ligne modifiée, ou entrée dont la ligne a été retirée), l'alerte « transport
manquant » par journée tombe. La valeur totale fait foi.

**Rabais.** L'outil compare la main-d'œuvre et le transport facturés à la valeur du temps inscrit, calculée avec les
règles : main-d'œuvre par technicien et par jour au 0,25 h supérieur, excédent de transport compris, et un transport
par entrée « En route ». Au-delà du seuil (Règles, 50 $ par défaut), une alerte non bloquante donne le rabais. Hugo
peut inscrire une raison facultative. Chaque approbation garde le rabais et sa raison. L'onglet Historique montre le
relevé des rabais (dernière approbation de chaque bon). Ce relevé répond à la demande d'Éric de voir les rabais
consentis (devis, client plafonné, anticipation).

**Salaire fixe.** Un technicien coché « Salaire fixe » dans Règles (Harry) a des heures de route ajustées sur sa
feuille de temps pour arriver à 40 h. Son transport reste à 1, et sa route n'est jamais ajoutée en main-d'œuvre
(pas d'alerte « transport long »).

**Forfaits.**
- Un bon dont toutes les lignes sont à 0 $ est un bon d'information : ménage au forfait Immoblox, refacturé par la
  comptabilité. L'outil ne le corrige pas et ne le signale pas (ni tarif, ni « sans revenu », ni « à perte »).
- Un bon qui contient un produit au forfait inscrit dans Règles (bacs à 95 $ par semaine) n'a pas d'alerte
  « heures non facturées », « transport manquant » ou rabais. Le nom exact du produit reste à confirmer dans
  Progression.

**Matériel.** Une ligne « Matériel en inventaire » à 0 $ veut dire qu'il n'y a pas de matériel : l'alerte est
retirée. Un achat déclaré et facturé en inventaire n'a jamais de facture, puisqu'Hugo l'estime : il n'y a pas
d'alerte « achat sans facture ».

**Confirmé, sans changement.**
- Hugo clique « Facturer » lui-même avant l'analyse : le blocage reste.
- Il corrige les minuteries oubliées dans Progression : aucune réduction d'heures dans l'outil.
- La « Note technicien » (`properties.info.notes`) est le champ réécrit. Les notes internes restent pour le bureau.
- Un seul transport par immeuble et par jour.
- Hugo inscrit lui-même les taux horaires.
- Il est disponible pour l'essai dans l'environnement de test à partir du 27 novembre.
