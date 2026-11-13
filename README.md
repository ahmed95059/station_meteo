# station_meteo
## a effacer (c la prompt pour l'agent )

# PROJET : SMART WEATHER STATION — Station météo intelligente en temps réel

Tu es un développeur senior spécialisé en Python, acquisition de données National Instruments (NI-DAQmx), développement web et systèmes de supervision.

Je suis étudiant en école d'ingénieurs et je réalise un projet de station météo avec une carte d'acquisition National Instruments et plusieurs capteurs physiques.

**Ta mission est de développer intégralement le projet**, du backend jusqu'à l'interface, avec un code simple, compréhensible, bien structuré, commenté en français et directement exécutable sous Windows 11 avec VS Code.

Ne te limite pas à proposer une architecture ou quelques exemples : crée les fichiers, implémente les fonctionnalités, teste le projet et corrige les erreurs.

## 1. Objectif général

Créer une application nommée **Smart Weather Station** permettant de :

- Lire les données physiques des capteurs via NI-DAQmx.
- Afficher les mesures en temps réel dans une interface web moderne.
- Enregistrer les données dans SQLite.
- Visualiser les graphiques et les historiques.
- Déclencher des alarmes configurables.
- Calculer des statistiques météorologiques.
- Fonctionner avec ou sans matériel grâce à un mode simulation.

Le fichier `stationMeteo_eleves.xlsx` est le cahier des charges. Lis toutes les lignes du fichier et prends-les en compte.

## 2. Technologies imposées

**Backend**
- Python 3.12
- FastAPI
- NI-DAQmx avec la bibliothèque Python `nidaqmx`
- SQLite avec `sqlite3` ou SQLAlchemy
- WebSocket pour les données en temps réel
- Pydantic pour la validation des données

**Frontend**
- HTML5, CSS3 et JavaScript
- Chart.js pour les graphiques
- Interface responsive avec thème sombre moderne
- Aucune obligation d'utiliser React, Node.js ou des outils frontend complexes

L'interface doit être servie directement par FastAPI pour simplifier le lancement.

## 3. Matériel et configuration NI

La station comporte :

- Capteur de température
- Girouette
- Anémomètre
- Pluviomètre
- Compteur / numéro de station
- Capteur d'humidité si disponible
- Capteur de luminosité si disponible

Correspondances indiquées dans les TP précédents :

- Humidité : AI2
- Girouette : AI3
- Température : AI6
- Luminosité : AI7

Ces correspondances sont à considérer comme des valeurs provisoires, non comme des branchements vérifiés.

Le modèle exact de la carte NI, son nom dans NI MAX et les voies de l'anémomètre et du pluviomètre restent à confirmer.

Créer un fichier `config.yaml` contenant :

- Nom du périphérique NI, par exemple `Dev1`
- Voies analogiques de chaque capteur
- Entrées numériques et entrées compteur
- Type de mesure de chaque capteur
- Fréquence d'acquisition
- Coefficients d'étalonnage
- Seuils d'alarme
- Paramètres de stockage
- Numéro de station

Créer également une page permettant de consulter et de modifier les principaux paramètres sans modifier le code.

Au lancement en mode matériel :

1. Détecter les périphériques NI disponibles.
2. Vérifier l'existence des voies configurées.
3. Afficher clairement les périphériques et voies trouvés.
4. Signaler les voies absentes ou incompatibles.
5. Ne jamais inventer de valeurs réelles lorsque la carte n'est pas connectée.

Utiliser les conversions physiques uniquement si les coefficients sont connus ou configurés. Si le capteur n'est pas étalonné, afficher sa tension brute avec une indication claire.

Pour l'anémomètre et le pluviomètre, prendre en charge les impulsions et les entrées compteur lorsque le matériel le permet. Prévoir une solution configurable selon les capacités de la carte, sans supposer un port physique inexistant.

## 4. Fonctionnalités obligatoires

### A. Température

- Afficher la température instantanée en °C après étalonnage.
- Afficher la température minimale et maximale.
- Configurer un seuil haut et un seuil bas.
- Déclencher une alarme en cas de dépassement.
- Définir les seuils selon les saisons.
- Calculer le temps cumulé pendant lequel la température reste hors limites.
- Enregistrer les températures avec date et heure.
- Afficher un graphique temps réel avec les seuils visibles.
- Afficher les historiques sur un jour, une semaine, un mois et un an.
- Permettre la sélection d'une période personnalisée.

### B. Girouette

- Afficher la valeur angulaire entre 0 et 360° après conversion.
- Afficher les directions cardinales : N, NE, E, SE, S, SO, O, NO.
- Afficher une boussole graphique dont l'aiguille tourne automatiquement.
- Afficher le graphique de direction en temps réel.
- Enregistrer les directions avec leurs horodatages.
- Ajouter une rose des vents historique.

### C. Anémomètre

- Afficher la vitesse du vent en km/h après étalonnage.
- Afficher le graphique en temps réel.
- Calculer les pics de vent sur une fenêtre configurable.
- Afficher les pics sur le graphique avec des marqueurs.
- Enregistrer les vitesses et les événements de pic.
- Afficher la vitesse moyenne et la vitesse maximale.

Attention à ne pas confondre la fréquence des impulsions, la vitesse instantanée et la vitesse moyenne. Les conversions doivent dépendre de la fiche technique du capteur.

### D. Pluviomètre

- Afficher la valeur brute du compteur.
- Afficher la quantité de pluie en mL lorsque la conversion est connue.
- Prévoir également les précipitations en mm si la surface de collecte est renseignée.
- Afficher le cumul des précipitations.
- Déclencher des alarmes sur seuil bas et seuil haut configurables.
- Afficher les seuils sur le graphique temps réel.
- Enregistrer les mesures.
- Permettre les historiques journaliers, hebdomadaires, mensuels et annuels.
- Sélectionner les dates d'affichage.
- Gérer les remises à zéro du compteur sans créer de cumul négatif.

### E. Compteur et station

- Afficher le numéro de station sous forme entière.
- Afficher sa représentation binaire.
- Représenter les bits avec des LED virtuelles allumées ou éteintes.
- Enregistrer le numéro de station dans la base de données.
- Permettre de modifier le numéro depuis les paramètres.
- Si un compteur physique est configuré, afficher également sa valeur indépendamment du numéro logique de station.

### F. Humidité et luminosité

Ces deux capteurs apparaissent dans les anciens TP. S'ils sont présents et utilisables :

- Afficher l'humidité relative en %.
- Afficher la luminosité en unité étalonnée.
- Ajouter leurs graphiques temps réel.
- Enregistrer leurs valeurs.

Ces modules doivent être optionnels pour ne pas empêcher le fonctionnement si les capteurs sont absents.

## 5. Interface utilisateur

Concevoir un dashboard moderne, professionnel et simple à comprendre.

Style souhaité :

- Thème sombre bleu nuit / gris anthracite
- Couleurs distinctes pour chaque capteur
- Graphiques lisibles
- Icônes météorologiques
- Animations légères
- Cartes avec les valeurs instantanées
- Interface utilisable sur PC et tablette
- Textes intégralement en français

Créer les pages suivantes :

**Dashboard**

Vue principale contenant toutes les mesures, les états des capteurs, la boussole, les graphiques récents et les alarmes.

**Historique**

Sélection d'un capteur, d'une date de début et d'une date de fin. Choix rapide : 24 h, 7 jours, 30 jours ou 1 an. Graphiques interactifs.

**Statistiques**

Température moyenne/minimale/maximale, vent moyen et maximal, précipitations cumulées, directions dominantes, durée des alarmes et synthèse de la période choisie.

**Alarmes**

Liste des alarmes avec date, capteur, valeur, seuil, statut et durée. Possibilité d'acquitter une alarme.

**Paramètres**

Choix du mode simulation/matériel, numéro de station, seuils, canaux NI, fréquence de mesure et coefficients de conversion.

Afficher en permanence un indicateur :

- Matériel connecté
- Mode simulation
- Matériel déconnecté
- Erreur de capteur

Ne pas afficher des données simulées comme si elles provenaient du matériel.

## 6. Backend Python

Créer une architecture claire avec :

- Un module d'acquisition NI.
- Un module de simulation.
- Un module de conversion des mesures.
- Un module de détection d'alarmes.
- Un module de statistiques.
- Un module de stockage SQLite.
- Une API FastAPI.
- Un WebSocket pour transmettre les mesures.

L'acquisition doit fonctionner indépendamment de l'affichage web.

Par défaut, viser une actualisation de l'interface toutes les secondes et une sauvegarde périodique configurable, par exemple toutes les 10 secondes, sans perdre les alarmes ni les pics significatifs.

Utiliser un seul service d'acquisition pour éviter que plusieurs connexions web ouvrent simultanément les mêmes voies NI.

Prévoir une fermeture propre des tâches NI et la reconnexion après une perte de communication.

## 7. Base de données SQLite

Créer automatiquement `weather.db` au premier démarrage.

Prévoir au minimum les tables :

**measurements** : identifiant, station, horodatage UTC, température, humidité, luminosité, vitesse du vent, direction, pluviométrie, valeurs brutes utiles et qualité des mesures.

**alarms** : identifiant, capteur, type, seuil, valeur, début, fin, durée et statut.

**wind_peaks** : date, valeur du pic, durée/fenêtre de calcul.

**stations** : identifiant et numéro de station.

**settings** : paramètres de l'application.

Les mesures doivent être conservées après fermeture et redémarrage. Utiliser des horodatages cohérents et afficher les heures locales dans l'interface.

Ajouter l'export CSV des données sélectionnées.

## 8. Mode simulation obligatoire

Le projet doit fonctionner immédiatement même sans carte NI.

Créer un simulateur générant des données réalistes mais clairement fictives :

- Variations progressives de température
- Variations d'humidité
- Changements de direction du vent
- Rafales occasionnelles
- Épisodes de pluie
- Déclenchement possible des alarmes

Ajouter un bouton permettant de passer du mode simulation au mode matériel en toute sécurité.

Le changement de mode doit fermer correctement les ressources de l'ancien mode.

Ne pas mélanger les données simulées et réelles dans les statistiques sans l'indiquer.

## 9. Fonctionnalités créatives supplémentaires

Après avoir implémenté le cahier des charges, ajouter :

**Indicateur de confort météo** : score simple calculé à partir de la température, de l'humidité et du vent, avec formule documentée.

**Résumé météo automatique** : texte descriptif fondé sur les mesures récentes, par exemple « Température stable, vent modéré, humidité en hausse ». Ne pas utiliser une API d'IA payante.

**Analyse des anomalies** : détecter les valeurs impossibles, les brusques variations et les capteurs qui restent bloqués. Distinguer une anomalie de mesure d'un événement météorologique réel.

**Rapport météo** : exporter un résumé de la journée avec statistiques et graphiques.

Ces bonus doivent rester secondaires. La priorité est le fonctionnement fiable de la station.

## 10. Structure souhaitée

Organiser le projet de façon simple :

```text
smart-weather-station/
│
├── backend/
│   ├── main.py
│   ├── acquisition.py
│   ├── simulator.py
│   ├── sensors.py
│   ├── database.py
│   ├── alarms.py
│   ├── statistics.py
│   └── config.py
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── tests/
│   ├── test_sensors.py
│   ├── test_alarms.py
│   └── test_database.py
│
├── data/
├── config.yaml
├── requirements.txt
├── start.bat
└── README.md
```

Adapte légèrement cette structure si nécessaire, mais évite de créer des dizaines de fichiers inutiles.

## 11. Simplicité et qualité du code

Je suis étudiant et je dois pouvoir comprendre et présenter ce projet.

Respecte les règles suivantes :

- Code clair, avec des noms de variables explicites.
- Commentaires en français pour les parties importantes.
- Fonctions courtes.
- Pas de complexité inutile.
- Pas de microservices, Docker ou Redis.
- Gestion des erreurs avec messages explicites.
- Pas de valeurs matérielles inventées.
- Pas de faux résultats présentés comme réels.
- Éviter les installations et configurations inutiles.

Créer un fichier `README.md` qui explique pas à pas :

1. Comment installer Python et les dépendances.
2. Comment vérifier la carte et les voies dans NI MAX.
3. Comment lancer le projet sous Windows.
4. Comment tester en simulation.
5. Comment passer aux vrais capteurs.
6. Comment modifier les ports et les coefficients.
7. Comment lire la base SQLite.
8. Comment expliquer l'architecture lors d'une soutenance.

Créer un fichier `start.bat` pour lancer facilement l'application, et afficher l'adresse locale de l'interface.

## 12. API attendue

Prévoir des routes telles que :

- `GET /api/status` : état du système
- `GET /api/measurements/latest` : dernières mesures
- `GET /api/measurements/history` : historique filtré
- `GET /api/statistics` : statistiques
- `GET /api/alarms` : alarmes
- `POST /api/alarms/{id}/acknowledge` : acquittement
- `GET /api/settings` : configuration
- `PUT /api/settings` : modification de la configuration
- `GET /api/export/csv` : export CSV
- `WS /ws/measurements` : flux temps réel

Prévoir la validation des paramètres, des réponses JSON cohérentes et la gestion des erreurs.

## 13. Tests et validation

Créer des tests automatisés pour :

- Conversion des valeurs des capteurs
- Calcul des directions cardinales
- Calcul des vitesses et des pics de vent
- Calcul du cumul pluviométrique
- Détection des seuils
- Calcul des durées hors limites
- Enregistrement dans SQLite
- Relecture de l'historique

Vérifier que :

- L'application démarre sans carte NI en mode simulation.
- Les graphiques se mettent à jour automatiquement.
- Les données sont sauvegardées.
- Les alarmes fonctionnent.
- Le changement de date fonctionne.
- Le redémarrage conserve l'historique.
- Le débranchement d'un matériel ne fait pas planter l'interface.

Ne prétends pas avoir testé la véritable carte NI si elle n'est pas accessible.

## 14. Méthode de travail

Commence par lire `stationMeteo_eleves.xlsx` et dresser une checklist de correspondance entre chaque exigence et le module du projet.

Ensuite :

1. Crée l'architecture et les fichiers.
2. Implémente d'abord le backend et la base SQLite.
3. Implémente le simulateur pour avoir des données immédiatement.
4. Développe l'interface complète.
5. Ajoute les graphiques et les WebSockets.
6. Implémente les alarmes, les historiques et les statistiques.
7. Ajoute l'intégration NI-DAQmx configurable.
8. Exécute les tests disponibles et corrige les problèmes.
9. Termine par la documentation et les instructions de lancement.

Ne t'arrête pas après avoir généré quelques fichiers. Poursuis jusqu'à obtenir une application fonctionnelle en simulation et une couche matérielle prête à être configurée.

Si un paramètre matériel manque, isole-le dans `config.yaml` avec une explication claire au lieu de bloquer tout le développement.

À la fin, donne-moi :

- La liste des fichiers créés.
- Les commandes exactes pour lancer l'application.
- L'adresse du dashboard.
- Les fonctionnalités opérationnelles.
- Les informations matérielles restant à vérifier.
- Les résultats des tests et les éventuelles limites.

**Priorité absolue :** une station météo réellement utilisable, stable, compréhensible et conforme au cahier des charges Excel, avec une belle interface temps réel et un backend Python fonctionnel.
