from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import acquisition, service
from backend.alarms import AlarmManager
from backend.config import SensorConfig, load_config, save_config
from backend.database import Database
from backend.main import create_app
from backend.sensors import RainAccumulator, cardinal, decode_encoder, direction_angle, linear
from backend.statistics import statistics


@pytest.mark.parametrize("value", range(16))
def test_all_encoder_positions_binary_and_gray(value):
    config = SensorConfig()
    bits = [bool(value & (1 << bit)) for bit in range(4)]
    assert decode_encoder(bits, config) == value
    config.encoder_active_low = True
    assert decode_encoder([not bit for bit in bits], config) == value
    config.encoder_reverse_bits = True
    assert decode_encoder([not bit for bit in reversed(bits)], config) == value
    config.encoder_active_low = config.encoder_reverse_bits = False
    config.encoder_encoding = "gray"
    gray = value ^ (value >> 1)
    assert decode_encoder([bool(gray & (1 << bit)) for bit in range(4)], config) == value


def test_encoder_adapter_reads_four_independent_lines(monkeypatch):
    import nidaqmx
    from nidaqmx.constants import LineGrouping
    settings = load_config()
    for sensor in settings.sensors.values():
        sensor.enabled = False
    settings.sensors["counter"].enabled = True
    settings.sensors["counter"].encoder_encoding = "binary"
    settings.sensors["counter"].encoder_active_low = False
    settings.sensors["counter"].encoder_reverse_bits = False
    task = MagicMock()
    task.read.return_value = [False, False, True, True]
    monkeypatch.setattr(nidaqmx, "Task", lambda: task)
    monkeypatch.setattr(acquisition, "inventory", lambda: {"devices": [{
        "name": settings.device, "simulated": False, "analog": [], "counters": [],
        "digital": [f"{settings.device}/port1/line{i}" for i in range(4)], "terminals": []}], "error": None})
    driver = acquisition.NIAcquisition(settings)
    try:
        assert driver.read()["raw"]["counter"]["value"] == 12
        assert task.di_channels.add_di_chan.call_args.kwargs["line_grouping"] == LineGrouping.CHAN_PER_LINE
    finally:
        driver.close()


@pytest.mark.parametrize("voltage,angle,bearing", [(3.5, 0, "N"), (0, 90, "E"), (1, 180, "S"), (4, 270, "O")])
def test_reported_vane_calibration(voltage, angle, bearing):
    config = SensorConfig(calibrated=True, scale=90, offset=-45, direction_mode="table",
                          direction_voltages={"N": 3.5, "E": 0, "S": 1, "O": 4})
    assert direction_angle(voltage, config) == angle
    assert cardinal(direction_angle(voltage + .05, config)) == bearing
    assert direction_angle(2.5, config) is None
    config.calibrated = False
    assert direction_angle(voltage, config) is None


def test_light_and_rain_hold_their_physical_meaning():
    config = SensorConfig(calibrated=True, scale=-100/4.8, offset=100)
    assert linear(0, config) == 100
    assert linear(2.4, config) == pytest.approx(50)
    assert linear(4.8, config) == pytest.approx(0)
    rain = RainAccumulator()
    rain.update(10, 2, 200)
    assert rain.update(12, 2, 200)["rain_ml"] == 4
    dry = rain.update(12, 2, 200)
    assert dry["rain_ml"] == 4 and dry["rain_delta_ml"] == 0 and dry["rain_count"] == 2
    restored = RainAccumulator.restore(rain.checkpoint())
    assert restored.update(0, 2, 200)["rain_count"] == 2
    assert restored.update(1, 2, 200)["rain_ml"] == 6
    assert RainAccumulator.restore(10).total_ml == 10  # Ancien format de base.
    unknown = RainAccumulator()
    unknown.update(0, None)
    assert unknown.update(3, None)["rain_count"] == 3
    assert unknown.update(3, None)["rain_ml"] is None


def test_alarms_stay_with_their_station_and_season(tmp_path):
    db = Database(tmp_path/"weather.db")
    settings = load_config()
    settings.alarms.seasonal = False
    settings.alarms.temperature.high = 20
    settings.alarms.temperature.low = None
    manager = AlarmManager(db, settings)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    def row(t, station=1):
        return {"timestamp": t.isoformat(), "source": "hardware", "station": station, "temperature": 30}
    manager.process(row(start))
    manager.process(row(start+timedelta(seconds=2)))
    manager.process(row(start+timedelta(seconds=3), 13))
    assert db.alarms("hardware",1)[0]["status"] == "interrupted"
    assert db.alarms("hardware",13)[0]["duration"] == 0
    manager.close()
    summer = datetime(2026, 7, 1, tzinfo=timezone.utc)
    manager.process(row(summer))
    manager.process(row(summer+timedelta(seconds=1)))
    result = statistics(db, start.isoformat(), (summer+timedelta(seconds=2)).isoformat(), "hardware", 1)
    assert result["temperature_alarm_seconds"] == 3
    assert result["temperature_alarm_seconds_by_season"] == {"hiver": 2, "printemps": 0, "ete": 1, "automne": 0}


def test_service_routes_measurements_rain_and_alarms_by_encoder(tmp_path, monkeypatch):
    settings = load_config()
    settings.mode = "hardware"
    settings.station_from_encoder = True
    settings.alarms.seasonal = False
    settings.alarms.temperature.low = None
    settings.alarms.temperature.high = 20
    settings.sensors["rain"].ml_per_pulse = 2
    readings = iter([(0, 0), (12, 1), (12, 2), (0, 3)])
    db = Database(tmp_path/"weather.db")
    station = service.WeatherService(settings, db, tmp_path/"config.yaml")
    class Card:
        def __init__(self, settings): pass
        def read(self):
            encoder, rain = next(readings)
            if encoder == 0 and rain == 3:
                station.stop_event.set()
            return {"raw": {"temperature": {"value": 2.98, "unit": "V"},
                            "counter": {"value": encoder}, "rain": {"value": rain}}, "errors": {}}
        def close(self): pass
    monkeypatch.setattr(service, "NIAcquisition", Card)
    monkeypatch.setattr(station.stop_event, "wait", lambda delay: None)
    station.run()
    rows = list(station.recent)
    assert [r["station"] for r in rows] == [1, 13, 13, 1]
    assert [r["counter"] for r in rows] == [0, 12, 12, 0]
    assert [r["rain_ml"] for r in rows] == [0, 2, 4, 2]
    assert station.snapshot()["status"]["station"] == 1
    for number in (1, 13):
        assert db.alarms("hardware", number)
        assert db.history(rows[0]["timestamp"], rows[-1]["timestamp"], "hardware", number)["count"] == 2


def test_database_clear_requires_confirmation_and_does_not_reinsert_old_batches(tmp_path):
    import time
    config = tmp_path/"config.yaml"
    path = tmp_path/"weather.db"
    settings = load_config()
    settings.mode = "simulation"
    settings.save_seconds = 300
    save_config(settings, config)
    original_config = config.read_bytes()
    app = create_app(config,path)
    with TestClient(app) as client:
        deadline = time.monotonic()+5
        while app.state.service.latest is None and time.monotonic()<deadline:
            time.sleep(.02)
        db = app.state.database
        marker = {"timestamp":"2020-01-01T00:00:00+00:00","station":15,"source":"hardware"}
        db.insert_measurements([marker])
        db.create_alarm(15,"hardware","temperature","high",20,30,marker["timestamp"])
        db.insert_peak({"timestamp":marker["timestamp"],"value":40,"window_seconds":30},"hardware",15)
        db.set_setting("rain:hardware:15:2",100)
        assert client.delete("/api/database").status_code == 422
        assert client.delete("/api/database?confirm=NON").status_code == 422
        assert client.delete("/api/database?confirm=EFFACER",headers={"Origin":"https://example.com"}).status_code == 403
        cutoff = datetime.now(timezone.utc).isoformat()
        assert client.delete("/api/database?confirm=EFFACER").status_code == 200
        with db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM measurements WHERE timestamp < ?",(cutoff,)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM wind_peaks").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM alarms WHERE station=15").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM stations WHERE number=15").fetchone()[0] == 0
        assert db.get_setting("rain:hardware:15:2") is None
        assert config.read_bytes() == original_config
        assert app.state.service.thread.is_alive()
