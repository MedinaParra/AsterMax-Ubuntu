# AsterMax Windows Native Bridge 0.2.0 beta

Segunda entrega ejecutable de la migración de AsterMax a Windows con backend Code_Aster nativo.

## Qué incorpora esta iteración

- detección de instalaciones Code_Aster/Salome-Meca en Windows;
- selección manual de `run_aster.bat`, `as_run.bat`, `python.exe` u otro lanzador compatible;
- diagnóstico del lanzador e intento de identificación de versión;
- creación automática de un caso mínimo `DEBUT(); FIN();`;
- generación automática del `.comm`, `.export` y ruta `.mess`;
- ejecución real del smoke test sin exigir una malla o modelo del usuario;
- lectura y clasificación del archivo `.mess`;
- resumen de alarmas, errores fatales y terminación normal;
- ejecución de archivos `.export` externos;
- arrastrar y soltar archivos `.export` sobre la ventana;
- salida `stdout`/`stderr` en vivo, cancelación del árbol de procesos y logs persistentes;
- workspace de validación en `%PUBLIC%\AsterMaxRuns` para reducir problemas de espacios en rutas.

## Uso recomendado

1. Instale o descomprima una distribución de Code_Aster para Windows.
2. Abra `AsterMax-Windows-Native.exe`.
3. Pulse **Detectar** o seleccione el lanzador manualmente.
4. Pulse **Diagnóstico** para comprobar el proceso y detectar la versión cuando el lanzador la informa.
5. Pulse **Validación automática**. AsterMax generará y ejecutará un caso mínimo real.
6. Revise el resumen y abra la carpeta de trabajo para inspeccionar `astermax_smoke.mess`.
7. Para ejecutar un cálculo propio, seleccione o arrastre un archivo `.export` y pulse **Ejecutar .export**.

La aplicación es portable y autocontenida. No requiere instalar .NET ni permisos administrativos.

## Archivos de usuario

```text
%LOCALAPPDATA%\AsterMax\windows-native.json
%LOCALAPPDATA%\AsterMax\logs\
%PUBLIC%\AsterMaxRuns\smoke-AAAAmmdd-HHMMSS\
```

## Compilar

```powershell
dotnet publish windows/AsterMax.WindowsNative/AsterMax.WindowsNative.csproj `
  -c Release `
  -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true
```

## Límite de validación

El smoke test comprueba que Code_Aster puede inicializarse, procesar un archivo de comandos y terminar normalmente. No valida todavía cálculo por elementos finitos ni equivalencia numérica Windows/Linux. La siguiente iteración debe incorporar un modelo mecánico pequeño con malla MED, desplazamiento conocido, reacción y comparación de tolerancias.

La interfaz Mechanical completa tampoco está incluida porque el repositorio remoto original aún no contiene el árbol fuente de AsterMax Mechanical 2.0.
