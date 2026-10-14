param([string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.56 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

function Replace-CSharpMethod([string]$text,[string]$signature,[string]$replacement){
  $start=$text.IndexOf($signature)
  if($start -lt 0){throw "C10.56 method missing: $signature"}
  $brace=$text.IndexOf('{',$start)
  if($brace -lt 0){throw "C10.56 opening brace missing: $signature"}
  $depth=0;$end=-1
  for($n=$brace;$n -lt $text.Length;$n++){
    if($text[$n] -eq '{'){$depth++}
    elseif($text[$n] -eq '}'){$depth--;if($depth -eq 0){$end=$n+1;break}}
  }
  if($end -lt 0){throw "C10.56 closing brace missing: $signature"}
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
            string processWorkDirectory = Path.Combine(workDirectory,
                "AsterMaxVis_" + Guid.NewGuid().ToString("N"));
            var watch = System.Diagnostics.Stopwatch.StartNew();
            string stdout = "";
            string stderr = "";
            int? exitCode = null;
            string failureKind = null;
            try
            {
                Directory.CreateDirectory(processWorkDirectory);
                _form.WriteDataToOutput("AsterMax CAD NetGen diagnostic: exe=\"" + executable +
                                        "\"; args=" + argument +
                                        "; cwd=\"" + processWorkDirectory + "\"; brep=\"" + brepFileName +
                                        "\"; brepExists=" + File.Exists(brepFileName) +
                                        "; brepBytes=" + (File.Exists(brepFileName) ? new FileInfo(brepFileName).Length.ToString() : "0") +
                                        "; vis=\"" + result.VisFileName + "\".");
                var psi = new System.Diagnostics.ProcessStartInfo();
                psi.CreateNoWindow = true;
                psi.FileName = executable;
                psi.Arguments = argument;
                psi.WorkingDirectory = processWorkDirectory;
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
                using (var process = new System.Diagnostics.Process())
                {
                    process.StartInfo = psi;
                    process.Start();
                    var stdoutTask = process.StandardOutput.ReadToEndAsync();
                    var stderrTask = process.StandardError.ReadToEndAsync();
                    if (!process.WaitForExit(180000))
                    {
                        failureKind = "TIMEOUT";
                        try { process.Kill(); process.WaitForExit(5000); }
                        catch (Exception killEx) { _form.WriteDataToOutput("AsterMax CAD NetGen shutdown warning: " + killEx.Message); }
                        result.Error = "NetGen preview timed out after 180 s.";
                    }
                    else
                    {
                        exitCode = process.ExitCode;
                        stdout = stdoutTask.GetAwaiter().GetResult();
                        stderr = stderrTask.GetAwaiter().GetResult();
                        if (process.ExitCode != 0)
                        {
                            failureKind = "NON_ZERO_EXIT";
                            result.Error = "NetGen preview exit code " + process.ExitCode + ".";
                        }
                    }
                }
                if (failureKind == null && (!File.Exists(result.VisFileName) || new FileInfo(result.VisFileName).Length == 0))
                {
                    failureKind = "ZERO_EXIT_MISSING_OUTPUT";
                    result.Error = "Visualization file is missing or empty.";
                }
                if (failureKind == null)
                {
                    result.VisualizationBytes = new FileInfo(result.VisFileName).Length;
                    result.Success = true;
                    return result;
                }
                return result;
            }
            catch (Exception ex)
            {
                failureKind = "PROCESS_START_OR_RUNTIME_EXCEPTION";
                result.Error = ex.GetType().Name + ": " + ex.Message;
                return result;
            }
            finally
            {
                watch.Stop();
                if (!result.Success)
                {
                    string auditRoot = Path.Combine(Application.StartupPath, "Audit", "NetGenFailures");
                    string auditDir = Path.Combine(auditRoot, DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff") + "_" + result.JobName);
                    try
                    {
                        Directory.CreateDirectory(auditDir);
                        string snapshotDir = Path.Combine(auditDir, "scratch");
                        if (Directory.Exists(processWorkDirectory))
                        {
                            Directory.CreateDirectory(snapshotDir);
                            foreach (string sourceFile in Directory.GetFiles(processWorkDirectory, "*", SearchOption.AllDirectories))
                            {
                                string relative = sourceFile.Substring(processWorkDirectory.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                                string targetFile = Path.Combine(snapshotDir, relative);
                                Directory.CreateDirectory(Path.GetDirectoryName(targetFile));
                                File.Copy(sourceFile, targetFile, true);
                            }
                        }
                        File.WriteAllText(Path.Combine(auditDir, "stdout.txt"), stdout ?? "");
                        File.WriteAllText(Path.Combine(auditDir, "stderr.txt"), stderr ?? "");
                        string diagnostic =
                            "failureKind=" + (failureKind ?? "UNKNOWN") + Environment.NewLine +
                            "executable=" + executable + Environment.NewLine +
                            "arguments=" + argument + Environment.NewLine +
                            "workingDirectory=" + processWorkDirectory + Environment.NewLine +
                            "brep=" + brepFileName + Environment.NewLine +
                            "brepExists=" + File.Exists(brepFileName) + Environment.NewLine +
                            "brepBytes=" + (File.Exists(brepFileName) ? new FileInfo(brepFileName).Length.ToString() : "0") + Environment.NewLine +
                            "exitCode=" + (exitCode.HasValue ? exitCode.Value.ToString() : "NOT_AVAILABLE") + Environment.NewLine +
                            "elapsedMilliseconds=" + watch.ElapsedMilliseconds + Environment.NewLine +
                            "vis=" + result.VisFileName + Environment.NewLine +
                            "visExists=" + File.Exists(result.VisFileName) + Environment.NewLine +
                            "visBytes=" + (File.Exists(result.VisFileName) ? new FileInfo(result.VisFileName).Length.ToString() : "0") + Environment.NewLine;
                        File.WriteAllText(Path.Combine(auditDir, "diagnostic.txt"), diagnostic);
                        _form.WriteDataToOutput("AsterMax CAD NetGen FAIL [" + (failureKind ?? "UNKNOWN") + "]: " + result.Error +
                                                " Diagnostic preserved at \"" + auditDir + "\".");
                        if (!String.IsNullOrWhiteSpace(stderr))
                            _form.WriteDataToOutput("AsterMax CAD NetGen stderr: " + stderr.Trim());
                    }
                    catch (Exception auditEx)
                    {
                        _form.WriteDataToOutput("AsterMax CAD NetGen audit warning: " + auditEx.Message);
                    }
                }
                try
                {
                    if (Directory.Exists(processWorkDirectory)) Directory.Delete(processWorkDirectory, true);
                }
                catch (Exception cleanupEx)
                {
                    _form.WriteDataToOutput("AsterMax CAD NetGen cleanup warning: " + cleanupEx.Message);
                }
            }
        }
'@
$c=Replace-CSharpMethod $c '        private AsterMaxPreparedBrepVisualization AsterMaxPrepareBrepVisualization(string brepFileName,' $prepare
Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.56: NetGen failure classification, stdout/stderr capture and preserved audit evidence applied.' -ForegroundColor Green
