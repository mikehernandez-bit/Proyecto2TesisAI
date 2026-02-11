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
x Encountered error while generating package metadata.
`-> pydantic-core
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
curl http://localhost:8001/api/projects/{id}
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
curl http://localhost:8001/api/prompts
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

### Callback 401 en `/api/integrations/n8n/callback`

**Causa:** Header `X-N8N-SECRET` no coincide con `N8N_SHARED_SECRET`.

**Solución:**
```bash
# .env en GicaGen
N8N_SHARED_SECRET=mi-secreto

# Header que debe enviar n8n
X-N8N-SECRET: mi-secreto
```

---

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

## Errores de GicaTesis / Formatos

### ¿Por qué no aparece mi formato en /formats?

**Causas posibles:**

| Causa | Verificación | Solución |
|-------|--------------|----------|
| `_meta.publish = false` | `jq ._meta.publish archivo.json` | Cambiar a `true` |
| `_meta.entity` incorrecto | `jq ._meta.entity archivo.json` | Debe ser `"format"` (no `"config"`) |
| Archivo en carpeta configs | Ver ubicación del archivo | Mover a carpeta formats |
| Error de sintaxis JSON | `jq . archivo.json` | Corregir JSON |

**Diagnóstico rápido:**
```bash
# Ver bloque meta
jq ._meta archivo.json
# Esperado: {"entity": "format", "publish": true, "university": "..."}
```

---

### ¿Por qué /formats/{id} retorna 404?

**Causas:**
1. El formato tiene `publish: false` -> No es publicable
2. El formato tiene `entity: "config"` -> Es una config, no formato
3. El ID no coincide con el nombre del archivo
4. El archivo no existe en GicaTesis

**Verificación:**
```bash
# Listar todos los formatos publicables
curl http://localhost:8000/api/v1/formats | jq '.[].id'
# Verificar si tu ID está en la lista
```

---

### ¿Por qué cambió la versión sin tocar formatos?

**Explicación esperada:**
La versión del catálogo debe calcularse **SOLO** con formatos publicables. Si cambió sin modificar formatos:

- [OK] Se agregó un nuevo formato publicable -> Normal
- [OK] Se modificó un formato existente -> Normal
- [X] Solo cambió una config -> **Bug** (reportar)

**Verificación:**
```bash
# Comparar versiones
curl http://localhost:8001/api/formats/version
# El campo "changed" indica si hubo cambios desde última sync
```

---

### ¿Por qué GicaGen no cachea / siempre pide todo?

**Causas posibles:**

1. **ETag no se envía correctamente**
   - Debe incluir comillas: `If-None-Match: "valor-exacto"`
   
2. **GicaTesis cambió hash**
   - Se agregaron/modificaron formatos publicables
   
3. **Cache corrupto**
   - Eliminar `data/gicatesis_cache.json` y reiniciar

**Verificación de ETag:**
```bash
# 1. Obtener ETag actual
curl -I http://localhost:8000/api/v1/formats | grep ETag

# 2. Verificar 304 con If-None-Match
curl -H 'If-None-Match: "VALOR_DEL_ETAG"' \
     -w "%{http_code}" \
     http://localhost:8000/api/v1/formats
# Esperado: 304
```

---

### GicaTesis no responde (502/504)

**Síntomas:**
- Error 502 en `/api/formats`
- Error 504 (timeout)
- `stale: true` en respuestas

**Verificación:**
```bash
# 1. Verificar que GicaTesis está corriendo
curl http://localhost:8001/healthz

# 2. Verificar puerto correcto en .env
echo $GICATESIS_BASE_URL
# Debe ser: http://localhost:8000/api/v1
```

**Solución:**
1. Iniciar GicaTesis en puerto 8000
2. Verificar variable `GICATESIS_BASE_URL`
3. GicaGen usará cache mientras tanto (`stale: true`)

---

## Comandos de Diagnóstico

```bash
# Verificar Python
python --version

# Verificar dependencias instaladas
pip list | grep fastapi

# Verificar que servidor responde
curl http://localhost:8001/healthz

# Ver archivos de datos
cat data/prompts.json
cat data/projects.json

# Ver DOCX generados
ls outputs/

# Ver cache de GicaTesis
cat data/gicatesis_cache.json | jq .catalogVersion
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


