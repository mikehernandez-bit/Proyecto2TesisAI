# Plan de mejoras pendientes para los índices UNAC

## Estado

**Pendiente de aplicar.** Este documento registra reglas y criterios de aceptación para una futura modificación del flujo de generación del Proyecto de Tesis UNAC. No implica cambios en el generador ni en los archivos DOCX o PDF actuales.

## 1. Índice de tablas

### Observación registrada

El documento generado contiene 5 tablas, pero el índice de tablas solo enumera 2.

- Las tablas 3.1 y 3.2 utilizan captions automáticos con el campo `SEQ Tabla` y, por ello, Word las incorpora al índice.
- Las tablas institucionales 5.1, `Cronograma de actividades`, y 6.1, `Presupuesto`, se insertan como texto exacto para conservar su formato, pero no tienen el campo `SEQ Tabla`.
- Las primeras entradas del índice aparecen en negrita porque sus captions automáticos también están en negrita.
- Falta el encabezado `Pág.` sobre la columna de números de página.

### Reglas pendientes

1. Conservar literalmente los títulos institucionales de las tablas 5.1 y 6.1.
2. Incorporar el campo técnico `SEQ Tabla` en esos títulos sin alterar su apariencia visual.
3. Aplicar a todas las entradas del índice tipografía Arial normal y sin negrita.
4. Insertar el encabezado `Pág.` alineado a la derecha sobre la columna de números de página.
5. Actualizar los campos del índice después de haber renderizado e insertado todas las tablas.
6. No depender únicamente del texto visible para identificar una tabla: cada tabla que deba aparecer en el índice tendrá un caption técnico reconocible por Word.

### Validación de aceptación

- Contar las tablas y los captions técnicos de tabla en el documento final.
- Confirmar que el número de entradas del índice sea igual al número de captions de tabla generados.
- Para el documento observado, la validación inicial debe comparar las 5 tablas existentes contra las entradas efectivamente generadas.
- Verificar que `Cronograma de actividades` y `Presupuesto` aparezcan en el índice sin cambios en sus títulos institucionales.
- Comprobar que ninguna entrada esté en negrita y que `Pág.` esté correctamente alineado.
- Bloquear la exportación definitiva o marcar el documento para revisión cuando los conteos no coincidan.

## 2. Índice de figuras

### Observación registrada

Las figuras 2.1 a 2.5 están registradas, pero sus captions incorporan innecesariamente el título completo de la tesis mediante expresiones como `aplicado a [título de tesis]`. Como el nombre del proyecto está en mayúsculas, las entradas resultan extensas y llegan al índice con bloques en mayúsculas.

El criterio esperado es un título corto, descriptivo y en estilo oración, por ejemplo:

- `Figura 2.1 Proceso del RCM`
- `Figura 2.2 Niveles taxonómicos`
- `Figura 2.3 Análisis de Modo y Efecto de Falla`
- `Figura 2.4 Motoniveladora CAT 24M`

### Reglas pendientes

1. Construir cada caption con el número de figura y un concepto técnico breve.
2. No repetir el título completo de la tesis dentro del caption.
3. Eliminar coletillas como `aplicado a [título de tesis]` cuando no aporten identificación técnica.
4. Normalizar el texto a estilo oración o título académico y evitar bloques en mayúsculas heredados del nombre del proyecto.
5. Definir un límite configurable de longitud para captions y entradas del índice.
6. Cuando un caption exceda el límite, generar una versión breve o enviarlo a revisión antes de exportar.
7. Insertar `Pág.` alineado a la derecha sobre la columna de páginas.
8. Aplicar Arial normal y sin negrita a todas las entradas del índice de figuras.

### Validación de aceptación

- Confirmar que cada figura incluida en el documento tenga un caption técnico y una entrada en el índice.
- Detectar captions que reproduzcan total o parcialmente el título del proyecto mediante una coletilla repetitiva.
- Detectar títulos completamente en mayúsculas, salvo siglas técnicas válidas como `RCM`, `CAT` o `AMEF`.
- Verificar el límite de longitud definido para el caption y para su representación en el índice.
- Comprobar uniformidad tipográfica y presencia del encabezado `Pág.`.

## 3. Índice de abreviaturas

### Observación registrada

El índice de abreviaturas actual es incompleto. En el documento aparecen siglas como `AMEF`, `CAT`, `CMMS`, `GMG`, `ISO`, `MTBF`, `MTTR`, `RCM`, `SAE` y `FMEA`, mientras que el índice recuperó únicamente `MTBF`, `SAE`, `IoT` y `FMEA`.

También existe una inconsistencia de idioma: el documento está en español, pero las definiciones recuperadas aparecen en inglés.

### Reglas pendientes

1. Analizar todo el documento final: párrafos, tablas, captions, capítulos, anexos y notas técnicas.
2. Mantener un catálogo técnico UNAC para apoyar el reconocimiento de siglas de mantenimiento y confiabilidad, incluidas `AMEF`, `CAT`, `CBM`, `CMMS`, `GMG`, `ISO`, `MTBF`, `MTTR`, `RCM` y `SAE`.
3. Usar el catálogo como ayuda de detección y normalización, no como una lista que se copie completa al índice.
4. Incorporar únicamente siglas realmente usadas y validadas en el documento.
5. Detectar definiciones por contexto en patrones como `Mantenimiento Centrado en Confiabilidad (RCM)` y `MTTR (Tiempo Medio Para Reparar)`.
6. Normalizar equivalencias lingüísticas y conceptuales, por ejemplo `AMEF` y `FMEA`, sin eliminar la variante que efectivamente se utilice.
7. Presentar las definiciones en español, salvo que el nombre oficial de una sigla internacional deba mantenerse en inglés.
8. Ordenar alfabéticamente las entradas finales.
9. No inventar definiciones: una expansión no confirmada debe quedar marcada para revisión.

### Validación de aceptación

- Crear un inventario de siglas detectadas y su ubicación en el documento final.
- Compararlo con las entradas del índice de abreviaturas.
- Verificar que toda sigla técnica repetida tenga una entrada validada o una observación explícita para revisión.
- Detectar entradas del índice correspondientes a siglas que no se usan en el documento.
- Comprobar el orden alfabético, la ausencia de duplicados y la coherencia del idioma.
- Tratar `AMEF`/`FMEA` y otras equivalencias como variantes relacionadas, conservando la forma realmente utilizada en el texto.

## 4. Orden futuro de aplicación

1. Generar todo el contenido, incluidas tablas, figuras, anexos y captions.
2. Ejecutar la normalización de títulos de tablas y figuras.
3. Insertar los campos técnicos `SEQ` y demás campos nativos de Word.
4. Analizar el documento final para construir el inventario de abreviaturas.
5. Crear o regenerar los tres índices.
6. Actualizar todos los campos de Word.
7. Ejecutar las validaciones de correspondencia, tipografía, longitud, idioma y encabezado `Pág.`.
8. Exportar a DOCX/PDF solo después de superar las validaciones o de dejar las excepciones marcadas para revisión.

## 5. Resumen de control

| Componente | Situación actual | Resultado esperado | Estado |
| --- | --- | --- | --- |
| Índice de tablas | 5 tablas y 2 entradas visibles | Una entrada por cada caption técnico de tabla | Pendiente |
| Índice de figuras | Captions extensos que repiten el título del proyecto | Captions breves, técnicos y normalizados | Pendiente |
| Índice de abreviaturas | Detección parcial y definiciones en inglés | Cobertura integral, definiciones validadas y preferentemente en español | Pendiente |
| Encabezado de páginas | Falta `Pág.` | `Pág.` alineado sobre la columna numérica | Pendiente |
| Tipografía de índices | Algunas entradas en negrita | Arial normal, sin negrita | Pendiente |

