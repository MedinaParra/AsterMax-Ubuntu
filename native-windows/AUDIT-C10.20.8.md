# AsterMax C10.20.8 — Ejecución funcional de comandos del ribbon

Fecha: 19 septiembre 2026

Base: C10.20.7 (`codex/c10207-model-session-identity`).

Rama: `codex/c10208-functional-command-smoke`.

## Hallazgo

La auditoría histórica de botones verificaba presencia, icono, nombre accesible y delegate enlazado, pero registraba explícitamente `execution=NOT_INVOKED`. El workflow B01 tampoco ejercitaba la mayoría de los comandos de edición: materiales, malla, pasos, apoyos y cargas se construían directamente en el modelo.

Por ello un botón podía superar la auditoría aun cuando su handler real no abriera el editor esperado o la operación nativa no funcionara.

## Reparación

El workflow ahora ejecuta funcionalmente 11 comandos del ribbon:

- Model / Materials
- Mesh / Mesh Controls
- Mesh / Generate Mesh
- Materiales / Asignar seccion
- Environment / Analysis Step
- Environment / Supports
- Environment / Loads
- Results / Contours
- Results / Deformed
- View / Fit
- View / Isometric

Los editores nativos se abren realmente, se comprueba `Visible`, y se ocultan con `CloseAllForms()` sin aceptar cambios. El conteo de entidades antes/después debe permanecer idéntico.

`Generate Mesh` es distinto: se ejecuta realmente el flujo nativo de mallado sobre la única pieza B01 y se exige crecimiento real de nodos y elementos. Después, la malla generada se reemplaza por el fixture HE8 determinista ya utilizado para la validación numérica del solver.

Se genera `command-execution-smoke.json`, y el cross-check obligatorio `command_execution_smoke` exige los 11 comandos y evidencia de malla real.

## Trazabilidad

C10.20.3-C10.20.7 habían evolucionado el comportamiento pero el JSON interno de sesión seguía estampado C10.20.2. C10.20.8 actualiza esa release embebida para que coincida con el manifest y los reportes.

## CI observable

El workflow mantiene `push` y añade `pull_request`, permitiendo asociar el run al commit del PR y recuperar jobs/logs mediante la integración de GitHub.

## Validación estática

Los guards de integración y orden de ejecución pasan. La comprobación específica verifica que:

`Generate Mesh real -> evidencia -> C1020PopulateB01Mesh HE8`

ocurre en ese orden.

No se inventan ni sintetizan resultados FEA.

## Límite

La validación definitiva es el run Windows x64: compilación, apertura real de editores, NetGen real, Code_Aster real y render integrado.
