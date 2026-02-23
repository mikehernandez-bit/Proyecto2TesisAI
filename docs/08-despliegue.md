# Despliegue

> Guia de build, release y deploy para GicaGen.

## Estado Actual

> [!NOTE]
> GicaGen es un proyecto en desarrollo. Esta guia cubre despliegue basico.

---

## Ambientes

| Ambiente | Descripcion | URL |
|----------|-------------|-----|
| **Local** | Desarrollo en maquina local | http://127.0.0.1:8001 |
| **Staging** | Pruebas pre-produccion | (por definir) |
| **Produccion** | Ambiente live | (por definir) |

> [!IMPORTANT]
> GicaGen usa el puerto **8001**. GicaTesis usa el puerto **8000**.

---

## Build

### Verificar codigo antes de deploy

```powershell
# 1. Activar entorno virtual
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Verificar que inicia
python -m uvicorn app.main:app --port 8001

# 3. Verificar health check
Invoke-RestMethod http://127.0.0.1:8001/healthz

# 4. Verificar encoding
python scripts/check_encoding.py
python scripts/check_mojibake.py
```

### No hay build step

GicaGen es una aplicacion Python + JavaScript vanilla. No requiere paso de build/compilacion.

---

## Deploy con Docker (Recomendado)

### Dockerfile (Propuesto)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copiar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar codigo
COPY app/ ./app/
COPY data/ ./data/

# Puerto
EXPOSE 8001

# Comando
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Comandos Docker

```bash
# Build imagen
docker build -t gicagen:latest .

# Ejecutar
docker run -d -p 8001:8001 \
  -e APP_ENV=prod \
  -e GICATESIS_BASE_URL=http://gicatesis:8000/api/v1 \
  -e GICAGEN_PORT=8001 \
  -v $(pwd)/data:/app/data \
  gicagen:latest

# Ver logs
docker logs -f <container_id>
```

---

## Deploy Manual (VPS/Servidor)

### 1. Preparar servidor

```bash
# Instalar Python 3.12
sudo apt update
sudo apt install python3.12 python3.12-venv

# Crear usuario
sudo useradd -m gicagen
sudo su - gicagen
```

### 2. Clonar y configurar

```bash
git clone <repo> /home/gicagen/app
cd /home/gicagen/app
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar systemd

```ini
# /etc/systemd/system/gicagen.service
[Unit]
Description=GicaGen API
After=network.target

[Service]
User=gicagen
WorkingDirectory=/home/gicagen/app
Environment="PATH=/home/gicagen/app/.venv/bin"
ExecStart=/home/gicagen/app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable gicagen
sudo systemctl start gicagen
sudo systemctl status gicagen
```

### 4. Configurar Nginx (opcional)

```nginx
# /etc/nginx/sites-available/gicagen
server {
    listen 80;
    server_name gicagen.example.com;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Variables de Entorno en Produccion

```bash
# Archivo .env o variables de sistema
APP_ENV=prod
APP_NAME="TesisAI Gen"

# GicaTesis
GICATESIS_BASE_URL=https://gicatesis.example.com/api/v1
GICATESIS_TIMEOUT=8
GICAGEN_PORT=8001
GICAGEN_BASE_URL=https://gicagen.example.com
GICAGEN_DEMO_MODE=false

# n8n (opcional)
N8N_WEBHOOK_URL=https://n8n.example.com/webhook/xxx
N8N_SHARED_SECRET=un-secreto-seguro
```

---

## Checklist Pre-Deploy

- [ ] Tests pasan (cuando se implementen)
- [ ] Variables de entorno configuradas
- [ ] `data/` tiene archivos JSON validos (o vacios: `[]`)
- [ ] Puerto 8001 disponible
- [ ] `/healthz` retorna `{"ok": true}`
- [ ] UI carga correctamente
- [ ] Encoding verificado (`python scripts/check_encoding.py`)

---

## Rollback

```bash
# Docker
docker stop gicagen-container
docker run -d -p 8001:8001 gicagen:previous-tag

# Systemd
sudo systemctl stop gicagen
cd /home/gicagen/app && git checkout v1.0.0
sudo systemctl start gicagen
```

---

## Monitoreo

### Health Check

```bash
# Endpoint
GET /healthz
# Respuesta esperada
{"ok": true, "app": "TesisAI Gen", "env": "prod", "gicatesis_url": "...", "port": 8001}
```

### Build Info

```bash
# Endpoint
GET /api/_meta/build
# Respuesta esperada
{"service": "gicagen", "cwd": "...", "started_at": "...", "git_commit": "..."}
```

### Logs

```bash
# Docker
docker logs -f <container_id>

# Systemd
journalctl -u gicagen -f
```
