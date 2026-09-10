param([string]$Root)
$ErrorActionPreference='Stop'

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solvePath)){ throw 'C10.01 requires C10.00 native solve transaction first.' }
$s=Get-Content $solvePath -Raw

$s=$s.Replace(
'internal enum AsterMaxSolveState { Idle, Preparing, ReadyToRun, Running, SolutionCurrent, SolutionStale, Failed }',
'internal enum AsterMaxSolveState { Idle, Preparing, ReadyToRun, Running, Postprocessing, SolutionCurrent, SolutionStale, Failed }')

if(-not $s.Contains('public string ResultBundleFile { get; private set; }')){
  $anchor='        public string MedFile { get; private set; }'
  if(-not $s.Contains($anchor)){ throw 'C10.01 MED property anchor missing.' }
  $insert=$anchor+[Environment]::NewLine+
'        public string ResultBundleFile { get; private set; }'+[Environment]::NewLine+
'        public string ResultVtuFile { get; private set; }'+[Environment]::NewLine+
'        public string PostprocessorExecutable { get; private set; }'+[Environment]::NewLine+
'        public int? PostprocessorExitCode { get; private set; }'
  $s=$s.Replace($anchor,$insert)
}

if(-not $s.Contains('tx.ResultBundleFile=Path.Combine(txDir,safe+".astermax-results.json");')){
  $anchor='            tx.MedFile=Path.Combine(txDir,safe+".rmed");'
  if(-not $s.Contains($anchor)){ throw 'C10.01 result path anchor missing.' }
  $insert=$anchor+[Environment]::NewLine+
'            tx.ResultBundleFile=Path.Combine(txDir,safe+".astermax-results.json");'+[Environment]::NewLine+
'            tx.ResultVtuFile=Path.Combine(txDir,safe+".astermax-results.vtu");'
  $s=$s.Replace($anchor,$insert)
}

$s=$s.Replace(
'["expected_med_file"]=safe+".rmed",',
'["expected_med_file"]=safe+".rmed",'+[Environment]::NewLine+
'                ["expected_results_bundle"]=safe+".astermax-results.json",'+[Environment]::NewLine+
'                ["expected_results_vtu"]=safe+".astermax-results.vtu",'+[Environment]::NewLine+
'                ["postprocessor_contract"]="ASTERMAX_MED_POSTPROCESSOR <med> <fingerprint> <bundle> <vtu>",')

$old=@'
            RequireUnchangedModel(liveModel);
            State=AsterMaxSolveState.SolutionCurrent;
            Message="SOLUTION_CURRENT: real solver evidence accepted. MED postprocess bridge is the next transaction stage.";
            WriteFinalState();
        }

        public void RequireUnchangedModel(CaeModel.FeModel liveModel)
'@

$new=@'
            RequireUnchangedModel(liveModel);
            State=AsterMaxSolveState.Postprocessing;
            Message="Code_Aster evidence accepted; waiting for verified MED postprocess handoff.";
            WriteFinalState();
        }

        public AsterMaxResultsBundle CompleteVerifiedResultsHandoff(CaeModel.FeModel liveModel)
        {
            if(State!=AsterMaxSolveState.Postprocessing)
                throw new InvalidOperationException("Solve transaction is not ready for postprocess handoff.");

            RequireUnchangedModel(liveModel);
            PostprocessorExecutable=Environment.GetEnvironmentVariable("ASTERMAX_MED_POSTPROCESSOR");
            if(String.IsNullOrWhiteSpace(PostprocessorExecutable) || !File.Exists(PostprocessorExecutable))
                Fail("MED postprocessor is not configured. Set ASTERMAX_MED_POSTPROCESSOR to a validated executable/script.");

            var psi=new ProcessStartInfo
            {
                FileName=PostprocessorExecutable,
                Arguments=Quote(MedFile)+" "+Quote(FrozenFingerprint)+" "+Quote(ResultBundleFile)+" "+Quote(ResultVtuFile),
                WorkingDirectory=Workspace,
                UseShellExecute=false,
                CreateNoWindow=true,
                RedirectStandardOutput=true,
                RedirectStandardError=true
            };
            using(var p=Process.Start(psi))
            {
                string stdout=p.StandardOutput.ReadToEnd();
                string stderr=p.StandardError.ReadToEnd();
                p.WaitForExit();
                PostprocessorExitCode=p.ExitCode;
                File.WriteAllText(Path.Combine(Workspace,"ASTERMAX_POSTPROCESS_STDOUT.log"),stdout,new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(Workspace,"ASTERMAX_POSTPROCESS_STDERR.log"),stderr,new UTF8Encoding(false));
            }

            if(PostprocessorExitCode!=0) Fail("MED postprocessor returned non-zero exit code: "+PostprocessorExitCode);
            if(!File.Exists(ResultBundleFile) || new FileInfo(ResultBundleFile).Length==0) Fail("AsterMax results bundle is missing or empty.");
            if(!File.Exists(ResultVtuFile) || new FileInfo(ResultVtuFile).Length==0) Fail("AsterMax VTU evidence is missing or empty.");

            RequireUnchangedModel(liveModel);
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);

            State=AsterMaxSolveState.SolutionCurrent;
            Message="SOLUTION_CURRENT: solver, MED postprocess, model identity and result bundle all verified.";
            WriteFinalState();
            return bundle;
        }

        public void RequireUnchangedModel(CaeModel.FeModel liveModel)
'@
if(-not $s.Contains('CompleteVerifiedResultsHandoff(')){
  if(-not $s.Contains($old)){ throw 'C10.01 postprocess insertion anchor missing.' }
  $s=$s.Replace($old,$new)
}

if(-not $s.Contains('["result_bundle_exists"]')){
  $anchor='                ["med_exists"]=File.Exists(MedFile),'
  if(-not $s.Contains($anchor)){ throw 'C10.01 final state anchor missing.' }
  $insert=$anchor+[Environment]::NewLine+
'                ["result_bundle_exists"]=!String.IsNullOrWhiteSpace(ResultBundleFile) && File.Exists(ResultBundleFile),'+[Environment]::NewLine+
'                ["result_vtu_exists"]=!String.IsNullOrWhiteSpace(ResultVtuFile) && File.Exists(ResultVtuFile),'+[Environment]::NewLine+
'                ["postprocessor"]=PostprocessorExecutable,'+[Environment]::NewLine+
'                ["postprocessor_exit_code"]=PostprocessorExitCode.HasValue?(JToken)PostprocessorExitCode.Value:JValue.CreateNull(),'
  $s=$s.Replace($anchor,$insert)
}

$oldUi=@'
                _asterMaxSolveTransaction.ExecuteConfiguredRunner(_controller.Model);
                tsslState.Text="AsterMax Solve: SOLUTION_CURRENT";
                MessageBox.Show(this,
                    "Code_Aster finished with verified normal-stop + non-empty MED evidence.

Model fingerprint remained CURRENT. No FEA values were invented.

Workspace: "+_asterMaxSolveTransaction.Workspace,
                    "AsterMax Native Solve",MessageBoxButtons.OK,MessageBoxIcon.Information);
'@
$newUi=@'
                _asterMaxSolveTransaction.ExecuteConfiguredRunner(_controller.Model);
                tsslState.Text="AsterMax Solve: POSTPROCESSING";
                _asterMaxLoadedResults=_asterMaxSolveTransaction.CompleteVerifiedResultsHandoff(_controller.Model);
                tsslState.Text="AsterMax Solve: SOLUTION_CURRENT";
                using(var viewport=new AsterMaxResultsViewportForm(_asterMaxLoadedResults)) viewport.ShowDialog(this);
'@
if(-not $s.Contains('_asterMaxLoadedResults=_asterMaxSolveTransaction.CompleteVerifiedResultsHandoff(')){
  if(-not $s.Contains($oldUi)){ throw 'C10.01 FrmMain handoff anchor missing.' }
  $s=$s.Replace($oldUi,$newUi)
}

Set-Content $solvePath $s -Encoding UTF8
Write-Host 'C10.01 automatic verified MED-to-VTK handoff injected.' -ForegroundColor Green
