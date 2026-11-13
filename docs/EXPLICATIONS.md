# Comprendre et présenter le projet

## 1. Le problème à résoudre

Un capteur transforme une grandeur physique en signal électrique. La carte NI numérise ou compte ce signal. Le programme doit ensuite convertir la mesure, conserver son origine, comparer les seuils, enregistrer les résultats et les présenter.

Le cours explique ces opérations avec LabVIEW, puis Python/Tkinter/Matplotlib. Ici, le principe d'acquisition reste le même ; FastAPI et le navigateur remplacent la fenêtre Tkinter, comme demandé dans le descriptif du projet. Il ne s'agit pas de refaire tous les exercices des documents.

## 2. Circulation d'une mesure

```text
Capteurs → carte NI → NIAcquisition ┐
                                  ├→ WeatherService → conversions → alarmes → SQLite
                  Simulator ──────┘         │
                                           └→ FastAPI → WebSocket → navigateur / Chart.js
```

Les deux sources sont exclusives. Le mode matériel ne se rabat jamais automatiquement sur le simulateur. Une perte USB produit des valeurs `null`, un état déconnecté et une tentative de reconnexion après au moins trois secondes.

`WeatherService` possède un thread unique. Il acquiert et stocke même si aucun navigateur n'est ouvert. Le navigateur ne crée aucune tâche NI. Dix onglets n'ouvrent donc pas dix fois les mêmes voies. Pour le contact lent du pluviomètre, un petit thread spécialisé lit une tâche numérique indépendante afin que la lecture analogique ne bloque pas la scrutation du contact.

## 3. Rôle des fichiers Python

| Fichier | Responsabilité et fonctions à connaître |
| --- | --- |
| `config.py` | `Settings` vérifie les types, limites, saisons, voies dupliquées et coefficients ; `load_config` lit le YAML ; `save_config` remplace le fichier atomiquement. |
| `acquisition.py` | `inventory` énumère les périphériques et voies ; `NIAcquisition.__init__` ouvre les tâches ; `read` lit des valeurs brutes ; `close` libère les ressources. `DigitalRain` compte les fronts d'un contact lent avec anti-rebond. |
| `simulator.py` | `Simulator.read` produit des variations progressives, des rafales et des épisodes de pluie fictifs ; `seed` permet des séquences reproductibles pour le développement. |
| `sensors.py` | Fonctions pures de conversion, direction cardinale, fréquence entre fronts, différence de compteurs ; `RainAccumulator` suit le cumul ; `WindPeaks` suit les fenêtres ; `AnomalyDetector` signale les incohérences ; `comfort` calcule le score pédagogique. |
| `alarms.py` | `temperature_limits` choisit la saison ; `AlarmManager.process` ouvre, prolonge et termine les épisodes ; `close` interrompt proprement les épisodes restants. |
| `database.py` | `Database.connect` gère fermeture et transaction ; `insert_measurements` écrit un lot et son cumul de pluie atomiquement ; `history` réduit les longues courbes ; `aggregates` calcule les statistiques complètes. `InstanceLock` empêche deux processus d'utiliser la même base pour l'acquisition. |
| `statistics.py` | `statistics` rassemble les agrégats et découpe les durées d'alarme à la période demandée. |
| `service.py` | `run` orchestre un cycle ; `snapshot` fournit l'état sans attendre NI ; `reconfigure` arrête l'ancien mode avant le nouveau ; `summary` construit un texte descriptif sans API d'IA. |
| `main.py` | Crée l'application, démarre/arrête le service avec le cycle de vie FastAPI, expose l'API, le WebSocket, le CSV, le rapport et les fichiers statiques. |

Les exceptions attendues de NI sont traitées par le service. Une erreur inattendue de stockage arrête le service avec un état d'erreur visible : on ne présente pas une acquisition arrêtée comme active. Les erreurs détaillées apparaissent aussi dans le terminal.

## 4. Conversions physiques

### Une conversion linéaire

La formule est `y = scale × x + offset`. `x` est une tension en volts ou une fréquence en hertz, selon le type choisi. `calibrated: false` signifie que l'étalonnage n'est pas confirmé : la valeur physique reste absente et l'interface affiche la valeur brute disponible. Activer un capteur signifie seulement qu'on demande à lire une voie ; cela ne prouve pas que le capteur est câblé.

### Température LM335 : exemple issu du TP1

Le TP1 donne 2,98 V à 25 °C et 0,01 V par degré :

```text
T = 25 + (U - 2,98) / 0,01 = 100 × U - 273
U = 3,08 V → T = 35 °C
```

Pour ce modèle et cette référence, `scale=100` et `offset=-273`. La relation idéale en kelvins peut mener à un autre décalage (−273,15) ; ne pas mélanger cette référence théorique et celle du TP. Vérifier le capteur réel, son conditionnement et deux points de mesure avant de valider une calibration.

### Girouette

Le TP1 indique 0,5–4,5 V, mais ne suffit pas à garantir le zéro mécanique. Si, après vérification, 0,5 V correspond à 0° et 4,5 V à 360° :

```text
angle = (U - 0,5) × 360 / (4,5 - 0,5) = 90 × U - 45
```

`scale=90`, `offset=-45`, puis l'angle est ramené modulo 360. Les huit secteurs cardinaux font 45° ; le secteur nord inclut les angles de 337,5° à 22,5°. La boussole indique l'origine du vent, sans géolocalisation.

### Humectation et fréquence

**Le capteur du TP2 détecte l'eau en surface. Son pourcentage n'est pas une humidité relative de l'air.** Il est donc nommé « humectation de surface ».

Le signal rectangulaire est échantillonné à 5000 Hz. Une fenêtre de 1000 points dure 0,2 s : elle couvre environ 5 périodes à 25 Hz et 20 périodes à 100 Hz. `frequency` recherche les franchissements montants du seuil de 2 V et calcule :

```text
f = Fe × (nombre de fronts - 1) / (indice dernier front - indice premier front)
```

Moins de deux fronts signifie fréquence indéterminée (`null`), pas 0 Hz. Le TP utilise 200 points pour visualiser le signal ; ce projet allonge la fenêtre pour mieux mesurer le bas de la plage. Ajuster le seuil dans `sensors.frequency` si le conditionnement réel diffère. Bruit, rebonds et aliasing restent des questions matérielles : ce détecteur n'est pas un analyseur universel.

À partir des références 100 Hz = sec, 25 Hz = mouillé :

```text
Hsurface = 100 × (100 - f) / 75
scale = -1,3333333333333333 ; offset = 133,33333333333334
```

Un autre capteur mesurant réellement l'humidité relative peut être configuré comme tel. Son étalonnage doit provenir de sa fiche technique. En simulation seulement, une humidité relative supplémentaire est générée, explicitement fictive et indépendante d'AI2.

### Anémomètre

Le cours compte les fronts descendants de PFI0 sur CTR0. Le compteur tourne ici en continu : on utilise la différence entre deux lectures, sans arrêter le comptage à chaque seconde.

```text
ΔN = compteur actuel - compteur précédent
f = ΔN / Δt réel
v = coefficient × f + décalage
Exemple du TP : 10 impulsions en 2 s → 5 Hz → 12 km/h, avec coefficient 2,4.
```

La vitesse affichée est une **vitesse estimée sur l'intervalle de comptage**. Ce n'est pas la moyenne de toute la journée. La première lecture ne donne pas de vitesse faute de référence temporelle. `frequency` est une alternative pour un signal câblé sur une entrée analogique échantillonnée. Ne pas déplacer un fil vers une borne supposée compatible sans vérifier la carte.

`WindPeaks` retient le maximum de chaque fenêtre non chevauchante de 30 s par défaut. Un maximum au-dessus de 30 km/h devient un événement conservé avec l'heure du maximum et la largeur de fenêtre. Il apparaît sur le graphique une fois la fenêtre terminée. Une fenêtre partielle est finalisée à l'arrêt. Le maximum glissant affiché sur la carte vent est, lui, recalculé à chaque acquisition sur les dernières 30 s.

### Pluviomètre

```text
Volume ajouté (mL) = nouvelles impulsions × mL par bascule
Cumul (mL) = cumul précédent + volume ajouté
Hauteur (mm) = 10 × volume (mL) / surface de collecte (cm²)
Exemple : 20 mL sur 200 cm² → 1 mm.
```

La première lecture sert de référence ; on n'attribue pas arbitrairement les anciens coups de compteur à la période courante. Une remise à zéro ajoute au plus les impulsions lues depuis le zéro. Un retour de la borne haute d'un compteur 32 bits est traité comme un débordement. Sans journal matériel, il est impossible de connaître les impulsions perdues pendant une déconnexion ou avant une remise à zéro externe ; le programme ne les invente pas.

Le cumul est conservé dans SQLite par source, station et coefficient mL/impulsion. Il ne redémarre pas à minuit : la pluie d'une période s'obtient en sommant `rain_delta_ml`. Les seuils d'alarme portent sur le **cumul mL**, comme indiqué dans l'interface. Un seuil bas est facultatif (`null`) pour éviter une alarme permanente à sec. Le coefficient fictif 2,5 mL et la surface fictive 200 cm² du simulateur ne deviennent jamais des paramètres matériels.

Le cours place le contact pluie sur P0.7. Il n'est pas garanti qu'un second compteur matériel soit disponible à côté de celui du vent. Le mode `digital`, à 10 ms avec anti-rebond de 40 ms, est prévu pour les contacts lents. Les impulsions trop courtes ou très rapprochées peuvent être perdues : ce mode n'est pas un comptage temps réel garanti sous Windows. Utiliser un compteur matériel si la carte et le câblage le permettent.

### Lumière et station

Le pourcentage de luminosité du TP est une échelle relative, pas des lux. Avec des références vérifiées de 0 et 4,8 V, un exemple de coefficient est `100/4.8`, en unité `%`. Ne pas déclarer des lux sans étalonnage photométrique. Les valeurs hors 0–100 % sont signalées.

Le numéro logique de station (0 à 65535) est un identifiant de stockage modifiable. Sa représentation sur 16 bits commande les LED virtuelles. L'encodeur physique du cours (port1, lignes 0–3) ou un compteur NI peut être lu dans le module `counter` : sa valeur reste séparée pour éviter de modifier silencieusement l'identité de l'archive.

## 5. Alarmes et durées

Un dépassement strict (`< low` ou `> high`) ouvre un épisode. L'égalité au seuil n'est pas un dépassement. Le passage sous le seuil ou au-dessus du seuil bas ferme l'épisode. Acquitter enregistre seulement que l'utilisateur l'a vu : l'épisode continue tant que la condition existe.

L'estimation de durée utilise le temps entre acquisitions successives. Si T=31 °C à t=0, T=32 °C à t=1 et T=29 °C à t=2 avec un seuil de 30 °C, l'épisode observé dure 2 s. La résolution reste celle du cycle d'acquisition, pas celle d'une mesure continue. Une mesure manquante termine l'observation à la dernière mesure valide. Un redémarrage interrompt l'épisode à `last_seen` : aucune durée ne s'ajoute pendant l'arrêt du PC. Les écarts de cycle sont bornés à deux périodes pour éviter de compter une longue pause logicielle comme une observation continue.

Les saisons sont météorologiques : hiver décembre–février, printemps mars–mai, été juin–août, automne septembre–novembre. La date est évaluée dans le fuseau configuré. Les seuils fournis sont des exemples pédagogiques modifiables, pas des recommandations météorologiques officielles.

## 6. Stockage, historiques et statistiques

SQLite est une base locale contenue dans `data/weather.db`. Les tables sont créées au démarrage. Chaque accès ouvre sa connexion, utilise une transaction et referme la connexion. Le journal WAL permet aux lecteurs de consulter la base pendant l'enregistrement.

| Table | Contenu |
| --- | --- |
| `measurements` | Station, source, date UTC, colonnes physiques et JSON `payload` contenant valeurs brutes, unités, qualité, limites, compteur, résumé. |
| `alarms` | Début, dernière observation, fin, seuil, dernière valeur, durée, état, acquittement, station et source. |
| `wind_peaks` | Heure réelle du maximum, valeur, fenêtre, station et source. |
| `stations` | Numéros logiques déjà enregistrés. |
| `settings` | Configuration active, versions identifiées par `configuration_id` et points de reprise des cumuls de pluie. Le YAML reste la configuration chargée au lancement. |

Par défaut, chaque acquisition est gardée (environ une par seconde) et les lots sont écrits toutes les dix secondes. Une alarme ou un pic déclenche aussi la vidange du lot. Un arrêt propre vide le dernier lot. Une coupure brutale peut perdre les acquisitions en mémoire depuis la dernière écriture, au maximum approximatif de la période configurée en fonctionnement normal. Prévoir la place disque : une année à 1 Hz représente environ 31,5 millions de lignes ; ce prototype n'implémente pas de rétention ni de partitionnement.

Les statistiques utilisent toutes les lignes enregistrées de la source et de la station choisies. Les moyennes sont des moyennes des échantillons, adaptées au cycle régulier ; ce ne sont pas des intégrations pondérées par le temps en cas de cadence très irrégulière. Les mesures physiques indisponibles sont `null`, jamais remplacées par 0.

Les courbes longues sont regroupées en au plus environ 1500 points (5000 au maximum via l'API). Les moyennes de température/vent et les extrema par groupe sont renvoyés ; les pics sont interrogés séparément. Pour la direction, une moyenne **circulaire** évite de transformer 359° et 1° en 180°. Deux directions exactement opposées peuvent donner une moyenne indéterminée. Les seuils et valeurs brutes détaillés restent présents sur les périodes non regroupées et dans le CSV complet ; choisir une période plus courte pour les inspecter. Les champs bruts ne sont pas reconstruits à partir de valeurs déjà agrégées.

La rose des vents compte les observations par secteur, sans pondération par la vitesse. Chaque `payload` référence une version de configuration (`configuration_id`) conservée dans `settings` sous la clé `configuration:<identifiant>` ; les anciens coefficients restent ainsi vérifiables. Éviter de comparer des périodes d'étalonnages différents sans examiner les données brutes. Le CSV sépare les colonnes par `;` et utilise un BOM UTF-8 pour Excel.

Les dates d'API doivent contenir un décalage ou `Z`. Elles sont normalisées en UTC. Le navigateur convertit les dates choisies localement vers UTC puis affiche les résultats dans son propre fuseau. Pour un rapport journalier, sélectionner de 00:00 à 23:59 du jour souhaité (ou l'intervalle précis voulu). Les bornes sont inclusives ; un export adjacent partage donc éventuellement un point de frontière.

## 7. Bonus et leurs limites

**Confort indicatif** : `max(0, min(100, 100 - 3×|T−22| − 0,5×|HR−50| − 0,6×vent))`. T en °C, HR en %, vent en km/h. C'est une formule pédagogique arbitraire, pas un indice biométéorologique ou un avis de santé. Le score reste indisponible si l'humidité relative réelle manque ; on ne remplace pas HR par l'humectation de surface.

**Résumé automatique** : compare la température actuelle à la plus ancienne mesure récente disponible ; une différence dépassant 0,8 °C donne une tendance. Le vent est dit faible sous 10 km/h, modéré sous 30, fort au-delà. Ces seuils décrivent le projet, pas une classification officielle. Le résumé ajoute la présence de pluie si le dernier incrément est positif.

**Anomalies** : signale une température hors −80…80 °C, une humidité/luminosité relative hors 0…100 %, un vent hors 0…500 km/h ; les valeurs hors domaine sont exclues des colonnes physiques mais les bruts restent consultables. Une variation thermique de plus de 3 °C/s ou une valeur inchangée dix minutes devient suspecte. Ce sont des heuristiques nécessitant un contrôle humain. Une rafale rapide n'est pas automatiquement classée comme panne ; le calme prolongé peut rendre un capteur légitimement stable.

**Rapport** : document HTML autonome produit par `/api/report`, statistiques et graphiques SVG intégrés. Le bouton d'impression permet d'enregistrer un PDF sans bibliothèque de génération PDF. Il n'utilise ni Chart.js ni Internet.

## 8. Interface web et API

`index.html` définit les cinq vues ; `style.css` gère le thème, la grille responsive et la boussole ; `app.js` relie les boutons aux routes et met à jour Chart.js. La navigation par fragments (`#history`, etc.) conserve le même WebSocket.

`GET` lit des données ; `PUT /api/settings` reçoit la configuration complète validée ; `POST /api/alarms/{id}/acknowledge` acquitte. Les dates incorrectes et seuils inversés renvoient HTTP 422, une alarme inconnue 404, une erreur de modification 503. Les clients WebSocket reçoivent `status` et `measurement` : ils n'envoient pas d'ordre d'acquisition. Le canal se reconnecte si le serveur redémarre ; les dernières valeurs reçues sont explicitement indiquées comme anciennes en cas de perte du serveur.

L'application est prévue pour `localhost` uniquement. Les écritures et WebSockets d'une autre origine sont refusés, et les noms d'hôte sont vérifiés. Il n'y a ni compte utilisateur, ni authentification réseau : ne pas exposer directement l'application sur Internet. Le responsive permet l'affichage sur un écran étroit ; une tablette distante nécessiterait une configuration réseau et d'accès distincte, hors de ce lancement local.

## 9. Exemple de présentation orale

1. Montrer le bandeau simulation : expliquer que les valeurs sont fictives et que la carte n'est pas nécessaire pour valider l'application.
2. Suivre une mesure depuis `Simulator.read` jusqu'à `measurements`, puis au graphique WebSocket.
3. Ouvrir Paramètres : désactiver les saisons et fixer temporairement un seuil haut thermique de 20 °C pour voir un épisode d'alarme.
4. Acquitter l'alarme, montrer qu'elle reste active, puis relever le seuil et vérifier la fin et la durée.
5. Montrer l'historique, les filtres source/station, le CSV et la rose des vents.
6. Expliquer avec le TP2 la distinction Hz / impulsions / km/h et la différence humectation / humidité relative.
7. Présenter les informations NI manquantes et le diagnostic ; aucune mesure réelle n'est revendiquée sans matériel.
8. Présenter les tests et les limites : résolution temporelle, étalonnage, scrutation lente, capacité disque.
