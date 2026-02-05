# Desarrollo Local

> Guía para configurar y ejecutar GicaGen en tu máquina local.

## Requisitos

- **Python 3.10-3.13** (⚠️ Python 3.14 puede tener problemas de compatibilidad)
- **Git** para clonar el repositorio
- **Editor de código** (VS Code recomendado)

## Instalación

### 1. Clonar repositorio

```bash
git clone <url-del-repo>
cd gicagen_tesis-main
```

### 2. Crear entorno virtual

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Mac/Linux
python -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno (opcional)

```bash
# Copiar ejemplo
cp .env.example .env

# Editar .env con tus valores
```

### 5. Ejecutar servidor

```bash
python -m uvicorn app.main:app --reload
```

### 6. Abrir aplicación

Navegar a: **http://127.0.0.1:8000/**

---

## Variables de Entorno

| Variable | Descripción | Default | Requerida |
|----------|-------------|---------|-----------|
| `APP_NAME` | Nombre de la aplicación | `TesisAI Gen` | No |
| `APP_ENV` | Ambiente (dev/prod) | `dev` | No |
| `FORMAT_API_BASE_URL` | URL de API externa de formatos | (vacío) | No |
| `FORMAT_API_KEY` | API key para formatos | (vacío) | No |
| `N8N_WEBHOOK_URL` | URL del webhook n8n | (vacío) | No |

**Archivo de referencia:** [`.env.example`](../.env.example)

---

## Estructura del Proyecto

```
gicagen_tesis-main/
├── app/                    # Código fuente
│   ├── main.py             # Entrypoint
│   ├── core/               # Lógica de negocio
│   └── modules/            # API y UI
├── data/                   # Datos JSON
├── docs/                   # Documentación
├── outputs/                # DOCX generados (creado automáticamente)
└── requirements.txt        # Dependencias
```

---

## Comandos Útiles

| Comando | Descripción |
|---------|-------------|
| `uvicorn app.main:app --reload` | Servidor con hot-reload |
| `uvicorn app.main:app --host 0.0.0.0 --port 8080` | Servidor en puerto específico |
| `pip freeze > requirements.txt` | Exportar dependencias |
| `pip install -r requirements.txt --upgrade` | Actualizar dependencias |

---

## Endpoints Principales

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/` | GET | Página principal (UI) |
| `/api/formats` | GET | Lista formatos |
| `/api/prompts` | GET/POST | Listar/crear prompts |
| `/api/prompts/{id}` | PUT/DELETE | Actualizar/eliminar prompt |
| `/api/projects` | GET | Lista proyectos |
| `/api/projects/generate` | POST | Iniciar generación |
| `/api/download/{id}` | GET | Descargar DOCX |
| `/healthz` | GET | Health check |

---

## Cómo Validar

1. Servidor inicia sin errores
2. `curl http://localhost:8000/healthz` retorna `{"ok": true, ...}`
3. UI carga en browser
4. Wizard completo funciona (crear proyecto demo)

---

## Problemas Comunes

Ver [09-troubleshooting.md](09-troubleshooting.md)
