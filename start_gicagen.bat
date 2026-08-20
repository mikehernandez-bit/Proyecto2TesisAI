@echo off
setlocal
title GicaGen Server (:8001)

cd /d "%~dp0"
echo ===================================================
echo   Iniciando GicaGen en http://127.0.0.1:8001
echo ===================================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8001 --reload
) else (
    echo [ERROR] No se encontro el entorno virtual .venv en Gicagen
    pause
)
endlocal
