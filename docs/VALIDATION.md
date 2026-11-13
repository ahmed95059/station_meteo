# Vérifications réalisées

Validation effectuée le **13 novembre 2026** sur Windows avec **Python 3.12.10**, installé localement dans `.runtime/python312`. Les versions directes utilisées sont figées dans `requirements.txt` et `requirements-dev.txt` ; leurs dépendances transitives restent résolues par pip.

## Tests automatisés

Commande depuis le dossier du projet :

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Résultat observé : **30 tests réussis**, en environ 6 secondes. Un avertissement de dépréciation provient du client de test Starlette utilisant httpx ; il ne signale pas un échec de l'application. `pip check` indique **No broken requirements found**.

| Domaine | Vérifications |
| --- | --- |
| Conversions | Étalonnage explicite, exemple LM335, directions et bornes des secteurs, fréquence et humectation, confort avec HR nécessaire. |
| Vent | Différences de compteur / temps écoulé, coefficient 2,4 du TP, débordement 32 bits, maxima de fenêtres, rafale distincte d'une panne. |
| Pluie | Premier relevé de référence, volume, mm, remise à zéro, conversion inconnue. |
| Alarmes | Saisons et changement de mois au fuseau local, seuils bas/haut, durée, découpage à une période, acquittement, interruption et redémarrage. |
| Base | Sauvegarde et relecture après réouverture, séparation source/station, filtres de dates, export complet, courbes regroupées et direction circulaire. |
| Service/API | Démarrage sans NI, pages statiques, WebSocket, CSV, rapport, validation HTTP, origine des écritures, changement de mode, perte/reconnexion et fermeture d'une doublure NI. |
| Adaptateur NI | Tâche analogique multivoies partagée, fréquence, compteur laissé actif entre lectures, voies absentes et fermeture après erreur d'initialisation, avec tâches factices. |
| Processus | Verrou d'instance empêchant deux propriétaires de la même base. |

`git diff --check` ne signale pas d'erreur d'espacement. Les tests d'intégration créent des bases temporaires et des copies de configuration ; ils n'altèrent pas la configuration principale.

## Vérification réelle du navigateur

Le script `tools/browser_check.py` a piloté **Edge sans fenêtre via Playwright** contre le serveur FastAPI local, avec une configuration et une base distinctes. Résultat :

```json
{"status":"ok","pages":5,"live_updates":true,"csv":true,"settings":true,
 "mode_switch":true,"widths":[1440,768,390],"javascript_errors":[]}
```

Il vérifie l'actualisation du texte et du nombre de points du graphique, les cinq vues, les raccourcis de dates, le changement de grandeur, le téléchargement CSV, les huit secteurs de la rose des vents, les réglages persistés et les changements de mode. Sans carte, le passage matériel affiche des tirets pour température et vent ; le retour simulation rétablit les données fictives. Aucun débordement horizontal de page n'a été constaté aux largeurs 768 et 390 px. La capture `data/dashboard-preview.png` a été inspectée visuellement.

Pour reproduire, utiliser deux terminaux PowerShell. **Le test modifie la configuration cible** : ne pas le diriger vers la base de travail.

Terminal 1 :

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
New-Item -ItemType Directory -Path data -Force
Copy-Item config.yaml data\browser-test.yaml
$env:WEATHER_CONFIG = "$PWD\data\browser-test.yaml"
$env:WEATHER_DB = "$PWD\data\browser-test.db"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1
```

Terminal 2 :

```powershell
.\.venv\Scripts\python.exe tools\browser_check.py http://127.0.0.1:8001
```

Edge doit être installé ; aucun téléchargement de navigateur n'est nécessaire. Arrêter le serveur de test avec Ctrl+C. Ces variables d'environnement sont limitées au terminal 1 : ouvrir un autre terminal pour le lancement normal si elles y sont encore définies.

## Ce qui n'a pas été validé physiquement

L'appel `/api/ni/devices` a renvoyé une liste vide, sans erreur de chargement NI. **Aucune carte ni aucun capteur réel n'a été mesuré.** Les essais de perte/reconnexion automatisés utilisent une doublure, et les essais navigateur constatent une absence de carte.

Restent à contrôler en laboratoire : modèle réel et nom NI MAX, brochage, niveau des tensions, terminal analogique approprié, nombre de compteurs disponibles, bornes PFI routables, durée/rebonds des contacts, coefficient volume du pluviomètre, surface de collecte, étalonnages et sens de la girouette.

L'intégration NI est codée et configurable, mais sa compatibilité effective avec une maquette doit être vérifiée lors de cette mise en service. Les tests d'historique utilisent des données synthétiques ; ils ne constituent ni une acquisition annuelle réelle, ni un test d'endurance ou de capacité sur des dizaines de millions de lignes.
