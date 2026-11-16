from datetime import datetime, timedelta, timezone

import pytest

from backend.database import Database, InstanceLock


def make_rows(count=100):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    return [{"station":1,"source":"simulation","timestamp":(start+timedelta(seconds=i)).isoformat(),
             "temperature":i,"wind":i/2,"direction":359 if i%2 else 1,"rain_delta_ml":2,
             "raw":{"temperature":{"value":2.98,"unit":"V"}},"quality":{"temperature":"Simulation fictive"}}
            for i in range(count)]


def test_storage_history_filters_and_restart(tmp_path):
    path=tmp_path/"weather.db"
    db=Database(path)
    rows=make_rows()
    db.insert_measurements(rows)
    db.insert_measurements([dict(rows[0],source="hardware",temperature=-10),dict(rows[0],station=2,temperature=200)])
    args=(rows[0]["timestamp"],rows[-1]["timestamp"],"simulation",1)
    restored=Database(path)
    history=restored.history(*args)
    assert history["count"] == 100
    assert history["items"][0]["raw"]["temperature"]["value"] == 2.98
    stats=restored.aggregates(*args)
    assert stats["temperature_mean"] == 49.5
    assert stats["rain_total_ml"] == 200
    assert stats["wind_rose"]["N"] == 100
    assert len(list(restored.iter_measurements(*args))) == 100
    clipped=restored.history(rows[10]["timestamp"],rows[20]["timestamp"],"simulation",1)
    assert clipped["count"] == 11


def test_downsampling_keeps_stats_complete(tmp_path):
    db=Database(tmp_path/"weather.db")
    rows=make_rows(200)
    db.insert_measurements(rows)
    args=(rows[0]["timestamp"],rows[-1]["timestamp"],"simulation",1)
    data=db.history(*args,limit=20)
    assert data["aggregated"]
    assert len(data["items"]) <= 21
    assert db.aggregates(*args)["temperature_max"] == 199
    assert all(min(r["direction"],360-r["direction"])<2 for r in data["items"])
    assert all(r["raw"]["temperature"]["value"] == pytest.approx(2.98) for r in data["items"])


def test_single_instance_lock(tmp_path):
    path=tmp_path/"weather.db"
    with InstanceLock(path):
        with pytest.raises(RuntimeError):
            with InstanceLock(path):
                pass
    with InstanceLock(path):
        pass
