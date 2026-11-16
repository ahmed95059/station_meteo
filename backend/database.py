"""SQLite : connexions courtes, transactions et requêtes paramétrées."""
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

VALUES = ("temperature", "humidity", "relative_humidity", "light", "wind", "direction", "rain_ml", "rain_mm", "rain_delta_ml")


class CircularMean:
    def __init__(self):
        self.x = self.y = self.count = 0

    def step(self, angle):
        if angle is not None:
            self.x += math.cos(math.radians(angle))
            self.y += math.sin(math.radians(angle))
            self.count += 1

    def finalize(self):
        if not self.count or math.hypot(self.x, self.y) < 1e-9:
            return None
        return math.degrees(math.atan2(self.y, self.x)) % 360


class InstanceLock:
    """Verrou OS relâché même après un crash ; évite deux acquisitions concurrentes."""
    def __init__(self, database_path):
        self.path = Path(str(database_path) + ".lock")

    def __enter__(self):
        import os
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("Une autre station utilise déjà cette base. Fermer l'autre processus (un seul worker).") from exc
        return self

    def __exit__(self, *args):
        self.file.close()


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS stations(number INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS measurements(
                    id INTEGER PRIMARY KEY, station INTEGER, source TEXT, timestamp TEXT,
                    temperature REAL, humidity REAL, relative_humidity REAL, light REAL,
                    wind REAL, direction REAL, rain_ml REAL, rain_mm REAL, rain_delta_ml REAL,
                    payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_measurements_period ON measurements(source,station,timestamp);
                CREATE TABLE IF NOT EXISTS alarms(
                    id INTEGER PRIMARY KEY, station INTEGER, source TEXT, sensor TEXT, type TEXT,
                    threshold REAL, value REAL, start TEXT, end TEXT, last_seen TEXT,
                    duration REAL DEFAULT 0, status TEXT DEFAULT 'active', acknowledged INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS wind_peaks(
                    id INTEGER PRIMARY KEY, station INTEGER, source TEXT, timestamp TEXT,
                    value REAL, window_seconds REAL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            ''')
            # Une interruption n'est jamais comptée comme une longue alarme observée.
            db.execute("UPDATE alarms SET end=last_seen,status='interrupted' WHERE end IS NULL")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.create_aggregate("circular_mean", 1, CircularMean)
        try:
            with db:
                yield db
        finally:
            db.close()

    def insert_measurements(self, rows, checkpoint=None):
        if not rows and checkpoint is None:
            return
        with self.connect() as db:
            for row in rows:
                db.execute("INSERT OR IGNORE INTO stations VALUES(?)", (row["station"],))
                names = ("station", "source", "timestamp") + VALUES
                db.execute(f"INSERT INTO measurements({','.join(names)},payload) VALUES({','.join('?' for _ in names)},?)",
                           [row.get(key) for key in names] + [json.dumps(row, ensure_ascii=False, allow_nan=False)])
            if checkpoint is not None:
                key, value = checkpoint
                db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def clear(self):
        """Vider les données dans une seule transaction, acquisition arrêtée par le service."""
        with self.connect() as db:
            for table in ("measurements", "alarms", "wind_peaks", "stations", "settings"):
                db.execute(f"DELETE FROM {table}")

    def set_setting(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def get_setting(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    @staticmethod
    def where(start, end, source, station):
        return "source=? AND station=? AND timestamp>=? AND timestamp<=?", (source, station, start, end)

    def history(self, start, end, source, station, limit=1500):
        where, args = self.where(start, end, source, station)
        with self.connect() as db:
            count = db.execute(f"SELECT COUNT(*) FROM measurements WHERE {where}", args).fetchone()[0]
            if count <= limit:
                rows = db.execute(f"SELECT payload FROM measurements WHERE {where} ORDER BY timestamp,id", args).fetchall()
                return {"count": count, "aggregated": False, "items": [json.loads(r[0]) for r in rows]}
            # Les graphiques annuels restent bornés ; statistiques et CSV utilisent toutes les lignes.
            seconds = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
            bucket = max(1, seconds / max(1, limit - 1))
            fields = ','.join(f'AVG({name}) AS {name}' for name in VALUES if name not in ('rain_delta_ml', 'direction'))
            rows = db.execute(f'''SELECT MIN(timestamp) AS timestamp,{fields},
                circular_mean(direction) AS direction,
                MAX(json_extract(payload,'$.rain_count')) AS rain_count,
                AVG(json_extract(payload,'$.raw.temperature.value')) AS raw_temperature,
                AVG(json_extract(payload,'$.raw.direction.value')) AS raw_direction,
                AVG(json_extract(payload,'$.raw.humidity.value')) AS raw_humidity,
                AVG(json_extract(payload,'$.raw.light.value')) AS raw_light,
                AVG(json_extract(payload,'$.raw.wind.value')) AS raw_wind,
                SUM(rain_delta_ml) AS rain_delta_ml, MIN(temperature) AS temperature_min,
                MAX(temperature) AS temperature_max, MAX(wind) AS wind_max
                FROM measurements WHERE {where}
                GROUP BY CAST((julianday(timestamp)-2440587.5)*86400/? AS INTEGER) ORDER BY timestamp''', (*args, bucket)).fetchall()
        items = [dict(r) for r in rows]
        for row in items:
            row["raw"] = {name: {"value": row.pop(f"raw_{name}")}
                          for name in ("temperature", "direction", "humidity", "light", "wind")}
        return {"count": count, "aggregated": True, "bucket_seconds": bucket, "items": items}

    def iter_measurements(self, start, end, source, station):
        where, args = self.where(start, end, source, station)
        with self.connect() as db:
            cursor = db.execute(f"SELECT payload FROM measurements WHERE {where} ORDER BY timestamp,id", args)
            for row in cursor:
                yield json.loads(row[0])

    def aggregates(self, start, end, source, station):
        where, args = self.where(start, end, source, station)
        with self.connect() as db:
            row = dict(db.execute(f'''SELECT COUNT(*) AS count,
                AVG(temperature) AS temperature_mean, MIN(temperature) AS temperature_min,
                MAX(temperature) AS temperature_max, AVG(wind) AS wind_mean, MAX(wind) AS wind_max,
                SUM(rain_delta_ml) AS rain_total_ml,
                SUM(json_extract(payload,'$.rain_delta_count')) AS rain_total_count,
                SUM(json_extract(payload,'$.rain_delta_mm')) AS rain_total_mm,
                AVG(relative_humidity) AS relative_humidity_mean
                FROM measurements WHERE {where}''', args).fetchone())
            rose = [0] * 8
            for sector, count in db.execute(f'''SELECT CAST(((direction+22.5)%360)/45 AS INTEGER),COUNT(*)
                FROM measurements WHERE {where} AND direction IS NOT NULL GROUP BY 1''', args):
                rose[sector] = count
        row["wind_rose"] = dict(zip(("N", "NE", "E", "SE", "S", "SO", "O", "NO"), rose))
        row["dominant_direction"] = max(row["wind_rose"], key=row["wind_rose"].get) if sum(rose) else None
        return row

    def create_alarm(self, station, source, sensor, kind, threshold, value, timestamp):
        with self.connect() as db:
            cursor = db.execute('''INSERT INTO alarms(station,source,sensor,type,threshold,value,start,last_seen)
                VALUES(?,?,?,?,?,?,?,?)''', (station, source, sensor, kind, threshold, value, timestamp, timestamp))
            return cursor.lastrowid

    def update_alarm(self, alarm_id, value, timestamp, duration, status="active"):
        with self.connect() as db:
            db.execute("UPDATE alarms SET value=?,last_seen=?,duration=?,status=?,end=? WHERE id=?",
                       (value, timestamp, duration, status, None if status == "active" else timestamp, alarm_id))

    def alarms(self, source, station, start=None, end=None):
        sql = "SELECT * FROM alarms WHERE source=? AND station=?"
        args = [source, station]
        if start:
            sql += " AND COALESCE(end,last_seen)>=?"
            args.append(start)
        if end:
            sql += " AND start<=?"
            args.append(end)
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql + " ORDER BY start DESC", args)]

    def acknowledge(self, alarm_id):
        with self.connect() as db:
            return db.execute("UPDATE alarms SET acknowledged=1 WHERE id=?", (alarm_id,)).rowcount > 0

    def insert_peak(self, event, source, station):
        if event:
            with self.connect() as db:
                db.execute("INSERT INTO wind_peaks(station,source,timestamp,value,window_seconds) VALUES(?,?,?,?,?)",
                           (station, source, event["timestamp"], event["value"], event["window_seconds"]))

    def peaks(self, start, end, source, station):
        where, args = self.where(start, end, source, station)
        with self.connect() as db:
            return [dict(r) for r in db.execute(f"SELECT * FROM wind_peaks WHERE {where} ORDER BY timestamp", args)]
