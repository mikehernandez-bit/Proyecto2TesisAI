# Registro de implementación del plan UNAC

## Resultado

Las mejoras de índices, captions, abreviaturas y citas nativas de Word fueron incorporadas al flujo real que genera el Proyecto de Tesis UNAC. La generación se detiene si los captions no corresponden con lo renderizado o si una fuente nativa no coincide con sus campos de cita.

## Cambios aplicados

### Tablas e índice de tablas

- Las tablas institucionales `5.1 Cronograma de actividades` y `6.1 Presupuesto de investigación` conservan su texto visible y ahora incluyen un campo nativo `SEQ Tabla`.
- Todos los captions de tabla se generan en Arial normal y sin negrita directa.
- El índice automático utiliza el estilo de Word `Table of Figures`, configurado en Arial 10 normal.
- Se inserta `Pág.` alineado a la derecha antes del campo del índice.
- El DOCX entrega resultados almacenados completos y elimina `w:updateFields`; Word ya no debe mostrar la advertencia genérica de actualización al abrirlo.

### Figuras e índice de figuras

- Los captions se reducen a un concepto técnico breve.
- Se eliminan coletillas repetitivas como `aplicado a [título del proyecto]`.
- Los títulos completamente en mayúsculas se convierten a estilo oración sin alterar siglas como `RCM`, `CAT`, `AMEF`, `MTBF` o `MTTR`.
- La longitud máxima configurada es de 120 caracteres y el recorte respeta límites de palabra.
- El índice incorpora `Pág.` y usa tipografía Arial normal.

### Índice de abreviaturas

- La detección recorre párrafos, tablas, captions, capítulos, anexos y notas que se renderizan en el documento.
- El catálogo técnico incluye `AMEF`, `CAT`, `CBM`, `CMMS`, `GMG`, `ISO`, `MTBF`, `MTTR`, `RCM`, `SAE`, `FMEA` y otras siglas técnicas previstas.
- Solo se incorporan siglas realmente usadas.
- Las definiciones se muestran en español cuando corresponde y se conservan en inglés cuando forman parte del nombre oficial.
- Las entradas se ordenan alfabéticamente.
- La validación detecta siglas técnicas repetidas que no tengan entrada en el índice.

### Citas y referencias nativas de Word

- Gicagen añade identificadores estables `SIM_*` a las referencias de prueba y coloca marcadores de cita en el contenido narrativo pertinente.
- GicaTesis clasifica las propuestas controladas como artículo de revista o libro y conserva autor, año, título y datos de publicación.
- Las fuentes se incorporan a la Lista actual del Administrador de fuentes de Word.
- Las citas se generan como campos `CITATION`; las citas múltiples se vinculan a todas sus fuentes.
- La sección de referencias utiliza un único campo `BIBLIOGRAPHY`.
- Cada fuente simulada incluye en `Comentarios` una advertencia que obliga a validarla o reemplazarla.
- La exportación se rechaza si existe una fuente sin cita, una cita con etiqueta desconocida o un número incorrecto de bibliografías.

### Corrección de longitud y densidad de citas

- Las menciones autor-año que redacta GICA se convierten a campos `CITATION` y dejan de ser texto manual desconectado del Administrador de fuentes.
- Una combinación normalizada de autor y año produce una sola fuente Word, aunque se cite varias veces.
- Los campos incorporan el modificador nativo `\t`, que impide que Word agregue el título de la fuente cuando un autor aparece en varias obras. La forma visible queda como `(Autor, año)` o una agrupación breve equivalente.
- Los títulos de las referencias simuladas se limitan al concepto de la sección; no repiten el título completo de la tesis.
- Para el Proyecto de Tesis UNAC se adopta como mínimo el patrón del ingeniero: Introducción 3; realidad problemática 5; antecedentes 10; bases teóricas 14; marco conceptual 2; términos básicos 13; operacionalización 2; diseño metodológico 2; método de investigación 1. Total de referencia: 52 menciones.
- No se fuerzan citas académicas en formulación del problema, objetivos, justificaciones propias, delimitaciones, hipótesis, cronograma, presupuesto o anexos.
- La exportación se rechaza si dos etiquetas distintas comparten exactamente autores y año, porque esa colisión puede hacer que Word expanda la cita con el título.

## Pruebas y controles ejecutados

| Control | Resultado |
| --- | --- |
| Caso con cinco tablas institucionales | 5 captions `SEQ Tabla`; validación superada |
| Eliminación intencional de un `SEQ Tabla` | Exportación rechazada correctamente |
| Encabezados de índices automáticos | 2 encabezados `Pág.` detectados |
| Abreviaturas en párrafos y tablas | Detectadas, traducidas cuando corresponde y ordenadas |
| Caption largo en mayúsculas | Normalizado a `Proceso del RCM` |
| Compilación de archivos modificados | Superada |
| Generación de muestra UNAC | Superada |
| Actualización de campos con Microsoft Word | Superada; cambios guardados en el DOCX |
| Revisión visual | 21 páginas revisadas, sin cortes ni superposiciones causados por estos cambios |
| Fuentes simuladas en Administrador de fuentes | 2 entradas detectadas en la Lista actual de Word |
| Campos bibliográficos nativos | 3 campos `CITATION` y 1 `BIBLIOGRAPHY` |
| Fuente incorporada pero no citada | Exportación rechazada correctamente |
| Revisión visual de la muestra bibliográfica | 6 páginas revisadas; citas y bibliografía materializadas correctamente |
| Documento completo después de la corrección | 53 campos `CITATION`, 40 fuentes Word y 0 marcadores internos sin resolver |
| Actualización de campos en Microsoft Word | 53 citas, 40 fuentes y 40 referencias conservadas después de `Ctrl+A` + `F9` |
| Densidad frente al ejemplo del ingeniero | 53 campos nativos frente a 52 menciones del documento de referencia |
| Revisión visual completa | 53 páginas revisadas tanto en el PDF actualizado por Word como en el PDF de Docker |
| Reconstrucción local | `gicagen` y `gicatesis` reconstruidos y saludables con `compose.local.yml` |
| Suites completas | GicaGen: 564 aprobadas y 2 omitidas; GicaTesis: 379 aprobadas |

## Actualización: política semántica integral de citas

- Los mínimos ya no se evalúan por capítulos agregados. Se auditan individualmente Introducción, 1.1, 2.1.1, 2.1.2, cada apartado canónico de 2.2.1 a 2.2.8, 2.3, 2.4, 3.2, 4.1 y 4.2.
- La prueba completa alcanzó: Introducción 3; realidad problemática 6; antecedentes internacionales 5; nacionales 5; RCM 3; proceso del RCM 2; taxonomía 0; AMEF 2; disponibilidad 1; confiabilidad 3; mantenibilidad 2; equipo 1; marco conceptual 2; términos básicos 13; operacionalización 2; diseño metodológico 2; método 1.
- El total final es de 53 campos nativos y 40 fuentes distintas. Una fuente repetida conserva un único tag y una sola entrada bibliográfica.
- Las tablas de operacionalización usan el mismo renderizador de citas que los párrafos; sus citas se materializan como campos `CITATION` dentro de las celdas.
- La bibliografía mantiene un único campo `BIBLIOGRAPHY` con 40 resultados visibles, incluso en LibreOffice/Docker, y continúa siendo actualizable por Word.
- Los proyectos guardados con las antiguas expansiones simuladas `Colaborador`/`Especialista` se actualizan de forma idempotente a citas breves sin cambiar sus tags.
- La validación posterior a `F9` reconoce las variaciones normales de formato que Word introduce, pero sigue exigiendo una entrada visible por cada identidad autor-año citada.

## Corrección de regresión: norma MIL-STD-1629A

- El render del proyecto `proj_5d5e716830` detectó 46 fuentes citadas, pero el validador solo reconoció 45 entradas visibles.
- La fuente involucrada fue `MIL-STD-1629A (1980)`: Gicagen la había serializado como si fuera una persona (`MIL-STD-1629A, M.`) y GicaTesis interpretó únicamente `A` como apellido.
- Gicagen ahora conserva los identificadores `MIL-STD`, ISO, IEC, EN, SAE y GMG como autores técnicos completos y genera tags descriptivos para ellos.
- GicaTesis reconoce tanto el formato nuevo como la forma heredada `MIL-STD-1629A, M.`, por lo que los proyectos ya guardados pueden reintentar únicamente el render sin regenerar contenido con IA.
- Se añadió una prueba integral que crea la fuente técnica, el campo `CITATION`, el campo `BIBLIOGRAPHY`, la lista actual de Word y valida su correspondencia visible.
- El reintento real de `proj_5d5e716830` finalizó con DOCX y PDF: 47 fuentes citadas, 47 entradas visibles reconocidas, 69 campos `CITATION`, un campo `BIBLIOGRAPHY` y cero fuentes sin correspondencia. El PDF de 58 páginas muestra `MIL-STD-1629A (1980)` sin la inicial artificial heredada.

La muestra `09_muestra_validacion_indices_unac.docx` contiene cuatro tablas captionadas porque ese es el contenido disponible en el JSON de prueba: 3.1, 3.2, 5.1 y 6.1. Las cuatro aparecen en el índice. La correspondencia de cinco tablas se verificó con una prueba estructural independiente.

## Código afectado

El generador de recomendaciones de figuras se encuentra en el proyecto Gicagen. La normalización, los renderizadores Word, la actualización de campos, la validación estructural y el guardado posterior a la conversión PDF se encuentran en el proyecto GicaTesis.

## Actualización: implementación del plan integral UNAC

- Se incorporó el perfil versionado `UNAC_MAINTENANCE_V1`, con la huella SHA-256 del entregable, mínimos narrativos por unidad, objetivos de generación con margen del 5 %, conceptos, citas y fórmulas exigidas.
- El conteo narrativo excluye títulos, captions, fuentes, guías de figuras, tablas, fórmulas, citas, índices y bibliografía. La auditoría informa palabras, mínimo, diferencia, cobertura temática y repetición por sección.
- GicaGen repara únicamente la sección deficitaria, con un máximo de dos reparaciones y un error final que muestra el déficit exacto.
- La matriz del proyecto es la fuente de verdad para problemas, objetivos e hipótesis. GicaTesis separa los rótulos en negrita y usa listas nativas `w:numPr` para los elementos específicos.
- Las fórmulas nuevas utilizan bloques canónicos con LaTeX y se renderizan como ecuaciones editables OMML. Las expresiones ambiguas se rechazan en vez de convertirse silenciosamente en texto.
- Se añadieron checkpoints duraderos por sección y por etapa de construcción. `Reintentar` conserva contenido y artefactos compatibles; `Regenerar todo` exige confirmación. Un fallo de DOCX, estabilización, PDF o validación no vuelve a llamar a la IA.
- La compatibilidad del checkpoint se determina mediante una huella de entradas, variables, formato, secciones y perfil; cambiar proveedor o modelo no invalida secciones ya aprobadas.
- El DOCX se estabiliza hasta tres ciclos con el PDF provisional. Los índices reciben páginas almacenadas verificables y la exportación falla si la paginación no converge.
- El índice de figuras almacena la caption completa numerada. Esto evita confundir títulos como `Disponibilidad inherente` con encabezados o texto narrativo al resolver la página.
- La muestra final de Docker contiene 53 campos `CITATION`, 45 fuentes distintas, un solo campo `BIBLIOGRAPHY`, cuatro captions `SEQ Tabla`, nueve captions `SEQ Figura`, cero relaciones externas y `updateFields` desactivado.
- Una generación adicional con el bloque canónico de disponibilidad confirmó un nodo `m:oMath`, cero LaTeX degradado a texto, cero relaciones externas y `updateFields` desactivado.
- Se inspeccionaron visualmente las 59 páginas del PDF final, incluidas páginas críticas a tamaño completo: índices, problemas y objetivos, tablas de operacionalización, cronograma, presupuesto, bibliografía y anexos.

## Pendiente deliberado

La mecánica nativa de Word ya está implementada con fuentes simuladas. Permanece pendiente conectar un servicio académico con acceso a Internet, validar metadatos reales y ampliar el mapeo a tesis, capítulos, normas, informes, guías y manuales técnicos. Antes de una entrega académica será obligatorio verificar o reemplazar todas las fuentes marcadas como simuladas.
