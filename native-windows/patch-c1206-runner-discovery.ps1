param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'

# C12.06 repairs the missing-runner incident without weakening native solver
# evidence. Discovery only identifies an adapter; its real backend probe and
# solve/output validation remain responsible for declaring Code_Aster ready.
$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content -LiteralPath $solvePath -Raw),"\r\n?","`n")

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $Old=[regex]::Replace($Old,"\r\n?","`n")
    $New=[regex]::Replace($New,"\r\n?","`n")
    if(-not $Text.Contains($Old)) { throw "C12.06 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

function Add-PostprocessReadiness([string]$Text) {
    if($Text.Contains('private static bool HasCodeAsterPostprocessTools(string startupPath)')) { return $Text }
    $helper=@'
        private static bool HasCodeAsterPostprocessTools(string startupPath)
        {
            if(String.IsNullOrWhiteSpace(startupPath)) return false;
            string tools=Path.Combine(startupPath,"AsterMaxTools");
            return File.Exists(Path.Combine(tools,"bridge-c964-med-results.py")) &&
                   File.Exists(Path.Combine(tools,"bind-c998-results-fingerprint.py")) &&
                   File.Exists(Path.Combine(tools,"qualify-mechanical-analysis.py"));
        }
'@
    $Text=Replace-Required $Text '        // C1206_DISCOVERY_CORE_END' ($helper+"`n"+'        // C1206_DISCOVERY_CORE_END')
    $probeAnchor='            JObject runnerProbe=ProbeCodeAsterRunner(runner);'
    $Text=Replace-Required $Text $probeAnchor ($probeAnchor+"`n"+'            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");')
    $diagnostic=@'
                ["runtime_contract"]="ASTERMAX_C1206_COMPLETE_RUNTIME_PROBE_V1",
                ["bridge_ready"]=File.Exists(Path.Combine(tools,"bridge-c964-med-results.py")),
                ["binder_ready"]=File.Exists(Path.Combine(tools,"bind-c998-results-fingerprint.py")),
                ["qualifier_ready"]=File.Exists(Path.Combine(tools,"qualify-mechanical-analysis.py")),
                ["runtime_ready"]=(bool)pythonProbe["ready"] && (bool)runnerProbe["ready"] &&
                                  HasCodeAsterPostprocessTools(Application.StartupPath),
'@
    $Text=Replace-Required $Text '                ["runtime_contract"]="ASTERMAX_C1006_FULL_RUNTIME_PROBE_V1",' $diagnostic
    $oldGate=@'
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
            string bridge=Path.Combine(tools,"bridge-c964-med-results.py");
            string binder=Path.Combine(tools,"bind-c998-results-fingerprint.py");

            JObject d=RuntimeDiagnostic();
            d["bridge_ready"]=File.Exists(bridge);
            d["binder_ready"]=File.Exists(binder);
            d["runtime_ready"]=(bool)d["python_ready"] &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               (bool)d["code_aster_backend_ready"] &&
                               File.Exists(bridge) && File.Exists(binder);
'@
    $Text=Replace-Required $Text $oldGate '            JObject d=RuntimeDiagnostic();'
    $oldVisible=@'
                string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
                d["bridge_ready"]=File.Exists(Path.Combine(tools,"bridge-c964-med-results.py"));
                d["binder_ready"]=File.Exists(Path.Combine(tools,"bind-c998-results-fingerprint.py"));
                d["runtime_ready"]=(bool)d["python_ready"] && (bool)d["code_aster_runner_ready"] && (bool)d["code_aster_backend_ready"] &&
                                   (bool)d["bridge_ready"] && (bool)d["binder_ready"];
'@
    $Text=Replace-Required $Text $oldVisible ''
    $Text=Replace-Required $Text '((bool?)d["code_aster_backend_ready"]==true && (bool?)d["python_ready"]==true)?MessageBoxIcon.Information:MessageBoxIcon.Warning' '((bool?)d["runtime_ready"]==true)?MessageBoxIcon.Information:MessageBoxIcon.Warning'
    $summaryAnchor='                "\nPython de resultados: "+((bool?)d["python_ready"]==true?"Disponible":"No disponible")+'
    $summaryNew=@'
                "\nPython de resultados: "+((bool?)d["python_ready"]==true?"Disponible":"No disponible")+
                "\nHerramientas de resultados: "+((bool?)d["bridge_ready"]==true && (bool?)d["binder_ready"]==true && (bool?)d["qualifier_ready"]==true?"Completas":"Faltan archivos; extraiga nuevamente el ZIP completo")+
'@
    $Text=Replace-Required $Text $summaryAnchor $summaryNew
    return $Text
}

if($s.Contains('// ASTERMAX_C1206_RUNNER_DISCOVERY')) {
    $updated=Add-PostprocessReadiness $s
    if($updated -ne $s){ Set-Content -LiteralPath $solvePath $updated -Encoding UTF8 }
    Write-Host 'C12.06 runner discovery and complete postprocess readiness already applied.'
    return
}

$old=@'
        private static string ResolveCodeAsterRunner()
        {
            string packaged=Path.Combine(Application.StartupPath,"AsterMaxRuntime","CodeAster","astermax-codeaster-runner.cmd");
            if(File.Exists(packaged)) return packaged;
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            return null;
        }
'@
$new=@'
        // ASTERMAX_C1206_RUNNER_DISCOVERY
        private static string ResolveCodeAsterRunner()
        {
            return ResolveCodeAsterRunnerFrom(Application.StartupPath,
                Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER"));
        }

        // C1206_DISCOVERY_CORE_BEGIN
        private static bool IsUsableCodeAsterRunner(string candidate)
        {
            if(String.IsNullOrWhiteSpace(candidate) || !File.Exists(candidate)) return false;
            string extension=Path.GetExtension(candidate).ToLowerInvariant();
            if(extension!=".exe" && extension!=".cmd" && extension!=".bat" && extension!=".ps1") return false;
            if(String.Equals(Path.GetFileName(candidate),"astermax-codeaster-runner.cmd",StringComparison.OrdinalIgnoreCase))
                return File.Exists(Path.Combine(Path.GetDirectoryName(candidate),"astermax-codeaster-runner.ps1"));
            return true;
        }

        private static string ResolveCodeAsterRunnerFrom(string startupPath,string configured)
        {
            if(!String.IsNullOrWhiteSpace(startupPath))
            {
                // The first location is the distribution contract. The second
                // accepts previously distributed adapter folders without an env var.
                string[] relatives=new[] {
                    Path.Combine("AsterMaxRuntime","CodeAster","astermax-codeaster-runner.cmd"),
                    Path.Combine("CodeAster","astermax-codeaster-runner.cmd")
                };
                foreach(string relative in relatives)
                {
                    try
                    {
                        string candidate=Path.GetFullPath(Path.Combine(startupPath,relative));
                        if(IsUsableCodeAsterRunner(candidate)) return candidate;
                    }
                    catch(ArgumentException) { }
                    catch(NotSupportedException) { }
                    catch(PathTooLongException) { }
                }
            }
            if(String.IsNullOrWhiteSpace(configured)) return null;
            try
            {
                string candidate=Path.GetFullPath(configured.Trim().Trim('"'));
                if(IsUsableCodeAsterRunner(candidate)) return candidate;
            }
            catch(ArgumentException) { }
            catch(NotSupportedException) { }
            catch(PathTooLongException) { }
            return null;
        }
        // C1206_DISCOVERY_CORE_END
'@
$s=Replace-Required $s $old $new

$legacyFailure='Fail("Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.");'
$friendlyFailure='Fail("No se encuentra el adaptador de Code_Aster o el paquete está incompleto.\n\nExtraiga todo el ZIP de AsterMax en una carpeta nueva, incluidos AsterMaxRuntime y AsterMaxTools.\nDespués use Solución > Instalar motor si falta Code_Aster, o Solución > Verificar para seleccionar una instalación existente.");'
$s=Replace-Required $s $legacyFailure $friendlyFailure

$summaryOld='return "Code_Aster: "+((bool?)d["code_aster_backend_ready"]==true?"DISPONIBLE":"NO DISPONIBLE")+'
$summaryNew=@'
return "Adaptador de AsterMax: "+((bool?)d["code_aster_runner_ready"]==true?"Disponible":"Falta o está incompleto; extraiga nuevamente el ZIP completo")+
                "\nCode_Aster: "+((bool?)d["code_aster_backend_ready"]==true?"DISPONIBLE":"NO DISPONIBLE")+
'@
$s=Replace-Required $s $summaryOld $summaryNew.TrimEnd()
$s=Replace-Required $s 'Use Runtime para seleccionar otra carpeta de instalación.' 'Use Solución > Verificar para seleccionar una instalación existente.\nSi no tiene Code_Aster, use Solución > Instalar motor y vuelva a Verificar cuando termine.'

$uiMethod=@'
        private void StartAsterMaxCodeAsterSetup()
        {
            try
            {
                string directory=Path.Combine(Application.StartupPath,"AsterMaxRuntime","CodeAster");
                string setup=Path.Combine(directory,"setup-codeaster-windows.cmd");
                if(!File.Exists(setup) || !File.Exists(Path.Combine(directory,"setup-codeaster-windows.ps1")))
                    throw new FileNotFoundException("El instalador de Code_Aster no está en el paquete. Extraiga todo el ZIP de AsterMax en una carpeta nueva.");
                // Only the explicit ribbon click opens setup. The setup process
                // owns installation/probing; do not block the WinForms UI thread.
                Process.Start(new ProcessStartInfo {
                    FileName=setup,
                    WorkingDirectory=directory,
                    UseShellExecute=true
                });
                tsslState.Text="Instalador Code_Aster abierto. Cuando termine, use Solución > Verificar.";
            }
            catch(Exception ex)
            {
                CaeGlobals.MessageBoxes.ShowError("No se pudo abrir el instalador de Code_Aster: "+ex.Message);
            }
        }

'@
$s=Replace-Required $s '        private void ShowAsterMaxRuntimePreflight()' ($uiMethod+'        private void ShowAsterMaxRuntimePreflight()')

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=[regex]::Replace((Get-Content -LiteralPath $uiPath -Raw),"\r\n?","`n")
$verifyTile='                CommandTile("Verificar", "PREFLIGHT", () => ShowAsterMaxRuntimePreflight(), true),'
$setupTile='                CommandTile("Instalar motor", "CODE_ASTER_SETUP", () => StartAsterMaxCodeAsterSetup(), true),'
$u=Replace-Required $u $verifyTile ($setupTile+"`n"+$verifyTile)

# The delivered build must identify itself, rather than retain the historical
# C10.41 RC1 caption shown in the incident screenshot.
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
$g=Get-Content -LiteralPath $globalsPath -Raw
$versionPattern='public static string ProgramName = "AsterMax Mechanical C10\.(?:40|41 RC1)";'
if([regex]::Matches($g,$versionPattern).Count -ne 1){ throw 'C12.06 known historical ProgramName assignment missing or ambiguous.' }
$g=[regex]::Replace($g,$versionPattern,'public static string ProgramName = "AsterMax Mechanical C12.06";')
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1034Audit.cs'
$a=Get-Content -LiteralPath $auditPath -Raw
$a=Replace-Required $a 'AsterMax Mechanical C10.41 RC1' 'AsterMax Mechanical C12.06'

$s=Add-PostprocessReadiness $s
Set-Content -LiteralPath $solvePath $s -Encoding UTF8
Set-Content -LiteralPath $uiPath $u -Encoding UTF8
Set-Content -LiteralPath $globalsPath $g -Encoding UTF8
Set-Content -LiteralPath $auditPath $a -Encoding UTF8
Write-Host 'C12.06 complete adapter discovery, native setup action and actionable diagnostics applied.'
