# Validación de evidencia del Tutorial 1

Continuación de `agent/c1029-load-histories` (`e0e0038`). Este cambio conserva
la línea del Tutorial 1; no incorpora ni reemplaza la rama paralela C10.40.

El comparador antes declaraba coincidencia de geometría/cargas y apoyos con
booleanos constantes. Ahora verifica el hash CAD del caso, las 30 caras del
manifiesto corregido (incluidas identidades, no sólo cantidades), presión,
apoyos, material, unidades, orden del elemento, cantidades de malla y metadatos
de procedencia/postproceso. El generador comparte el manifiesto y rechaza un
STEP con otro hash antes de mallar.

- Metadatos incompatibles: informe BLOCKED, salida 2 y exclusión de convergencia.
- Valores no finitos, negativos o no numéricos: error; no se conserva un informe
  anterior en la ruta de salida.
- Tensión nula: factor de seguridad `null`, nunca un Infinity no estándar en JSON.
- Diferencias numéricas: diagnóstico separado de la admisión de evidencia.
- Referencia ANSYS: instantánea anterior al refinamiento; incluso coincidir
  dentro del 5 % no certifica equivalencia convergida.

Las verificaciones de metadatos no autentican por sí solas una ejecución ni
prueban identidad de conectividad CAD → malla → resultados. Los archivos reales
MED/RMED/MESS, su trazabilidad y la calificación mecánica siguen siendo necesarios.
No se modifica la GUI ni se declara un nuevo resultado de elementos finitos.

Pruebas locales ejecutadas: ocho pruebas de regresión nuevas (con subcasos) y
seis casos existentes de calificación mecánica, PASS. Los datos de las pruebas
son sintéticos y no son resultados físicos. CI adicional: Linux y Windows.
