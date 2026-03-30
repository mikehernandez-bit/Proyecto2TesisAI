from __future__ import annotations

import logging
import json
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.core.config import settings
from app.modules.api.router import router as api_router
from app.modules.ui.router import router as ui_router

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME)

# --- CONFIGURACIÓN DE RUTA DE DATOS ---
PROMPTS_FILE = os.path.join(os.getcwd(), "data", "prompts.json")

@app.middleware("http")
async def no_cache_static_js(request: Request, call_next):
    response: Response = await call_next(request)
    if request.url.path.startswith("/static/js/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(ui_router)
app.include_router(api_router, prefix="/api")

# --- NUEVO ENDPOINT: GUARDAR PROMPT EN JSON ---
@app.post("/api/save-prompt")
async def save_prompt(data: dict):
    """
    Recibe el paquete del editor y lo guarda/actualiza en data/prompts.json
    """
    try:
        # Asegurar que la carpeta data exista
        os.makedirs(os.path.dirname(PROMPTS_FILE), exist_ok=True)

        prompts_list = []
        
        # 1. Leer archivo existente si existe y no está vacío
        if os.path.exists(PROMPTS_FILE) and os.stat(PROMPTS_FILE).st_size > 0:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                try:
                    prompts_list = json.load(f)
                except json.JSONDecodeError:
                    prompts_list = []

        # 2. Obtener el ID único del nuevo prompt
        id_nuevo = data.get("id_unico")
        if not id_nuevo:
            raise HTTPException(status_code=400, detail="Falta el id_unico en los datos")

        # 3. Actualizar si existe o añadir si es nuevo
        found = False
        for i, p in enumerate(prompts_list):
            if p.get("id_unico") == id_nuevo:
                prompts_list[i] = data
                found = True
                break
        
        if not found:
            prompts_list.append(data)

        # 4. Escribir físicamente en el archivo
        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(prompts_list, f, indent=2, ensure_ascii=False)

        logger.info(f"Prompt guardado exitosamente: {id_nuevo}")
        return {"status": "success", "message": f"Prompt {id_nuevo} guardado correctamente."}

    except Exception as e:
        logger.error(f"Error al guardar prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    """Log configuration on startup."""
    logger.info(f"{settings.APP_NAME} starting")
    logger.info(f"GicaGen port: {settings.GICAGEN_PORT}")
    logger.info(f"GicaTesis base URL: {settings.GICATESIS_BASE_URL}")
    logger.info(f"GicaTesis timeout: {settings.GICATESIS_TIMEOUT}s")
    # Verificar si el archivo de prompts existe
    if not os.path.exists(PROMPTS_FILE):
        logger.warning(f"Archivo de prompts no encontrado en: {PROMPTS_FILE}. Se creará al primer guardado.")


@app.get("/healthz")
def healthz():
    """Health check endpoint."""
    return {
        "ok": True,
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "gicatesis_url": settings.GICATESIS_BASE_URL,
        "port": settings.GICAGEN_PORT,
    }
    
@app.delete("/api/delete-prompt/{id_unico}")
async def delete_prompt(id_unico: str):
    """
    Elimina un prompt específico del archivo data/prompts.json
    """
    try:
        if not os.path.exists(PROMPTS_FILE):
            return {"status": "error", "message": "Archivo no encontrado"}

        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            prompts_list = json.load(f)

        # Filtramos la lista para dejar fuera el que queremos borrar
        nueva_lista = [p for p in prompts_list if p.get("id_unico") != id_unico]

        with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
            json.dump(nueva_lista, f, indent=2, ensure_ascii=False)

        logger.info(f"Prompt eliminado del JSON: {id_unico}")
        return {"status": "success", "message": f"Prompt {id_unico} eliminado correctamente."}

    except Exception as e:
        logger.error(f"Error al eliminar prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
