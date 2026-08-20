@echo off
setlocal enabledelayedexpansion
title Ecosistema GICA

set "GICAGEN_DIR=%~dp0"
set "GICATESIS_DIR=%~dp0..\Gicatesis"

echo ===================================================================
echo   INICIANDO ECOSISTEMA GICA (GicaTesis :8000 ^| GicaGen :8001)
echo ===================================================================

:: Iniciar GicaTesis
start "GicaTesis (Puerto 8000)" cmd /k "cd /d ""%GICATESIS_DIR%"" && echo [GICATESIS] Iniciando servidor en http://127.0.0.1:8000 ... && "".venv\Scripts\python.exe"" -m uvicorn app.main:app --port 8000 --reload || (echo. && echo [ERROR] Fallo al iniciar GicaTesis && pause)"

:: Iniciar GicaGen
start "GicaGen (Puerto 8001)" cmd /k "cd /d ""%GICAGEN_DIR%"" && echo [GICAGEN] Iniciando servidor en http://127.0.0.1:8001 ... && "".venv\Scripts\python.exe"" -m uvicorn app.main:app --port 8001 --reload || (echo. && echo [ERROR] Fallo al iniciar GicaGen && pause)"

echo Servidores iniciados en ventanas separadas.
timeout /t 5 >nul
endlocal
