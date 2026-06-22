@echo off
setlocal

set "GICATESIS_DIR=C:\Users\jhoan\Documents\gicateca_tesis"
set "GICAGEN_DIR=C:\Users\jhoan\Documents\VS_Project\GicaGenCorregir"

start "GicaTesis" cmd /k "cd /d %GICATESIS_DIR% && .venv\Scripts\activate && python -m uvicorn app.main:app --port 8000 --reload"
start "GicaGen" cmd /k "cd /d %GICAGEN_DIR% && .venv\Scripts\activate && python -m uvicorn app.main:app --port 8001 --reload"

endlocal
