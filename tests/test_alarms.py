from datetime import datetime, timedelta, timezone

import pytest

from backend.alarms import AlarmManager, temperature_limits
from backend.config import load_config
from backend.database import Database
from backend.statistics import statistics


def test_seasons_follow_local_calendar():
    settings = load_config()
    assert temperature_limits(settings, datetime(2026,1,15,tzinfo=timezone.utc)).high == 18
    assert temperature_limits(settings, datetime(2026,7,15,tzinfo=timezone.utc)).high == 35
    # 28 février 23h30 UTC = 1er mars à Paris.
    assert temperature_limits(settings, datetime(2026,2,28,23,30,tzinfo=timezone.utc)).high == 28


def test_alarm_duration_and_acknowledgement(tmp_path):
    db = Database(tmp_path/"weather.db")
    settings = load_config()
    settings.alarms.seasonal = False
    settings.alarms.temperature.low = 10
    settings.alarms.temperature.high = 30
    manager = AlarmManager(db, settings)
    start = datetime(2026,1,1,tzinfo=timezone.utc)
    def sample(second, value):
        return {"timestamp": (start+timedelta(seconds=second)).isoformat(), "source":"simulation", "station":1, "temperature":value, "rain_ml":None}
    assert manager.process(sample(0, 31))
    manager.process(sample(1, 34))
    alarm = db.alarms("simulation",1)[0]
    assert db.acknowledge(alarm["id"])
    assert db.alarms("simulation",1)[0]["status"] == "active"
    manager.process(sample(2, 29))
    alarm = db.alarms("simulation",1)[0]
    assert alarm["duration"] == 2
    assert alarm["status"] == "closed"
    stats = statistics(db,start.isoformat(),(start+timedelta(seconds=10)).isoformat(),"simulation",1)
    assert stats["temperature_alarm_seconds"] == 2
    partial = statistics(db,(start+timedelta(seconds=1)).isoformat(),(start+timedelta(seconds=5)).isoformat(),"simulation",1)
    assert partial["temperature_alarm_seconds"] == 1


def test_missing_sensor_and_restart_do_not_invent_alarm_time(tmp_path):
    path = tmp_path/"weather.db"
    db = Database(path)
    settings = load_config()
    manager = AlarmManager(db,settings)
    now = datetime(2026,1,1,tzinfo=timezone.utc)
    row={"timestamp":now.isoformat(),"temperature":40,"rain_ml":None,"station":1,"source":"hardware"}
    manager.process(row)
    row["timestamp"]=(now+timedelta(seconds=1)).isoformat()
    manager.process(row)
    row.update(timestamp=(now+timedelta(hours=1)).isoformat(),temperature=None)
    manager.process(row)
    assert db.alarms("hardware",1)[0]["duration"] == 1
    row.update(temperature=40)
    manager.process(row)
    restored=Database(path)
    alarms=restored.alarms("hardware",1)
    assert alarms[0]["status"] == "interrupted"
    assert alarms[0]["duration"] == 0


@pytest.mark.parametrize("unit,sensor", [("mL", "rain_ml"), ("mm", "rain_mm"), ("impulsions", "rain_count")])
def test_rain_low_and_high(tmp_path, unit, sensor):
    db=Database(tmp_path/"weather.db")
    settings=load_config()
    settings.alarms.rain_unit=unit
    settings.alarms.rain.low=5
    settings.alarms.rain.high=20
    manager=AlarmManager(db,settings)
    now=datetime.now(timezone.utc)
    base={"station":1,"source":"simulation","temperature":None}
    manager.process(dict(base,timestamp=now.isoformat(),**{sensor:0}))
    manager.process(dict(base,timestamp=(now+timedelta(seconds=1)).isoformat(),**{sensor:30}))
    assert {a["type"] for a in db.alarms("simulation",1)} == {"low","high"}
