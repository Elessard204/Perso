# Volet 2 : validation du kilométrage des techniciens (notes de départ)

Notes de départ et réponses de Hugo, gardées comme référence. Le module est construit : voir
`2026-11-16-kilometrage-design.md`.

## But (selon Éric)
Garde-fou avant la paie : contre-vérifier le kilométrage inscrit par les techniciens pour détecter
une erreur de saisie ou un kilométrage gonflé, au lieu de le payer à l'aveugle. Hugo doit pouvoir
valider rapidement, puis transmettre à Sabrina (paie, aux deux semaines).

## Ce qu'on sait
- Aujourd'hui, Hugo ignore le km déclaré : il refait chaque journée dans Google Maps à partir de la
  feuille de temps globale, en ajoutant de mémoire les arrêts au magasin (±10 km par rapport au
  carnet manuel de Vadim, essai de plusieurs semaines).
- Progression fournit les coordonnées GPS de chaque immeuble (`clientAddress.position`,
  `locationAddress.position`) : aucun géocodage nécessaire.
- Les entrées de temps donnent l'ordre des visites de la journée (`start`, `duration`, activité
  « En route » / « En cours »). `sourceStart` garde l'heure d'origine quand une entrée a été modifiée.
- Le km déclaré est dans `properties.info.km` : texte libre, par bon (pas par jour), parfois cumulé sur
  plusieurs jours (« 52 pour les deux jours », « +14km achat + 6km… »), souvent vide sur les bons MA.
  `info.km_retour` existe mais est vide partout.
- Exemple : AS003469, 530 km déclarés, 4 jours à Saint-Césaire (environ 65 km de Brossard) avec
  45 à 80 min de route par trajet : plausible.

## Questions envoyées à Hugo
1. Kilomètres remboursés : maison → 1er immeuble? retour? seulement entre immeubles?
2. Qui y a droit : auto personnelle seulement, ou aussi camion de la compagnie?
3. Taux au km et dates de la période de paie.
4. Arrêts au magasin : magasins habituels par technicien, ou tolérance par jour.
5. Adresse de départ de chaque technicien (ville ou code postal), si le trajet depuis la maison compte.
6. Seuil d'écart à signaler (10 km par période? un pourcentage?).
7. Où le km est inscrit quand il y a plusieurs bons dans la journée; utilité de « km retour ».

## Pistes techniques (à trancher avec Éric)
- Distances routières : Google Maps (payant, clé API) ou OpenStreetMap/OSRM (gratuit).
- Lecture du texte libre du km : règles simples + IA pour les cas ambigus.

## Réponses de Hugo (2026-11-16)
- Trajet payé : maison → premier immeuble → … → dernier immeuble → maison, chaque jour travaillé.
  Toujours présumé, même si l'ouvrier ne part pas de chez lui ou n'y retourne pas.
- Exemption : jours où l'ouvrier utilise un véhicule loué (Uhaul) plutôt que son véhicule personnel.
- Taux : 0,61 $/km. Période de paie : deux semaines, du dimanche au samedi.
- Arrêts au magasin : trop de variables (technicien, type de travail, carte de crédit Progim, compte de
  dépense, secteur). Aucune règle fixe possible.
- Adresses des ouvriers : dans la charte de feuille de temps de Hugo et les dossiers d'employés
  (Hugo enverra l'information). Données personnelles : à garder hors du dépôt Git.
- Seuil d'écart : sans objet pour Hugo, puisqu'il ne regarde pas le km déclaré.
- Km déclaré : inscrit sur le bon de la job. Hugo ne le consulte jamais (plus de 10 h/semaine à ouvrir
  chaque bon); le champ sert surtout à rassurer les gars. Le km payé est celui que Hugo reconstitue.
- Rénovations : type de tâche « Rénovation », numéros SRP (intégré à l'outil de révision des bons).
