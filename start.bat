@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto ready
if exist ".runtime\python312\python.exe" (
  ".runtime\python312\python.exe" -m venv .venv
) else (
  py -3.12 -m venv .venv
)
if errorlevel 1 (
  echo Python 3.12 est requis. Installer Python puis relancer ce fichier.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Echec de l'installation. Verifier la connexion Internet.
  pause
  exit /b 1
)
:ready
echo.
echo Smart Weather Station : http://127.0.0.1:8000
echo API interactive : http://127.0.0.1:8000/docs
echo Ouvrir cette adresse dans le navigateur. Ctrl+C pour arreter proprement.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
if errorlevel 1 pause
endlocal
