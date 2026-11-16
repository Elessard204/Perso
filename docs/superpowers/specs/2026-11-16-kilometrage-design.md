# Kilométrage des techniciens : calcul et contre-vérification (design)

Date : 2026-11-16. Demandé par Éric (propriétaire). Utilisateur principal : Hugo (coordonnateur des services
techniques). Destinataire du résultat : Sabrina (directrice des finances, paie dans Netris).
Notes de départ et réponses de Hugo : `2026-11-16-kilometrage-notes.md`.

## 1. Intention

Aux deux semaines, les techniciens sont payés au kilomètre pour leurs déplacements avec leur véhicule
personnel. Éric veut un garde-fou : ne pas payer de façon aveugle, détecter une erreur de saisie ou un
kilométrage gonflé.

Situation réelle (Hugo) : le km inscrit par les techniciens dans Progression n'est jamais consulté. Hugo
refait chaque journée de chaque technicien dans Google Maps à partir de la feuille de temps globale,
ajoute de mémoire les arrêts au magasin, et c'est ce km qui est payé. C'est long et repose sur sa mémoire.

Le nouvel outil fait donc deux choses (approche C retenue par Éric) :
1. **Calculer le km à payer** de chaque technicien sur la période, à partir des visites inscrites dans
   Progression, avec la règle de Hugo. Hugo complète (magasin, jours Uhaul), valide, exporte pour Sabrina.
2. **Afficher le km déclaré par le technicien à côté** et signaler les écarts au-delà d'un seuil que Hugo
   règle lui-même.

## 2. Objectifs, non-objectifs, anti-objectifs

Objectifs
- Remplacer le travail manuel de Hugo dans Google Maps pour une période de paie complète.
- Montant à payer par technicien, au taux en vigueur, prêt à transmettre à Sabrina en Excel.
- Écarts entre le km déclaré et le km calculé visibles d'un coup d'œil, avec un seuil réglable.
- Chaque journée vérifiable : l'ordre des immeubles visités et la distance de chaque trajet.

Non-objectifs (version 1)
- Aucune écriture dans Progression (lecture seule).
- Pas d'intégration directe à Netris : un fichier Excel que Sabrina saisit ou importe.
- Pas de déduction automatique des arrêts au magasin (trop de variables selon Hugo) : saisie manuelle.
- Pas de modification des heures : elles sont lues telles quelles dans Progression (Hugo les corrige dans
  Progression lors de sa consolidation). L'export reprend la feuille de temps hebdomadaire de Progression
  (vérifié : mêmes totaux à la minute près, semaine du 2026-10-04) en y ajoutant le km à payer.

Anti-objectifs (échec même si « ça marche »)
- Un montant à payer faux ou changé sans trace. Toute correction manuelle est inscrite à l'historique.
- Des adresses personnelles d'employés dans le dépôt Git ou dans un fichier partagé lisible par tous.
- Un flot d'alertes inutiles qui pousse Hugo à ignorer l'outil.

## 3. Règles (fournies par Hugo)

- Trajet payé, pour chaque jour travaillé : domicile → premier immeuble → … → dernier immeuble → domicile.
  Toujours présumé, même si l'ouvrier ne part pas de chez lui ou n'y retourne pas.
- Exception : un jour où l'ouvrier utilise un véhicule loué (Uhaul) n'est pas payé. Coché par Hugo.
- Taux : 0,61 $/km (réglable dans Règles).
- Période : deux semaines, du dimanche au samedi. La date de début d'une période de référence est réglable
  (Règles); l'outil propose la période courante et la précédente.
- Arrêts au magasin : km ajoutés à la main par Hugo, par jour.
- Seuil d'écart : un nombre de km par technicien et par période (défaut 10 km), réglable par Hugo dans
  Règles. Le bon est signalé si |km déclaré − km à payer| dépasse ce seuil. Pas de seuil en pourcentage.

## 4. Données

Progression (API REST, base `https://progim.progressionlive.com/server/rest`, même clé que la révision des bons)
- `GET /timeEntry/list?start=<début>,<fin>` donne toutes les entrées de temps de la période (500 par page,
  paginer avec `startResult`). Champs utiles : `humanResource`, `activity` (« En route », « En cours »),
  `start`, `duration`, `task` (id, code). 137 entrées pour une semaine réelle.
- Les coordonnées GPS de l'immeuble sont sur la tâche : `clientAddress.position` (latitude, longitude);
  `locationAddress` pour le logement. Lire chaque tâche une seule fois (cache par id).
- Km déclaré : `properties.info.km` de la tâche, texte libre, par bon (pas par jour), parfois cumulé sur
  plusieurs jours, souvent vide sur les bons de maintenance. `info.km_retour` existe mais est vide partout.
- Les entrées ont des champs `punchInPosition` / `punchOutPosition`, vides chez Progim (la géolocalisation
  au pointage n'est pas activée). Hors de la version 1; piste à proposer à Éric plus tard.

Domicile des techniciens
- Code postal complet à 6 caractères (ex. J4W 3J9) par technicien, saisi par Hugo dans l'onglet Règles.
  Précision suffisante (environ 1 km par jour en ville). Refuser un code à 3 caractères.
- Stocké avec les clés, dans le profil Windows de la personne (`%APPDATA%\ProgimRevisionBons`), jamais
  dans le dossier SharePoint partagé ni dans Git. Conséquence acceptée : saisi sur chaque poste qui
  utilise l'onglet (en pratique, celui de Hugo).
- Admissibilité : chaque technicien vu dans la période apparaît dans Règles avec une case « Employé Progim
  (sur la paie, payé au km) » et son code postal. Tous les employés sur la paie sont payés au km (seule
  exception : les jours Uhaul). Les sous-traitants (rayés sur la feuille de temps de Hugo, ex. Toufik
  Bessaci, Takfarinas Challal, Djamal Guenane) ont la case décochée : statut « sous-traitant », aucun km,
  exclus de l'export. Un technicien jamais configuré, ou coché sans code postal : statut « à configurer »,
  aucun montant. Rien n'est payé par défaut.

Google Maps
- Géocodage des codes postaux (Geocoding API), une fois par code, gardé en cache dans le profil.
- Distances routières (Routes API, calcul de matrice ou d'itinéraire), mises en cache par paire de
  coordonnées arrondies. Volume estimé : environ 400 trajets par période, dans la portion gratuite.
- Clé API Google saisie dans l'onglet Règles, section Connexions, comme les autres clés.

## 5. Calcul

Pour chaque technicien et chaque jour de la période :
1. Prendre ses entrées de temps du jour, triées par `start`.
2. En tirer la suite des immeubles visités (adresse de la tâche de chaque entrée), en fusionnant les
   visites consécutives au même immeuble. Une entrée sans tâche, ou dont la tâche n'a pas de position GPS,
   n'est pas un arrêt : elle est ignorée et le jour est marqué « à vérifier » avec la raison, pour que Hugo
   ajoute les km à la main au besoin.
3. Trajet : domicile → immeubles dans l'ordre → domicile. Distance routière de chaque tronçon.
4. Km du jour = somme des tronçons + km magasin saisis par Hugo; 0 si le jour est coché Uhaul.

Par technicien et par période : km calculé, km magasin, km à payer, montant (km à payer × taux),
km déclaré, écart, statut.

Km déclaré
- Pour chaque bon dont au moins une entrée du technicien tombe dans la période, lire `info.km`.
- Nombre simple (« 60km », « 25 KM », « 49 ») : lecture directe. Texte ambigu (« 52 pour les deux jours »,
  « +14km achat + 6km… ») : lu par l'IA (Claude) qui renvoie un nombre et une confiance; si la confiance
  est faible, la valeur est marquée « à vérifier » et montrée telle quelle.
- Un bon dont les jours débordent la période : le km déclaré est réparti au prorata des jours travaillés
  dans la période (règle de l'outil, affichée dans le détail).
- Bon partagé par plusieurs techniciens (un seul champ km par bon, auteur inconnu) : son km déclaré n'est
  attribué à personne; il est exclu de la comparaison et affiché dans le détail « partagé, non attribué ».
- Bon sans km déclaré : compté 0 et marqué « non déclaré ». Un technicien sans aucune déclaration n'est pas
  signalé en écart (constat, pas alerte).

## 6. Écran (nouvel onglet « Kilométrage » dans l'outil Révision des bons)

```
Kilométrage — période du dim. 8 au sam. 21 novembre 2026          Taux : 0,61 $/km
Technicien   Jours  Km calculé  Magasin  Km à payer  Montant    Km déclaré  Écart
Igor H.        9       612        +18        630     384,30 $      655       +25 km
Vadim Z.      10       480        +25        505     308,05 $      720      +215 km ⚠
Toufik B.      8       210          0        210     128,10 $        —     non déclaré

Détail — Vadim Z., mar. 10 nov. : domicile (J4W) → AS003195 → AS003258 → domicile
        132 km   [ ] Uhaul (jour exclu)   + km magasin [ 12 ]
```

- Choix de la période (courante, précédente, ou autre période de deux semaines).
- Ligne par technicien; un clic ouvre le détail jour par jour (immeubles, tronçons, km, cases Uhaul et
  magasin, bons et km déclarés).
- « Valider la période » : fige les chiffres de la période (copie conservée) et permet l'export.
  « Rouvrir » reste possible, inscrit à l'historique avec la raison; l'export suivant porte la mention
  « révisé » et la date. Pas de ligne d'ajustement reportée à la période suivante en version 1.
- « Exporter Excel » : un fichier par période qui reprend la feuille de temps que Hugo envoie à Sabrina
  (Netris) : une feuille par semaine « Semaine du AAAA-MM-JJ - AAAA-MM-JJ », colonnes
  `Ressource humaine | Dim. | Lun. | Mar. | Mer. | Jeu. | Ven. | Sam. | Total | Km à payer | Montant km`,
  heures au format H:MM (somme de toutes les entrées de temps du jour, « En route » et « En cours »),
  une ligne par employé sur la paie seulement, ligne Total; plus une feuille « Détail » (trajets par jour).
  Le km d'une semaine = somme des km payés de ses jours. Si Netris exige un numéro d'employé pour importer,
  une colonne « no Netris » s'ajoute plus tard (profil, comme les codes postaux).
- Onglet Règles : taux au km, seuil d'écart (km), date de début d'une période de référence, codes postaux
  des techniciens, clé Google.

## 7. Contraintes

- Même architecture que la révision des bons : Python portable sous Windows, sans pip; serveur local
  127.0.0.1 avec jeton; page HTML; déploiement par SharePoint (fichiers de 1 Mo au plus).
- Appels Google en HTTP direct (urllib), sans bibliothèque à installer. L'export Excel doit se faire sans
  nouvelle dépendance lourde (ou avec une roue ajoutée au manifeste `roues.toml`, même procédé que le SDK
  de Claude).
- Progression : lecture seule, gestion du 429 déjà en place, `maxResults` ≤ 500.
- Historique : validation de période, cases Uhaul, km magasin et toute modification inscrits au journal
  (qui, quand, avant, après).

## 8. Laissé au constructeur

- Découpage en modules (calcul pur testable séparé des appels réseau), structure du cache, format exact
  du journal pour ce volet, détails de l'interface dans le style existant.
- Choix de l'API Google précise (Routes `computeRouteMatrix` ou `computeRoutes`) selon le coût et la
  simplicité, tant que les distances sont routières.
- Mode démo avec faux techniciens, faux trajets et fausses distances, sans réseau.

## 9. Décisions prises par Claude (à vérifier par Éric)

- Admissibilité : case « Employé Progim (sur la paie, payé au km) »; sous-traitants décochés et exclus de
  l'export; rien n'est payé sans code postal et case cochée.
- Bons partagés : km déclaré exclu de la comparaison, affiché à part.
- Arrêt sans position GPS : ignoré, jour marqué « à vérifier ».
- Période validée : réouverture permise et tracée, export marqué « révisé »; pas de report d'ajustement.
- Codes postaux (et numéros Netris éventuels) dans le profil Windows, jamais dans le dossier partagé.
- Export calqué sur la feuille de temps hebdomadaire de Progression (heures lues, non modifiées) + km.
- Seuil d'écart en km seulement (demande d'Éric), défaut 10 km par technicien et par période.

## 10. Changement lié dans l'outil de révision : coût horaire à partir du taux de base

Sabrina fournit le taux horaire de base de chaque employé (liste de paie). Dans l'onglet Règles, Hugo inscrit
ce taux de base par technicien; l'outil calcule le coût chargé :
`coût chargé = taux de base × (1 + DAS + vacances + fériés)`, avec trois pourcentages communs réglables :
DAS 12 %, vacances 6 % (tous les employés, chiffre de la paie fourni par Sabrina), fériés 5 %, soit un
facteur de 1,23. Exemple : 35 $ × 1,23 = 43,05 $ (arrondi au cent, demi vers le haut). Le « coût moyen » pour un technicien absent de la
liste est aussi un taux de base. Les taux ne sont pas inscrits par Claude : Hugo les entre et les modifie.
Aucune donnée personnelle (NAS, date de naissance, adresse) n'est conservée; seulement nom, taux de base et
code postal.
