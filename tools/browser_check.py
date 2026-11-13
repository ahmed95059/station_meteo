"""Vérification réelle avec Edge installé ; aucune installation de navigateur.

Préparer : python -m pip install playwright
Lancer le serveur puis : python tools/browser_check.py http://127.0.0.1:8000
La base et la configuration doivent être celles d'un environnement de test.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(url)
    assert response.status == 200
    page.wait_for_function("document.querySelector('#value-temperature').textContent.includes('°C')")
    first = page.locator('#last-update').inner_text()
    page.wait_for_function("old => document.querySelector('#last-update').textContent !== old", arg=first)
    assert page.evaluate("Chart.getChart('chart-temperature').data.labels.length") >= 2
    page.locator('[data-page=history]').click()
    page.wait_for_function("document.querySelector('#history-info').textContent.includes('mesures enregistrées')")
    page.locator('[data-days="7"]').click()
    page.select_option('#history-sensor', 'wind')
    page.wait_for_timeout(300)
    with page.expect_download() as download:
        page.locator('#export-csv').click()
    assert download.value.suggested_filename.endswith('.csv')
    page.locator('[data-page=statistics]').click()
    page.wait_for_function("document.querySelector('#statistics-cards').textContent.includes('Température moyenne')")
    assert page.evaluate("Chart.getChart('rose-chart').data.labels.length") == 8
    page.locator('[data-page=alarms]').click()
    page.wait_for_selector('#alarms-body tr')
    acknowledge = page.locator('[data-ack]').first
    if acknowledge.count():
        acknowledge.click()
        page.wait_for_function("document.querySelector('#alarms-body').textContent.includes('Acquittée')")
    page.locator('[data-page=settings]').click()
    page.locator('[data-path="station_number"]').fill('6')
    page.locator('[data-path="alarms.seasonal"]').uncheck()
    page.locator('[data-path="alarms.temperature.high"]').fill('10')
    page.locator('#settings-form [type=submit]').click()
    page.wait_for_function("document.querySelector('#settings-result').textContent.includes('enregistrés')")
    page.wait_for_function("document.querySelector('#station-header').textContent === '06'")
    page.locator('[data-page=dashboard]').click()
    page.wait_for_function("document.querySelector('#value-temperature').textContent.includes('°C')")
    page.wait_for_function("Chart.getChart('chart-temperature').data.labels.length >= 5")
    page.locator('#switch-mode').click()
    page.wait_for_function("document.querySelector('#system-status').textContent === 'Matériel déconnecté'")
    assert page.locator('#value-temperature').inner_text() == '—'
    assert page.locator('#value-wind').inner_text() == '—'
    page.locator('#switch-mode').click()
    page.wait_for_function("document.querySelector('#system-status').textContent === 'Mode simulation'")
    page.wait_for_function("Chart.getChart('chart-temperature').data.labels.length >= 5")
    # Export d'une capture locale pour inspection visuelle ; fichier généré, non versionné.
    screenshot = Path('data/dashboard-preview.png')
    screenshot.parent.mkdir(exist_ok=True)
    page.screenshot(path=str(screenshot), full_page=True)
    page.set_viewport_size({"width": 768, "height": 1024})
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    for name in ['history', 'statistics', 'alarms', 'settings', 'dashboard']:
        page.locator(f'[data-page={name}]').click()
        page.wait_for_timeout(100)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), name
    assert not errors, errors
    print(json.dumps({"status":"ok", "pages":5, "live_updates":True,"csv":True,"settings":True,
                      "mode_switch":True,"widths":[1440,768,390],"javascript_errors":errors},ensure_ascii=False))
    browser.close()
