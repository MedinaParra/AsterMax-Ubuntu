param([string]$Root)
$ErrorActionPreference='Stop'

# C10.06 — Python MED postprocess capability gate.
# Existence of python.exe is not sufficient: the exact runtime must execute and import
# numpy + h5py before Solve is admitted. No dependency is mocked and no result is synthesized.

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.06 requires C10.05 first.' }
$s=Get-Content $solvePath -Raw

# Add PATH fallback only after packaged and explicit runtimes. The capability probe below
# rejects aliases/stubs/broken installations and runtimes missing numpy or h5py.
$old=@'
        private static string ResolvePythonRuntime()
        {
            string packaged=Path.Combine(Application.StartupPath,"AsterMaxRuntime","Python","python.exe");
            if(File.Exists(packaged)) return packaged;
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_PYTHON");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            return null;
        }
'@
$new=@'
        private static string ResolvePythonRuntime()
        {
            string packaged=Path.Combine(Application.StartupPath,"AsterMaxRuntime","Python","python.exe");
            if(File.Exists(packaged)) return packaged;
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_PYTHON");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            string path=Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach(string raw in path.Split(Path.PathSeparator))
            {
                string dir=(raw??"").Trim().Trim('"');
                if(String.IsNullOrWhiteSpace(dir)) continue;
                try
                {
                    string candidate=Path.Combine(dir,"python.exe");
                    if(File.Exists(candidate)) return candidate;
                }
                catch { }
            }
            return null;
        }
'@
if(-not $s.Contains($old)){ throw 'C10.06 ResolvePythonRuntime anchor missing.' }
$s=$s.Replace($old,$new)

$anchor='        private static JObject ProbeCodeAsterRunner(string runner)'
if(-not $s.Contains('private static JObject ProbePythonRuntime(string python)')){
$helper=@'
        private static JObject ProbePythonRuntime(string python)
        {
            JObject p=new JObject
            {
                ["schema"]="astermax-python-med-probe/v1",
                ["ready"]=false,
                ["python"]=python,
                ["exit_code"]=JValue.CreateNull(),
                ["stdout"]="",
                ["stderr"]="",
                ["required_modules"]=new JArray("numpy","h5py")
            };
            if(String.IsNullOrWhiteSpace(python) || !File.Exists(python)) return p;
            try
            {
                string code="import sys,numpy,h5py; print('ASTERMAX_PYTHON_MED_OK|'+sys.version.split()[0]+'|numpy='+numpy.__version__+'|h5py='+h5py.__version__)";
                ProcessStartInfo psi=new ProcessStartInfo
                {
                    FileName=python,
                    Arguments="-c "+Quote(code),
                    WorkingDirectory=Application.StartupPath,
                    UseShellExecute=false,
                    CreateNoWindow=true,
                    RedirectStandardOutput=true,
                    RedirectStandardError=true
                };
                using(Process process=Process.Start(psi))
                {
                    string stdout=process.StandardOutput.ReadToEnd();
                    string stderr=process.StandardError.ReadToEnd();
                    if(!process.WaitForExit(15000))
                    {
                        try { process.Kill(); } catch { }
                        p["stderr"]="Python capability probe timed out after 15 seconds.";
                        return p;
                    }
                    p["exit_code"]=process.ExitCode;
                    p["stdout"]=stdout==null?"":stdout.Trim();
                    p["stderr"]=stderr==null?"":stderr.Trim();
                    p["ready"]=process.ExitCode==0 &&
                               stdout!=null &&
                               stdout.IndexOf("ASTERMAX_PYTHON_MED_OK|",StringComparison.Ordinal)>=0;
                }
            }
            catch(Exception ex)
            {
                p["stderr"]=ex.GetType().Name+": "+ex.Message;
            }
            return p;
        }

'@
  if(-not $s.Contains($anchor)){ throw 'C10.06 Python probe insertion anchor missing.' }
  $s=$s.Replace($anchor,$helper+$anchor)
}

$old=@'
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            JObject runnerProbe=ProbeCodeAsterRunner(runner);
            return new JObject
            {
                ["runtime_contract"]="ASTERMAX_C1005_REAL_BACKEND_PROBE_V1",
                ["python_ready"]=!String.IsNullOrWhiteSpace(python),
                ["python_source"]=String.IsNullOrWhiteSpace(python)?"missing":(python.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),
'@
$new=@'
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            JObject pythonProbe=ProbePythonRuntime(python);
            JObject runnerProbe=ProbeCodeAsterRunner(runner);
            return new JObject
            {
                ["runtime_contract"]="ASTERMAX_C1006_FULL_RUNTIME_PROBE_V1",
                ["python_executable_found"]=!String.IsNullOrWhiteSpace(python),
                ["python_ready"]=(bool)pythonProbe["ready"],
                ["python_source"]=String.IsNullOrWhiteSpace(python)?"missing":(python.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":(!String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("ASTERMAX_PYTHON"))?"environment":"path")),
                ["python_probe"]=pythonProbe,
'@
if(-not $s.Contains($old)){ throw 'C10.06 RuntimeDiagnostic Python anchor missing.' }
$s=$s.Replace($old,$new)

$old=@'
            d["runtime_ready"]=!String.IsNullOrWhiteSpace(python) &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               (bool)d["code_aster_backend_ready"] &&
                               File.Exists(bridge) && File.Exists(binder);
'@
$new=@'
            d["runtime_ready"]=(bool)d["python_ready"] &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               (bool)d["code_aster_backend_ready"] &&
                               File.Exists(bridge) && File.Exists(binder);
'@
if(-not $s.Contains($old)){ throw 'C10.06 RequireRuntimeReady Python anchor missing.' }
$s=$s.Replace($old,$new)

# Recheck at the postprocess boundary in case the interpreter/modules changed after preflight.
$old=@'
            PostprocessorExecutable=ResolvePythonRuntime();
            if(String.IsNullOrWhiteSpace(PostprocessorExecutable))
                Fail("No validated Python postprocess runtime found. Package AsterMaxRuntime\\Python\\python.exe or set ASTERMAX_PYTHON.");

            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
'@
$new=@'
            PostprocessorExecutable=ResolvePythonRuntime();
            JObject pythonProbe=ProbePythonRuntime(PostprocessorExecutable);
            if(PostprocessorExecutable==null || (bool)pythonProbe["ready"]==false)
                Fail("Python MED postprocess runtime is not ready. AsterMax requires a real Python runtime with numpy+h5py. "+pythonProbe.ToString(Formatting.None));

            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
'@
if(-not $s.Contains($old)){ throw 'C10.06 postprocess Python gate anchor missing.' }
$s=$s.Replace($old,$new)

$s=$s.Replace('["release"]="C10.05"','["release"]="C10.06"')
Set-Content $solvePath $s -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $uiPath -Raw
$u=$u.Replace('Code_Aster | WSL verified solve','Code_Aster | verified runtime + MED')
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.06 Python numpy+h5py MED capability probe injected.' -ForegroundColor Green
