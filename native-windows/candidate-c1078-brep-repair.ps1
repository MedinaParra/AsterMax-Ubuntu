param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
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

            if (!File.Exists(executable))
            {
                string missing = "No se encontró NetGen: " + executable;
                _form.WriteDataToOutput(missing);
                if (showError) MessageBoxes.ShowError(missing);
                return null;
            }
            if (!File.Exists(brepFileName) || new FileInfo(brepFileName).Length == 0)
            {
                string missing = "El archivo BREP no existe o está vacío: " + brepFileName;
                _form.WriteDataToOutput(missing);
                if (showError) MessageBoxes.ShowError(missing);
                return null;
            }
            try
            {
                string argument = "BREP_VISUALIZATION " +
                                  "\"" + brepFileName.ToUTF8() + "\" " +
                                  "\"" + visFileName.ToUTF8() + "\" " +
                                  _settings.Graphics.GeometryDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture);

                _form.WriteDataToOutput("AsterMax CAD tessellation START: " + Path.GetFileName(brepFileName) +
                                        " -> " + Path.GetFileName(visFileName));
                _form.WriteDataToOutput("NetGen exe=" + executable + "; args=" + argument +
                    "; cwd=" + calculixSettings.WorkDirectory);
                _netgenJob = new NetgenJob(jobName, executable, argument, calculixSettings.WorkDirectory);
                _netgenJob.AppendOutput += netgenJob_AppendOutput;
                _netgenJob.Submit();

                if (_netgenJob.JobStatus != JobStatus.OK)
                {
                    string message = "AsterMax CAD tessellation FAIL: NetGen did not complete for " +
                                     Path.GetFileName(brepFileName) + ". Estado=" + _netgenJob.JobStatus + "; exit=" + (_netgenJob.AsterMaxExitCode.HasValue ? _netgenJob.AsterMaxExitCode.Value.ToString() : "no disponible") + "; BREP=" + brepFileName + "; VIS=" + visFileName; 
                    _errors.Add(message);
                    _form.WriteDataToOutput(message);
                    if (showError) MessageBoxes.ShowError("No se pudo generar la visualización BREP.\n" + message + "\nRevisa la ventana de salida para ver el diagnóstico de NetGen.");
                    return null;
                }

                if (!File.Exists(visFileName) || new FileInfo(visFileName).Length == 0)
                {
                    string message = "AsterMax CAD tessellation FAIL: visualization file is missing or empty for " +
                                     Path.GetFileName(brepFileName) + ".";
                    _errors.Add(message);
                    _form.WriteDataToOutput(message);
                    if (showError) MessageBoxes.ShowError("NetGen no generó un archivo de visualización válido.\n" + message);
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
if($c.Contains('"Importing brep file failed."')){throw 'Unreplaced generic BREP failure message'}
Set-Content $controllerPath $c -Encoding UTF8
$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
$u=$u.Replace('AsterMax Mechanical C10.41 RC1','AsterMax Mechanical C10.78 BREP repair')
Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.78 BREP prerequisites, invariant arguments, unique visualization, actionable errors applied.'
