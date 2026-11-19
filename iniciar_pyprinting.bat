@echo off
rem Inicia el lanzador de PyPrinting 3.0 / PySpectrum 3.0 con el entorno .venv del repositorio.
rem El entorno se crea con tools\install\instalar.ps1 (Python 3.11).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No existe .venv. Instalar primero:
    echo     powershell -ExecutionPolicy Bypass -File tools\install\instalar.ps1
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
