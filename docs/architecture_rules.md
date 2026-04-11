# Reglas de Arquitectura: Generación de Documentos (GicaGen)

Este documento define las reglas críticas para el intercambio de datos entre GicaGen (BFF) y GicaTesis (Motor de Renderizado) para evitar errores de visualización y asegurar la escalabilidad.

## 1. Regla de Limpieza de Datos (Strict Payload Filtering)
GicaGen nunca debe enviar cadenas literales que representen valores nulos de bases de datos antiguas o frameworks frontend.
- **Prohibición**: No enviar `"none"`, `"null"`, `"nan"`, `"undefined"` (case-insensitive).
- **Razón**: Si el motor de GicaTesis recibe estos strings, los considera "datos válidos" y bloquea los placeholders del sistema, dejando el documento con palabras como "None" en lugar de espacios en blanco o placeholders institucionales.
- **Implementación**: Usar el mapper `map_maestria_values` que limpia estos valores antes de enviarlos.

## 2. Regla de Punto Único de Verdad (Variable Mapping)
Todas las variables enviadas a GicaTesis deben estar normalizadas bajo nombres canónicos.
- **Uso**: `values_with_title` en `payload_helpers.py` centraliza la fusión de variables del proyecto, variables del mago y títulos.
- **Escalabilidad**: Al añadir nuevas secciones (ej: Anexos, Matrices), los nombres de las variables deben registrarse en el `maestria_payload_mapper.py` para asegurar consistencia.

## 3. Inclusión de AI Result
El payload hacia GicaTesis debe incluir la estructura `aiResult` con secciones tipadas por `path`.
- **Razón**: Permite separar el contenido generado por IA de los metadatos institucionales del proyecto.

## 4. Separación de Responsabilidades (Paso 3 vs Paso 5)
Para evitar redundancias y fallos en la experiencia de usuario:
- **Paso 3 (Datos)**: Es de uso exclusivo para recolección técnica. **Prohibido añadir botones de validación o corrección por IA** en este paso.
- **Paso 5 (Generación)**: Es el único punto donde la IA interviene para validar el título, corregir gramática y generar contenido.
- **Selección de Secciones**: Para flujos de carátula rápidos, se debe forzar únicamente la selección de la sección inyectada `titulo-info-basica` en el Paso 2.

## 5. Regla de Selección Estricta (Strict Selection)
El backend debe actuar como un filtro pasivo de la selección realizada en el frontend.
- **Prohibición**: El backend NO debe expandir, añadir o inferir secciones adicionales que no hayan sido explícitamente enviadas en la lista de seleccionados del Proyecto (Paso 2).
- **Fallback**: En caso de recibir una selección manual, queda prohibido el uso de fallbacks a "generar todas las secciones por defecto".
- **Razón**: Asegura que el Paso 5 sea un espejo fiel de la intención del usuario y evita costos innecesarios de IA y generación de contenido no deseado.
## 6. Regla de Integridad Modular (Frontend Refactoring)
Al unificar o mover funciones entre módulos de JavaScript, se debe garantizar la continuidad de la carga de la aplicación.
- **Acción**: Si una función se mueve de un archivo 'A' a un archivo 'B', el archivo 'A' debe actuar como puente re-exportando la función (`export { func } from './B.js'`).
- **Prohibición**: Queda prohibido dejar módulos con referencias rotas o exportaciones faltantes que causen `SyntaxError`.
- **Razón**: Los errores modulares detienen la ejecución de todo el sistema, dejando los botones del Dashboard y el Wizard inactivos sin dar avisos visibles en la terminal.
- **Validación**: Tras cualquier cambio en módulos compartidos, el primer paso de verificación es refrescar el Dashboard y confirmar que los botones siguen respondiendo.
