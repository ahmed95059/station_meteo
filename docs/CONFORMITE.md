# Correspondance avec le cahier des charges

Source lue : `stationMeteo_eleves.xlsx`, feuille **Feuil2**, 56 lignes (les lignes vides et les titres ont aussi été parcourus).
Les TPs et le cours servent de références techniques ; leurs exercices LabVIEW/Tkinter ne remplacent pas le projet FastAPI demandé.

| Cellules | Exigence | Réalisation |
| --- | --- | --- |
| A1, A3 | Température | `sensors.py`, carte du tableau de bord |
| A4–A5 | Seuils haut et bas | `alarms.py`, page Paramètres |
| A6 | Temps hors limites de saison | `temperature_limits`, `statistics.py`, page Statistiques |
| A7 | Enregistrer les températures | table `measurements` |
| A8 | Courbe en direct avec limites | `app.js`, Chart.js, courbes de seuil |
| A9–A10 | Jour/semaine/mois/an et dates | page Historique, filtres UTC, dates locales |
| A12–A13 | Valeur de girouette | conversion configurable, valeur brute si non étalonnée |
| A14 | Courbe de direction | courbe dédiée au tableau de bord |
| A15–A16 | Texte et boussole | `cardinal`, boussole CSS accessible |
| A17 | Historique des directions | `measurements`, rose des vents statistique |
| A19, A21–A23 | Compteur binaire/LED/entier et station enregistrée | numéro logique 16 bits, compteur physique séparé, table `stations` |
| A25, A27–A28 | Anémomètre et courbe | comptage NI ou fréquence analogique configurable, courbe vent |
| A29–A30 | Calcul et marqueurs de pics | `WindPeaks`, table `wind_peaks`, points de pic |
| A31–A32 | Sauvegarde mesures et pics | transactions SQLite, événements immédiats |
| A34, A36 | Compteur du pluviomètre | champ `rain_count`, carte pluie |
| A37 | Conversion mL | coefficient obligatoire `ml_per_pulse` |
| A38–A40 | Alarmes pluie et limites sur graphe | seuils du cumul mL, courbe pluie |
| A41–A42 | Historique et dates pluie | mêmes filtres ; A41 mentionne « température » dans la rubrique pluie : interprété comme l'historique de pluie |
| A44, A46 | Statistiques météo | agrégats SQL, durée, rose des vents, filtres source/station |
| A50–A51 | Ergonomie IHM | cinq vues, thème sombre, navigation clavier, responsive |
| A53 | Bonus | confort pédagogique, résumé local, anomalies, rapport HTML imprimable |
| A55 | Stabilité | service indépendant, reconnexion, fermeture, tests, verrou d'instance |

## Références techniques extraites

- TP1 p. 3 et 14 : LM335, 2,98 V à 25 °C et 10 mV/°C ; pas une calibration de la maquette présente.
- TP1 p. 4 : AI3 girouette, 0,5–4,5 V ; AI7 lumière, 0–4,8 V. L'orientation doit être mesurée.
- TP2 p. 6–9 : humectation de surface AI2, 100 Hz sec / 25 Hz mouillé ; vent PFI0/CTR0, 2,4 km/h par Hz sur le capteur du TP, fronts descendants.
- Cours p. 9–11 : AI6 température ; contact pluie P0.7 ; encodeur 4 bits port P1 ; compteur CTR0.
- Cours p. 15–16 : fréquence obtenue entre fronts d'un bloc échantillonné ; ce projet utilise 1000 points à 5000 Hz par défaut (fenêtre de 200 ms).
- Cours p. 25–27 : exceptions, fermeture des tâches, USB-6001/6009. Ces deux modèles sont des exemples du labo, pas l'identification de la carte connectée.

Les réservations effectives de voies et les valeurs physiques de la carte restent à vérifier sur le matériel. La couche NI n'utilise aucune sortie électrique.
