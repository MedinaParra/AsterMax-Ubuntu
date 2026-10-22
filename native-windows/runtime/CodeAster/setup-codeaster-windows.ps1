param(
    [switch]$Unattended,
    [string]$InstallerPath,
    [string]$LogDirectory
)

$ErrorActionPreference = 'Stop'
$providerUrl = 'https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi'
$providerSize = [int64]398012592
$providerSha256 = 'B789FEFFC12E0FECBCFBABE6D386FA15C1AB74797C8C9D27A5733F8D2B5D092D'
$runner = Join-Path $PSScriptRoot 'astermax-codeaster-runner.ps1'
$script:probe = $null
$script:installExit = $null
$script:installed = $false
$script:logRoot = $null

function Save-SetupResult([string]$Status, [string]$Message) {
    if (-not $script:logRoot) { return }
    [ordered]@{
        schema = 'astermax-native-setup/v1'
        release = 'C12.06'
        status = $Status
        message = $Message
        completed_utc = [DateTime]::UtcNow.ToString('o')
        transport = 'WINDOWS_NATIVE'
        installed_by_this_run = $script:installed
        msi_exit_code = $script:installExit
        provider_url = $providerUrl
        provider_sha256 = $providerSha256.ToLowerInvariant()
        provider_size_bytes = $providerSize
        solver_installer_redistributed = $false
        solver_probe = $script:probe
        model_validation = 'NOT_RUN'
        synthetic_results_allowed = $false
    } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $script:logRoot 'setup-result.json') -Encoding UTF8
}

function Get-NativeProbe {
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $process.StartInfo.FileName = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $process.StartInfo.Arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -File "' + $runner + '" probe'
    $process.StartInfo.WorkingDirectory = $PSScriptRoot
    $process.StartInfo.UseShellExecute = $false
    $process.StartInfo.CreateNoWindow = $true
    $process.StartInfo.RedirectStandardOutput = $true
    $process.StartInfo.RedirectStandardError = $true
    try {
        if (-not $process.Start()) { throw 'No se pudo ejecutar la comprobacion del motor.' }
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(150000)) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID $process.Id /T /F 2>&1 | Out-Null
            throw 'La comprobacion del motor excedio 150 segundos.'
        }
        $stdout = $outTask.Result
        $stderr = $errTask.Result
        $stdout | Set-Content -LiteralPath (Join-Path $script:logRoot 'native-probe.json') -Encoding UTF8
        $stderr | Set-Content -LiteralPath (Join-Path $script:logRoot 'native-probe-stderr.log') -Encoding UTF8
        try { $result = $stdout.Trim() | ConvertFrom-Json } catch {
            throw ('El adaptador devolvio un diagnostico invalido. ' + $stderr.Trim())
        }
        if ($process.ExitCode -ne 0 -or $result.transport -ne 'WINDOWS_NATIVE' -or $result.wsl_required -eq $true) {
            $result.ready = $false
        }
        return $result
    }
    finally { $process.Dispose() }
}

function Assert-Installer([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'No se encontro el instalador descargado.' }
    $bytes = (Get-Item -LiteralPath $Path).Length
    if ($bytes -ne $providerSize) { throw "Tamano de instalador incorrecto: $bytes; esperado $providerSize." }
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($hash -ne $providerSha256) { throw 'El SHA-256 del instalador no coincide. No se ejecutara el archivo.' }
}

function Download-ProviderInstaller([string]$Destination) {
    # Fetch the unmodified MSI from its publisher. Keep it outside the application
    # ZIP and do not replace the installer's NTFS-link setup with file extraction.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $curl = Get-Command curl.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        $offset = if (Test-Path -LiteralPath $Destination) { (Get-Item -LiteralPath $Destination).Length } else { [int64]0 }
        if ($offset -eq $providerSize) {
            try { Assert-Installer $Destination; return } catch {
                # This is our managed download cache, never an explicit user path.
                Remove-Item -LiteralPath $Destination -Force
                $offset = 0
            }
        }
        if ($offset -gt $providerSize) { Remove-Item -LiteralPath $Destination -Force; $offset = 0 }
        Write-Host "Descargando Code_Aster 2025: intento $attempt, $offset de $providerSize bytes."
        if ($curl) {
            $curlArgs = @('-L','--fail','--proto','=https','--proto-redir','=https','--connect-timeout','30','--max-time','900','--speed-time','60','--speed-limit','1024')
            if ($offset -gt 0) { $curlArgs += @('--continue-at',[string]$offset) }
            $curlArgs += @('--output',$Destination,$providerUrl)
            & $curl.Source @curlArgs
            $downloadExit = $LASTEXITCODE
            if ($downloadExit -eq 33 -and (Test-Path -LiteralPath $Destination)) {
                Remove-Item -LiteralPath $Destination -Force
            }
        }
        else {
            try { Invoke-WebRequest -Uri $providerUrl -OutFile $Destination -UseBasicParsing -TimeoutSec 900 } catch { Write-Warning $_.Exception.Message }
        }
        if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -eq $providerSize) {
            Assert-Installer $Destination
            return
        }
        if ($attempt -lt 8) { Start-Sleep -Seconds ([Math]::Min(15,2*$attempt)) }
    }
    throw 'No se pudo completar la descarga. Revise su conexion y vuelva a ejecutar Instalar motor; se retomara la descarga parcial.'
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
        throw 'Este asistente requiere Windows de 64 bits.'
    }
    if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
        throw 'Falta el adaptador. Extraiga todo el ZIP de AsterMax en una carpeta nueva.'
    }
    $local = [Environment]::GetFolderPath('LocalApplicationData')
    if ([string]::IsNullOrWhiteSpace($LogDirectory)) {
        $LogDirectory = Join-Path $local ('AsterMax\Logs\CodeAsterSetup\' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss'))
    }
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    $script:logRoot = (Resolve-Path -LiteralPath $LogDirectory).Path
    Write-Host 'ASTERMAX C12.06 - CONFIGURACION DE CODE_ASTER PARA WINDOWS' -ForegroundColor Cyan
    Write-Host 'Se comprobara la instalacion existente antes de descargar el motor original del proveedor.'
    Write-Host ('Registro: ' + $script:logRoot)
    $script:probe = Get-NativeProbe
    if ($script:probe.ready -eq $true) {
        Save-SetupResult 'PASS' 'Instalacion nativa existente comprobada; no se reinstalo.'
        Write-Host 'Code_Aster ya funciona. Puede volver a AsterMax y usar Solucion > Resolver.' -ForegroundColor Green
        exit 0
    }
    # An existing launcher which fails a real probe requires diagnosis; reinstalling
    # blindly can conceal the original failure or alter a configured installation.
    if ($script:probe.backend -and $script:probe.backend -ne 'missing') {
        throw ('Se encontro Code_Aster, pero su prueba fallo. Seleccione su instalacion en Solucion > Verificar. Detalle: ' + $script:probe.message)
    }
    if ($script:probe.message -match 'Configured Windows launcher not found') {
        throw ('La configuracion explicita apunta a un ejecutor inexistente. ' + $script:probe.message)
    }

    if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
        $cache = Join-Path $local 'AsterMax\Downloads\CodeAster2025'
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        $InstallerPath = Join-Path $cache 'code-aster_v2025_std.msi'
        Write-Host 'Descarga necesaria: aproximadamente 398 MB. Se verificara el archivo antes de instalarlo.'
        Download-ProviderInstaller $InstallerPath
    }
    $InstallerPath = (Resolve-Path -LiteralPath $InstallerPath).Path
    Assert-Installer $InstallerPath
    Write-Host 'Instalando Code_Aster nativo. Windows puede solicitar autorizacion para completar la instalacion.'
    $installLog = Join-Path $script:logRoot 'msi-install.log'
    $ui = if ($Unattended) { '/qn' } else { '/passive' }
    $installArgs = '/i "' + $InstallerPath + '" ' + $ui + ' /norestart /l*v "' + $installLog + '"'
    $installProcess = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\msiexec.exe') -ArgumentList $installArgs -PassThru
    try {
        if (-not $installProcess.WaitForExit(900000)) { throw 'El instalador sigue activo tras 15 minutos. Espere a que termine y revise su registro; no se iniciara otra instalacion.' }
        $script:installExit = $installProcess.ExitCode
    }
    finally { $installProcess.Dispose() }
    if ($script:installExit -notin @(0,3010)) { throw "El instalador termino con codigo $script:installExit. Revise msi-install.log." }
    $script:installed = $true
    Write-Host 'Comprobando la ejecucion real de Code_Aster...'
    $script:probe = Get-NativeProbe
    if ($script:probe.ready -ne $true) { throw ('El instalador termino, pero la prueba del motor no paso. ' + $script:probe.message) }

    # Preserve the application's existing configuration fields. This records a
    # detected installation, without editing PATH or persistent environment vars.
    $configDir = Join-Path $local 'AsterMax'
    New-Item -ItemType Directory -Force -Path $configDir | Out-Null
    $configPath = Join-Path $configDir 'code-aster-windows.json'
    $config = [pscustomobject]@{}
    if (Test-Path -LiteralPath $configPath) {
        try { $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json } catch { $config = [pscustomobject]@{} }
    }
    $installRoot = Split-Path -Parent $script:probe.backend
    $config | Add-Member -NotePropertyName installation -NotePropertyValue $installRoot -Force
    $config | Add-Member -NotePropertyName configured_by -NotePropertyValue 'AsterMax C12.06' -Force
    $tempConfig = $configPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($tempConfig,($config | ConvertTo-Json -Depth 10),(New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tempConfig -Destination $configPath -Force
    Save-SetupResult 'PASS' 'Instalacion y prueba real del motor nativo completadas.'
    Write-Host 'LISTO. Vuelva a AsterMax y use Solucion > Resolver.' -ForegroundColor Green
    if ($script:installExit -eq 3010) { Write-Host 'El instalador tambien recomienda reiniciar Windows al terminar su trabajo.' }
    exit 0
}
catch {
    $message = $_.Exception.Message
    Save-SetupResult 'FAIL' $message
    [Console]::Error.WriteLine('No se completo la configuracion: ' + $message)
    if ($script:logRoot) { [Console]::Error.WriteLine('Registro: ' + $script:logRoot) }
    exit 1
}
