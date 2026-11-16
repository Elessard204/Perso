# Volet 2 : validation du kilométrage des techniciens (notes de départ)

État : en attente des réponses de Hugo (règle de remboursement). Aucun code écrit.

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
