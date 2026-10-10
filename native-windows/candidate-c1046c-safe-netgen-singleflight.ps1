param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.46c missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

function Replace-CSharpMethod([string]$text,[string]$signature,[string]$replacement){
  $start=$text.IndexOf($signature)
  if($start -lt 0){throw "C10.46c method missing: $signature"}
  $brace=$text.IndexOf('{',$start)
  if($brace -lt 0){throw "C10.46c opening brace missing: $signature"}
  $depth=0;$end=-1
  for($n=$brace;$n -lt $text.Length;$n++){
    if($text[$n] -eq '{'){$depth++}
    elseif($text[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
  }
  if($end -lt 0){throw "C10.46c closing brace missing: $signature"}
  return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

# Windows GitHub evidence shows that two concurrent NetGenMesher BREP_VISUALIZATION
# processes hang even on a 25-body analytic STEP, while the same path with one
# worker completes. Until a batch/persistent NetGen interface is proven safe,
# keep external visualization conversion single-flight. Model/VTK mutation was
# already serial and remains unchanged.
$method=@'
        private Dictionary<string, AsterMaxPreparedBrepVisualization> AsterMaxPrepareLeafBrepVisualizations(string[] filesToImport)
        {
            var prepared = new Dictionary<string, AsterMaxPreparedBrepVisualization>(StringComparer.OrdinalIgnoreCase);
            if (filesToImport == null || filesToImport.Length == 0) return prepared;
            if (!_asterMaxCadVisualizationDeflectionOverride.HasValue) return prepared;

            string[] leaves = filesToImport.Where(fileName =>
                !String.IsNullOrWhiteSpace(fileName) &&
                !fileName.ToLowerInvariant().Contains("compound")).ToArray();
            if (leaves.Length < 8) return prepared;

            int requestedWorkers = 1;
            string workerText = Environment.GetEnvironmentVariable("ASTERMAX_CAD_TESSELLATION_WORKERS");
            int configuredWorkers;
            if (!String.IsNullOrWhiteSpace(workerText) && Int32.TryParse(workerText, out configuredWorkers) && configuredWorkers > 0)
                requestedWorkers = configuredWorkers;
            int workers = 1;
            if (requestedWorkers > 1)
                _form.WriteDataToOutput("AsterMax CAD NetGen concurrency disabled: requested " + requestedWorkers +
                                        " worker(s), effective 1 after Windows timeout qualification.");

            string executable = Application.StartupPath + Globals.NetGenMesher;
            string workDirectory = _settings.Calculix.WorkDirectory;
            double deflection = _asterMaxCadVisualizationDeflectionOverride.Value;

            var watch = System.Diagnostics.Stopwatch.StartNew();
            foreach (string brepFileName in leaves)
                prepared[brepFileName] = AsterMaxPrepareBrepVisualization(brepFileName, executable, workDirectory, deflection);
            watch.Stop();

            int successCount = prepared.Values.Count(item => item != null && item.Success);
            _form.WriteDataToOutput("AsterMax CAD single-flight preview: " + successCount + "/" + leaves.Length +
                                    " VIS preparados con " + workers + " worker en " +
                                    watch.ElapsedMilliseconds + " ms; BREP exacto conservado.");
            return prepared;
        }
'@
$c=Replace-CSharpMethod $c '        private Dictionary<string, AsterMaxPreparedBrepVisualization> AsterMaxPrepareLeafBrepVisualizations(string[] filesToImport)' $method
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.46c: unsafe concurrent NetGen preview disabled; external BREP->VIS preparation is single-flight.' -ForegroundColor Green
