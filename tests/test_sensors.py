from datetime import datetime, timedelta, timezone

import pytest

from backend.config import SensorConfig, load_config
from backend.sensors import AnomalyDetector, RainAccumulator, WindPeaks, cardinal, comfort, counter_delta, frequency, linear


def test_calibration_is_explicit():
    sensor = SensorConfig(scale=100, offset=-273)
    assert linear(2.98, sensor) is None
    sensor.calibrated = True
    assert linear(2.98, sensor) == pytest.approx(25)


@pytest.mark.parametrize("angle, expected", [(0,"N"),(22.4,"N"),(22.5,"NE"),(90,"E"),(180,"S"),(225,"SO"),(270,"O"),(315,"NO"),(360,"N"),(-45,"NO")])
def test_cardinal(angle, expected):
    assert cardinal(angle) == expected


def test_frequency_and_surface_wetness():
    samples = [0 if i % 50 < 25 else 4 for i in range(1000)]
    assert frequency(samples, 5000) == 100
    assert frequency([0, 4, 4], 5000) is None
    humidity = SensorConfig(calibrated=True, scale=-100/75, offset=10000/75, kind="frequency")
    assert linear(100, humidity) == pytest.approx(0)
    assert linear(25, humidity) == pytest.approx(100)


def test_wind_counting_uses_elapsed_time():
    hz = counter_delta(12, 2) / 2
    assert hz == 5
    assert linear(hz, SensorConfig(calibrated=True, scale=2.4)) == 12
    assert counter_delta(2, 2**32 - 2) == 4
    assert counter_delta(3, 20) == 3


def test_rain_resets_and_restart():
    rain = RainAccumulator(total_ml=10)
    assert rain.update(100, 2, 200)["rain_ml"] == 10  # premier compteur = référence
    assert rain.update(103, 2, 200)["rain_delta_ml"] == 6
    after_reset = rain.update(1, 2, 200)
    assert after_reset["rain_ml"] == 18
    assert after_reset["rain_mm"] == .9
    assert rain.update(4, None)["rain_ml"] is None


def test_peaks_are_maxima_of_separate_windows():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    peaks = WindPeaks(10, 20)
    assert peaks.update(start, 10) is None
    peaks.update(start+timedelta(seconds=2), 32)
    peaks.update(start+timedelta(seconds=5), 25)
    event = peaks.update(start+timedelta(seconds=10), 9)
    assert event["value"] == 32
    assert event["timestamp"] == (start+timedelta(seconds=2)).isoformat()
    assert peaks.finish() is None


def test_comfort_requires_relative_humidity():
    assert comfort(22, 50, 0) == 100
    assert comfort(22, None, 10) is None
    assert 0 <= comfort(-50, 100, 150) <= 100


def test_anomalies_do_not_label_a_gust_as_sensor_failure():
    detector = AnomalyDetector()
    now = datetime.now(timezone.utc)
    assert detector.check("wind", 10, now) == []
    assert detector.check("wind", 80, now+timedelta(seconds=1)) == []
    assert detector.check("temperature", 1000, now)
    detector.check("humidity", 40, now)
    assert "bloqué" in detector.check("humidity", 40, now+timedelta(seconds=601))[0]


def test_configuration_rejects_bad_limits_or_duplicate_channels():
    from backend.config import Settings
    from pydantic import ValidationError
    data = load_config().model_dump()
    data["alarms"]["temperature"] = {"low": 30, "high": 10}
    with pytest.raises(ValidationError):
        Settings.model_validate(data)
    data = load_config().model_dump()
    data["sensors"]["direction"]["channel"] = "ai6"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)
