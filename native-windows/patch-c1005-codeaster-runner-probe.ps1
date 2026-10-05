param([string]$Root)
$ErrorActionPreference='Stop'

# C10.05 — packaged Windows->WSL Code_Aster runner adapter plus a real backend probe.
# A runner file existing is no longer enough: Solve is READY only when the adapter proves
# that a genuine as_run executable is available behind WSL. No synthetic solver fallback.

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.05 requires C10.03/C10.04 native solve chain first.' }
$s=Get-Content $solvePath -Raw

# Batch/PowerShell runner files are scripts, not Win32 executables. Route them through the
# appropriate host while preserving redirected evidence logs.
$old=@'
            var psi=new ProcessStartInfo
            {
                FileName=RunnerExecutable,
                Arguments=Quote(ExportFile)+" "+Quote(Workspace),
                WorkingDirectory=Workspace,
                UseShellExecute=false,
                CreateNoWindow=true,
                RedirectStandardOutput=true,
                RedirectStandardError=true
            };
'@
$new=@'
            var psi=CreateRunnerProcess(RunnerExecutable,Quote(ExportFile)+" "+Quote(Workspace),Workspace);
'@
if(-not $s.Contains($old)){ throw 'C10.05 runner ProcessStartInfo anchor missing.' }
$s=$s.Replace($old,$new)

$anchor='        private static string ResolvePythonRuntime()'
if(-not $s.Contains('private static JObject ProbeCodeAsterRunner(string runner)')){
$helpers=@'
        private static ProcessStartInfo CreateRunnerProcess(string runner,string arguments,string workingDirectory)
        {
            if(String.IsNullOrWhiteSpace(runner)) throw new ArgumentNullException("runner");
            string ext=Path.GetExtension(runner).ToLowerInvariant();
            ProcessStartInfo psi=new ProcessStartInfo();
            if(ext==".cmd" || ext==".bat")
            {
                psi.FileName=Environment.GetEnvironmentVariable("COMSPEC") ?? "cmd.exe";
                psi.Arguments="/d /s /c \"call "+Quote(runner)+" "+arguments+"\"";
            }
            else if(ext==".ps1")
            {
                string host=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),
                                         "WindowsPowerShell","v1.0","powershell.exe");
                psi.FileName=File.Exists(host)?host:"powershell.exe";
                psi.Arguments="-NoLogo -NoProfile -ExecutionPolicy Bypass -File "+Quote(runner)+" "+arguments;
            }
            else
            {
                psi.FileName=runner;
                psi.Arguments=arguments;
            }
            psi.WorkingDirectory=String.IsNullOrWhiteSpace(workingDirectory)?Application.StartupPath:workingDirectory;
            psi.UseShellExecute=false;
            psi.CreateNoWindow=true;
            psi.RedirectStandardOutput=true;
            psi.RedirectStandardError=true;
            return psi;
        }

        private static JObject ProbeCodeAsterRunner(string runner)
        {
            JObject p=new JObject
            {
                ["schema"]="astermax-codeaster-runner-probe/v1",
                ["ready"]=false,
                ["runner"]=runner,
                ["exit_code"]=JValue.CreateNull(),
                ["stdout"]="",
                ["stderr"]=""
            };
            if(String.IsNullOrWhiteSpace(runner) || !File.Exists(runner)) return p;
            try
            {
                using(Process process=Process.Start(CreateRunnerProcess(runner,"probe",Application.StartupPath)))
                {
                    string stdout=process.StandardOutput.ReadToEnd();
                    string stderr=process.StandardError.ReadToEnd();
                    if(!process.WaitForExit(15000))
                    {
                        try { process.Kill(); } catch { }
                        p["stderr"]="Runner probe timed out after 15 seconds.";
                        return p;
                    }
                    p["exit_code"]=process.ExitCode;
                    p["stdout"]=stdout==null?"":stdout.Trim();
                    p["stderr"]=stderr==null?"":stderr.Trim();
                    p["ready"]=process.ExitCode==0;
                }
            }
            catch(Exception ex)
            {
                p["stderr"]=ex.GetType().Name+": "+ex.Message;
            }
            return p;
        }

'@
  if(-not $s.Contains($anchor)){ throw 'C10.05 runtime helper anchor missing.' }
  $s=$s.Replace($anchor,$helpers+$anchor)
}

$old=@'
        public static JObject RuntimeDiagnostic()
        {
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            return new JObject
            {
                ["runtime_contract"]="ASTERMAX_C1002_PORTABLE_RUNTIME_V1",
                ["python_ready"]=!String.IsNullOrWhiteSpace(python),
                ["python_source"]=String.IsNullOrWhiteSpace(python)?"missing":(python.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),
                ["code_aster_runner_ready"]=!String.IsNullOrWhiteSpace(runner),
                ["code_aster_runner_source"]=String.IsNullOrWhiteSpace(runner)?"missing":(runner.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),
                ["unit_contract"]="MM_N_S_MPA",
                ["synthetic_results_allowed"]=false
            };
        }
'@
$new=@'
        public static JObject RuntimeDiagnostic()
        {
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            JObject runnerProbe=ProbeCodeAsterRunner(runner);
            return new JObject
            {
                ["runtime_contract"]="ASTERMAX_C1005_REAL_BACKEND_PROBE_V1",
                ["python_ready"]=!String.IsNullOrWhiteSpace(python),
                ["python_source"]=String.IsNullOrWhiteSpace(python)?"missing":(python.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),
                ["code_aster_runner_ready"]=!String.IsNullOrWhiteSpace(runner),
                ["code_aster_runner_source"]=String.IsNullOrWhiteSpace(runner)?"missing":(runner.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),
                ["code_aster_backend_ready"]=(bool)runnerProbe["ready"],
                ["code_aster_runner_probe"]=runnerProbe,
                ["unit_contract"]="MM_N_S_MPA",
                ["synthetic_results_allowed"]=false
            };
        }
'@
if(-not $s.Contains($old)){ throw 'C10.05 RuntimeDiagnostic anchor missing.' }
$s=$s.Replace($old,$new)

$old=@'
            d["runtime_ready"]=!String.IsNullOrWhiteSpace(python) &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               File.Exists(bridge) && File.Exists(binder);
'@
$new=@'
            d["runtime_ready"]=!String.IsNullOrWhiteSpace(python) &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               (bool)d["code_aster_backend_ready"] &&
                               File.Exists(bridge) && File.Exists(binder);
'@
if(-not $s.Contains($old)){ throw 'C10.05 RequireRuntimeReady anchor missing.' }
$s=$s.Replace($old,$new)

$old='                d["runtime_ready"]=(bool)d["python_ready"] && (bool)d["code_aster_runner_ready"] &&'
$new='                d["runtime_ready"]=(bool)d["python_ready"] && (bool)d["code_aster_runner_ready"] && (bool)d["code_aster_backend_ready"] &&'
if(-not $s.Contains($old)){ throw 'C10.05 visible preflight anchor missing.' }
$s=$s.Replace($old,$new)

# Avoid pinning the export profile to an obsolete solver version; let the validated installation
# resolve its stable version. The packaged runner rewrites only the transport-neutral /analysis/ paths.
$s=$s.Replace('P version 15.2\n','P version stable\n')
$s=$s.Replace('["release"]="C10.00"','["release"]="C10.05"')
Set-Content $solvePath $s -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $uiPath -Raw
$u=$u.Replace('Code_Aster | native solve','Code_Aster | WSL verified solve')
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.05 genuine Code_Aster backend probe and script-runner host injected.' -ForegroundColor Green
