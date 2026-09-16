# AsterMax C10.09 — revisión de integración

Fecha: 2026-09-14. Base: C10.08.1, rama codex/c1004-unified-native-codeaster.

Esta revisión cubre la cadena de parches que construye el ejecutable, ModelTree nativo, cinta, importación/mallado, entrada Run, exportador, procesos externos y entrega de resultados. No acredita equivalencia completa con ANSYS ni una auditoría exhaustiva de cada algoritmo heredado.

| Área | Hallazgo | Cambio / límite |
|---|---|---|
| Outline | La prueba anterior aceptaba CAD y malla sin comprobar el panel visible. La captura del usuario muestra el panel vacío; no se reprodujo su configuración de pantalla. | Montaje explícito del ModelTree, docking y orden de controles; proyección única de los nodos nativos. Prueba portable exige cuerpo CAD en el árbol visible y captura PNG. |
| Identidad del modelo | Los nombres internos son contratos usados por búsqueda, menús y regeneración. | Se conservan TreeNode.Name y objetos nativos. El árbol nuevo contiene referencias a estos nodos, sin modificar el archivo PMX. |
| Selección y edición | El árbol nativo distribuye eventos según la vista activa y SelectedNodes. | Los nodos proyectados activan la vista correspondiente y reutilizan selección, doble clic, menú contextual y teclado del árbol original. |
| Run | RunAnalysis(string) aún llamaba al ejecutor heredado; Solve de la cinta usaba Code_Aster. | Ambas entradas llaman RunAsterMaxNativeSolve. Solution ofrece Solve sin necesidad de crear un trabajo heredado. |
| Cinta | Model → Materials apuntaba a un menú; Environment contenía solo etiquetas. | Acciones directas para material, paso, apoyo y carga. |
| Procesos | Lectura secuencial de stdout/stderr podía bloquear; los probes esperaban las lecturas antes del timeout. | Lectura concurrente de ambos streams; timeout de probes antes de recuperar las cadenas. |
| CAD / malla | Dependencias NetGen se perdieron en una entrega previa. | Se conserva incorporación con hash fijado y prueba real del paquete. |
| Exportador | Contrato estático MM/N/MPa; TETRA4/TETRA10/HEXA8; exige exactamente un material, apoyo y carga. | Límite vigente. No presentar contactos, múltiples materiales o análisis arbitrarios como resueltos. |
| Resultados | MED→bundle→ventana AsterMaxResultsViewportForm. | La ventana propia sigue vigente. Los campos del árbol de resultados nativo no se inventan ni se llenan con muestras. Integración total pendiente. |
| Interfaz durante Solve | Ejecución sincrónica en el hilo de interfaz. | Pendiente ejecución asíncrona/cancelación transaccional. El cambio de streams no elimina este límite. |
| Coordenadas | Backend actual usa coordenadas cartesianas globales. | Nodo global informativo; no implica soporte de sistemas locales editables. |
| Correspondencia ANSYS | La organización sigue Project → Model → Geometry/Materials/Coordinate Systems/Connections/Mesh/Named Selections/Static Structural/Solution. | Adaptación funcional a entidades existentes, no copia exacta ni equivalencia total. Se preservan Steps, asignaciones de sección y colecciones nativas. |

## Evidencia y alcance

- La cadena completa de parches se aplicó localmente al upstream fijado sin error.
- El harness MED C10.07 pasó para cuatro familias. Sus datos son fixtures de prueba, no evidencia de ejecución de solver.
- El workflow de esta versión ejecuta además un caso real Code_Aster y admisión de equilibrio/resultado, separado del harness.
- La validación Windows del nuevo árbol y el paquete solo se consideran aprobados cuando su workflow finaliza con éxito. Consultar el estado del commit entregado.
- Pendiente demostrar en Windows el caso del usuario PrimerAnalisisBarra.pmx desde edición hasta resultados, y todos los comandos de menú, multiselección, cambios DPI y ciclos extensos de guardar/reabrir.

Referencia de estructura: documentación oficial ANSYS Mechanical, Outline:
https://ansyshelp.ansys.com/public/Views/Secured/corp/v251/en/wb_sim/ds_Tree_Outline.html
