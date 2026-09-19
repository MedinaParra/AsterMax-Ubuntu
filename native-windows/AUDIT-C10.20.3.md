# AsterMax C10.20.3 — Cancel Solve y ejecución externa rastreada

Fecha: 19 septiembre 2026

Base: C10.20.2 (`codex/c10202-async-solve-ui`).

Rama: `codex/c10203-cancel-solve`.

## Hallazgos

1. El Solve ya corría fuera del hilo WinForms, pero no existía una ruta de cancelación de usuario.
2. El runner Windows puede permanecer activo hasta su timeout externo; una auditoría de 600 s podía terminar matando toda la aplicación.
3. El postproceso Python conservaba una lectura secuencial de stdout y stderr en `RunCaptured`, lo que podía bloquearse si uno de los pipes se llenaba.

## Reparaciones

- Se agrega `Cancel Solve` a la cinta Solution.
- La transacción expone `RequestCancel()` y estado `Cancelled`.
- La solicitud de cancelación no bloquea la UI: la terminación se ejecuta en un `Task.Run`.
- Se usa `taskkill /PID <pid> /T /F` para terminar el árbol del runner; `Process.Kill()` queda como fallback.
- Runner Code_Aster, bridge MED y binder de fingerprint pasan por un único `RunTrackedProcess`.
- stdout y stderr se drenan concurrentemente con `ReadToEndAsync`.
- Se comprueba cancelación antes de lanzar procesos y después de que terminan.
- El árbol de modelo y el menú principal permanecen bloqueados durante Solve; la cinta queda activa únicamente para permitir Cancel.
- `InvokeAsterMaxCommand` rechaza otros comandos AsterMax mientras hay un Solve activo.
- La auditoría de botones exige que `Cancel Solve` exista y tenga acción enlazada.

## Validación estática

24/24 invariantes PASS:
- API de cancelación;
- kill de árbol + fallback;
- cancelación no bloqueante;
- lectura concurrente de pipes;
- runner y postprocesos usando la misma ruta rastreada;
- control Cancel en ribbon;
- bloqueo de otras acciones;
- patch-chain y workflow;
- versionado de reportes.

La prueba de regresión no genera ni simula resultados FEA.

## Límites

- El workflow exitoso no cancela intencionalmente el solve B01, por lo que la prueba dinámica completa de cancelación debe ejecutarse como un escenario separado.
- La terminación del árbol usa la herramienta Windows `taskkill`; si el sistema impide esa llamada, se intenta `Process.Kill()`, que puede no eliminar nietos del proceso.
- Falta revisar explícitamente la política de resultados previos cuando un nuevo Solve se cancela o falla.
