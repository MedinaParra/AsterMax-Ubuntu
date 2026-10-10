param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.45 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# ----------------------------------------------------------------------
# C10.45: bounded parallelism only for temporary BREP -> VIS generation.
# Model mutation, compound construction, tree updates and VTK remain serial.
# ----------------------------------------------------------------------
if(-not $c.Contains('private sealed class AsterMaxPreparedBrepVisualization')){
    $anchor='        public string[] ImportBrepPartFile(string brepFileName, bool showError = true)'
    $pos=$c.IndexOf($anchor)
    if($pos -lt 0){throw 'C10.45 ImportBrepPartFile anchor missing.'}
    $helpers=@'
        private sealed class AsterMaxPreparedBrepVisualization
        {
            public string BrepFileName;
            public string VisFileName;
            public string JobName;
            public bool Success;
            public string Error;
            public long VisualizationBytes;
        }

        private AsterMaxPreparedBrepVisualization AsterMaxPrepareBrepVisualization(string brepFileName,
                                                                                   string executable,
                                                                                   string workDirectory,
                                                                                   double deflection)
        {
            var result = new AsterMaxPreparedBrepVisualization();
            result.BrepFileName = brepFileName;
            result.VisFileName = Tools.GetNonExistentRandomFileName(workDirectory, ".vis");
            result.JobName = "BrepParallel_" + Path.GetFileNameWithoutExtension(result.VisFileName);
            string deflectionText = deflection.ToString(System.Globalization.CultureInfo.InvariantCulture);
            string argument = "BREP_VISUALIZATION " +
                              "\"" + brepFileName.ToUTF8() + "\" " +
                              "\"" + result.VisFileName.ToUTF8() + "\" " +
                              deflectionText;
            try
            {
                var psi = new System.Diagnostics.ProcessStartInfo();
                psi.CreateNoWindow = true;
                psi.FileName = executable;
                psi.Arguments = argument;
                psi.WorkingDirectory = workDirectory;
                psi.UseShellExecute = false;
                psi.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
                using (var process = new System.Diagnostics.Process())
                {
                    process.StartInfo = psi;
                    process.Start();
                    if (!process.WaitForExit(600000))
                    {
                        try { process.Kill(); } catch { }
                        result.Error = "NetGen preview timed out after 600 s.";
                        return result;
                    }
                    if (process.ExitCode != 0)
                    {
                        result.Error = "NetGen preview exit code " + process.ExitCode + ".";
                        return result;
                    }
                }
                if (!File.Exists(result.VisFileName) || new FileInfo(result.VisFileName).Length == 0)
                {
                    result.Error = "Visualization file is missing or empty.";
                    return result;
                }
                result.VisualizationBytes = new FileInfo(result.VisFileName).Length;
                result.Success = true;
                return result;
            }
            catch (Exception ex)
            {
                result.Error = ex.Message;
                return result;
            }
        }

        private Dictionary<string, AsterMaxPreparedBrepVisualization> AsterMaxPrepareLeafBrepVisualizations(string[] filesToImport)
        {
            var prepared = new Dictionary<string, AsterMaxPreparedBrepVisualization>(StringComparer.OrdinalIgnoreCase);
            if (filesToImport == null || filesToImport.Length == 0) return prepared;
            if (!_asterMaxCadVisualizationDeflectionOverride.HasValue) return prepared;

            string[] leaves = filesToImport.Where(fileName =>
                !String.IsNullOrWhiteSpace(fileName) &&
                !fileName.ToLowerInvariant().Contains("compound")).ToArray();
            if (leaves.Length < 8) return prepared;

            int workers = Math.Min(4, Math.Max(1, Environment.ProcessorCount));
            string workerText = Environment.GetEnvironmentVariable("ASTERMAX_CAD_TESSELLATION_WORKERS");
            int configuredWorkers;
            if (!String.IsNullOrWhiteSpace(workerText) && Int32.TryParse(workerText, out configuredWorkers))
                workers = Math.Max(1, Math.Min(8, configuredWorkers));

            string executable = Application.StartupPath + Globals.NetGenMesher;
            string workDirectory = _settings.Calculix.WorkDirectory;
            double deflection = _asterMaxCadVisualizationDeflectionOverride.Value;
            var concurrent = new System.Collections.Concurrent.ConcurrentDictionary<string, AsterMaxPreparedBrepVisualization>(StringComparer.OrdinalIgnoreCase);
            var options = new System.Threading.Tasks.ParallelOptions { MaxDegreeOfParallelism = workers };

            var watch = System.Diagnostics.Stopwatch.StartNew();
            System.Threading.Tasks.Parallel.ForEach(leaves, options, brepFileName =>
            {
                concurrent[brepFileName] = AsterMaxPrepareBrepVisualization(brepFileName, executable, workDirectory, deflection);
            });
            watch.Stop();

            foreach (var entry in concurrent) prepared[entry.Key] = entry.Value;
            int successCount = prepared.Values.Count(item => item != null && item.Success);
            _form.WriteDataToOutput("AsterMax CAD parallel preview: " + successCount + "/" + leaves.Length +
                                    " VIS preparados con " + workers + " worker(s) en " +
                                    watch.ElapsedMilliseconds + " ms.");
            return prepared;
        }

        private string[] AsterMaxImportPreparedBrep(AsterMaxPreparedBrepVisualization prepared)
        {
            if (prepared == null) return null;
            try
            {
                if (!prepared.Success)
                {
                    string error = "AsterMax CAD parallel tessellation FAIL: " + Path.GetFileName(prepared.BrepFileName) +
                                   ": " + prepared.Error;
                    _errors.Add(error);
                    _form.WriteDataToOutput(error);
                    return null;
                }

                string[] addedPartNames = _model.ImportGeometryFromBrepFile(prepared.VisFileName, prepared.BrepFileName);
                if (addedPartNames == null || addedPartNames.Length == 0)
                {
                    string error = "AsterMax CAD parallel import EMPTY: " + Path.GetFileName(prepared.BrepFileName) + ".";
                    _errors.Add(error);
                    _form.WriteDataToOutput(error);
                    return null;
                }

                _form.WriteDataToOutput("AsterMax CAD parallel import PASS: " + Path.GetFileName(prepared.BrepFileName) +
                                        ", " + addedPartNames.Length + " pieza(s), VIS=" +
                                        prepared.VisualizationBytes + " bytes.");
                return addedPartNames;
            }
            finally
            {
                try
                {
                    if (!String.IsNullOrWhiteSpace(prepared.VisFileName) && File.Exists(prepared.VisFileName))
                        File.Delete(prepared.VisFileName);
                }
                catch (Exception ex)
                {
                    _form.WriteDataToOutput("AsterMax CAD parallel cleanup warning: " + ex.Message);
                }
            }
        }

'@
    $c=$c.Substring(0,$pos)+$helpers+$c.Substring($pos)
}

# Inject the preprocessing dictionary into ImportCADAssemblyFile and route only
# leaf BREPs through it. Compounds keep the existing recursive serial path.
$signature='        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)'
$start=$c.IndexOf($signature)
if($start -lt 0){throw 'C10.45 ImportCADAssemblyFile missing.'}
$brace=$c.IndexOf('{',$start)
$depth=0;$end=-1
for($n=$brace;$n -lt $c.Length;$n++){
    if($c[$n] -eq '{'){$depth++}
    elseif($c[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
}
if($end -lt 0){throw 'C10.45 ImportCADAssemblyFile closing brace missing.'}
$method=$c.Substring($start,$end-$start)

if(-not $method.Contains('asterMaxPreparedVisualizations')){
    $ifToken='            if (filesToImport != null)'
    $ifPos=$method.IndexOf($ifToken)
    if($ifPos -lt 0){
        $ifToken='                if (filesToImport != null)'
        $ifPos=$method.IndexOf($ifToken)
    }
    if($ifPos -lt 0){throw 'C10.45 filesToImport loop anchor missing.'}
    $indent=$ifToken.Substring(0,$ifToken.IndexOf('if'))
    $prep=$indent+'Dictionary<string, AsterMaxPreparedBrepVisualization> asterMaxPreparedVisualizations ='+"`n"+
          $indent+'    AsterMaxPrepareLeafBrepVisualizations(filesToImport);'+"`n"
    $method=$method.Substring(0,$ifPos)+$prep+$method.Substring($ifPos)

    $old='                            addedPartNames = ImportBrepPartFile(partFileName);'
    if(-not $method.Contains($old)){
        $old='                                addedPartNames = ImportBrepPartFile(partFileName);'
    }
    if(-not $method.Contains($old)){throw 'C10.45 leaf ImportBrepPartFile call missing.'}
    $leafIndent=$old.Substring(0,$old.IndexOf('addedPartNames'))
    $new=$leafIndent+'AsterMaxPreparedBrepVisualization asterMaxPrepared;'+"`n"+
         $leafIndent+'if (asterMaxPreparedVisualizations.TryGetValue(partFileName, out asterMaxPrepared))'+"`n"+
         $leafIndent+'    addedPartNames = AsterMaxImportPreparedBrep(asterMaxPrepared);'+"`n"+
         $leafIndent+'else'+"`n"+
         $leafIndent+'    addedPartNames = ImportBrepPartFile(partFileName);'
    $method=$method.Replace($old,$new)
    $c=$c.Substring(0,$start)+$method+$c.Substring($end)
}

Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.45: bounded parallel BREP->VIS preparation + serial model import applied.' -ForegroundColor Green
