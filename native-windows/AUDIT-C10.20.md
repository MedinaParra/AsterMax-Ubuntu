# AsterMax C10.20 — Auditoría de conformidad de flujo Windows

## Estado de esta revisión

**Ejecución end-to-end: PENDIENTE DE EVIDENCIA CI.** Este documento no declara cerrado el pendiente histórico de `AUDIT-C10.09.md` / `AUDIT-C10.17.md` hasta que el workflow `AsterMax C10.20 Windows Workflow Conformance` produzca y publique su artefacto real.

La referencia de orden de trabajo es únicamente el flujo declarado para AsterMax: Geometry -> Materials -> Coordinate Systems -> Connections -> Mesh -> Named Selections -> Static Structural -> Solution -> Results. Esto no constituye una afirmación de equivalencia con ANSYS Mechanical.

## Fase 0

### 0.1 — Integridad del MSI Code_Aster

El criterio de bloqueo MD5 fue sustituido por SHA-256 y tamaño observado. El registro de procedencia está en `native-windows/CODE-ASTER-WINDOWS-MSI-SHA256.md`.

- SHA-256 observado: `B789FEFFC12E0FECBCFBABE6D386FA15C1AB74797C8C9D27A5733F8D2B5D092D`
- Tamaño observado: `398012592` bytes
- Origen: proveedor Simulease, URL documentada en el registro
- Fecha de observación: 2026-09-16

La corrida usada para obtener el fingerprint instaló el MSI con código 0, pero su smoke histórico falló posteriormente en descubrimiento de `as_run.bat`; por tanto ese antecedente prueba el fingerprint/instalación, no el funcionamiento end-to-end del solver.

### 0.2 — Pin del upstream PrePoMax

Todos los checkouts de `tsvilans/PrePoMax` en `.github/workflows/` deben usar el commit inmutable `3669e65581650e5d9d868aa761db9efd856f8571`. `native-windows/validate-workflow-pins.py` falla ante cualquier checkout flotante. La corrida oficial del pin audit sobre el HEAD canónico debe conservarse como evidencia de este punto.

### 0.3 — Tamaño de resultados

Esta rama conserva `astermax-results-bundle/v0`, VTU ASCII por streaming con precisión `.15g` y arrays del bundle JSON por streaming. No se migra a un esquema v1 en C10.20 para no mezclar una migración de persistencia con la primera prueba integral de GUI nativa.

Frontera operativa declarada para esta iteración: hasta aproximadamente 1,000,000 nodos, 500,000 TET10 y 5,000,000 referencias de conectividad, con un presupuesto combinado de artefactos del orden de 1.5 GiB. **Esta frontera es una política operativa conservadora, no un límite físico demostrado por benchmark de C10.20.** Superarla requiere medir tamaño/tiempo y reabrir la decisión entre VTU appended-binario y bundle v1 sin duplicación de topología.

## Fase 1 — Contrato de conformidad

`native-windows/workflow-conformance/workflow-contract.json` exige, para cada etapa obligatoria:

1. captura PNG de la ventana;
2. árbol de modelo serializado;
3. snapshot del estado producido por el modelo existente de `AsterMaxWorkflowStates.cs`;
4. transición esperada vs. observada.

Una etapa sólo puede quedar `PASS` con las cuatro evidencias presentes. Evidencia ausente se transforma en `NOT_EXERCISED`, nunca en `PASS`. Un `FAIL` en una etapa obligatoria hace fallar el workflow.

El fixture preferido histórico `PrimerAnalisisBarra.pmx` no estaba disponible en la rama al definir el contrato. Se usa el fallback documentado B01 reconstruido paramétricamente: barra 100 x 10 x 10 mm, acero lineal E=210000 MPa, nu=0.3, empotramiento en x=0 y fuerza total 10000 N en x=100.

El recorrido también registra guardado/reapertura PMX, ciclos repetidos, recorrido de superficie de menús/cinta, multiselección de árbol y DPI. El recorrido de presencia/wiring de un comando no se considera ejecución funcional del comando. Un cambio de DPI no disponible en el runner se registra `NOT_EXERCISED`.

## Evidencia requerida para cerrar el pendiente histórico

Pendiente hasta obtener una corrida real del workflow `.github/workflows/astermax-workflow-conformance.yml` sobre el HEAD final, con artefacto `AsterMax-C10.20-Workflow-Conformance` que contenga el reporte JSON/HTML y evidencias por etapa.

No se cerrará el pendiente de C10.09/C10.17 sólo porque el código compile, porque el contrato exista o porque el auditor de botones encuentre comandos.

## Límites explícitos

- C10.20 prueba exclusivamente el caso B01 que realmente sea ejecutado por el runner; no generaliza a todas las geometrías, materiales, contactos, no linealidades o tipos de análisis.
- El recorrido de menús/cinta distingue presencia y wiring de ejecución funcional. Comandos no ejecutados quedan declarados como tales.
- `NOT_EXERCISED` es un resultado permitido y no suma como `PASS`.
- La captura WinForms demuestra la ventana/estado observable definido en el contrato; cualquier evidencia específica del framebuffer VTK debe provenir del mecanismo de captura nativo ya existente, no inferirse de una captura vacía.
- La persistencia PMX sólo queda demostrada si los ciclos reales de guardar/reabrir terminan y los estados/modelo permanecen consistentes.
- El solver sólo queda demostrado para esta corrida si existe evidencia de ejecución real de Code_Aster y el bundle admitido conserva `fea_values_invented=false`.
- Esta auditoría no asigna porcentaje global de equivalencia ni declara equivalencia con ANSYS.

## Fase 2 — Harness de tutoriales

No se considera completada hasta que exista `native-windows/tutorial-harness/`, sus contratos v1 y sus reportes ejecutables. Su estado se documentará aquí después de cerrar o clasificar honestamente la Fase 1.
