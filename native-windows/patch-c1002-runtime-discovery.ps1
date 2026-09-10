param([string]$Root)
$ErrorActionPreference='Stop'

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.02 requires C10.01 first.' }
$s=Get-Content $solvePath -Raw

# Remove mandatory environment-only Python configuration. Prefer packaged runtime, then explicit env.
$old=@'
            PostprocessorExecutable=Environment.GetEnvironmentVariable("ASTERMAX_PYTHON");
            if(String.IsNullOrWhiteSpace(PostprocessorExecutable) || !File.Exists(PostprocessorExecutable))
                Fail("Python postprocess runtime is not configured. Set ASTERMAX_PYTHON to a validated python.exe with numpy+h5py.");

            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
'@
$new=@'
            PostprocessorExecutable=ResolvePythonRuntime();
            if(String.IsNullOrWhiteSpace(PostprocessorExecutable))
                Fail("No validated Python postprocess runtime found. Package AsterMaxRuntime\\Python\\python.exe or set ASTERMAX_PYTHON.");

            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
'@
if(-not $s.Contains('ResolvePythonRuntime()')){
  if(-not $s.Contains($old)){ throw 'C10.02 Python runtime anchor missing.' }
  $s=$s.Replace($old,$new)
}

$anchor='        private ProcessStartInfo CreatePythonProcess(string python,string arguments)'
if(-not $s.Contains('private string ResolvePythonRuntime()')){
$helpers=@'
        private string ResolvePythonRuntime()
        {
            string packaged=Path.Combine(Application.StartupPath,"AsterMaxRuntime","Python","python.exe");
            if(File.Exists(packaged)) return packaged;
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_PYTHON");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            return null;
        }

        private string ResolveCodeAsterRunner()
        {
            string packaged=Path.Combine(Application.StartupPath,"AsterMaxRuntime","CodeAster","astermax-codeaster-runner.cmd");
            if(File.Exists(packaged)) return packaged;
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            return null;
        }

        public JObject RuntimeDiagnostic()
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
  if(-not $s.Contains($anchor)){ throw 'C10.02 helper anchor missing.' }
  $s=$s.Replace($anchor,$helpers+$anchor)
}

# C10.00 runner resolution: use packaged runtime first, explicit env second.
$s=$s.Replace('string runner=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");','string runner=ResolveCodeAsterRunner();')
$s=$s.Replace('Fail("Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to an executable path.");','Fail("Code_Aster runner is not available. Package AsterMaxRuntime\\CodeAster\\astermax-codeaster-runner.cmd or set ASTERMAX_CODE_ASTER_RUNNER.");')

Set-Content $solvePath $s -Encoding UTF8
Write-Host 'C10.02 portable runtime discovery injected.' -ForegroundColor Green
