# AsterMax C10.20.6 — Coherencia de estados de Solve y evidencia atómica

Fecha: 19 septiembre 2026

Base: C10.20.5 (`codex/c10205-close-safe-solve`).

Rama: `codex/c10206-solve-state-coherence`.

## Hallazgos

El flujo asíncrono ya permitía Cancel desde el hilo UI, pero persistían dos problemas:

- `Cancelling` existía en el enum sin convertirse en el estado real de la transacción.
- el worker y el hilo UI podían escribir `ASTERMAX_SOLVE_STATE.json` en ventanas concurrentes.

Además, algunas rutas directas de fallo podían sobrescribir una cancelación solicitada.

## Reparación

- `RequestCancel()` es idempotente y cambia realmente la transacción a `Cancelling`.
- Las transiciones `Running`, `Postprocessing` y `SolutionCurrent` pasan por `TransitionOrCancel()`.
- Una cancelación solicitada se vuelve sticky: una transición posterior de éxito no puede sobrescribirla.
- `Fail()` también respeta una cancelación pendiente.
- Los fallos de runner no configurado y exit code no cero pasan por el gate de fallo/cancelación.
- Se agregan locks separados para transición de estado y persistencia del archivo.
- Cada snapshot incorpora `state_revision` y `cancel_requested`.
- La persistencia usa archivo temporal y `File.Replace`/Move para evitar que un lector observe JSON parcialmente escrito.

## Validación estática

30/30 invariantes PASS.

No se ejecuta ni se inventa FEA en esta validación.

## Límite

La prueba definitiva de carreras requiere Windows real y cancelación durante distintos puntos de la transacción: runner, bridge MED y binder.
