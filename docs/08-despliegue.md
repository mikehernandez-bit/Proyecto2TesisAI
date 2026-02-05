# Despliegue

> Guía de build, release y deploy para GicaGen.

## Estado Actual

> [!NOTE]
> GicaGen es un proyecto en desarrollo. Esta guía cubre despliegue básico.

---

## Ambientes

| Ambiente | Descripción | URL |
|----------|-------------|-----|
| **Local** | Desarrollo en máquina local | http://127.0.0.1:8000 |
| **Staging** | Pruebas pre-producción | (por definir) |
| **Producción** | Ambiente live | (por definir) |

---

## Build

### Verificar código antes de deploy

```bash
# 1. Activar entorno virtual
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 2. Verificar que inicia
python -m uvicorn app.main:app

# 3. Verificar health check
curl http://localhost:8000/healthz
```

### No hay build step

GicaGen es una aplicación Python + JavaScript vanilla. No requiere paso de build/compilación.

---

## Deploy con Docker (Recomendado)

### Dockerfile (Propuesto)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copiar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY app/ ./app/
COPY data/ ./data/

# Puerto
EXPOSE 8000

# Comando
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Comandos Docker

```bash
# Build imagen
docker build -t gicagen:latest .

# Ejecutar
docker run -d -p 8000:8000 \
  -e APP_ENV=prod \
  -e FORMAT_API_BASE_URL=https://api.example.com \
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
ExecStart=/home/gicagen/app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
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
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Variables de Entorno en Producción

```bash
# Archivo .env o variables de sistema
APP_ENV=prod
APP_NAME=GicaGen
FORMAT_API_BASE_URL=https://api.formatos.example.com
FORMAT_API_KEY=xxx
N8N_WEBHOOK_URL=https://n8n.example.com/webhook/xxx
```

---

## Checklist Pre-Deploy

- [ ] Tests pasan (cuando se implementen)
- [ ] Variables de entorno configuradas
- [ ] `data/` tiene archivos JSON válidos (o vacíos: `[]`)
- [ ] Puerto 8000 disponible
- [ ] `/healthz` retorna `{"ok": true}`
- [ ] UI carga correctamente

---

## Rollback

```bash
# Docker
docker stop gicagen-container
docker run -d -p 8000:8000 gicagen:previous-tag

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
{"ok": true, "app": "GicaGen", "env": "prod"}
```

### Logs

```bash
# Docker
docker logs -f <container_id>

# Systemd
journalctl -u gicagen -f
```
