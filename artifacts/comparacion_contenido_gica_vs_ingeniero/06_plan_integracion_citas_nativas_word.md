# Plan de integración de citas y bibliografía nativas de Microsoft Word

## Estado actual

**Integración técnica aplicada para fuentes simuladas.** GICA genera etiquetas estables, marcadores internos de cita y referencias estructuradas. GicaTesis los convierte en fuentes de la Lista actual del Administrador de fuentes, campos `CITATION` y un campo `BIBLIOGRAPHY`.

La prueba no convierte las fuentes inventadas en válidas. Cada entrada nativa incluye una advertencia explícita en `Comentarios`, y el texto del documento exige validarlas, corregirlas o reemplazarlas antes de una entrega académica. La conexión con fuentes reales y verificadas permanece pendiente.

## Objetivo

Conseguir que las citas del documento generado por GICA sean campos editables de Microsoft Word y que la sección de referencias bibliográficas se actualice automáticamente desde las mismas fuentes.

## Fases

1. **Definir el estilo bibliográfico.** Aplicado en la prueba con APA y configuración regional español (Perú); falta confirmar la exigencia final de la universidad.
2. **Crear un registro estructurado de fuentes.** Aplicado para artículos y libros simulados; faltan tesis, capítulos, normas, informes y manuales reales.
3. **Usar identificadores internos estables.** Aplicado mediante etiquetas `SIM_*`.
4. **Generar contenido mediante marcadores.** Aplicado con `[[CITE:...]]` y `[[SOURCE:...]]`.
5. **Validar antes de exportar.** Aplicado: toda fuente incorporada debe tener al menos una cita, no se admiten etiquetas desconocidas y debe existir exactamente una bibliografía.
6. **Insertar las fuentes en Word.** Aplicado en el almacén bibliográfico `customXml` del `.docx`.
7. **Insertar campos `CITATION`.** Aplicado, incluida la cita múltiple mediante el modificador `\\m`.
8. **Insertar el campo `BIBLIOGRAPHY`.** Aplicado para las fuentes citadas.
9. **Actualizar campos mediante Microsoft Word.** Aplicado en la muestra; el convertidor también guarda el DOCX después de actualizar los campos.
10. **Migrar documentos existentes.** Convertir automáticamente solo las coincidencias seguras; enviar las ambiguas o inexistentes a revisión.
11. **Agregar controles en GICA.** Mostrar el número de citas, fuentes, inconsistencias, duplicados y referencias pendientes.
12. **Ejecutar pruebas de aceptación.** Verificar que editar una fuente actualice todas las citas y que agregar o eliminar una cita modifique la bibliografía.

## Decisión técnica recomendada

Utilizar campos nativos de Word con texto visual almacenado como respaldo. Esto permitirá trabajar con el administrador de fuentes de Word y conservar una representación visible en lectores que no actualicen los campos automáticamente.

## Dependencia de la política de fuentes

La conversión nativa de una fuente simulada se autoriza únicamente como prueba técnica y debe conservar la advertencia en `Comentarios`. Para una entrega académica, solo se admitirán documentos que cumplan [05_clasificacion_y_politica_de_fuentes.md](05_clasificacion_y_politica_de_fuentes.md); las páginas web genéricas siguen excluidas.

## Evidencia de aceptación técnica

La muestra `10_muestra_validacion_citas_nativas_word.docx` fue abierta y actualizada con Microsoft Word. El resultado fue:

- 2 fuentes en la Lista actual: 1 artículo de revista y 1 libro.
- 3 campos `CITATION`, incluida una cita múltiple.
- 1 campo `BIBLIOGRAPHY`.
- 2 fuentes con advertencia de simulación en `Comentarios`.
- 6 páginas revisadas visualmente, incluida la página de respeto institucional.
