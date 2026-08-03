# AsterMax Windows Native Bridge 0.1.0 beta

Primera entrega ejecutable de la migración de AsterMax a Windows con backend Code_Aster nativo.

## Alcance de esta beta

Esta aplicación es el puente funcional del solver. Permite:

- detectar instalaciones Code_Aster/Salome-Meca en Windows;
- seleccionar manualmente `run_aster.bat`, `as_run.bat`, `python.exe` u otro lanzador compatible;
- comprobar que el lanzador responde;
- seleccionar y ejecutar un trabajo `.export`;
- mostrar `stdout` y `stderr` durante la ejecución;
- cancelar el árbol de procesos;
- guardar logs en `%LOCALAPPDATA%\AsterMax\logs`;
- guardar la configuración sin permisos de administrador.

No contiene todavía la interfaz Mechanical completa porque el repositorio remoto original solo conserva el README. La GUI, el modelador, el mallador, el solver TET4 interno y el postproceso deberán integrarse desde el paquete fuente recuperado de AsterMax 2.0.

## Uso

1. Instale o descomprima una distribución de Code_Aster para Windows.
2. Abra `AsterMax-Windows-Native.exe`.
3. Pulse **Detectar** o seleccione el lanzador manualmente.
4. Pulse **Probar Code_Aster**.
5. Seleccione un archivo `.export`.
6. Pulse **Ejecutar análisis**.

La aplicación es portable y autocontenida. No requiere instalar .NET ni permisos administrativos.

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

Esta beta valida la integración de procesos, rutas, diagnóstico y captura de resultados. No certifica todavía equivalencia numérica entre las compilaciones Linux y Windows de Code_Aster. Esa validación se realizará mediante la matriz de casos AsterMax y los archivos `.comm`, `.export`, `.med`, `.mess` y resultados comparables.
