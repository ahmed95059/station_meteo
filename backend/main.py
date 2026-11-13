"""API et fichiers statiques : lancer avec un seul worker Uvicorn."""
import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .acquisition import inventory
from .config import ROOT, Settings, load_config
from .database import Database, InstanceLock
from .service import WeatherService
from .statistics import statistics


def create_app(config_path=None, database_path=None):
    config_path = Path(config_path or os.environ.get("WEATHER_CONFIG", ROOT / "config.yaml"))
    database_path = Path(database_path or os.environ.get("WEATHER_DB", ROOT / "data" / "weather.db"))

    @asynccontextmanager
    async def lifespan(app):
        with InstanceLock(database_path):
            app.state.database = Database(database_path)
            app.state.service = WeatherService(load_config(config_path), app.state.database, config_path)
            app.state.settings_lock = asyncio.Lock()
            app.state.service.start()
            try:
                yield
            finally:
                await asyncio.to_thread(app.state.service.stop)

    app = FastAPI(title="Smart Weather Station", description="Supervision locale de la station météo", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_writes(request, call_next):
        if request.method in ("PUT", "POST", "DELETE"):
            origin = request.headers.get("origin")
            if origin and urlsplit(origin).netloc != request.headers.get("host"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Modification refusée depuis une autre origine."}, status_code=403)
        return await call_next(request)

    def scope(start=None, end=None, source=None, station=None):
        now = datetime.now(timezone.utc)
        left, right = start or now - timedelta(days=1), end or now
        if left.tzinfo is None or right.tzinfo is None:
            raise HTTPException(422, "Les dates doivent inclure le fuseau horaire (Z ou +01:00).")
        left, right = left.astimezone(timezone.utc), right.astimezone(timezone.utc)
        if left >= right:
            raise HTTPException(422, "La date de début doit précéder la date de fin.")
        if (right-left).days > 3660:
            raise HTTPException(422, "La période maximale est de 10 ans.")
        settings = app.state.service.settings
        return left.isoformat(), right.isoformat(), source or settings.mode, station if station is not None else settings.station_number

    @app.get("/api/status")
    def status():
        return app.state.service.snapshot()["status"]

    @app.get("/api/measurements/latest")
    def latest():
        return app.state.service.snapshot()

    @app.get("/api/measurements/recent")
    def recent():
        with app.state.service.lock:
            return {"items": list(app.state.service.recent)}

    @app.get("/api/measurements/history")
    def history(start: datetime | None = None, end: datetime | None = None,
                source: Literal["simulation", "hardware"] | None = None,
                station: int | None = Query(None, ge=0, le=65535), limit: int = Query(1500, ge=20, le=5000)):
        args = scope(start, end, source, station)
        return dict(app.state.database.history(*args, limit), source=args[2], station=args[3],
                    peaks=app.state.database.peaks(*args))

    @app.get("/api/statistics")
    def stats(start: datetime | None = None, end: datetime | None = None,
              source: Literal["simulation", "hardware"] | None = None,
              station: int | None = Query(None, ge=0, le=65535)):
        return statistics(app.state.database, *scope(start, end, source, station))

    @app.get("/api/alarms")
    def alarms(start: datetime | None = None, end: datetime | None = None,
               source: Literal["simulation", "hardware"] | None = None,
               station: int | None = Query(None, ge=0, le=65535)):
        left, right, origin, number = scope(start, end, source, station)
        return {"items": app.state.database.alarms(origin, number, left, right), "source": origin, "station": number}

    @app.post("/api/alarms/{alarm_id}/acknowledge")
    def acknowledge(alarm_id: int):
        if not app.state.database.acknowledge(alarm_id):
            raise HTTPException(404, "Alarme inconnue.")
        return {"ok": True}

    @app.get("/api/settings")
    def settings():
        return app.state.service.settings.model_dump()

    @app.put("/api/settings")
    async def update_settings(settings: Settings):
        async with app.state.settings_lock:
            try:
                await asyncio.to_thread(app.state.service.reconfigure, settings)
            except Exception as exc:
                raise HTTPException(503, f"Impossible d'appliquer les paramètres : {exc}") from exc
        return {"ok": True, "settings": settings.model_dump()}

    @app.get("/api/ni/devices")
    async def ni_devices():
        return await asyncio.to_thread(inventory)

    @app.get("/api/export/csv")
    def export_csv(start: datetime | None = None, end: datetime | None = None,
                   source: Literal["simulation", "hardware"] | None = None,
                   station: int | None = Query(None, ge=0, le=65535)):
        args = scope(start, end, source, station)
        columns = ["timestamp", "station", "source", "temperature", "humidity", "humidity_kind", "relative_humidity", "light",
                   "wind", "direction", "rain_count", "rain_ml", "rain_mm", "rain_delta_ml", "counter", "configuration_id", "raw", "quality", "units"]

        def generate():
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            writer.writerow(columns)
            yield "\ufeff" + output.getvalue()
            for row in app.state.database.iter_measurements(*args):
                output.seek(0)
                output.truncate()
                fields = []
                for key in columns:
                    value = row.get(key, "")
                    if isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False)
                    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
                        value = "'" + value
                    fields.append(value)
                writer.writerow(fields)
                yield output.getvalue()
        return StreamingResponse(generate(), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="mesures-meteo.csv"'})

    @app.get("/api/report", response_class=HTMLResponse)
    def report(start: datetime | None = None, end: datetime | None = None,
               source: Literal["simulation", "hardware"] | None = None,
               station: int | None = Query(None, ge=0, le=65535)):
        args = scope(start, end, source, station)
        data = statistics(app.state.database, *args)
        rows = app.state.database.history(*args, limit=400)["items"]
        def graph(key, title, unit, color):
            values = [(i, r[key]) for i, r in enumerate(rows) if r.get(key) is not None]
            if not values:
                return f"<h2>{title}</h2><p>Aucune mesure étalonnée.</p>"
            low, high = min(v for _, v in values), max(v for _, v in values)
            points = ' '.join(f'{30+i/max(1,len(rows)-1)*740:.1f},{170-(v-low)/max(1,high-low)*130:.1f}' for i,v in values)
            return f'<h2>{title}</h2><p>{low:.2f} à {high:.2f} {unit}</p><svg viewBox="0 0 800 200" role="img" aria-label="{title}"><path d="M30 20V180H780" fill="none" stroke="#888"/><polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/></svg>'
        labels = {"count": "Mesures", "temperature_mean": "Température moyenne (°C)", "temperature_min": "Température min (°C)",
                  "temperature_max": "Température max (°C)", "wind_mean": "Vent moyen (km/h)", "wind_max": "Vent max (km/h)",
                  "rain_total_ml": "Pluie de la période (mL)", "dominant_direction": "Direction dominante", "temperature_alarm_seconds": "Temps thermique hors limites (s)"}
        table = ''.join(f'<tr><th>{label}</th><td>{escape(str(round(data[key],2) if isinstance(data[key],float) else data[key] if data[key] is not None else "—"))}</td></tr>' for key,label in labels.items())
        return f'''<!doctype html><html lang="fr"><meta charset="utf-8"><title>Rapport météo</title>
        <style>body{{font:16px system-ui;max-width:900px;margin:40px auto;padding:20px;color:#16243b}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd}}svg{{width:100%}}@media print{{button{{display:none}}}}</style>
        <h1>Rapport météo · Station {args[3]}</h1><p>Source : <strong>{"SIMULATION — données fictives" if args[2]=="simulation" else "Matériel NI"}</strong></p>
        <p>Période UTC : {escape(args[0])} → {escape(args[1])}</p><button onclick="print()">Imprimer / enregistrer en PDF</button><table>{table}</table>
        {graph("temperature", "Température", "°C", "#bf7836")}{graph("wind", "Vent", "km/h", "#299385")}{graph("rain_ml", "Cumul de pluie", "mL", "#406fc4")}
        <p>Graphiques réduits à 400 points au maximum ; statistiques calculées sur toutes les mesures enregistrées. Le vent est une moyenne des fenêtres de comptage, pas une vitesse instantanée ponctuelle.</p></html>'''

    @app.websocket("/ws/measurements")
    async def measurements_socket(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(app.state.service.snapshot())
                await asyncio.sleep(app.state.service.settings.interval_seconds)
        except (WebSocketDisconnect, RuntimeError):
            pass

    app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "frontend" / "index.html")

    return app


app = create_app()
