from unittest.mock import MagicMock

import pytest

from backend import acquisition
from backend.config import load_config


def setup_ni(monkeypatch):
    import nidaqmx
    created = []
    def task_factory():
        task = MagicMock()
        created.append(task)
        return task
    monkeypatch.setattr(nidaqmx, "Task", task_factory)
    monkeypatch.setattr(acquisition, "inventory", lambda: {"error": None, "devices": [{
        "name": "Dev1", "model": "DOUBLURE DE TEST", "simulated": False,
        "analog": ["Dev1/ai6", "Dev1/ai3", "Dev1/ai2"],
        "counters": ["Dev1/ctr0"], "digital": [], "terminals": ["/Dev1/PFI0"]}]})
    return created


def test_adapter_shares_analog_task_and_counts_continuously(monkeypatch):
    created = setup_ni(monkeypatch)
    settings = load_config()
    settings.sensors["humidity"].enabled = True
    settings.sensors["wind"].enabled = True
    settings.sensors["wind"].channel = "ctr0"
    settings.sensors["wind"].terminal = "PFI0"
    settings.sensors["light"].enabled = True  # voie absente du faux inventaire
    driver = acquisition.NIAcquisition(settings)
    assert len(created) == 2  # une tâche AI multivoies + un compteur
    analog, counter = created
    analog.read.return_value = [[2.98]*1000, [2.5]*1000, [0 if i%50<25 else 4 for i in range(1000)]]
    counter.read.return_value = 12
    result = driver.read()
    assert result["raw"]["temperature"]["value"] == pytest.approx(2.98)
    assert result["raw"]["humidity"]["value"] == 100
    assert result["raw"]["wind"]["value"] == 12
    assert "light" in result["errors"]
    counter.start.assert_called_once()
    counter.stop.assert_not_called()
    driver.close()
    assert all(task.close.call_count == 1 for task in created)


def test_partial_initialization_error_closes_all_tasks(monkeypatch):
    created = setup_ni(monkeypatch)
    settings = load_config()
    settings.sensors["wind"].enabled = True
    settings.sensors["wind"].channel = "ctr0"
    settings.sensors["wind"].terminal = "PFI999"
    with pytest.raises(ValueError, match="Borne compteur absente"):
        acquisition.NIAcquisition(settings)
    assert created and all(task.close.call_count == 1 for task in created)
