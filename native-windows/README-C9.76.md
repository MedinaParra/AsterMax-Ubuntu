# AsterMax Mechanical C9.76 — Windows x64

## Cómo ejecutar
1. Extrae TODO el ZIP en una carpeta nueva.
2. Abre AsterMax Mechanical.exe.
3. Conserva las carpetas lib, NetGen y las DLL junto al EXE. Requiere Windows x64 y .NET Framework 4.8.

## Qué puedes revisar
- Importar Cube-mm.stp o tu geometría STEP desde Home / Import Geometry.
- Ver la geometría en el viewport nativo; usar Fit, Isometric y selección.
- Configurar y generar malla desde Mesh.
- Preparar material, sección y paso en Model; apoyos y cargas en Environment.
- Guardar y volver a abrir proyectos .pmx. Example-mesh.pmx contiene la malla del caso de prueba.

## Validación y alcance
La prueba automatizada ejecuta el EXE real en Windows, importa STEP, genera malla volumétrica, cambia entre geometría y modelo, guarda/reabre el proyecto y verifica que coordenadas, conectividad y unidades conservan el mismo SHA-256. También captura el framebuffer VTK y verifica que contiene geometría visible.
Consulta C9.76_VALIDATION.json, ASTERMAX_RUNTIME_STEP.json y FRAMEBUFFER_VALIDATION.json para los resultados. Las imágenes se capturan desde la aplicación real.

Esta versión cierra la reparación de arranque, CAD, viewport, malla y persistencia. Code_Aster y la reimportación de resultados todavía NO están integrados en esta compilación. Las pestañas Solution y Results no constituyen un flujo de cálculo validado. No incluye solver CalculiX. No se declara PMV completo ni equivalencia con software comercial.

## Código y licencias
Código y compilación: https://github.com/MedinaParra/AsterMax-Ubuntu/tree/codex/c975-native-startup-repair
Base de código: https://github.com/tsvilans/PrePoMax/tree/3669e65581650e5d9d868aa761db9efd856f8571
PrePoMax GPL-3.0; bibliotecas de terceros conservan sus licencias. Mesa OpenGL: licenses/Mesa.
