# Smart Weather Station — station météo en temps réel

Projet Python 3.12 / FastAPI / NI-DAQmx / SQLite avec interface web française. Il démarre en **simulation**, sans carte NI. L'interface affiche toujours l'origine des mesures et ne remplace jamais une panne matérielle par des valeurs fictives.

La correspondance avec toutes les lignes utiles du cahier des charges Excel est dans [CONFORMITE.md](docs/CONFORMITE.md). Les formules, les modules et leurs fonctions, les choix et les limites sont détaillés dans [EXPLICATIONS.md](docs/EXPLICATIONS.md). Les résultats des vérifications sont dans [VALIDATION.md](docs/VALIDATION.md).

## Démarrer sur ce poste

Python 3.12 et les dépendances ont été préparés dans `.runtime` et `.venv` (dossiers locaux non versionnés).

Depuis PowerShell dans le dossier du projet :

```powershell
.\start.bat
```

Ou directement :

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Dashboard : **http://127.0.0.1:8000**. API interactive : **http://127.0.0.1:8000/docs**.

Garder le terminal ouvert. Arrêter avec `Ctrl+C` pour sauvegarder le dernier lot et fermer les tâches NI. Un seul processus d'acquisition doit fonctionner ; un verrou protège la base contre les lancements concurrents. Ne pas utiliser plusieurs workers ou `--reload` pour les mesures réelles.

## Installer sur un autre PC Windows 11

1. Installer Python **3.12 64 bits** depuis [python.org](https://www.python.org/downloads/), avec le lanceur `py` et `pip`.
2. Ouvrir le dossier dans VS Code avec l'extension Python Microsoft.
3. Exécuter dans PowerShell :

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\start.bat
```

L'activation du venv et une modification de la politique d'exécution PowerShell ne sont pas nécessaires. Dans VS Code, choisir `.venv\Scripts\python.exe` via « Python: Select Interpreter ». La configuration F5 est fournie dans `.vscode/launch.json`.

Internet est nécessaire à l'installation. L'application fonctionne ensuite sans CDN : Chart.js et sa licence sont inclus dans `frontend/vendor`. Le paquet Python `nidaqmx` ne remplace pas **le pilote système NI-DAQmx**, nécessaire seulement pour le matériel. Aucun Docker, Node.js, abonnement ou clé d'API n'est requis.

## Fonctionnalités

| Vue | Fonctions |
| --- | --- |
| Tableau de bord | Mesures en direct, six courbes, limites thermiques/pluie, boussole, compteur pluie, station entière/binaire/LED, compteur physique séparé, résumé, confort indicatif, alarmes actives. |
| Historique | Capteur, source, station, dates locales ; 24 h / 7 j / 30 j / 1 an ; graphiques et export CSV complet. |
| Statistiques | Température moyenne/min/max, vent moyen/max, pluie de la période, direction dominante, rose des vents, temps thermique hors limites, rapport avec graphiques imprimable en PDF. |
| Alarmes | Seuil bas/haut, saison, début/fin, durée observée, acquittement indépendant de la fin de l'épisode. |
| Paramètres | Mode, numéro logique, voies/bornes NI, activation, types de mesure, coefficients, unités, cadence, sauvegarde, fenêtre de pic, saisons et diagnostic NI. |

Les archives sont séparées par source et numéro de station. Les valeurs non étalonnées sont montrées en brut lorsqu'elles sont disponibles ; les courbes physiques restent vides tant que la conversion n'est pas confirmée. Les courbes longues sont regroupées ; statistiques et CSV utilisent toutes les acquisitions enregistrées.

Le bouton « Passer au matériel » ferme l'ancien mode avant le nouveau. Sans carte : état « Matériel déconnecté », valeurs absentes, diagnostic et reconnexion périodique. Le bouton de retour à la simulation reste disponible.

## Essai guidé en simulation

1. Lancer le projet : vérifier le bandeau **SIMULATION · DONNÉES ENTIÈREMENT FICTIVES**.
2. Observer les courbes plusieurs secondes, les directions et les rafales. La pluie apparaît par épisodes.
3. Dans Paramètres, désactiver temporairement les saisons, fixer le seuil thermique haut à **20 °C** et enregistrer. La simulation commence vers 22 °C : une alarme s'ouvre.
4. Dans Alarmes, cliquer « 24 h » pour inclure les nouvelles observations, puis acquitter. L'épisode reste actif tant que le dépassement existe.
5. Relever le seuil à **30 °C** et enregistrer. Une modification des réglages interrompt l'ancien épisode ; le nouveau service réévalue les seuils.
6. Attendre dix secondes, puis explorer Historique, CSV et Statistiques. Un raccourci de période actualise aussi la date de fin.
7. Arrêter avec Ctrl+C, relancer et vérifier l'archive. Le tampon du direct repart à zéro ; SQLite conserve l'historique.

Réactiver ensuite les saisons si souhaité. Les seuils proposés sont pédagogiques, pas des limites officielles.

## Passer aux vrais capteurs

1. Installer le [pilote NI-DAQmx](https://www.ni.com/fr/support/downloads/drivers/download.ni-daq-mx.html) adapté à la carte et Windows.
2. Brancher la carte. Dans **NI MAX → Périphériques et interfaces**, relever son **modèle réel**, son nom exact (`Dev1` est un exemple), et vérifier qu'elle n'est pas simulée NI MAX.
3. Relever les voies AI, les lignes numériques, les compteurs et les bornes PFI. Tester les signaux et choisir RSE/DIFF/NRSE selon le câblage.
4. Identifier les capteurs, leur alimentation, les masses, les plages électriques autorisées et les références d'étalonnage.
5. Fermer les panneaux de test NI MAX et les programmes LabVIEW réservant les voies.
6. Dans Paramètres, renseigner le nom NI et activer seulement les capteurs branchés. Laisser l'étalonnage désactivé jusqu'à sa vérification.
7. Rechercher les périphériques et passer au matériel. Les premières valeurs peuvent rester en volts, hertz ou impulsions.
8. Renseigner les coefficients vérifiés, puis activer l'étalonnage. Une voie absente ou une réservation incompatible produit un diagnostic explicite.

Références des documents, **à vérifier sur la maquette présente** :

| Capteur | Voie de référence | Signal / conversion de référence |
| --- | --- | --- |
| Température | AI6 (cours p. 9) | TP1 : LM335, 2,98 V à 25 °C, 10 mV/°C. Exemple `scale=100`, `offset=-273` après confirmation. |
| Girouette | AI3 | TP1 : 0,5–4,5 V ; zéro et sens à mesurer. |
| Humectation | AI2 | TP2 : 100 Hz sec / 25 Hz mouillé. **Ce n'est pas l'humidité relative de l'air.** |
| Lumière | AI7 | TP1 : 0–4,8 V ; pourcentage relatif, pas des lux sans étalonnage. |
| Vent | CTR0 / PFI0 dans les TP | Front descendant ; exemple 2,4 km/h par Hz pour le capteur du TP. Désactivé par défaut. |
| Pluie | P0.7 dans le cours p. 10 | Contact lent : `port0/line7` si confirmé. Volume par bascule et surface inconnus. |
| Encodeur station | Port1, lignes 0–3 | Exemple `port1/line0:3` si confirmé. Lecture séparée du numéro logique. |

Le cours présente USB-6001 et USB-6009 ; cela n'identifie pas la carte connectée. Ne pas supposer un second compteur pour la pluie si le vent réserve déjà le seul compteur disponible.

## Ports, coefficients et stockage

La page Paramètres valide la configuration complète, ferme le service précédent, écrit `config.yaml` et redémarre l'acquisition. On peut aussi modifier le YAML quand le serveur est arrêté. `null` signifie non renseigné ou seuil désactivé.

Exemple **illustratif**, à vérifier avant utilisation :

```yaml
wind:
  enabled: true
  kind: counter
  channel: ctr0
  terminal: PFI0
  edge: FALLING
  calibrated: true
  scale: 2.4
  offset: 0
  unit: km/h
```

Les voies sont relatives au périphérique : `ai6`, `ctr0`, `port0/line7`, pas `Dev1/ai6`. La borne compteur accepte `PFI0` ou `/Dev1/PFI0`. La conversion est `valeur physique = scale × brut + offset` ; la pluie utilise `ml_per_pulse` et éventuellement `collector_cm2`.

`interval_seconds` règle le cycle complet (au moins 1 s pour le vent) ; `sample_rate_hz` règle les échantillons analogiques. Avec `sample_count=1000` à 5000 Hz, la fenêtre analogique dure 200 ms. Le débit total disponible dépend de la carte.

`save_seconds` règle l'écriture des lots : toutes les acquisitions sont conservées, les événements sont immédiats. Le fichier est `data/weather.db`. Les variables `WEATHER_DB` et `WEATHER_CONFIG` permettent de choisir des chemins distincts pour les tests. Les coefficients fictifs du simulateur ne sont jamais transférés au matériel.

## Lire et sauvegarder SQLite

Ouvrir `data/weather.db` dans DB Browser for SQLite ou une extension SQLite de VS Code :

```sql
SELECT timestamp, source, station, temperature, wind, rain_ml
FROM measurements ORDER BY id DESC LIMIT 20;

SELECT sensor, threshold, start, end, duration, status, acknowledged
FROM alarms ORDER BY id DESC;

SELECT * FROM wind_peaks ORDER BY timestamp DESC;
```

Arrêter le serveur avant de copier `weather.db` pour une sauvegarde simple. À chaud, employer l'API de sauvegarde SQLite plutôt qu'une copie ignorant son journal WAL.

Chaque mesure porte la source, la station, l'heure UTC et une version de configuration. `payload` contient les valeurs brutes, unités et qualités. `settings` conserve les versions des coefficients et les cumuls de pluie. Le CSV et le rapport utilisent les filtres de l'interface ; le rapport contient ses graphiques SVG et s'imprime en PDF dans le navigateur.

## Tests et validation

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Les tests couvrent conversions, directions, fréquence, vent, pics, pluie, remises à zéro, saisons, seuils, durées, acquittement, SQLite, filtres, moyenne circulaire, redémarrage, verrou, API, WebSocket et perte/reconnexion NI **avec des doublures de test**. Les bases temporaires ne touchent pas à `data/weather.db`.

`tools/browser_check.py` vérifie l'interface avec Edge et Playwright. Il doit viser une configuration et une base de test, car il modifie station, seuils et mode. Commandes et résultats : [VALIDATION.md](docs/VALIDATION.md).

## Limites et soutenance

- La vraie carte et les capteurs n'ont pas été testés. Le diagnostic initial ne détecte aucun périphérique NI.
- AI2 dans le TP mesure l'humectation. Une vraie humidité relative exige un autre capteur ; le confort matériel reste absent sans HR.
- Le contact pluie scruté en logiciel peut perdre des impulsions courtes. Utiliser un compteur matériel si possible. Les impulsions pendant une coupure sont inconnues.
- Windows/Python ne garantit pas le temps réel dur. La vitesse correspond à l'intervalle compté ; les durées d'alarme ont la résolution du cycle.
- Une coupure brutale peut perdre le lot en mémoire. L'arrêt propre sauvegarde ce lot.
- Aucune rétention automatique : une année à 1 Hz représente environ 31,5 millions de lignes et nécessite un espace disque adapté.
- Modifier les paramètres interrompt les épisodes et réinitialise la référence du compteur ; archives et cumuls validés sont conservés.
- L'application écoute sur `127.0.0.1`, sans authentification réseau. Ne pas l'exposer directement sur Internet. L'accès d'une tablette distante demanderait une configuration réseau et d'accès distincte.

## Organisation du projet

```text
backend/             configuration, NI, simulation, conversions, alarmes,
                     statistiques, SQLite, service et API
frontend/            index.html, style.css, app.js, vendor/Chart.js
tests/               test_sensors, test_alarms, test_database,
                     test_acquisition, test_api
docs/                CONFORMITE.md, EXPLICATIONS.md, VALIDATION.md
tools/               read_sources.py, browser_check.py
data/                base créée au lancement
.vscode/             interpréteur, tests et F5
config.yaml          configuration commentée
requirements*.txt    dépendances
pytest.ini           configuration des tests
start.bat            lancement Windows
```

[EXPLICATIONS.md](docs/EXPLICATIONS.md) développe chaque module et chaque calcul, du capteur au graphique, et propose un déroulé de démonstration orale. Le parcours local du skill Sites a guidé la vérification de l'interface et le projet conserve le backend Python demandé.

Références officielles : [NI-DAQmx Python](https://nidaqmx-python.readthedocs.io/en/stable/), [canaux et compteurs](https://nidaqmx-python.readthedocs.io/en/stable/task_channels.html), [WebSockets FastAPI](https://fastapi.tiangolo.com/advanced/websockets/).
