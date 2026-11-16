"""Vérification Edge isolée : aucune lecture NI, aucune écriture dans la base réelle."""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import service
from backend.config import load_config, save_config
from backend.main import create_app


def main():
    readings = {"counter": 0, "direction": 3.5, "light": 2.4, "rain": 0}
    class TestCard:
        def __init__(self, settings): pass
        def read(self):
            values = dict(readings, temperature=2.98, humidity=75, wind=0)
            return {"raw": {key: {"value": value, "unit": "V"} for key, value in values.items()}, "errors": {}}
        def close(self): pass

    service.NIAcquisition = TestCard
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config = load_config()
        config.mode = "hardware"
        config.station_from_encoder = True
        config.save_seconds = 1
        config.alarms.seasonal = False
        config.alarms.temperature.low = 10
        config.alarms.temperature.high = 24
        config.rain_display_unit = "impulsions"
        save_config(config,root/"config.yaml")
        app = create_app(root/"config.yaml",root/"weather.db")
        server = uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=8002,log_level="error"))
        thread = threading.Thread(target=server.run,daemon=True)
        thread.start()
        try:
            deadline = time.monotonic()+10
            while not server.started and time.monotonic()<deadline:
                time.sleep(.05)
            assert server.started
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge",headless=True)
                page = browser.new_page(viewport={"width":1440,"height":1100})
                errors = []
                page.on("pageerror",lambda error: errors.append(str(error)))
                page.goto("http://127.0.0.1:8002")
                page.wait_for_function("document.querySelector('#value-temperature').textContent.includes('°C')")
                page.wait_for_function("Chart.getChart('chart-temperature').data.labels.length>=2")
                assert page.evaluate("Chart.getChart('chart-temperature').chartArea.height") > 100
                assert page.locator("#station-leds .led").count() == 4
                assert page.locator("#station-leds .on").count() == 0
                assert page.locator("#station-header").inner_text() == "01"
                for value,binary,station in [(12,"1100","13"),(15,"1111","16"),(0,"0000","01")]:
                    readings["counter"] = value
                    page.wait_for_function("expected=>document.querySelector('#station-header').textContent===expected",arg=station)
                    assert page.locator("#station-binary").inner_text() == binary
                    assert page.locator("#station-leds .on").count() == binary.count("1")
                    assert page.locator("#archive-station").input_value() == str(int(station))
                page.reload()
                page.wait_for_function("Chart.getChart('chart-temperature').data.labels.length>=2")
                assert page.evaluate("recent.every(row=>row.station===1)")
                for voltage,bearing,angle in [(0,"E",90),(1,"S",180),(4,"O",270),(3.5,"N",0)]:
                    readings["direction"] = voltage
                    page.wait_for_function("bearing=>document.querySelector('#direction-cardinal').textContent===bearing",arg=bearing)
                    assert page.locator("#compass-needle").get_attribute("style").find(f"rotate({angle}deg)") >= 0
                readings["light"] = 0
                page.wait_for_function("document.querySelector('#value-light').textContent.includes('100,0')")
                readings["light"] = 4.8
                page.wait_for_function("document.querySelector('#value-light').textContent.startsWith('0,0')")
                readings["rain"] = 3
                page.wait_for_function("document.querySelector('#value-rain').textContent.includes('3,0')")
                assert "impulsions" in page.locator("#value-rain").inner_text()
                page.click("[data-page=history]")
                page.wait_for_function("Chart.getChart('history-chart').data.datasets[0]?.data.some(v=>v!==null)")
                count = page.evaluate("Chart.getChart('history-chart').data.labels.length")
                page.wait_for_function("count=>Chart.getChart('history-chart').data.labels.length>count",arg=count,timeout=12000)
                page.select_option("#history-sensor","rain_count")
                page.wait_for_function("Chart.getChart('history-chart').data.datasets[0]?.data.includes(3)")
                page.click("[data-page=statistics]")
                page.wait_for_function("document.querySelector('#statistics-summary').textContent.includes('Hiver')")
                assert page.locator("#statistics-summary").inner_text().count("Temps hors limites") == 4
                page.click("[data-page=settings]")
                page.wait_for_selector("#page-settings:not([hidden])")
                low = page.locator('[data-path="alarms.temperature.low"]')
                high = page.locator('[data-path="alarms.temperature.high"]')
                assert low.is_visible() and high.is_visible()
                page.locator('[data-path="alarms.seasonal"]').check()
                assert not low.is_visible()
                assert page.locator('[data-path="alarms.seasons.automne.high"]').is_visible()
                page.locator('[data-path="alarms.seasonal"]').uncheck()
                low.fill("15")
                high.fill("26")
                page.locator("#settings-form [type=submit]").click()
                page.wait_for_function("document.querySelector('#settings-result').textContent.includes('enregistrés')")
                assert page.locator('[data-path="sensors.direction.direction_voltages.N"]').input_value() == "3.5"
                assert page.locator('[data-path="alarms.temperature.low"]').input_value() == "15"
                # Confirmation refusée : aucune suppression.
                page.once("dialog",lambda dialog: dialog.dismiss())
                page.click("#clear-database")
                assert page.locator("#clear-result").inner_text() == ""
                page.once("dialog",lambda dialog: dialog.accept("EFFACER"))
                page.click("#clear-database")
                page.wait_for_function("document.querySelector('#clear-result').textContent.includes('Base effacée')")
                page.click("[data-page=dashboard]")
                page.wait_for_function("Chart.getChart('chart-temperature').data.datasets[0]?.data.some(v=>v!==null)")
                for width in [768,390]:
                    page.set_viewport_size({"width":width,"height":900})
                    for name in ["history","statistics","alarms","settings","dashboard"]:
                        page.click(f"[data-page={name}]")
                        page.wait_for_selector(f"#page-{name}:not([hidden])")
                        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (width,name)
                page.set_viewport_size({"width":1440,"height":1100})
                page.click("[data-page=dashboard]")
                page.wait_for_timeout(200)
                Path("data").mkdir(exist_ok=True)
                page.screenshot(path="data/corrections-preview.png",full_page=True)
                assert not errors, errors
                assert page.locator("#notice").is_hidden(), page.locator("#notice").inner_text()
                offline = browser.new_context()
                offline.route("**/vendor/chart.umd.min.js", lambda route: route.abort())
                fallback = offline.new_page()
                fallback.on("pageerror",lambda error: errors.append(str(error)))
                fallback.goto("http://127.0.0.1:8002/#settings")
                fallback.wait_for_selector('[data-path="alarms.temperature.low"]')
                assert "Chart.js" in fallback.locator("#notice").inner_text()
                assert not errors, errors
                offline.close()
                browser.close()
                print(json.dumps({"status":"ok","encoder_positions":[0,12,15],
                                  "directions":["N","E","S","O"],"live_and_history":True,
                                  "settings":True,"database_confirmation":True,"javascript_errors":errors}))
        finally:
            server.should_exit = True
            thread.join(15)


if __name__ == "__main__":
    main()
