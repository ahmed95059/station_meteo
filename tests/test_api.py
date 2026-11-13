import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import ROOT, load_config, save_config
from backend.main import create_app


def prepare(tmp_path):
    config=tmp_path/"config.yaml"
    settings=load_config()
    settings.mode="simulation"  # Les tests restent indépendants du mode choisi sur la vraie station.
    settings.save_seconds=1
    save_config(settings,config)
    return config,tmp_path/"weather.db"


def await_measurement(client, source="simulation"):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        data=client.get('/api/measurements/latest').json()
        if data["measurement"] and data["measurement"]["source"]==source:
            return data
        time.sleep(.05)
    raise AssertionError("Le service n'a pas fourni de mesure")


def test_simulation_api_websocket_csv_report_restart(tmp_path):
    config,database=prepare(tmp_path)
    app=create_app(config,database)
    with TestClient(app) as client:
        data=await_measurement(client)
        assert data["status"]["state"] == "simulation"
        assert data["measurement"]["temperature"] is not None
        assert client.get('/').status_code == 200
        assert client.get('/static/vendor/chart.umd.min.js').status_code == 200
        with client.websocket_connect('/ws/measurements') as websocket:
            assert websocket.receive_json()["measurement"]["source"] == "simulation"
        time.sleep(1.2)
        assert client.get('/api/measurements/history').json()["count"] >= 2
        assert client.get('/api/statistics').json()["source"] == "simulation"
        csv=client.get('/api/export/csv')
        assert 'simulation' in csv.text and 'timestamp;station;source' in csv.text
        assert 'SIMULATION' in client.get('/api/report').text
        assert client.get('/api/measurements/history?start=2026-01-01&end=2026-02-01').status_code == 422
        assert client.get('/api/statistics?station=-1').status_code == 422
        assert client.post('/api/alarms/999/acknowledge').status_code == 404
        assert client.put('/api/settings',json=client.get('/api/settings').json(),headers={'Origin':'https://example.com'}).status_code == 403
    with TestClient(create_app(config,database)) as client:
        assert client.get('/api/measurements/history').json()["count"] >= 2


def test_mode_switch_never_falls_back_to_fake_hardware(tmp_path, monkeypatch):
    from backend import service
    def disconnected(settings):
        raise RuntimeError("Carte débranchée — test contrôlé")
    monkeypatch.setattr(service,"NIAcquisition",disconnected)
    config,database=prepare(tmp_path)
    with TestClient(create_app(config,database)) as client:
        await_measurement(client)
        settings=client.get('/api/settings').json()
        settings["mode"]="hardware"
        assert client.put('/api/settings',json=settings).status_code == 200
        data=await_measurement(client,"hardware")
        assert data["status"]["state"] == "disconnected"
        assert data["measurement"]["temperature"] is None
        assert data["measurement"]["wind"] is None
        assert 'débranchée' in data["status"]["message"]
        settings["mode"]="simulation"
        assert client.put('/api/settings',json=settings).status_code == 200
        assert await_measurement(client)["measurement"]["temperature"] is not None
        invalid=dict(settings,station_number=70000)
        assert client.put('/api/settings',json=invalid).status_code == 422


def test_reconnection_and_resource_closure(tmp_path,monkeypatch):
    from backend import service
    attempts=[]
    class FakeCard:
        def __init__(self,settings):
            self.closed=False
            self.diagnostics={}
            attempts.append(self)
        def read(self):
            if len(attempts)==1:
                raise RuntimeError("perte USB simulée pour le test")
            return {"raw":{"temperature":{"value":2.98,"unit":"V"}},"errors":{}}
        def close(self):
            self.closed=True
    monkeypatch.setattr(service,"NIAcquisition",FakeCard)
    config,database=prepare(tmp_path)
    settings=load_config(config)
    settings.mode="hardware"
    settings.sensors["temperature"].calibrated=True
    settings.sensors["temperature"].scale=100
    settings.sensors["temperature"].offset=-273
    save_config(settings,config)
    with TestClient(create_app(config,database)) as client:
        deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            data=client.get('/api/measurements/latest').json()
            if data.get('measurement',{} ) and data['measurement']['temperature']==25:
                break
            time.sleep(.1)
        assert data['measurement']['temperature']==25
        assert attempts[0].closed
    assert attempts[-1].closed
