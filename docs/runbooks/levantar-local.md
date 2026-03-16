# Runbook: comprobacion de uso conjunto GicaTesis + GicaGen

## Objetivo
Este documento deja evidencia operativa de que GicaGen usa GicaTesis para
consumir formatos en local.

## Regla de operacion
Para ver formatos reales en GicaGen, debes ejecutar GicaTesis.

## 1) Levantar GicaTesis
Ejecuta GicaTesis en `:8000` desde su propio repositorio.

```powershell
cd C:\Users\jhoan\Documents\gicateca_tesis
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

## 2) Levantar GicaGen
Ejecuta GicaGen en `:8001` con esta secuencia:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001
```

## 3) Comprobacion tecnica (evidencia)
Con ambos servicios arriba, valida estos endpoints:

```powershell
# GicaTesis
Invoke-RestMethod http://127.0.0.1:8000/healthz
Invoke-RestMethod http://127.0.0.1:8000/api/v1/formats

# GicaGen
Invoke-RestMethod http://127.0.0.1:8001/healthz
Invoke-RestMethod http://127.0.0.1:8001/api/formats
```

### Criterio de aceptacion
- `http://127.0.0.1:8000/api/v1/formats` responde OK en GicaTesis.
- `http://127.0.0.1:8001/api/formats` responde OK en GicaGen.
- En UI `http://127.0.0.1:8001/`, el paso de seleccion de formato carga datos.

## 3.1) Smoke de render string-only

Valida compatibilidad total con contenido plano:

```powershell
$body = @{
  formatId = "demo"
  values = @{ title = "Smoke string" }
  mode = "simulation"
  aiResult = @{
    sections = @(
      @{
        path = "Introduccion"
        content = "Texto completamente plano."
      }
    )
  }
} | ConvertTo-Json -Depth 8

Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/v1/render/docx `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -OutFile .\outputs\smoke-string.docx
```

## 3.2) Smoke de render estructurado

Valida tabla real y figura placeholder sin imprimir objetos crudos:

```powershell
$body = @{
  formatId = "demo"
  values = @{ title = "Smoke estructurado" }
  mode = "simulation"
  aiResult = @{
    sections = @(
      @{
        path = "Cronograma"
        content = @(
          @{ tipo = "parrafo"; texto = "Resumen del cronograma." }
          @{
            tipo = "tabla"
            titulo = "Tabla 1. Cronograma"
            encabezados = @("Actividad", "Mes 1", "Mes 2")
            filas = @(
              @("Revision", "X", "")
            )
          }
        )
      },
      @{
        path = "II. MARCO TEORICO/2.1 Bases teoricas"
        content = @(
          @{ tipo = "parrafo"; texto = "Marco teorico resumido." }
          @{
            tipo = "figura"
            caption = "Figura 1. Modelo conceptual."
            ruta_placeholder = "assets/placeholder_figura.png"
          }
        )
      }
    )
  }
} | ConvertTo-Json -Depth 10

Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/v1/render/docx `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -OutFile .\outputs\smoke-structured.docx
```

Resultado esperado:
- El DOCX se genera con `200 OK`.
- No aparecen listas/diccionarios crudos en el documento.
- La tabla sale como tabla real.
- La figura sale como caption + placeholder.

## 4) Prueba funcional rapida en UI
1. Abre `http://127.0.0.1:8001/`.
2. En el wizard, entra al paso 1.
3. Verifica que aparezcan tarjetas de formato.
4. Completa un flujo basico hasta generar.

## 5) Rutina diaria (Git)
Usa esta rutina diaria:

```powershell
git fetch origin
git checkout Mike
git pull origin main
git add .
git commit -m "Finalizada la parte de [descripcion de tu tarea]"
git push origin Mike
```

## 6) Nota de seguridad
No subas claves API ni tokens al repositorio. Usa solo `.env` local.
