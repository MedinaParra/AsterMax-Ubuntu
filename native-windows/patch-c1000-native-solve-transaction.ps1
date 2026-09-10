param([string]$Root)
$ErrorActionPreference='Stop'

# C10.00 — Native Solve transaction controller.
# Integrates live FeModel readiness/fingerprint/export into AsterMax Mechanical.
# It never fabricates FEA values and never claims a bundled Windows solver runtime.

$src=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$code=@'
using System;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal enum AsterMaxSolveState { Idle, Preparing, ReadyToRun, Running, SolutionCurrent, SolutionStale, Failed }

    internal sealed class AsterMaxNativeSolveTransaction
    {
        public const string Schema = "astermax-native-solve-transaction/v0";
        public string Workspace { get; private set; }
        public string BaseName { get; private set; }
        public string FrozenFingerprint { get; private set; }
        public AsterMaxSolveState State { get; private set; }
        public string Message { get; private set; }
        public string ExportFile { get; private set; }
        public string MessFile { get; private set; }
        public string MedFile { get; private set; }
        public string RunnerExecutable { get; private set; }
        public int? RunnerExitCode { get; private set; }

        private AsterMaxNativeSolveTransaction() { State=AsterMaxSolveState.Idle; }

        public static AsterMaxNativeSolveTransaction Prepare(CaeModel.FeModel model, string rootWorkspace, string baseName)
        {
            if(model==null) throw new ArgumentNullException("model");
            var readiness=AsterMaxPreSolveReadiness.Evaluate(model);
            if(readiness.Status!="READY")
                throw new InvalidOperationException("Solve blocked by engineering readiness gate: "+readiness.AuditSummary()+" | "+String.Join("; ",readiness.Issues));

            var fp=AsterMaxModelFingerprint.Extract(model);
            if(String.IsNullOrWhiteSpace(rootWorkspace)) throw new InvalidOperationException("A writable AsterMax workspace is required.");
            Directory.CreateDirectory(rootWorkspace);
            string safe=String.IsNullOrWhiteSpace(baseName)?"analysis":baseName;
            string txDir=Path.Combine(rootWorkspace,"Solve-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss",CultureInfo.InvariantCulture));
            Directory.CreateDirectory(txDir);

            var tx=new AsterMaxNativeSolveTransaction();
            tx.State=AsterMaxSolveState.Preparing;
            tx.Workspace=txDir;
            tx.BaseName=safe;
            tx.FrozenFingerprint=fp.Sha256;

            JObject exportManifest=AsterMaxCodeAsterNativeExporter.Export(model,txDir,safe);
            tx.ExportFile=Path.Combine(txDir,safe+".export");
            tx.MessFile=Path.Combine(txDir,safe+".mess");
            tx.MedFile=Path.Combine(txDir,safe+".rmed");
            WriteExport(tx.ExportFile,safe);

            JObject manifest=new JObject
            {
                ["schema"]=Schema,
                ["release"]="C10.00",
                ["state"]="READY_TO_RUN",
                ["model_fingerprint_sha256"]=tx.FrozenFingerprint,
                ["unit_contract"]="mm/N/MPa",
                ["solver_backend"]="Code_Aster",
                ["solver_runtime_bundled"]=false,
                ["runner_contract"]="ASTERMAX_CODE_ASTER_RUNNER <export-file> <workspace>",
                ["mail_file"]=safe+".mail",
                ["comm_file"]=safe+".comm",
                ["export_file"]=safe+".export",
                ["expected_med_file"]=safe+".rmed",
                ["fea_values_invented"]=false,
                ["native_exporter_manifest"]=exportManifest
            };
            File.WriteAllText(Path.Combine(txDir,"ASTERMAX_SOLVE_TRANSACTION.json"),manifest.ToString(Formatting.Indented),new UTF8Encoding(false));
            tx.State=AsterMaxSolveState.ReadyToRun;
            tx.Message="Code_Aster transaction prepared and fingerprint frozen.";
            return tx;
        }

        public void ExecuteConfiguredRunner(CaeModel.FeModel liveModel)
        {
            if(State!=AsterMaxSolveState.ReadyToRun) throw new InvalidOperationException("Solve transaction is not ready to run.");
            RunnerExecutable=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");
            if(String.IsNullOrWhiteSpace(RunnerExecutable) || !File.Exists(RunnerExecutable))
            {
                State=AsterMaxSolveState.Failed;
                Message="Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.";
                WriteFinalState();
                throw new FileNotFoundException(Message,RunnerExecutable);
            }

            State=AsterMaxSolveState.Running;
            WriteFinalState();
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
            using(var p=Process.Start(psi))
            {
                string stdout=p.StandardOutput.ReadToEnd();
                string stderr=p.StandardError.ReadToEnd();
                p.WaitForExit();
                RunnerExitCode=p.ExitCode;
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDOUT.log"),stdout,new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDERR.log"),stderr,new UTF8Encoding(false));
            }

            if(RunnerExitCode!=0)
            {
                State=AsterMaxSolveState.Failed;
                Message="Code_Aster runner returned non-zero exit code: "+RunnerExitCode;
                WriteFinalState();
                throw new InvalidOperationException(Message);
            }
            if(!File.Exists(MessFile) || new FileInfo(MessFile).Length==0) Fail("Code_Aster .mess evidence is missing or empty.");
            if(!File.Exists(MedFile) || new FileInfo(MedFile).Length==0) Fail("Code_Aster MED result is missing or empty.");

            string mess=File.ReadAllText(MessFile);
            if(mess.IndexOf("<I> <FIN> ARRET NORMAL",StringComparison.OrdinalIgnoreCase)<0 && mess.IndexOf("ARRET NORMAL",StringComparison.OrdinalIgnoreCase)<0)
                Fail("Code_Aster normal termination marker was not found in .mess.");

            RequireUnchangedModel(liveModel);
            State=AsterMaxSolveState.SolutionCurrent;
            Message="SOLUTION_CURRENT: real solver evidence accepted. MED postprocess bridge is the next transaction stage.";
            WriteFinalState();
        }

        public void RequireUnchangedModel(CaeModel.FeModel liveModel)
        {
            var now=AsterMaxModelFingerprint.Extract(liveModel);
            if(!String.Equals(FrozenFingerprint,now.Sha256,StringComparison.OrdinalIgnoreCase))
            {
                State=AsterMaxSolveState.SolutionStale;
                Message="SOLUTION_STALE: active FeModel changed after the solve transaction was frozen.";
                WriteFinalState();
                throw new InvalidOperationException(Message);
            }
        }

        private void Fail(string message)
        {
            State=AsterMaxSolveState.Failed; Message=message; WriteFinalState(); throw new InvalidOperationException(message);
        }

        private void WriteFinalState()
        {
            if(String.IsNullOrWhiteSpace(Workspace) || !Directory.Exists(Workspace)) return;
            JObject state=new JObject
            {
                ["schema"]=Schema,
                ["release"]="C10.00",
                ["state"]=State.ToString().ToUpperInvariant(),
                ["message"]=Message,
                ["model_fingerprint_sha256"]=FrozenFingerprint,
                ["runner"]=RunnerExecutable,
                ["runner_exit_code"]=RunnerExitCode.HasValue?(JToken)RunnerExitCode.Value:JValue.CreateNull(),
                ["mess_exists"]=File.Exists(MessFile),
                ["med_exists"]=File.Exists(MedFile),
                ["fea_values_invented"]=false
            };
            File.WriteAllText(Path.Combine(Workspace,"ASTERMAX_SOLVE_STATE.json"),state.ToString(Formatting.Indented),new UTF8Encoding(false));
        }

        private static void WriteExport(string path,string n)
        {
            string text="P actions make_etude\nP version 15.2\nP mode interactif\nP time_limit 300\nP memory_limit 2048\nP ncpus 1\nP mpi_nbcpu 1\n\n"+
                "F comm /analysis/"+n+".comm D 1\n"+
                "F mail /analysis/"+n+".mail D 20\n"+
                "F mess /analysis/"+n+".mess R 6\n"+
                "F resu /analysis/"+n+".resu R 80\n"+
                "F rmed /analysis/"+n+".rmed R 81\n";
            File.WriteAllText(path,text,new UTF8Encoding(false));
        }
        private static string Quote(string s){ return "\""+(s??"").Replace("\"","\\\"")+"\""; }
    }

    public partial class FrmMain
    {
        private AsterMaxNativeSolveTransaction _asterMaxSolveTransaction;

        private void RunAsterMaxNativeSolve()
        {
            try
            {
                if(_controller==null || _controller.Model==null) throw new InvalidOperationException("No active FeModel is available.");
                string work=_controller.Settings.GetWorkDirectory();
                _asterMaxSolveTransaction=AsterMaxNativeSolveTransaction.Prepare(_controller.Model,work,"astermax-analysis");
                tsslState.Text="AsterMax Solve: READY_TO_RUN";
                _asterMaxSolveTransaction.ExecuteConfiguredRunner(_controller.Model);
                tsslState.Text="AsterMax Solve: SOLUTION_CURRENT";
                MessageBox.Show(this,
                    "Code_Aster finished with verified normal-stop + non-empty MED evidence.\n\nModel fingerprint remained CURRENT. No FEA values were invented.\n\nWorkspace: "+_asterMaxSolveTransaction.Workspace,
                    "AsterMax Native Solve",MessageBoxButtons.OK,MessageBoxIcon.Information);
            }
            catch(Exception ex)
            {
                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";
                CaeGlobals.MessageBoxes.ShowError("AsterMax Solve blocked: "+ex.Message);
            }
        }
    }
}
'@
Set-Content $src $code -Encoding UTF8

$proj=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $proj -Raw
if(-not $p.Contains('Forms\AsterMaxNativeSolveTransaction.cs')){
  $anchor='<Compile Include="Forms\AsterMaxResultsWorkspace.cs" />'
  if(-not $p.Contains($anchor)){throw 'C10.00 requires AsterMaxResultsWorkspace.cs project anchor.'}
  $p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxNativeSolveTransaction.cs" />')
  Set-Content $proj $p -Encoding UTF8
}

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('CommandTile("Solve", "CODE_ASTER"')){
  $old='                StateCard("Solver", "Code_Aster integration path"),'
  if(-not $u.Contains($old)){throw 'C10.00 Solution ribbon anchor missing.'}
  $new='                CommandTile("Solve", "CODE_ASTER", () => RunAsterMaxNativeSolve(), true),'+[Environment]::NewLine+$old
  $u=$u.Replace($old,$new)
  Set-Content $ui $u -Encoding UTF8
}

Write-Host 'C10.00 native Solve transaction controller injected (WinForms compile contract fixed).' -ForegroundColor Green
