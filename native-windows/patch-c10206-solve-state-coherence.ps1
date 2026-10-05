param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.6 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")

$fieldAnchor='        private readonly object _activeProcessSync=new object();'
$fieldNew=@'
        private readonly object _activeProcessSync=new object();
        private readonly object _stateTransitionSync=new object();
        private readonly object _stateFileSync=new object();
        private long _stateRevision;
'@
$s=Replace-Required $s $fieldAnchor $fieldNew.TrimEnd()

$requestOld=@'
        public void RequestCancel()
        {
            _cancelRequested=true;
            Process active=null;
            lock(_activeProcessSync) active=_activeProcess;
            if(active!=null) Task.Run(() => TryTerminateProcessTree(active));
        }
'@
$requestNew=@'
        public void RequestCancel()
        {
            Process active=null;
            lock(_stateTransitionSync)
            {
                if(_cancelRequested) return;
                _cancelRequested=true;
                if(State==AsterMaxSolveState.ReadyToRun ||
                   State==AsterMaxSolveState.Running ||
                   State==AsterMaxSolveState.Postprocessing)
                {
                    State=AsterMaxSolveState.Cancelling;
                    Message="CANCELLING: termination requested for the active native Solve.";
                    WriteFinalState();
                }
            }
            lock(_activeProcessSync) active=_activeProcess;
            if(active!=null) Task.Run(() => TryTerminateProcessTree(active));
        }
'@
$requestOld=[regex]::Replace($requestOld,"\r\n?","`n")
$requestNew=[regex]::Replace($requestNew,"\r\n?","`n")
$s=Replace-Required $s $requestOld $requestNew

$throwOld=@'
        private void ThrowIfCancellationRequested()
        {
            if(!_cancelRequested) return;
            State=AsterMaxSolveState.Cancelled;
            Message="CANCELLED: native Solve was cancelled by the user.";
            WriteFinalState();
            throw new OperationCanceledException(Message);
        }
'@
$throwNew=@'
        private void ThrowIfCancellationRequested()
        {
            if(!_cancelRequested) return;
            string message;
            lock(_stateTransitionSync)
            {
                State=AsterMaxSolveState.Cancelled;
                Message="CANCELLED: native Solve was cancelled by the user.";
                WriteFinalState();
                message=Message;
            }
            throw new OperationCanceledException(message);
        }

        private void TransitionOrCancel(AsterMaxSolveState next,string message)
        {
            lock(_stateTransitionSync)
            {
                if(_cancelRequested)
                {
                    State=AsterMaxSolveState.Cancelled;
                    Message="CANCELLED: native Solve was cancelled by the user.";
                    WriteFinalState();
                    throw new OperationCanceledException(Message);
                }
                State=next;
                Message=message;
                WriteFinalState();
            }
        }
'@
$throwOld=[regex]::Replace($throwOld,"\r\n?","`n")
$throwNew=[regex]::Replace($throwNew,"\r\n?","`n")
$s=Replace-Required $s $throwOld $throwNew

$executeGuard='            if(State!=AsterMaxSolveState.ReadyToRun) throw new InvalidOperationException("Solve transaction is not ready to run.");'
$s=Replace-Required $s $executeGuard ($executeGuard+"`n"+'            ThrowIfCancellationRequested();')

$runningOld=@'
            State=AsterMaxSolveState.Running;
            WriteFinalState();
'@
$runningNew='            TransitionOrCancel(AsterMaxSolveState.Running,"RUNNING: native Code_Aster runner started.");'
$runningOld=[regex]::Replace($runningOld,"\r\n?","`n")
$s=Replace-Required $s $runningOld $runningNew

$missingRunnerOld=@'
            if(String.IsNullOrWhiteSpace(RunnerExecutable) || !File.Exists(RunnerExecutable))
            {
                State=AsterMaxSolveState.Failed;
                Message="Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.";
                WriteFinalState();
                throw new FileNotFoundException(Message,RunnerExecutable);
            }
'@
$missingRunnerNew=@'
            if(String.IsNullOrWhiteSpace(RunnerExecutable) || !File.Exists(RunnerExecutable))
            {
                Fail("Code_Aster runner is not configured. Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.");
            }
'@
$missingRunnerOld=[regex]::Replace($missingRunnerOld,"\r\n?","`n")
$missingRunnerNew=[regex]::Replace($missingRunnerNew,"\r\n?","`n")
$s=Replace-Required $s $missingRunnerOld $missingRunnerNew

$runnerExitOld=@'
            if(RunnerExitCode!=0)
            {
                State=AsterMaxSolveState.Failed;
                string details=BuildRunnerFailureDiagnostic(Workspace,RunnerExitCode.Value);
                Message="Code_Aster solve failed (runner exit "+RunnerExitCode+")."+
                    (String.IsNullOrWhiteSpace(details)?"":"\n\n"+details);
                WriteFinalState();
                throw new InvalidOperationException(Message);
            }
'@
$runnerExitNew=@'
            if(RunnerExitCode!=0)
            {
                string details=BuildRunnerFailureDiagnostic(Workspace,RunnerExitCode.Value);
                Fail("Code_Aster solve failed (runner exit "+RunnerExitCode+")."+
                    (String.IsNullOrWhiteSpace(details)?"":"\n\n"+details));
            }
'@
$runnerExitOld=[regex]::Replace($runnerExitOld,"\r\n?","`n")
$runnerExitNew=[regex]::Replace($runnerExitNew,"\r\n?","`n")
$s=Replace-Required $s $runnerExitOld $runnerExitNew

$postOld=@'
            RequireUnchangedModel(liveModel);
            State=AsterMaxSolveState.Postprocessing;
            Message="Code_Aster evidence accepted; waiting for verified MED postprocess handoff.";
            WriteFinalState();
'@
$postNew=@'
            ThrowIfCancellationRequested();
            RequireUnchangedModel(liveModel);
            TransitionOrCancel(AsterMaxSolveState.Postprocessing,
                "Code_Aster evidence accepted; waiting for verified MED postprocess handoff.");
'@
$postOld=[regex]::Replace($postOld,"\r\n?","`n")
$postNew=[regex]::Replace($postNew,"\r\n?","`n")
$s=Replace-Required $s $postOld $postNew

$currentOld=@'
            State=AsterMaxSolveState.SolutionCurrent;
            Message="SOLUTION_CURRENT: solver, MED bridge, fingerprint binding and VTK-ready result bundle all verified.";
            WriteFinalState();
            return bundle;
'@
$currentNew=@'
            ThrowIfCancellationRequested();
            TransitionOrCancel(AsterMaxSolveState.SolutionCurrent,
                "SOLUTION_CURRENT: solver, MED bridge, fingerprint binding and VTK-ready result bundle all verified.");
            return bundle;
'@
$currentOld=[regex]::Replace($currentOld,"\r\n?","`n")
$currentNew=[regex]::Replace($currentNew,"\r\n?","`n")
$s=Replace-Required $s $currentOld $currentNew

$failOld=@'
        private void Fail(string message)
        {
            State=AsterMaxSolveState.Failed; Message=message; WriteFinalState(); throw new InvalidOperationException(message);
        }
'@
$failNew=@'
        private void Fail(string message)
        {
            lock(_stateTransitionSync)
            {
                if(_cancelRequested)
                {
                    State=AsterMaxSolveState.Cancelled;
                    Message="CANCELLED: native Solve was cancelled by the user.";
                    WriteFinalState();
                    throw new OperationCanceledException(Message);
                }
                State=AsterMaxSolveState.Failed;
                Message=message;
                WriteFinalState();
            }
            throw new InvalidOperationException(message);
        }
'@
$failOld=[regex]::Replace($failOld,"\r\n?","`n")
$failNew=[regex]::Replace($failNew,"\r\n?","`n")
$s=Replace-Required $s $failOld $failNew

$writePattern='(?s)        private void WriteFinalState\(\)\s*\{(.*?)\n        \}\n\n        private static void WriteExport'
$m=[regex]::Match($s,$writePattern)
if(-not $m.Success){ throw 'C10.20.6 WriteFinalState structural anchor missing.' }
$body=$m.Groups[1].Value
if($body.Contains('_stateRevision')){ throw 'C10.20.6 state revision already injected unexpectedly.' }

$writeOld='            File.WriteAllText(Path.Combine(Workspace,"ASTERMAX_SOLVE_STATE.json"),state.ToString(Formatting.Indented),new UTF8Encoding(false));'
if(-not $body.Contains($writeOld)){ throw 'C10.20.6 state-file write anchor missing.' }

$feaAnchor='                ["fea_values_invented"]=false'
if(-not $body.Contains($feaAnchor)){ throw 'C10.20.6 FEA provenance anchor missing in state JSON.' }
$body=$body.Replace($feaAnchor,
'                ["cancel_requested"]=_cancelRequested,'+"`n"+
'                ["state_revision"]=revision,'+"`n"+
$feaAnchor)

$writeNew=@'
            string finalPath=Path.Combine(Workspace,"ASTERMAX_SOLVE_STATE.json");
            string tempPath=finalPath+"."+Guid.NewGuid().ToString("N")+".tmp";
            File.WriteAllText(tempPath,state.ToString(Formatting.Indented),new UTF8Encoding(false));
            try
            {
                if(File.Exists(finalPath)) File.Replace(tempPath,finalPath,null);
                else File.Move(tempPath,finalPath);
            }
            finally
            {
                if(File.Exists(tempPath)) File.Delete(tempPath);
            }
'@
$writeNew=[regex]::Replace($writeNew,"\r\n?","`n").TrimEnd()
$body=$body.Replace($writeOld,$writeNew)

$newWrite=@'
        private void WriteFinalState()
        {
            lock(_stateFileSync)
            {
                long revision=System.Threading.Interlocked.Increment(ref _stateRevision);
__BODY__
            }
        }

        private static void WriteExport
'@
$trimmed=$body.Trim([char[]]@(10,13))
$indented=(($trimmed -split '\n') | ForEach-Object { '    '+$_ }) -join [Environment]::NewLine
$newWrite=$newWrite.Replace('__BODY__',$indented)
$newWrite=[regex]::Replace($newWrite,"\r\n?","`n")
$s=[regex]::Replace($s,$writePattern,[System.Text.RegularExpressions.MatchEvaluator]{ param($x) $newWrite },1)

Set-Content $solvePath $s -Encoding UTF8
Write-Host 'C10.20.6 Solve state coherence and atomic evidence hotfix applied.' -ForegroundColor Green
