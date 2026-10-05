# AsterMax C10.20.5 — Cierre seguro durante Solve activo

Fecha: 19 septiembre 2026

Base: C10.20.4 (`codex/c10204-result-lifecycle`).

Rama: `codex/c10205-close-safe-solve`.

## Hallazgo

El formulario principal podía entrar en `Disposed` mientras el worker asíncrono de Solve seguía ejecutando Code_Aster o el postproceso. En ese camino `ResetAsterMaxIntegratedResults()` limpiaba referencias como `_asterMaxSolveTransaction` y `_asterMaxLoadedResults` antes de que el worker hubiese terminado.

## Reparación

- `FrmMain.FormClosing` queda enlazado a `AsterMaxFormClosingDuringSolve`.
- Si no hay Solve activo, el cierre continúa normalmente.
- Si existe un Solve activo:
  - el primer cierre se cancela con `e.Cancel=true`;
  - se registra intención de cierre;
  - se solicita `RequestCancel()` sobre la transacción;
  - la UI permanece viva mientras termina el worker.
- En el `finally` del Solve:
  - se captura la intención de cierre;
  - se limpia el estado `_asterMaxSolveInProgress`;
  - se restaura la UI;
  - sólo entonces se programa `BeginInvoke(new Action(Close))`.
- El reset de proyecto limpia también la intención de cierre pendiente.

## Validación estática

20/20 invariantes PASS.

La prueba confirma, entre otros puntos, que `_asterMaxSolveInProgress=false` ocurre antes del segundo `Close()`.

No se ejecuta ni se inventa FEA en esta prueba estática.

## Límite

La prueba definitiva requiere Windows real: iniciar Solve, cerrar la ventana durante el cálculo, comprobar cancelación del árbol de procesos y verificar que la aplicación se cierra únicamente después de terminar la transacción.
