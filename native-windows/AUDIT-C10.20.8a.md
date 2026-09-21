# AsterMax C10.20.8a — Auditoría de cadena de parches y harness de errores

Fecha: 20 septiembre 2026

Base auditada: `codex/c10208-functional-command-smoke` @ `aacc02a4c9512d8c4fdc131da017f06a9181d38f`.

Rama de reparación: `codex/c10208a-error-harness`.

## Evidencia observada

El workflow Windows `35510976466` completó correctamente la validación estática, pero falló antes de compilar en la etapa de aplicación de parches. La primera falla reproducible fue `patch-c10203-cancel-solve.ps1`.

La excepción fue un `anchor missing` sobre el cuerpo completo de `RunCaptured(ProcessStartInfo psi,string stem)`. Esto demuestra que la validación de dependencias era insuficiente: verificaba orden y símbolos declarados/consumidos, pero no ejercitaba la compatibilidad real de los anchors contra el árbol transformado por todos los parches anteriores.

## Causa raíz

C10.20.3 exigía una copia exacta de una implementación histórica de `RunCaptured`. Ese tipo de anchor es frágil frente a hotfixes anteriores que cambian detalles de I/O síncrono/asíncrono sin cambiar la identidad ni la responsabilidad del método.

La reparación reemplaza ese anchor de cuerpo completo por un anchor estructural sobre la firma y límites del método. Antes de sustituirlo se comprueba que el cuerpo encontrado tenga una implementación reconocible (`Process.Start` o `RunTrackedProcess`). Si la estructura no coincide, el parche falla de forma cerrada en vez de editar código no reconocido.

## Harness C10.20.8a

Se agrega `harness-c10208a-patch-chain.ps1` para ejecutar la cadena de parches como procesos PowerShell aislados.

Por cada parche conserva:

- ordinal y nombre;
- exit code y duración;
- stdout y stderr independientes;
- SHA-256 antes/después de archivos críticos;
- clasificación de falla;
- últimas líneas de stdout/stderr.

Ante la primera falla el harness se detiene, crea `patch-chain-harness.json`, `PATCH_FAILURE.json` y una copia de los archivos fuente críticos en `failure-snapshot`. No intenta ejecutar parches dependientes sobre un árbol incompleto.

Las clases iniciales de falla son `ANCHOR_DRIFT`, `PATCH_PARSE_ERROR`, `TARGET_PATH_MISSING`, `PATCH_RUNTIME_FAILURE` y `PATCH_FILE_MISSING`.

## Regla de auditoría

Un PASS estático de `validate-patch-chain.py` ya no es evidencia suficiente para afirmar que la cadena es aplicable. El gate Windows debe ejecutar la cadena completa mediante el harness sobre el commit upstream fijado y conservar el reporte, tanto en PASS como en FAIL.

## Límite de afirmación

Esta auditoría no afirma todavía que AsterMax compile, que Code_Aster resuelva ni que la GUI C10.20.8 cierre correctamente. Esos estados sólo se aceptarán cuando el workflow Windows posterior a esta reparación produzca evidencia real de build, runtime y workflow conformance.
