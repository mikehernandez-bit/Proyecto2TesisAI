# Plan de integración de citas y bibliografía nativas de Microsoft Word

## Objetivo

Conseguir que las citas del documento generado por GICA sean campos editables de Microsoft Word y que la sección de referencias bibliográficas se actualice automáticamente desde las mismas fuentes.

## Fases

1. **Definir el estilo bibliográfico.** Determinar el estilo exigido por la universidad, el idioma y los tipos de fuente admitidos.
2. **Crear un registro estructurado de fuentes.** Guardar autores, año, título, tipo documental, publicación, DOI, URL e identificadores oficiales.
3. **Usar identificadores internos estables.** Cada fuente tendrá una etiqueta única que será utilizada por todas sus citas.
4. **Generar contenido mediante marcadores.** GICA deberá producir referencias internas a las fuentes, no textos finales como `(Autor, 2024)`.
5. **Validar antes de exportar.** Detectar citas sin fuente, referencias no utilizadas, duplicados, metadatos incompletos y fuentes simuladas.
6. **Insertar las fuentes en Word.** Incorporarlas en el almacén bibliográfico del `.docx` para que aparezcan en `Referencias > Administrar fuentes`.
7. **Insertar campos `CITATION`.** Sustituir los marcadores internos por citas nativas vinculadas a las fuentes registradas.
8. **Insertar el campo `BIBLIOGRAPHY`.** Generar la bibliografía desde las fuentes realmente utilizadas.
9. **Actualizar campos mediante Microsoft Word.** Abrir, actualizar y guardar el documento para materializar las citas, la bibliografía y demás campos.
10. **Migrar documentos existentes.** Convertir automáticamente solo las coincidencias seguras; enviar las ambiguas o inexistentes a revisión.
11. **Agregar controles en GICA.** Mostrar el número de citas, fuentes, inconsistencias, duplicados y referencias pendientes.
12. **Ejecutar pruebas de aceptación.** Verificar que editar una fuente actualice todas las citas y que agregar o eliminar una cita modifique la bibliografía.

## Decisión técnica recomendada

Utilizar campos nativos de Word con texto visual almacenado como respaldo. Esto permitirá trabajar con el administrador de fuentes de Word y conservar una representación visible en lectores que no actualicen los campos automáticamente.

## Dependencia de la política de fuentes

La integración no deberá convertir referencias simuladas ni páginas web genéricas. Solo se crearán fuentes nativas de Word para documentos que cumplan [05_clasificacion_y_politica_de_fuentes.md](05_clasificacion_y_politica_de_fuentes.md).

