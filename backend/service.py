"""Service unique, indépendant des clients WebSocket et de l'affichage."""
import logging
import hashlib
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone

from .acquisition import NIAcquisition, inventory
from .alarms import AlarmManager, rain_sensor, season_at, temperature_limits
from .config import ROOT, load_config, save_config
from .database import Database, InstanceLock
from .sensors import AnomalyDetector, RainAccumulator, WindPeaks, cardinal, comfort, counter_delta, direction_angle, linear
from .simulator import Simulator

logger = logging.getLogger(__name__)


class WeatherService:
    def __init__(self, settings, database, config_path=ROOT / "config.yaml"):
        self.settings, self.db, self.config_path = settings, database, config_path
        self.thread, self.latest = None, None
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.status = {"state": "starting", "message": "Démarrage de l'acquisition"}
        self.recent = deque(maxlen=300)

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run_guarded, name="station-acquisition", daemon=True)
        self.thread.start()

    def run_guarded(self):
        try:
            self.run()
        except Exception as exc:
            logger.exception("Échec du démarrage ou de la fermeture du service")
            with self.lock:
                self.status = {"state": "error", "message": f"Service arrêté : {exc}"}

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=15)
            if self.thread.is_alive():
                raise RuntimeError("La tâche NI ne s'est pas fermée ; redémarrer l'application avant de rouvrir les voies.")

    def reconfigure(self, settings):
        self.stop()
        try:
            save_config(settings, self.config_path)
        except Exception:
            self.start()
            raise
        self.settings = settings
        with self.lock:
            self.latest = None
            self.recent.clear()
            self.status = {"state": "starting", "message": "Application des paramètres"}
        self.start()

    def clear_database(self):
        self.stop()  # Le dernier lot est vidé AVANT la suppression.
        try:
            self.db.clear()
            with self.lock:
                self.latest = None
                self.recent.clear()
                self.status = {"state": "starting", "message": "Base effacée, nouvelle acquisition"}
        finally:
            self.start()

    def snapshot(self):
        with self.lock:
            return {"status": dict(self.status, mode=self.settings.mode, station=self.latest["station"] if self.latest else self.settings.station_number),
                    "measurement": self.latest}

    def run(self):
        settings = self.settings
        driver, batch = None, []
        alarm_manager = AlarmManager(self.db, settings)
        peaks = WindPeaks(settings.peak_window_seconds, settings.peak_threshold_kmh)
        detector = AnomalyDetector()
        rain_config = settings.sensors["rain"]
        # Un changement d'étalonnage crée un nouveau cumul, sans réinterpréter l'ancien.
        rain_coefficient = 2.5 if settings.mode == "simulation" else rain_config.ml_per_pulse
        station = settings.station_number
        rain_key = f"rain:{settings.mode}:{station}:{rain_coefficient}"
        rain = RainAccumulator.restore(self.db.get_setting(rain_key, 0))
        previous_wind, previous_time = None, None
        window = deque()
        last_save = 0
        cycle = time.monotonic()
        configuration_id = hashlib.sha256(json.dumps(settings.model_dump(), sort_keys=True).encode()).hexdigest()[:16]
        self.db.set_setting("configuration", settings.model_dump())
        self.db.set_setting(f"configuration:{configuration_id}", settings.model_dump())

        def flush():
            nonlocal last_save
            self.db.insert_measurements(batch, checkpoint=(rain_key, rain.checkpoint()))
            batch.clear()
            last_save = cycle

        try:
            while not self.stop_event.is_set():
                cycle = time.monotonic()
                now = datetime.now(timezone.utc)
                row = {name: None for name in ("temperature", "humidity", "relative_humidity", "light", "wind", "direction", "rain_ml", "rain_mm", "rain_delta_ml", "rain_delta_mm", "rain_delta_count", "rain_count", "counter")}
                row.update(timestamp=now.isoformat(), station=station, source=settings.mode,
                           raw={}, quality={}, configuration_id=configuration_id,
                           units={name: s.unit for name, s in settings.sensors.items()})
                row["humidity_kind"] = settings.sensors["humidity"].quantity
                try:
                    if driver is None:
                        driver = Simulator() if settings.mode == "simulation" else NIAcquisition(settings)
                        rain.previous, previous_wind, previous_time = None, None, None
                    values = driver.read()
                    encoder = values.get("raw", {}).get("counter", {}).get("value")
                    if settings.mode == "hardware" and settings.station_from_encoder and encoder is not None:
                        if not 0 <= encoder <= 15:
                            raise ValueError("Encodeur hors plage 0–15.")
                        next_station = int(encoder) + 1
                        if next_station != station:
                            flush()
                            alarm_manager.close()
                            self.db.insert_peak(peaks.finish(), settings.mode, station)
                            peaks = WindPeaks(settings.peak_window_seconds, settings.peak_threshold_kmh)
                            window.clear()
                            detector = AnomalyDetector()
                            previous_wind, previous_time = None, None
                            previous_rain = rain.previous
                            station = next_station
                            rain_key = f"rain:{settings.mode}:{station}:{rain_coefficient}"
                            rain = RainAccumulator.restore(self.db.get_setting(rain_key, 0))
                            rain.previous = previous_rain
                            last_save = 0
                        row["station"] = station
                    if settings.mode == "simulation":
                        row.update(values)
                        row["units"].update(temperature="°C", direction="°", wind="km/h", rain="mL", humidity="%", light="%")
                        row.update(rain.update(values["rain_count"], 2.5, 200))
                        row["quality"] = {name: "Simulation fictive" for name in settings.sensors}
                        row["simulation_note"] = "Pluie fictive : 2,5 mL/impulsion, collecteur 200 cm². Humidité relative fictive indépendante d'AI2."
                    else:
                        row["raw"] = values["raw"]
                        for name, config in settings.sensors.items():
                            raw = values["raw"].get(name, {}).get("value")
                            row["quality"][name] = values["errors"].get(name) or ("Désactivé" if not config.enabled else "Étalonné" if config.calibrated else "Brut, non étalonné")
                            if name in ("temperature", "direction", "humidity", "light"):
                                row[name] = direction_angle(raw, config) if name == "direction" else linear(raw, config)
                                if name == "direction" and raw is not None and config.calibrated and row[name] is None:
                                    row["quality"][name] = "Tension hors des directions étalonnées : compléter la table."
                            elif name == "wind" and raw is not None:
                                read_time = values["raw"][name].get("read_monotonic", time.monotonic())
                                dt = read_time - previous_time if previous_time is not None else 0
                                hz = counter_delta(raw, previous_wind) / dt if dt > 0 else None
                                if config.kind == "frequency":
                                    hz = raw
                                row["wind"] = linear(hz, config)
                                row["raw"][name]["frequency_hz"] = hz
                                previous_wind, previous_time = raw, read_time
                            elif name == "rain" and raw is not None:
                                row["rain_count"] = raw
                                row.update(rain.update(raw, config.ml_per_pulse if config.calibrated else None, config.collector_cm2))
                                if not config.ml_per_pulse or not config.calibrated:
                                    row["quality"][name] = "Volume inconnu : renseigner et vérifier les mL par impulsion."
                                elif settings.rain_display_unit == "mm" and not config.collector_cm2:
                                    row["quality"][name] = "Hauteur inconnue : renseigner la surface de collecte en cm²."
                            elif name == "counter":
                                row["counter"] = raw
                        if row["humidity_kind"] == "relative_humidity":
                            row["relative_humidity"] = row["humidity"]
                    if row["direction"] is not None:
                        row["direction"] %= 360
                    anomalies = []
                    for name in ("temperature", "humidity", "wind", "light"):
                        # Une luminosité dans une unité autre que % n'a pas la même plage.
                        if name == "light" and row["units"][name] != "%":
                            continue
                        warnings = detector.check(name, row[name], now)
                        if warnings:
                            row["quality"][name] = " ".join(warnings)
                            anomalies += warnings
                            if warnings[0].startswith("Valeur hors domaine"):
                                row[name] = None
                                if name == "humidity":
                                    row["relative_humidity"] = None
                    errors = values.get("errors", {})
                    status = {"state": "simulation" if settings.mode == "simulation" else "sensor_error" if errors or anomalies else "connected",
                              "message": "Données fictives — aucun capteur réel" if settings.mode == "simulation" else " ; ".join(errors.values()) or "Acquisition NI active",
                              "diagnostics": getattr(driver, "diagnostics", None)}
                except Exception as exc:
                    logger.warning("Acquisition : %s", exc)
                    if driver:
                        driver.close()
                        driver = None
                    row.update({name: None for name in ("temperature", "humidity", "relative_humidity", "light", "wind", "direction", "rain_ml", "rain_mm", "rain_delta_ml", "rain_delta_mm", "rain_delta_count", "rain_count", "counter")})
                    row["quality"] = {name: str(exc) for name in settings.sensors}
                    status = {"state": "disconnected", "message": str(exc)}
                row["cardinal"] = cardinal(row["direction"]) if row["direction"] is not None else None
                row["comfort"] = comfort(row["temperature"], row["relative_humidity"], row["wind"])
                row["limits"] = {"temperature": temperature_limits(settings, now).model_dump(), rain_sensor(settings): settings.alarms.rain.model_dump()}
                row["season"] = season_at(settings, now)
                row["temperature_limit_mode"] = "seasonal" if settings.alarms.seasonal else "fixed"
                row["summary"] = self.summary(row)
                changed = alarm_manager.process(row)
                row["temperature_alarm_seconds"] = sum(a["duration"] for key, a in alarm_manager.active.items() if key[0] == "temperature")
                event = peaks.update(now, row["wind"])
                self.db.insert_peak(event, settings.mode, station)
                window.append((now, row["wind"]))
                while window and (now-window[0][0]).total_seconds() > settings.peak_window_seconds:
                    window.popleft()
                speeds = [v for _, v in window if v is not None]
                row["wind_window_max"] = max(speeds) if speeds else None
                row["peak"] = event
                batch.append(row)
                if changed or event or cycle - last_save >= settings.save_seconds:
                    flush()
                with self.lock:
                    self.latest, self.status = row, status
                    self.recent.append(row)
                delay = max(0, settings.interval_seconds - (time.monotonic() - cycle))
                self.stop_event.wait(max(delay, 3 if status["state"] == "disconnected" else 0))
        except Exception as exc:
            logger.exception("Arrêt du service d'acquisition")
            with self.lock:
                self.status = {"state": "error", "message": f"Service arrêté : {exc}"}
        finally:
            try:
                if driver:
                    driver.close()
            finally:
                alarm_manager.close()
                self.db.insert_peak(peaks.finish(), settings.mode, station)
                flush()

    def summary(self, row):
        if row["temperature"] is None:
            return "Mesure thermique indisponible : vérifier la connexion et l'étalonnage."
        trend = "stable"
        with self.lock:
            previous = next((m["temperature"] for m in self.recent if m["temperature"] is not None and m["station"] == row["station"]), None)
        if previous is not None and abs(row["temperature"]-previous) > .8:
            trend = "en hausse" if row["temperature"] > previous else "en baisse"
        wind = "indisponible" if row["wind"] is None else "faible" if row["wind"] < 10 else "modéré" if row["wind"] < 30 else "fort"
        return f"Température {trend}, vent {wind}." + (" Pluie détectée." if (row.get("rain_delta_count") or row["rain_delta_ml"] or 0) > 0 else "")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with InstanceLock(ROOT / "data" / "weather.db"):
        service = WeatherService(load_config(), Database(ROOT / "data" / "weather.db"))
        service.start()
        print("Acquisition autonome en cours. Ctrl+C pour arrêter.")
        try:
            while service.thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            service.stop()
