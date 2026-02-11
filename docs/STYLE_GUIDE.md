# Guía de Estilo y Encoding

> OBLIGATORIO: Reglas para mantener la integridad del repositorio y evitar problemas de encoding (mojibake).

## 1. Encoding

- **Todos los archivos DEBEN guardarse en UTF-8.**
- Evitar BOM (Byte Order Mark) si es posible.
- **Configuración de VS Code recomendada:**
  ```json
  "files.encoding": "utf8",
  "files.autoGuessEncoding": false
  ```

## 2. Caracteres Prohibidos

Para evitar corrupción cruzada entre sistemas (Windows Latin-1 vs Linux UTF-8), **NO USAR** los siguientes caracteres en documentación ni código fuente:

- **Flechas Unicode:** `\u2192` (Right Arrow), `\u2190` (Left Arrow). **Usar ASCII:** `->`, `<-`
- **Emojis:** **Usar etiquetas de texto:** `[WARN]`, `[OK]`, `[X]`
- **Box Drawing:** `\u251C` (Box Vertical and Right), etc. **Usar ASCII para árboles (`+--`, `|`, `--`).**

### Ejemplo de Árboles (Correcto vs Incorrecto)

❌ **Incorrecto (Box Drawing):**
(Evitar caracteres gráficos de caja)

✅ **Correcto (ASCII Seguro):**
```
Carpeta/
+-- Archivo
`-- Otro
```

## 3. Validación

Se ha incluido un script de verificación en `scripts/check_encoding.py`.
Antes de hacer commit, ejecutar:

```bash
python scripts/check_encoding.py
python scripts/check_mojibake.py
```
