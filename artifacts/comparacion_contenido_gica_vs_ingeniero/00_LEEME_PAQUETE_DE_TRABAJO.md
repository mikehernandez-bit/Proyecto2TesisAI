# Paquete de trabajo: comparación GICA vs. tesis del ingeniero

## Finalidad

Esta carpeta reúne los documentos de trabajo utilizados para comparar el proyecto de tesis generado por GICA con el documento de referencia del ingeniero. Debe conservarse como base para las siguientes revisiones y mejoras del generador.

## Regla principal sobre fuentes

No se aceptan páginas web genéricas como fuentes académicas. Las fuentes deben corresponder a documentos identificables, verificables y clasificables, como artículos científicos, tesis, libros, capítulos de libro, normas técnicas o documentos técnicos oficiales.

Un DOI, una URL, un enlace de repositorio o una dirección de descarga se utiliza solamente para localizar el documento. La existencia de un enlace no convierte una página web en una fuente académica válida.

La política completa se encuentra en [05_clasificacion_y_politica_de_fuentes.md](05_clasificacion_y_politica_de_fuentes.md).

## Contenido de la carpeta

| Archivo o carpeta | Propósito |
| --- | --- |
| `01_gica_proyecto_tesis.md` | Conversión completa a Markdown del documento generado por GICA. |
| `02_ejemplo_ingeniero.md` | Conversión completa a Markdown del documento de referencia. |
| `03_comparacion_contenido_gica_vs_ingeniero.md` | Comparación íntegra, sección por sección. |
| `04_auditoria_citas_por_seccion.md` | Conteo y auditoría de citas en cada sección y subsección. |
| `05_clasificacion_y_politica_de_fuentes.md` | Clasificación de las 29 referencias del ejemplo y política obligatoria para futuras fuentes. |
| `06_plan_integracion_citas_nativas_word.md` | Plan para utilizar el administrador nativo de citas y bibliografía de Microsoft Word. |
| `07_plan_mejoras_indices_unac.md` | Mejoras pendientes para los índices de tablas, figuras y abreviaturas del Proyecto de Tesis UNAC. |
| `assets/` | Imágenes extraídas de ambos documentos y utilizadas por los Markdown. |
| `build_report.py` | Generador reproducible de las conversiones, la comparación y la auditoría. |

## Documentos de origen

- GICA: `C:\Users\ingmi\Downloads\proj_977dcadd83.docx`
- Ejemplo del ingeniero: `C:\Users\ingmi\Downloads\ENTREGABLE 1_TESIS II_CAT 24M - VERSIÓN 07 - 06.02.26.docx`

## Principio de conservación

Los archivos `01` y `02` son conversiones fieles de los documentos de origen y no deben mezclarse con observaciones editoriales. Las reglas, análisis y propuestas deben mantenerse en los archivos `03` en adelante.
