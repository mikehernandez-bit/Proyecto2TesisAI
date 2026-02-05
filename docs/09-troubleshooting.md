# Troubleshooting

> Errores comunes y sus soluciones.

---

## Errores de Instalación

### Error: `pip` no reconocido

**Síntoma:**
```
pip : El término 'pip' no se reconoce como nombre de un cmdlet
```

**Solución:**
```bash
python -m pip install -r requirements.txt
```

---

### Error: `pydantic-core` falla al compilar

**Síntoma:**
```
error: metadata-generation-failed
× Encountered error while generating package metadata.
╰─> pydantic-core
```

**Causa:** Estás usando Python 3.14 (muy nuevo, sin wheels precompilados).

**Solución:** Usar Python 3.12:
```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

### Error: No se encuentra `python`

**Síntoma:**
```
python : El término 'python' no se reconoce
```

**Solución:** Usar el launcher de Python:
```bash
py -m venv .venv
```

---

## Errores de Ejecución

### Error: `ModuleNotFoundError: No module named 'app'`

**Causa:** Ejecutando desde directorio incorrecto o sin activar venv.

**Solución:**
```bash
cd gicagen_tesis-main
.venv\Scripts\activate
python -m uvicorn app.main:app --reload
```

---

### Error: Puerto 8000 en uso

**Síntoma:**
```
[ERROR] Address already in use
```

**Solución:**
```bash
# Opción 1: Usar otro puerto
python -m uvicorn app.main:app --port 8001

# Opción 2: Matar proceso existente (Windows)
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

---

### Error: `FileNotFoundError: data/prompts.json`

**Causa:** Archivo JSON no existe.

**Solución:**
```bash
# Crear archivos vacíos
echo [] > data/prompts.json
echo [] > data/projects.json
```

---

## Errores de API

### Error 404 en `/api/download/{id}`

**Causas posibles:**
1. Proyecto no existe
2. Proyecto aún en `processing`
3. Archivo DOCX fue eliminado

**Verificación:**
```bash
curl http://localhost:8000/api/projects/{id}
# Verificar que status = "completed" y output_file existe
```

---

### Error 500 en `/api/projects/generate`

**Causas posibles:**
1. `prompt_id` inválido
2. Error en generación DOCX

**Verificación:**
```bash
# Ver logs del servidor
# Verificar que el prompt existe
curl http://localhost:8000/api/prompts
```

---

## Errores de UI

### UI no carga estilos

**Causa:** CDN de Tailwind/FontAwesome no accesible.

**Solución:** Verificar conexión a internet o servir CSS localmente.

---

### Wizard no avanza de paso

**Causa:** Formato o prompt no seleccionado.

**Solución:** Hacer clic en una tarjeta de formato/prompt antes de "Siguiente".

---

## Errores de n8n

### n8n no responde

**Síntoma:** Generación siempre cae a modo demo.

**Verificación:**
```bash
# 1. Verificar variable configurada
echo $N8N_WEBHOOK_URL

# 2. Probar webhook manualmente
curl -X POST $N8N_WEBHOOK_URL -H "Content-Type: application/json" -d '{}'
```

---

## Comandos de Diagnóstico

```bash
# Verificar Python
python --version

# Verificar dependencias instaladas
pip list | grep fastapi

# Verificar que servidor responde
curl http://localhost:8000/healthz

# Ver archivos de datos
cat data/prompts.json
cat data/projects.json

# Ver DOCX generados
ls outputs/
```

---

## Obtener Ayuda

Si el problema persiste:

1. Revisar logs del servidor
2. Buscar error en issues del repositorio
3. Crear issue con:
   - Versión de Python (`python --version`)
   - Sistema operativo
   - Mensaje de error completo
   - Pasos para reproducir
