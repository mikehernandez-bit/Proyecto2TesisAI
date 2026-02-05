# Runbook: Levantar Proyecto Local

> Pasos para ejecutar GicaGen en tu máquina.

## Pre-requisitos

- Python 3.10-3.13 instalado
- Git instalado
- Terminal/PowerShell

## Pasos

### 1. Clonar repositorio

```bash
git clone <url>
cd gicagen_tesis-main
```

### 2. Crear entorno virtual

**Windows:**
```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Verificar archivos de datos

```bash
# Verificar que existen (o crearlos vacíos)
cat data/prompts.json     # Debe ser [] o lista de prompts
cat data/projects.json    # Debe ser [] o lista de proyectos
```

### 5. Ejecutar servidor

```bash
python -m uvicorn app.main:app --reload
```

### 6. Verificar funcionamiento

```bash
# En otra terminal
curl http://localhost:8000/healthz
# Esperado: {"ok":true,"app":"TesisAI Gen","env":"dev"}
```

### 7. Abrir UI

Navegar a: **http://127.0.0.1:8000/**

## Validación

| Check | Comando/Acción | Resultado Esperado |
|-------|----------------|-------------------|
| Health check | `curl /healthz` | `{"ok": true}` |
| UI carga | Abrir browser | Página con sidebar |
| API responde | `curl /api/prompts` | Array de prompts |

## Troubleshooting

Ver [09-troubleshooting.md](../09-troubleshooting.md)
