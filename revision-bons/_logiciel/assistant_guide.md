# Guide de l'outil « Révision des bons »

Outil interne de Gestion immobilière Progim, utilisé par les services techniques (Hugo, coordonnateur) pour
préparer la facturation des bons de service de Progression Live. L'outil prépare et vérifie chaque bon selon les
règles de facturation; la personne qui l'utilise révise les exceptions et approuve. Rien n'est écrit dans
Progression sans approbation. Les feuilles de temps (paie) ne sont jamais modifiées.

## Le flux dans Progression

1. Le technicien passe le bon à « Terminé ».
2. Hugo clique « Facturer » dans l'onglet Feuille de temps du bon, dans Progression. Progression crée une ligne
   par entrée de temps : une entrée « En route » donne une ligne Transport, une entrée « En cours » donne une
   ligne Main d'oeuvre. L'API de Progression n'a pas d'équivalent à ce bouton : il faut le cliquer avant
   d'analyser, sinon l'outil bloque le bon.
3. L'outil charge les bons, applique les règles, lit les factures jointes et révise la description.
4. Hugo révise, approuve, puis l'outil écrit les corrections dans Progression. L'écriture réelle reste
   verrouillée jusqu'à l'essai dans l'environnement de test de Progression (à partir du 27 novembre 2026); d'ici
   là, l'envoi est une simulation qui n'écrit rien.
5. Hugo passe le bon à « Prêt à facturer », puis au 1er du mois à « Transférer au système comptable ».

## Utiliser l'outil

- Lancer « Révision des bons.bat » (dossier SharePoint « Révisions des bons de service »). « Essai (démo).bat »
  ouvre l'outil avec des bons fictifs, sans rien lire ni écrire dans Progression.
- Onglet À réviser : choisir la période, « Charger les bons », puis « Analyser ». Cliquer sur un bon ouvre sa
  fiche : l'original à côté de la proposition, la règle qui a produit chaque valeur (colonne Origine), les
  pièces jointes et le temps réel de chaque technicien. Tout se modifie : quantité, prix, libellé, description.
  Cocher les bons, « Approuver la sélection », puis « Envoyer les bons approuvés ».
- Statuts : « Prêt » = aucune alerte selon les règles; « À vérifier » = au moins une alerte non bloquante, lire
  la raison; « Bloqué » = à corriger dans Progression, puis réanalyser; « Envoyé » = déjà écrit.
- « Prêt » n'est pas une garantie : l'outil ne connaît que les feuilles de temps et les pièces jointes. Sur les
  bons d'octobre 2026, Hugo a modifié environ 4 bons « Prêts » sur 10 avec de l'information que l'outil ne voit
  pas (rabais convenu, heures ajoutées, aide qui n'a pas poinçonné). Jeter un coup d'œil avant d'approuver.
- Une ligne modifiée par l'utilisateur n'est plus touchée par l'outil. Une ligne retirée par l'outil s'affiche
  barrée; pour la garder, lui redonner une quantité dans la fiche.
- Onglet Kilométrage : km à payer de chaque technicien par période de paie (domicile, immeubles visités dans
  l'ordre, retour), à côté du km déclaré, avec l'écart signalé au-delà du seuil. Ajuster au besoin (arrêts au
  magasin, Uhaul), « Valider la période », puis « Exporter Excel » pour la paie.
- Onglet Règles : toutes les règles et tous les garde-fous, réglables. Section Connexions : les clés API
  (Progression, Claude, Google Maps), gardées dans le profil Windows de la personne. Chaque personne qui utilise
  l'outil sur son poste doit inscrire les clés une fois.
- Onglet Améliorations : le journal d'améliorations (voir plus bas), avec un statut et une note par
  recommandation, et un export Excel pour les rencontres de revue.
- Onglet Historique : bons approuvés et écrits (qui, quand), relevé des rabais, questions posées à Jarvis.
- Jarvis (bouton en haut à droite, et « Pourquoi ? » à côté de chaque alerte d'une fiche) : l'assistant de
  l'outil. Il explique les règles et ce qui se passe sur le bon ouvert, et aide à trouver des améliorations.
  Il ne modifie rien.

## Règles de facturation

### Main-d'œuvre
Chaque ligne est arrondie au 0,25 h supérieur, minimum 0,25 h, et n'est jamais réduite. Exemples : 2 h 05 donne
2,25 h; 2 h 15 reste 2,25 h; 0 h 01 donne 0,25 h. L'excédent de transport (voir Transport) s'ajoute à la
dernière ligne du technicien avant l'arrondi. Une entrée de travail de moins d'une minute (clic par erreur) est
ignorée. L'outil ne réduit jamais des heures : une minuterie oubliée se corrige dans Progression.

### Transport
Un seul transport par technicien et par jour sur un bon, en quantité 1. Un aller-retour au magasin n'en ajoute
pas : la ligne de transport en trop est retirée (barrée), et l'utilisateur peut la remettre. Un trajet inscrit à
0 minute compte quand même : le technicien s'est déplacé. Au-delà de 60 minutes de trajet, l'excédent passe en
main-d'œuvre, avec l'alerte « transport long » (possible oubli de changer le statut à « Travaux commencés »);
l'alerte disparaît si l'utilisateur modifie lui-même cette ligne. Un technicien à salaire fixe garde un transport
à 1 et sa route n'est jamais ajoutée en main-d'œuvre. Le même technicien dans le même immeuble le même jour sur
deux bons est signalé (« transport en double »). Une journée de travail sans aucun trajet inscrit est signalée
(« transport manquant ») : c'est un jugement, Hugo décide s'il ajoute un transport.

### Tarifs selon le type de bon
Appel de service : service SMMP, 65 $/h, transport 50 $. Maintenance : service SELP, 45 $/h, transport 40 $.
Rénovation : service SRP, 85 $/h, transport 50 $, jamais imposé automatiquement. Seul le taux que Progression met
par défaut (65 $/h et 50 $) est corrigé automatiquement selon le type de bon. Tout autre taux a été choisi par
quelqu'un : il est gardé et signalé s'il est hors grille (« tarif non standard »).

### Matériel
Le matériel acheté est refacturé à partir des factures jointes au bon : une ligne par facture, au sous-total
avant taxes + 15 % (écofrais, consignes et livraison compris; taxes exclues), quantité 1, articles en
description (un par ligne, sans le fournisseur, le numéro de facture ni les codes SKU : ceux-ci restent dans la
colonne Origine). Une ligne « Matériel acheté » à 0 $, vide ou inscrite par le technicien (ex. « gypse »), est
remplacée par la ligne de la facture; une ligne vide inutile est retirée. Une date de facture lue avec le jour et
le mois inversés (11-04 lu 04-11) est remise à l'endroit quand l'inversion tombe près du bon.
Chaque ligne porte la référence de sa facture (fournisseur + numéro) : une même facture ne peut jamais être
refacturée deux fois, même sur un autre bon. Le matériel en inventaire est estimé par Hugo; une ligne
« Matériel en inventaire » à 0 $ veut dire qu'il n'y a pas de matériel. Un achat facturé en inventaire n'a
jamais de facture : pas d'alerte « achat sans facture ».

### Description des travaux
L'IA révise la « Note technicien » (le texte que le client voit). Elle corrige l'orthographe et la syntaxe, ou
résume un texte confus, sans jamais inventer de travail. Elle garde intacts les quantités, emplacements,
équipements et numéros de modèle. Un détail tiré d'une photo est marqué « à vérifier ». Si le technicien n'a
rien écrit, une description est proposée et signalée. Si la révision échoue, le texte original est gardé. Les
notes internes restent pour le bureau.

### Cas particuliers reconnus
- Journées fusionnées : Hugo regroupe parfois plusieurs visites sur une ligne en gardant la même valeur (deux
  visites de 2 h facturées 4,75 h et un transport). Une ligne de main-d'œuvre dont la quantité ne correspond ni
  au temps créé par « Facturer » ni à ce temps arrondi au 0,25 h, ou sans entrée de temps liée, est une ligne
  modifiée à la main : l'outil n'y touche plus et l'alerte « transport manquant » tombe. Quand une ligne est
  supprimée dans Progression, ses entrées perdent leur lien; sur un bon qui a une ligne modifiée à la main, ces
  entrées ne bloquent pas (cliquer « Facturer » recréerait les lignes en double).
- Rabais : quand la main-d'œuvre et le transport facturés sont plus de 50 $ sous la valeur du temps inscrit,
  une alerte non bloquante donne le montant. La valeur du temps se calcule avec les mêmes règles : main-d'œuvre
  par technicien et par jour au 0,25 h supérieur (excédent de transport compris, sauf salaire fixe), plus un
  transport par technicien et par jour, au tarif du type de bon. L'utilisateur peut inscrire une raison
  (facultative), même après l'approbation; chaque rabais approuvé va au relevé des rabais (onglet Historique).
- Salaire fixe (case dans Règles) : transport à 1, route jamais ajoutée en main-d'œuvre.
- Produit au forfait (liste dans Règles, ex. « Bacs ordures / recyclage », 95 $ par semaine) : pas d'alerte
  « heures non facturées », « transport manquant » ni rabais.
- Bon à 0 $ (toutes les lignes à 0 $, ex. ménage au forfait Immoblox refacturé par la comptabilité) : aucune
  correction ni alerte de facturation.

### Rentabilité
L'outil estime la marge de chaque bon : revenu facturé contre le coût du temps des techniciens (taux de base
inscrit dans Règles, plus 12 % de charges, 6 % de vacances et 5 % de fériés) et le coût du matériel. Les frais
fixes (coordination, administration, logiciels, bureau) ne sont pas comptés. Sans taux pour un technicien, la
marge est « inconnue ».

## Garde-fous

Tant que « Facturer » n'a pas été cliqué, seul le blocage « heures non facturées » s'affiche : rabais,
rentabilité et alertes de transport viennent des lignes de temps, qui n'existent pas encore. Une note texte ou
une vidéo jointe au bon n'est pas envoyée à l'IA et ne déclenche aucune alerte.

Bloquent le bon (statut « Bloqué ») :
- Heures non facturées : des entrées de temps d'une minute et plus ne sont liées à aucune ligne, sur un bon sans
  ligne modifiée à la main. Cliquer « Facturer » dans Progression, puis réanalyser.
- Bon sans heures : aucune entrée de temps sur le bon.
- Facture en double : la même facture est jointe deux fois au bon, ou déjà refacturée sur un autre bon.

Passent le bon « À vérifier » :
- Tarif hors grille pour le type de bon; type de bon sans tarif.
- Transport long, transport manquant, transport en double; excédent de transport sans ligne de main-d'œuvre où
  l'ajouter (à facturer à la main).
- Rabais de plus de 50 $ sous la valeur du temps inscrit.
- Rentabilité : bon sans revenu, à perte ou sous la marge minimale.
- Plus de 12 h pour un technicien dans une journée.
- Facture à contrôler : total des lignes différent du sous-total (plus de 0,05 $), date à plus de 30 jours du
  bon ou dans le futur, ligne de plus de 1 000 $, pièce jointe incertaine (facture floue, page manquante, reçu de
  stationnement).
- Facture incomplète : aucun sous-total lu (souvent une page 1 de 2) : le montant vient des lignes lues.
- Facture sans numéro lisible : la détection des factures refacturées en double ne peut pas la reconnaître.
- Champ « Achat » du technicien contredit : achat déclaré sans facture jointe, ou « Non » avec une facture.
- Description créée ou enrichie par l'IA, ou révision impossible.

## Ce qui reste au jugement d'Hugo

Le clic « Facturer » et les changements d'état dans Progression; le prix du matériel en inventaire; les fusions
de journées et les rabais (l'outil les reconnaît et les signale); les heures ajoutées au-delà du temps inscrit;
une aide qui n'a pas poinçonné sur le bon; l'ajout d'un transport quand aucun trajet n'est inscrit; les plafonds
de soumission; la refacturation à un locataire. L'outil ne peut pas facturer du temps qui n'est pas inscrit :
chaque technicien, aides compris, doit poinçonner sur chaque bon.

## Questions fréquentes

- Pourquoi mon bon est bloqué alors que j'ai cliqué « Facturer » ? Une entrée de temps a pu être ajoutée après
  le clic (deuxième visite). Recliquer « Facturer », puis réanalyser. Si les lignes ont été fusionnées à la main,
  le bon ne devrait pas être bloqué : vérifier qu'une ligne de main-d'œuvre a bien été modifiée.
- Pourquoi un transport est barré ? Le technicien a déjà un transport ce jour-là sur ce bon. Pour le garder,
  redonner une quantité à la ligne dans la fiche.
- Pourquoi la main-d'œuvre a augmenté ? Arrondi au 0,25 h supérieur, ou excédent d'un trajet de plus de 60 min.
  La colonne Origine de la fiche donne la raison exacte.
- L'outil a changé mon taux horaire, pourquoi ? Seul le taux par défaut de Progression (65 $/h, 50 $) est
  remplacé par le tarif du type de bon (ex. Maintenance 45 $/h et 40 $). Un autre taux est gardé.
- Comment faire une fusion de journées ? Modifier la quantité de la ligne de main-d'œuvre dans la fiche (ou dans
  Progression) en gardant la valeur totale; l'outil ne touche plus à cette ligne.
- Pourquoi une alerte de rabais ? Le facturé est plus de 50 $ sous la valeur du temps inscrit. Si c'est voulu
  (devis, client plafonné, anticipation), inscrire la raison dans la fiche.
- Les clés sont manquantes ? Les inscrire dans Règles, section Connexions, sur le poste qui utilise l'outil.
- Peut-on écrire dans Progression ? Pas encore : l'écriture est verrouillée jusqu'à l'essai en environnement de
  test. L'envoi actuel est une simulation.

## Améliorer l'outil : le journal d'améliorations

L'outil s'améliore d'une fois à l'autre grâce au journal d'améliorations. Quand une règle donne un mauvais
résultat, qu'une alerte revient pour rien ou qu'un cas n'est pas prévu, on le note avec le bouton « Recommander
une amélioration » du panneau de Jarvis (ou « Proposer une amélioration » dans l'onglet Améliorations). Jarvis
rédige un brouillon à partir de la conversation : titre, problème, cas concret (bon, technicien, chiffres) et
deux ou trois solutions, la recommandée en premier. On vérifie, on complète, on enregistre.

Statuts : Nouvelle (vient d'être notée), À discuter (à voir à la prochaine revue), Retenue (décidé de le faire),
Écartée (décidé de ne pas le faire, la note dit pourquoi), Faite (en place dans l'outil). Éric, Hugo et Claude
en font le tour ensemble; chaque décision retenue modifie l'outil ou les règles, et s'ajoute à la section
« Décisions prises » ci-dessous, que Jarvis connaît.

Bonnes idées à noter : une alerte qui sort souvent pour rien (et pourquoi), une correction faite à la main
encore et encore (l'outil pourrait la faire), un cas client particulier (plafond, forfait, refacturation), une
consigne aux techniciens qui éviterait des corrections (ex. poinçonner l'aide sur le bon).

## Décisions prises

- 16 novembre 2026 (cas à valider avec Hugo) : journées fusionnées respectées; rabais signalé au-delà de 50 $
  avec raison facultative et relevé; case « Salaire fixe »; produits au forfait; bons à 0 $ sans alerte;
  alerte « inventaire à 0 $ » retirée.
- 17 novembre 2026 (essai sur les 154 bons d'octobre) : un seul transport par technicien et par jour sur un bon;
  trajet de 0 minute compté comme transport; entrées de travail de moins d'une minute ignorées; pas de blocage
  « Facturer » sur un bon dont une ligne a été modifiée à la main (fusion faite dans Progression).
- 17 novembre 2026 : Harry à salaire fixe; « Bacs ordures / recyclage » au forfait; taux de base des
  techniciens inscrits à partir de la liste de paie.
- 17 novembre 2026 (premiers résultats réels avec l'IA, 32 bons) : description du matériel limitée aux
  articles; lignes du technicien à 0 $ remplacées par la facture; dates jour/mois inversées corrigées; alertes
  « facture incomplète », « sans numéro » et « dans le futur »; réponses « S/o », « Nou » comprises comme
  « pas d'achat »; fausses alertes retirées avant « Facturer » et pour les notes ou vidéos jointes.
- Questions ouvertes (posées à Hugo le 17 novembre) : tolérance de quelques minutes avant d'arrondir au quart
  d'heure suivant, ou règle stricte; mise à 0 $ automatique des bons de ménage Immoblox; transport sur les
  interventions faites par Hugo lui-même.

## Qui contacter

Pour une décision sur une règle (la changer, une exception récurrente, un cas non prévu), voir avec Éric Lessard.
Les réglages se changent dans l'onglet Règles.
