@echo off
setlocal

set "GICATESIS_DIR=C:\Users\henye\Desktop\GICA\gicateca_tesis-main\gicateca_tesis-main"
set "GICAGEN_DIR=C:\Users\henye\Desktop\GICA\Proyecto2TesisAI-main\Proyecto2TesisAI-main"

start "GicaTesis" cmd /k "cd /d %GICATESIS_DIR% && .venv\Scripts\activate && python -m uvicorn app.main:app --port 8000 --reload"
start "GicaGen" cmd /k "cd /d %GICAGEN_DIR% && .venv\Scripts\activate && python -m uvicorn app.main:app --port 8001 --reload"

endlocal
