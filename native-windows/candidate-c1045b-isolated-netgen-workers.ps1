param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.45b missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

function Replace-CSharpMethod([string]$text,[string]$signature,[string]$replacement){
  $start=$text.IndexOf($signature)
  if($start -lt 0){throw "C10.45b method missing: $signature"}
  $brace=$text.IndexOf('{',$start)
  if($brace -lt 0){throw "C10.45b opening brace missing: $signature"}
  $depth=0;$end=-1
  for($n=$brace;$n -lt $text.Length;$n++){
    if($text[$n] -eq '{'){$depth++}
    elseif($text[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
  }
  if($end -lt 0){throw "C10.45b closing brace missing: $signature"}
  return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

$prepare=@'
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

            // NetGenMesher is not treated as re-entrant inside a shared working directory.
            // Give every external process its own scratch directory while keeping BREP/VIS
            // paths absolute. This isolates fixed-name temporary files used internally.
            string processWorkDirectory = Path.Combine(workDirectory,
                "AsterMaxVis_" + Guid.NewGuid().ToString("N"));
            try
            {
                Directory.CreateDirectory(processWorkDirectory);
                var psi = new System.Diagnostics.ProcessStartInfo();
                psi.CreateNoWindow = true;
                psi.FileName = executable;
                psi.Arguments = argument;
                psi.WorkingDirectory = processWorkDirectory;
                psi.UseShellExecute = false;
                psi.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
                using (var process = new System.Diagnostics.Process())
                {
                    process.StartInfo = psi;
                    process.Start();
                    if (!process.WaitForExit(180000))
                    {
                        try { process.Kill(); } catch { }
                        result.Error = "NetGen preview timed out after 180 s.";
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
            finally
            {
                try
                {
                    if (Directory.Exists(processWorkDirectory))
                        Directory.Delete(processWorkDirectory, true);
                }
                catch { }
            }
        }
'@
$c=Replace-CSharpMethod $c '        private AsterMaxPreparedBrepVisualization AsterMaxPrepareBrepVisualization(string brepFileName,' $prepare

# Conservative default: two isolated external processes. Advanced users/tests can
# request up to four; higher fan-out is deliberately blocked until separately proven.
$c=$c.Replace('int workers = Math.Min(4, Math.Max(1, Environment.ProcessorCount));',
              'int workers = Math.Min(2, Math.Max(1, Environment.ProcessorCount));')
$c=$c.Replace('workers = Math.Max(1, Math.Min(8, configuredWorkers));',
              'workers = Math.Max(1, Math.Min(4, configuredWorkers));')
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.45b: isolated NetGen scratch directories + conservative worker cap applied.' -ForegroundColor Green
