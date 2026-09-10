# AsterMax C9.76.1 — Materiales — Windows x64

Extrae TODO el ZIP en una carpeta nueva y ejecuta AsterMax Mechanical.exe. No requiere instalador. Conserva lib, NetGen y las DLL. Requiere .NET Framework 4.8.

## Flujo de materiales
1. Importa tu geometria y genera la malla.
2. Abre Materiales > Biblioteca.
3. Selecciona Acero_elastico_referencia y copialo al modelo; guarda/cierra la biblioteca.
4. Usa Editar material para ajustar las propiedades, o Nuevo material para crear uno propio.
5. Asignar a pieza abre una seccion solida: selecciona el material y la pieza o region.
6. Guarda el proyecto .pmx. Las propiedades y asignaciones se conservan al abrirlo.

La biblioteca nativa permite guardar materiales propios y abrir otras bibliotecas .lib. No se agregan materiales al modelo automaticamente.

El acero de referencia solo define elasticidad isotropa y densidad a temperatura ambiente: E=210000 MPa, Poisson=0.3, densidad=7850 kg/m3 (7.85e-9 tonne/mm3). No representa un grado certificado ni incluye plasticidad o limite de fluencia.
Fuente: SSAB Precision Steel Tube Handbook, p.187:
https://www.ssab.com/-/media/C7B2AA431A3545C38796EA08EC59B148.ashx

La prueba del EXE importa STEP, genera malla, agrega material y seccion, comprueba conversion mm-tonne a m-kg, guarda/reabre y verifica propiedades y asignacion. Example-mesh.pmx contiene ese caso.

Code_Aster y el flujo de resultados aun no estan integrados en esta version. No se incluye solver CalculiX.
Codigo y licencias: https://github.com/MedinaParra/AsterMax-Ubuntu/tree/codex/c975-native-startup-repair
Base GPL-3.0: https://github.com/tsvilans/PrePoMax/tree/3669e65581650e5d9d868aa761db9efd856f8571
