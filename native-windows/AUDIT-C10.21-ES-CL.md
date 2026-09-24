# AsterMax Mechanical C10.21 — Windows es-CL

## Objetivo

Crear una edición de AsterMax Mechanical para Windows con interfaz orientada a ingeniería en español de Chile, manteniendo sin cambios el núcleo numérico, la trazabilidad y el uso exclusivo de Code_Aster.

## Alcance implementado

- Cultura de interfaz y formato regional: `es-CL`.
- Pestañas, comandos principales, árbol del modelo, menús, formularios abiertos, encabezados de grillas y estados CAE traducidos al español.
- Terminología técnica preferida: geometría, malla, mallado, apoyos, condiciones de borde, cargas, análisis, solución, resultados, deformación, esfuerzo equivalente y reacciones.
- Se conservan en inglés los nombres propios y marcas técnicas cuando corresponde: AsterMax Mechanical, Code_Aster, STEP, TET4, TET10, MPa.
- La traducción no cambia nombres de tipos, namespaces, identificadores internos, contratos JSON, archivos de evidencia ni entradas/salidas del solver.

## Seguridad de la integración

La localización se aplica como el último parche de presentación, después de C10.20.8a/C10.20.11. No modifica ecuaciones, malla, exportación Code_Aster ni postproceso.

## Estado de validación

- Código y parche creados en GitHub.
- La compilación/ejecución Windows debe considerarse **BLOCKED** hasta que GitHub Actions ejecute el flujo en un runner Windows y produzca evidencia real.
- No se declara PASS de compilación, GUI, mallado ni solver sin esa evidencia.
