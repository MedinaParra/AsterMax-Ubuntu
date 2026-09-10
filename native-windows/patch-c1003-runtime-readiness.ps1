param([string]$Root)
$ErrorActionPreference='Stop'

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.03 requires C10.02 first.' }
$s=Get-Content $solvePath -Raw

# Fix the actual runner resolution site left untouched by C10.02.
$s=$s.Replace(
'            RunnerExecutable=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");',
'            RunnerExecutable=ResolveCodeAsterRunner();')

$s=$s.Replace('        private string ResolvePythonRuntime()','        private static string ResolvePythonRuntime()')
$s=$s.Replace('        private string ResolveCodeAsterRunner()','        private static string ResolveCodeAsterRunner()')
$s=$s.Replace('        public JObject RuntimeDiagnostic()','        public static JObject RuntimeDiagnostic()')

$anchor='        private ProcessStartInfo CreatePythonProcess(string python,string arguments)'
if(-not $s.Contains('public static JObject RequireRuntimeReady()')){
$gate=@'
        public static JObject RequireRuntimeReady()
        {
            string python=ResolvePythonRuntime();
            string runner=ResolveCodeAsterRunner();
            string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
            string bridge=Path.Combine(tools,"bridge-c964-med-results.py");
            string binder=Path.Combine(tools,"bind-c998-results-fingerprint.py");

            JObject d=RuntimeDiagnostic();
            d["bridge_ready"]=File.Exists(bridge);
            d["binder_ready"]=File.Exists(binder);
            d["runtime_ready"]=!String.IsNullOrWhiteSpace(python) &&
                               !String.IsNullOrWhiteSpace(runner) &&
                               File.Exists(bridge) && File.Exists(binder);
            d["solver_backend"]="Code_Aster";
            d["postprocess_backend"]="MED -> AsterMax bundle -> VTK";
            d["fea_values_invented"]=false;

            if((bool)d["runtime_ready"]==false)
                throw new InvalidOperationException(
                    "Runtime preflight BLOCKED. "+d.ToString(Formatting.None));
            return d;
        }

'@
  if(-not $s.Contains($anchor)){ throw 'C10.03 helper anchor missing.' }
  $s=$s.Replace($anchor,$gate+$anchor)
}

$solveAnchor='                if(_controller==null || _controller.Model==null) throw new InvalidOperationException("No active FeModel is available.");'
if(-not $s.Contains('AsterMaxNativeSolveTransaction.RequireRuntimeReady();')){
  if(-not $s.Contains($solveAnchor)){ throw 'C10.03 Run Solve anchor missing.' }
  $s=$s.Replace($solveAnchor,$solveAnchor+[Environment]::NewLine+
'                AsterMaxNativeSolveTransaction.RequireRuntimeReady();')
}

$frmAnchor='        private void RunAsterMaxNativeSolve()'
if(-not $s.Contains('private void ShowAsterMaxRuntimePreflight()')){
$method=@'
        private void ShowAsterMaxRuntimePreflight()
        {
            try
            {
                JObject d=AsterMaxNativeSolveTransaction.RuntimeDiagnostic();
                string tools=Path.Combine(Application.StartupPath,"AsterMaxTools");
                d["bridge_ready"]=File.Exists(Path.Combine(tools,"bridge-c964-med-results.py"));
                d["binder_ready"]=File.Exists(Path.Combine(tools,"bind-c998-results-fingerprint.py"));
                d["runtime_ready"]=(bool)d["python_ready"] && (bool)d["code_aster_runner_ready"] &&
                                   (bool)d["bridge_ready"] && (bool)d["binder_ready"];
                MessageBox.Show(this,d.ToString(Formatting.Indented),
                    "AsterMax Runtime Preflight",MessageBoxButtons.OK,
                    (bool)d["runtime_ready"]?MessageBoxIcon.Information:MessageBoxIcon.Warning);
            }
            catch(Exception ex)
            {
                CaeGlobals.MessageBoxes.ShowError("Runtime preflight failed: "+ex.Message);
            }
        }

'@
  if(-not $s.Contains($frmAnchor)){ throw 'C10.03 FrmMain anchor missing.' }
  $s=$s.Replace($frmAnchor,$method+$frmAnchor)
}

Set-Content $solvePath $s -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $uiPath -Raw
if(-not $u.Contains('CommandTile("Runtime", "PREFLIGHT"')){
  $solveTile='                CommandTile("Solve", "CODE_ASTER", () => RunAsterMaxNativeSolve(), true),'
  if(-not $u.Contains($solveTile)){ throw 'C10.03 Solve tile anchor missing.' }
  $u=$u.Replace($solveTile,
    '                CommandTile("Runtime", "PREFLIGHT", () => ShowAsterMaxRuntimePreflight(), true),'+[Environment]::NewLine+$solveTile)
  Set-Content $uiPath $u -Encoding UTF8
}

Write-Host 'C10.03 strict runtime readiness preflight injected.' -ForegroundColor Green
