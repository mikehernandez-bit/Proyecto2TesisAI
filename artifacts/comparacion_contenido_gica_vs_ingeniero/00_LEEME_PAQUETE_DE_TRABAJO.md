# Paquete de trabajo: comparación GICA vs. tesis del ingeniero

## Finalidad

Esta carpeta reúne los documentos de trabajo utilizados para comparar el proyecto de tesis generado por GICA con el documento de referencia del ingeniero. Debe conservarse como base para las siguientes revisiones y mejoras del generador.

## Regla principal sobre fuentes

No se aceptan páginas web genéricas como fuentes académicas. Las fuentes deben corresponder a documentos identificables, verificables y clasificables, como artículos científicos, tesis, libros, capítulos de libro, normas técnicas o documentos técnicos oficiales.

Un DOI, una URL, un enlace de repositorio o una dirección de descarga se utiliza solamente para localizar el documento. La existencia de un enlace no convierte una página web en una fuente académica válida.

La política completa se encuentra en [05_clasificacion_y_politica_de_fuentes.md](05_clasificacion_y_politica_de_fuentes.md). Durante el desarrollo se permite temporalmente contenido con referencias simuladas, pero debe quedar identificado como material de prueba y no puede considerarse una tesis académicamente validada.

## Contenido de la carpeta

| Archivo o carpeta | Propósito |
| --- | --- |
| `01_gica_proyecto_tesis.md` | Conversión completa a Markdown del documento generado por GICA. |
| `02_ejemplo_ingeniero.md` | Conversión completa a Markdown del documento de referencia. |
| `03_comparacion_contenido_gica_vs_ingeniero.md` | Comparación íntegra, sección por sección. |
| `04_auditoria_citas_por_seccion.md` | Conteo y auditoría de citas en cada sección y subsección. |
| `05_clasificacion_y_politica_de_fuentes.md` | Clasificación de las 29 referencias del ejemplo y política obligatoria para futuras fuentes. |
| `06_plan_integracion_citas_nativas_word.md` | Plan y estado de la integración con el administrador nativo de citas y bibliografía de Microsoft Word. |
| `07_plan_mejoras_indices_unac.md` | Reglas y estado de aplicación de los índices de tablas, figuras y abreviaturas del Proyecto de Tesis UNAC. |
| `08_registro_implementacion_plan_unac.md` | Registro técnico, pruebas ejecutadas, resultados y pendientes reales. |
| `09_muestra_validacion_indices_unac.docx` | Muestra generada y actualizada con Microsoft Word para validar índices y captions. |
| `10_muestra_validacion_citas_nativas_word.docx` | Muestra con fuentes simuladas visibles en la Lista actual de Word, tres campos `CITATION` y una bibliografía nativa. |
| `10_muestra_validacion_citas_nativas_word.pdf` | Vista materializada de la muestra después de actualizar todos los campos en Microsoft Word. |
| `10_entrada_muestra_citas_nativas_word.json` | Entrada reproducible utilizada para generar la muestra de citas nativas. |
| `11_muestra_validacion_citas_corregidas.docx` | Documento completo de control con citas breves, densidad basada en el ejemplo y fuentes en el Administrador de fuentes de Word. |
| `11_muestra_validacion_citas_corregidas.pdf` | Vista del documento de control después de actualizar los campos con Microsoft Word. |
| `11_entrada_validacion_citas_corregidas.json` | Entrada reproducible del documento completo de control. |
| `assets/` | Imágenes extraídas de ambos documentos y utilizadas por los Markdown. |
| `build_report.py` | Generador reproducible de las conversiones, la comparación y la auditoría. |

## Documentos de origen

- GICA: `C:\Users\ingmi\Downloads\proj_977dcadd83.docx`
- Ejemplo del ingeniero: `C:\Users\ingmi\Downloads\ENTREGABLE 1_TESIS II_CAT 24M - VERSIÓN 07 - 06.02.26.docx`

## Principio de conservación

Los archivos `01` y `02` son conversiones fieles de los documentos de origen y no deben mezclarse con observaciones editoriales. Las reglas, análisis y propuestas deben mantenerse en los archivos `03` en adelante.
