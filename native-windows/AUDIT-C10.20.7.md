# AsterMax C10.20.7 — Identidad de sesión de modelo antes de publicar resultados

Fecha: 19 septiembre 2026

Base: C10.20.6 (`codex/c10206-solve-state-coherence`).

Rama: `codex/c10207-model-session-identity`.

## Hallazgo

El fingerprint protege contra cambios de contenido del FeModel, pero por sí solo no prueba que el modelo activo al terminar el worker sea la misma instancia/sesión que inició el Solve. Dos proyectos distintos pueden ser geométricamente equivalentes y producir el mismo fingerprint.

## Verificación upstream

En el PrePoMax fijado, `Controller.Clear()` llama `_form.ClearControls()` y luego `ClearModel()`, que reemplaza `_model` por un nuevo `FeModel`. Por ello `ClearControls()` es una señal válida para incrementar una revisión de sesión AsterMax.

## Reparación

- Se agrega `_asterMaxModelSessionRevision`.
- `ResetAsterMaxIntegratedResults()`, llamado desde `ClearControls()`, incrementa esa revisión.
- Al iniciar Solve se congelan:
  - referencia exacta al `FeModel`;
  - revisión de sesión;
  - transacción activa.
- Antes de publicar el bundle, el hilo UI exige simultáneamente:
  - misma transacción;
  - misma instancia `FeModel` mediante `Object.ReferenceEquals`;
  - misma revisión de sesión.
- Si cualquiera cambia, el bundle calculado no se publica.
- El workflow genera `model-session-identity.json` y exige el cross-check `model_session_identity`.

## Validación

26/26 invariantes PASS.

El test de regresión analiza específicamente el bloque `publishNew` y comprueba que los guards de identidad/revisión se ejecutan antes de asignar `_asterMaxLoadedResults`.

No se generan ni se simulan valores FEA.

## Límite

La validación dinámica definitiva requiere intentar New/Open durante un Solve mediante cualquier ruta nativa no cubierta por el bloqueo de UI y comprobar que la publicación es rechazada.
