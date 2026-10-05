# AsterMax C10.20.1 — Auditoría y hotfix de semántica de carga

Fecha: 19 septiembre 2026

Base auditada: `codex/c1020-workflow-conformance`, commit `b6e5c6adace5f44be37bdb97920d10807c26a9ab`.

Rama de reparación: `codex/c10201-cload-semantics-hotfix`.

## Alcance

Esta revisión se concentró en la cadena nativa Windows: modelo PrePoMax/AsterMax -> contrato -> exportador Code_Aster -> Solve -> resultados -> auditoría de conformidad. No declara equivalencia completa con ANSYS Mechanical y no introduce resultados FEA sintéticos.

## Hallazgo crítico corregido — CLoad

PrePoMax trata `CLoad.F1/F2/F3` como componentes de fuerza **por nodo**. La cadena AsterMax anterior los copiaba al contrato como `fx_total_n/fy_total_n/fz_total_n` y el exportador los dividía nuevamente por la cantidad de nodos del grupo.

Impacto: un `CLoad` creado desde la interfaz podía llegar a Code_Aster reducido por un factor igual al número de nodos seleccionados. Por ejemplo, 2500 N por nodo sobre cuatro nodos debía producir 10000 N totales, pero el contrato anterior podía reinterpretarlo como 2500 N totales y exportar 625 N por nodo.

### Reparación

- El contrato nuevo conserva explícitamente `fx_per_node_n/fy_per_node_n/fz_per_node_n`.
- El exportador usa esos valores directamente con `FORCE_NODALE`.
- Los contratos legacy que contienen `fx_total_n` siguen siendo admitidos y se distribuyen por cantidad de nodos para no romper evidencia/artefactos anteriores.
- El manifiesto del exportador registra `load_semantics`, fuerza por nodo y fuerza total reconstruida.
- El caso B01 conserva su requisito físico de 10000 N totales usando cuatro `CLoad` efectivos de 2500 N/nodo.
- Se agregó un cross-check runtime que exige para B01: `PER_NODE_CLOAD`, 4 nodos, 2500 N/nodo y 10000 N total.

## Hallazgo corregido — evidencia perdida en timeout/crash

El runner de conformidad podía matar el proceso por timeout y lanzar una excepción antes de producir el reporte final, aun cuando ya existían checkpoints parciales.

Ahora el runner:
- conserva la sesión parcial;
- registra código de salida y condición de timeout;
- crea una sesión mínima de fallo si el proceso murió antes de escribir una;
- ejecuta el generador de reporte antes de devolver el error;
- mantiene PASS/FAIL/NOT_EXERCISED ya observados.

## Validación realizada

La revisión estática posterior al hotfix comprobó 17 invariantes y obtuvo 17/17 PASS:

- contrato CLoad por nodo;
- exportador per-node;
- compatibilidad legacy de fuerzas totales;
- B01 = 4 x 2500 N = 10000 N;
- cross-check runtime de procedencia de fuerza;
- incorporación del hotfix en el workflow;
- dependencia correcta en patch-chain;
- prueba de regresión de semántica;
- versionado C10.20.1;
- preservación de reporte tras timeout.

La prueba `native-windows/test-c10201-cload-semantics.py` sólo valida contratos/código; no genera ni sustituye resultados FEA.

## Pendientes antes de considerar C10.20.1 liberable

1. Ejecutar el workflow Windows completo sobre el HEAD de la rama y confirmar compilación Release x64.
2. Confirmar instalación/descubrimiento del Code_Aster nativo y Solve real.
3. Revisar el artefacto de conformidad: Geometry -> Materials -> Coordinate Systems -> Connections -> Mesh -> Named Selections -> Static Structural -> Solution -> Results.
4. Confirmar el cross-check `cload_semantics` con el manifiesto real del Solve.
5. Confirmar PMX save/reopen, viewport integrado y ausencia de resultados stale.
6. La ejecución de Solve continúa siendo sincrónica en el hilo GUI; la asincronía/cancelación transaccional sigue como pendiente separado.

No se declara cerrado ningún pendiente histórico hasta disponer y revisar evidencia real del workflow Windows.
