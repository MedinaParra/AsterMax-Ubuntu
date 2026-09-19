# AsterMax C10.20.2 — Solve asíncrono y protección de la interfaz

Fecha: 19 septiembre 2026

Base: C10.20.1 (`codex/c10201-cload-semantics-hotfix`).

Rama: `codex/c10202-async-solve-ui`.

## Hallazgo

El flujo nativo de Solve seguía ejecutando el runner Code_Aster y el postproceso MED en el hilo WinForms. Aunque la lectura de stdout/stderr ya había sido corregida para evitar deadlocks de pipes, `RunAsterMaxNativeSolve()` seguía bloqueando la interfaz mientras esperaba el proceso externo.

Consecuencias:
- ventana sin respuesta durante solves largos;
- imposibilidad de demostrar que la UI sigue procesando eventos;
- riesgo de doble ejecución si distintas entradas activan Solve;
- UX distinta del flujo esperado de una aplicación CAE interactiva.

## Reparación C10.20.2

- `RunAsterMaxNativeSolve()` pasa a `async void` sólo en el borde de eventos WinForms.
- La preparación/fingerprint se congela en el hilo UI.
- Solver + postproceso se ejecutan dentro de `Task.Run`.
- La continuación vuelve al hilo UI antes de cargar/renderizar el bundle.
- Un flag single-flight impide un segundo Solve mientras existe uno activo.
- Ribbon, árbol de modelo y menú principal quedan temporalmente bloqueados para impedir mutaciones concurrentes del FeModel.
- Se preserva el estado previo Enabled de esos controles y sólo se restaura si el gate realmente fue activado.
- Un Timer WinForms registra heartbeats durante el solve para demostrar que el hilo UI procesa eventos.
- Se registra el ID del hilo UI y del worker para demostrar separación real.
- La auditoría dispara intencionalmente una segunda solicitud de Solve y exige que sea rechazada.
- Las carpetas de transacción ahora usan fracción de segundo + GUID corto para impedir colisiones de nombres.

## Evidencia exigida

El cross-check `async_solve_ui` requiere simultáneamente:
- worker thread distinto del UI thread;
- al menos un heartbeat WinForms durante el solve;
- al menos una solicitud duplicada rechazada;
- solve completado sin error asíncrono;
- transacción ya fuera del estado in-progress.

La evidencia se escribe en `async-solve-ui.json`.

## Validación estática

21/21 invariantes del hotfix y su integración pasan en la revisión estática:
- Task.Run presente;
- single-flight presente;
- UI gate simétrico;
- protección de fallo durante Prepare;
- heartbeat;
- IDs de thread;
- espera de auditoría;
- solicitud duplicada de auditoría;
- workspace único;
- patch-chain;
- workflow;
- contrato;
- reportes versionados.

## Límites

- Esto no implementa aún un botón Cancel de usuario.
- El runner nativo conserva su timeout externo de 3.600.000 ms y mata el árbol de procesos en timeout.
- La evidencia definitiva requiere build Windows x64 + Code_Aster real + workflow GUI.
- No se generan resultados FEA sintéticos.
