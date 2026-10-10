param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$projectPath = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
foreach($p in @($controllerPath,$uiPath,$projectPath)){ if(!(Test-Path $p)){ throw "C10.43 missing: $p" } }

function Replace-CSharpMethod([string]$text,[string]$signature,[string]$replacement){
    $start=$text.IndexOf($signature)
    if($start -lt 0){ throw "C10.43 method missing: $signature" }
    $brace=$text.IndexOf('{',$start)
    if($brace -lt 0){ throw "C10.43 opening brace missing: $signature" }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $text.Length; $n++){
        if($text[$n] -eq '{'){ $depth++ }
        elseif($text[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $end=$n+1; break }
        }
    }
    if($end -lt 0){ throw "C10.43 closing brace missing: $signature" }
    return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# ----------------------------------------------------------------------
# 1. Reliable BREP visualization transaction.
# Every CAD part gets a unique .vis and NetGen job name. This removes stale
# shared visualization files and is a prerequisite for safe bounded parallelism.
# ----------------------------------------------------------------------
$brepMethod=@'
        public string[] ImportBrepPartFile(string brepFileName, bool showError = true)
        {
            CalculixSettings calculixSettings = _settings.Calculix;
            if (calculixSettings.WorkDirectory == null || !Directory.Exists(calculixSettings.WorkDirectory))
            {
                MessageBoxes.ShowWorkDirectoryError();
                return null;
            }

            string executable = Application.StartupPath + Globals.NetGenMesher;
            string visFileName = Tools.GetNonExistentRandomFileName(calculixSettings.WorkDirectory, ".vis");
            string visStem = Path.GetFileNameWithoutExtension(visFileName);
            string jobName = "Brep_" + visStem;

            try
            {
                string argument = "BREP_VISUALIZATION " +
                                  "\"" + brepFileName.ToUTF8() + "\" " +
                                  "\"" + visFileName.ToUTF8() + "\" " +
                                  _settings.Graphics.GeometryDeflection.ToString();

                _form.WriteDataToOutput("AsterMax CAD tessellation START: " + Path.GetFileName(brepFileName) +
                                        " -> " + Path.GetFileName(visFileName));
                _netgenJob = new NetgenJob(jobName, executable, argument, calculixSettings.WorkDirectory);
                _netgenJob.AppendOutput += netgenJob_AppendOutput;
                _netgenJob.Submit();

                if (_netgenJob.JobStatus != JobStatus.OK)
                {
                    string message = "AsterMax CAD tessellation FAIL: NetGen did not complete for " +
                                     Path.GetFileName(brepFileName) + ".";
                    _errors.Add(message);
                    _form.WriteDataToOutput(message);
                    if (showError) MessageBoxes.ShowError("Importing brep file failed.");
                    return null;
                }

                if (!File.Exists(visFileName) || new FileInfo(visFileName).Length == 0)
                {
                    string message = "AsterMax CAD tessellation FAIL: visualization file is missing or empty for " +
                                     Path.GetFileName(brepFileName) + ".";
                    _errors.Add(message);
                    _form.WriteDataToOutput(message);
                    if (showError) MessageBoxes.ShowError("CAD visualization generation failed.");
                    return null;
                }

                long visualizationBytes = new FileInfo(visFileName).Length;
                string[] addedPartNames = _model.ImportGeometryFromBrepFile(visFileName, brepFileName);
                if (addedPartNames == null || addedPartNames.Length == 0)
                {
                    string message = "AsterMax CAD import EMPTY: NetGen produced visualization data but no geometry was accepted from " +
                                     Path.GetFileName(brepFileName) + ".";
                    _errors.Add(message);
                    _form.WriteDataToOutput(message);
                    if (showError) MessageBoxes.ShowError("No geometry to import.");
                    return null;
                }

                _form.WriteDataToOutput("AsterMax CAD tessellation PASS: " + addedPartNames.Length +
                                        " pieza(s), VIS=" + visualizationBytes + " bytes, job=" + jobName + ".");
                return addedPartNames;
            }
            finally
            {
                try
                {
                    if (File.Exists(visFileName)) File.Delete(visFileName);
                }
                catch (Exception ex)
                {
                    _form.WriteDataToOutput("AsterMax CAD cleanup warning: " + ex.Message);
                }
            }
        }
'@
$c=Replace-CSharpMethod $c '        public string[] ImportBrepPartFile(string brepFileName, bool showError = true)' $brepMethod

# ----------------------------------------------------------------------
# 2. Stage-level diagnostics for STEP/IGES/BREP assemblies.
# Distinguish split failure, empty import, partial import, and complete import.
# ----------------------------------------------------------------------
if(-not $c.Contains('ASTERMAX_CAD_SPLIT_EMPTY')){
    $splitLine='                string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);'
    if(-not $c.Contains($splitLine)){
        $splitLine='            string[] filesToImport = SplitAssembly(assemblyFileName, splitCommand);'
    }
    if(-not $c.Contains($splitLine)){ throw 'C10.43 SplitAssembly call anchor missing after C10.42.' }
    $indent=$splitLine.Substring(0,$splitLine.IndexOf('string[]'))
    $replacement=$indent+'int asterMaxErrorsBefore = _errors.Count;'+"`n"+$splitLine+"`n"+$indent+'if (asterMaxTopLevelCadImport)'+"`n"+$indent+'{'+"`n"+$indent+'    int splitCount = filesToImport == null ? 0 : filesToImport.Length;'+"`n"+$indent+'    _form.WriteDataToOutput("AsterMax CAD SPLIT: " + splitCount + " archivo(s) BREP temporales.");'+"`n"+$indent+'    if (splitCount == 0)'+"`n"+$indent+'    {'+"`n"+$indent+'        string splitMessage = "ASTERMAX_CAD_SPLIT_EMPTY: el archivo CAD no produjo cuerpos BREP importables.";'+"`n"+$indent+'        _errors.Add(splitMessage);'+"`n"+$indent+'        _form.WriteDataToOutput(splitMessage);'+"`n"+$indent+'    }'+"`n"+$indent+'}'
    $c=$c.Replace($splitLine,$replacement)
}

if(-not $c.Contains('ASTERMAX_CAD_IMPORT_COMPLETE')){
    $stop='                asterMaxCadImportWatch.Stop();'
    if(-not $c.Contains($stop)){ $stop='            asterMaxCadImportWatch.Stop();' }
    if(-not $c.Contains($stop)){ throw 'C10.43 C10.42 import telemetry anchor missing.' }
    $indent=$stop.Substring(0,$stop.IndexOf('asterMax'))
    $diagnostics=@"
${indent}if (asterMaxTopLevelCadImport)
${indent}{
${indent}    int asterMaxErrorDelta = _errors.Count - asterMaxErrorsBefore;
${indent}    if (allAddedPartNames.Count == 0)
${indent}    {
${indent}        string emptyMessage = "ASTERMAX_CAD_IMPORT_EMPTY: no se incorporó ninguna pieza al modelo.";
${indent}        if (asterMaxErrorDelta == 0) _errors.Add(emptyMessage);
${indent}        _form.WriteDataToOutput(emptyMessage);
${indent}    }
${indent}    else if (asterMaxErrorDelta > 0)
${indent}        _form.WriteDataToOutput("ASTERMAX_CAD_IMPORT_PARTIAL: " + allAddedPartNames.Count +
${indent}                                " pieza(s), " + asterMaxErrorDelta + " error(es).");
${indent}    else
${indent}        _form.WriteDataToOutput("ASTERMAX_CAD_IMPORT_COMPLETE: " + allAddedPartNames.Count +
${indent}                                " pieza(s), 0 errores.");
${indent}}
"@
    $c=$c.Replace($stop,$diagnostics.TrimEnd()+"`n"+$stop)
}

# A failed recursive compound import must not create an empty CompoundGeometryPart.
if(-not $c.Contains('AsterMax compound import produced no geometry.')){
    $compoundCall='            importedPartNames = ImportCADAssemblyFile(brepFileName, "BREP_ASSEMBLY_SPLIT_TO_PARTS");'
    if(-not $c.Contains($compoundCall)){ throw 'C10.43 compound recursive import anchor missing.' }
    $compoundGuard=$compoundCall+"`n"+'            if (importedPartNames == null || importedPartNames.Length == 0)'+"`n"+
                   '                throw new CaeException("AsterMax compound import produced no geometry.");'
    $c=$c.Replace($compoundCall,$compoundGuard)
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# 3. Runtime import audit hook. Used only when ASTERMAX_C1043_AUDIT_DIR is set.
# ----------------------------------------------------------------------
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1043ImportAudit.cs'
$audit=@'
using System;
using System.IO;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void StartAsterMaxC1043ImportAudit()
        {
            string directory = Environment.GetEnvironmentVariable("ASTERMAX_C1043_AUDIT_DIR");
            if (String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);

            int expectedParts = 100;
            int configured;
            if (Int32.TryParse(Environment.GetEnvironmentVariable("ASTERMAX_C1043_EXPECTED_PARTS"), out configured) && configured > 0)
                expectedParts = configured;

            int ticks = 0;
            var timer = new Timer { Interval = 500 };
            timer.Tick += (s, e) =>
            {
                ticks++;
                int partCount = _controller != null && _controller.Model != null && _controller.Model.Geometry != null
                    ? _controller.Model.Geometry.Parts.Count : 0;
                bool idle = _controller != null && !IsStateWorking();
                bool ready = idle && partCount >= expectedParts;
                if (!ready && ticks < 360) return;

                timer.Stop();
                timer.Dispose();
                bool pass = false;
                var report = new JObject();
                try
                {
                    int errors = _controller == null ? -1 : _controller.GetNumberOfErrors();
                    report["release"] = "C10.43-candidate";
                    report["expected_parts"] = expectedParts;
                    report["cad_bodies"] = partCount;
                    report["controller_errors"] = errors;
                    report["idle"] = idle;
                    report["elapsed_ms_upper_bound"] = ticks * 500;
                    pass = ready && errors == 0;
                    report["pass"] = pass;
                    if (!pass)
                        report["error"] = "Large STEP import did not reach the expected complete/idle/error-free state.";
                }
                catch (Exception ex)
                {
                    report["pass"] = false;
                    report["error"] = ex.ToString();
                }

                File.WriteAllText(Path.Combine(directory, "c1043-import-report.json"), report.ToString(Formatting.Indented));
                Environment.ExitCode = pass ? 0 : 1;
                _c10209AuditShutdownDirectory = directory;
                if (_controller != null) _controller.ModelChanged = false;
                BeginInvoke(new Action(() => Close()));
            };
            timer.Start();
        }
    }
}
'@
Set-Content $auditPath $audit -Encoding UTF8

$p=[regex]::Replace((Get-Content $projectPath -Raw),"\r\n?","`n")
if(-not $p.Contains('Forms\AsterMaxC1043ImportAudit.cs')){
    $anchor='<Compile Include="Forms\AsterMaxC1034Audit.cs" />'
    if(-not $p.Contains($anchor)){ throw 'C10.43 project C1034 audit anchor missing.' }
    $p=$p.Replace($anchor,$anchor+"`n    "+'<Compile Include="Forms\AsterMaxC1043ImportAudit.cs" />')
}
Set-Content $projectPath $p -Encoding UTF8

$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
if(-not $u.Contains('StartAsterMaxC1043ImportAudit();')){
    $anchor='                StartAsterMaxC1034OutlineAudit();'
    if(-not $u.Contains($anchor)){ throw 'C10.43 C1034 audit startup anchor missing.' }
    $u=$u.Replace($anchor,$anchor+"`n                StartAsterMaxC1043ImportAudit();")
}
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.43: unique CAD tessellation transactions + staged import diagnostics + runtime audit hook applied.' -ForegroundColor Green
