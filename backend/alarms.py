"""Une alarme représente un épisode observé, l'acquittement ne masque pas le seuil."""
from datetime import datetime
from zoneinfo import ZoneInfo


def season_at(settings, timestamp):
    month = timestamp.astimezone(ZoneInfo(settings.timezone)).month
    season = "hiver" if month in (12, 1, 2) else "printemps" if month < 6 else "ete" if month < 9 else "automne"
    return season


def temperature_limits(settings, timestamp):
    return settings.alarms.seasons[season_at(settings, timestamp)] if settings.alarms.seasonal else settings.alarms.temperature


def rain_sensor(settings):
    return {"mL": "rain_ml", "mm": "rain_mm", "impulsions": "rain_count"}[settings.alarms.rain_unit]


class AlarmManager:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.active = {}
        self.context = None

    def process(self, measurement):
        now = datetime.fromisoformat(measurement["timestamp"])
        context = (measurement["source"], measurement["station"], season_at(self.settings, now))
        if self.context is not None and context != self.context:
            self.close()
        self.context = context
        bounds = {"temperature": temperature_limits(self.settings, now), rain_sensor(self.settings): self.settings.alarms.rain}
        expected = {}
        for sensor, limits in bounds.items():
            value = measurement.get(sensor)
            if value is None:
                continue
            for kind, threshold in (("low", limits.low), ("high", limits.high)):
                if threshold is not None and (value < threshold if kind == "low" else value > threshold):
                    expected[(sensor, kind, threshold)] = value
        changed = False
        for key in list(self.active):
            alarm = self.active[key]
            if key not in expected:
                # Valeur manquante : fin à la dernière observation, pas à une date supposée.
                missing = measurement.get(key[0]) is None
                stamp = alarm["last"] if missing else now
                if not missing:
                    alarm["duration"] += min((now-alarm["last"]).total_seconds(), 2*self.settings.interval_seconds)
                self.db.update_alarm(alarm["id"], alarm["value"], stamp.isoformat(), alarm["duration"], "interrupted" if missing else "closed")
                del self.active[key]
                changed = True
        for key, value in expected.items():
            if key not in self.active:
                alarm_id = self.db.create_alarm(measurement["station"], measurement["source"], *key, value, now.isoformat())
                self.active[key] = {"id": alarm_id, "last": now, "duration": 0, "value": value}
                changed = True
            else:
                alarm = self.active[key]
                alarm["duration"] += min((now-alarm["last"]).total_seconds(), 2*self.settings.interval_seconds)
                alarm.update(last=now, value=value)
                self.db.update_alarm(alarm["id"], value, now.isoformat(), alarm["duration"])
        return changed

    def close(self):
        for alarm in self.active.values():
            self.db.update_alarm(alarm["id"], alarm["value"], alarm["last"].isoformat(), alarm["duration"], "interrupted")
        self.active.clear()
