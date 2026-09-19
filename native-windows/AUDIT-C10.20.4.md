# AsterMax C10.20.4 — Ciclo de vida de resultados previos

Fecha: 19 septiembre 2026

Base: C10.20.3 (`codex/c10203-cancel-solve`).

Rama: `codex/c10204-result-lifecycle`.

## Hallazgo

El fingerprint del bundle determina si un resultado corresponde al FeModel actual. Eso es correcto para integridad geométrica/modelal, pero no distingue entre:

- el último Solve exitoso;
- un resultado exitoso anterior retenido;
- un Solve nuevo que está corriendo;
- un Solve nuevo que terminó cancelado o fallido.

Por ello un bundle anterior podía seguir apareciendo como `Current` después de un intento posterior fallido/cancelado, aunque no fuera el resultado de ese último intento.

## Reparación

- Se agrega estado explícito `_asterMaxPreviousResultsRetained`.
- Al comenzar un Solve con resultados anteriores:
  - el viewport anterior se oculta;
  - los campos quedan deshabilitados;
  - el árbol muestra `Previous solution - new solve running`.
- Si el Solve termina correctamente:
  - se publica el nuevo bundle;
  - se limpia la marca de resultado anterior;
  - el estado vuelve a `Current`.
- Si falla o se cancela:
  - el bundle anterior se conserva;
  - si sigue siendo compatible con el modelo, se habilita como `Previous successful solution retained`;
  - si el modelo cambió, prevalece el estado `Stale - solve again`.
- Una carga manual de resultados limpia la marca de retención.
- New/Open/Reset limpia también la marca.
- Solution Information declara explícitamente cuando se está mostrando el último resultado exitoso retenido tras un Solve posterior no completado.

## Validación estática

22/22 invariantes PASS:
- estado de retención;
- etiquetas de solving/retained;
- bloqueo de campos durante Solve;
- restauración tras fallo/cancelación;
- reemplazo en éxito;
- limpieza por carga manual;
- limpieza por reset;
- refresh final;
- patch-chain y workflow;
- versionado C10.20.4.

No se sintetiza información FEA en esta prueba.

## Límite

La validación dinámica definitiva requiere una secuencia Windows real: Solve exitoso A -> iniciar Solve B -> cancelar/fallar B -> comprobar que A reaparece etiquetado como resultado exitoso anterior, nunca como resultado de B.
