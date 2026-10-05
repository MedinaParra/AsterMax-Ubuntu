# Auditoría de integridad de resultados — 16 septiembre 2026

Base revisada: C10.10.1 / hotfix C10.16, commit `e29b7f300360d4d841a2ce98b8e7fb24d1a7236f`, rama `codex/c1004-unified-native-codeaster`.

Alcance: ejecutor nativo Windows y conversión de resultados MED. Esta revisión no certifica toda la aplicación ni equivalencia con ANSYS.

## Hallazgos corregidos

1. **Admisión de resultados anteriores.** El runner copiaba el workspace completo y buscaba cualquier MESS/RMED con fecha posterior a inicio menos dos segundos. Un rerun podía aceptar archivos anteriores recientes o archivos ajenos al export. Ahora elimina las salidas exactas declaradas antes del lanzamiento y exige esas mismas salidas no vacías. Rechaza destinos ambiguos o fuera de la carpeta temporal.
2. **Pérdida de diagnósticos.** El bloque finally borraba siempre la carpeta temporal, incluso cuando fallaba el lanzamiento o vencía el tiempo de espera. Ahora conserva la carpeta en caso de fallo y copia su contenido a una subcarpeta de diagnóstico; no promueve salidas fallidas al workspace principal. La limpieza automática se aplica únicamente tras éxito y copia completos.
3. **Publicación previa a validación.** El puente MED escribía JSON/VTU antes de comprobar valores finitos y requisitos de regresión. Ahora comprueba esos requisitos y la magnitud del desplazamiento antes de publicar; JSON prohíbe NaN/Infinity. Un rechazo de datos conserva cualquier artefacto previo sin sobrescribirlo.

También se corrigió el fixture C10.07, que carecía del atributo MAI requerido por el lector C10.11.

## Verificación

- 4 casos de lectura de familias: TETRA4, TETRA10, mezcla y HEXA8.
- 7 casos de rechazo: coordenadas, desplazamientos, tensiones o von Mises no finitos; desbordamiento de magnitud; modelo de regresión incorrecto; conservación de archivos existentes.
- 6 casos del runner sobre Windows PowerShell 5.1: éxito, resultados antiguos recientes, salidas ajenas, error de proceso, excepción de lanzamiento y ruta fuera del directorio temporal.
- Las 6 pruebas iniciales del conversor fallaron contra el código anterior y pasaron tras la corrección.
- El workflow `astermax-c1017-audit-regression.yml` verifica estas pruebas en Windows. Consultar el resultado del commit final en la PR #341.

Los casos MED son fixtures de formato y el runner usa comandos de prueba. **No son ejecuciones de Code_Aster ni validaciones físicas.**

## Pendientes y límites

- Ejecutar un modelo recién importado desde la interfaz Windows con Code_Aster instalado, revisar unidades/regiones/equilibrio y guardar/reabrir PMX.
- Validar visualmente contornos y repetir menús/Run; no se ejecutó la GUI en esta auditoría.
- No se compiló ni distribuyó un EXE nuevo. Los cambios se entregan en una rama y PR en borrador, sin fusionar.
- Las carpetas de ejecución fallida se conservan intencionalmente y pueden ocupar espacio. No se implementa una política de retención en este cambio.
- La escritura JSON/VTU no constituye una transacción atómica ante fallos de disco; este cambio impide publicar datos rechazados por las comprobaciones, no garantiza recuperación ante fallos de almacenamiento.
