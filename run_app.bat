@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creando entorno virtual...
  python -m venv .venv
)

echo [2/3] Instalando dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo [3/3] Iniciando app web local...
".venv\Scripts\python.exe" web_app.py
