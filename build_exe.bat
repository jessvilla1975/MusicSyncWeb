@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
)

echo Instalando dependencias para build...
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller

echo Generando ejecutable...
".venv\Scripts\pyinstaller.exe" --onefile --name MusicSyncWebApp web_app.py

echo.
echo Listo. Ejecutable creado en: dist\MusicSyncWebApp.exe
pause
