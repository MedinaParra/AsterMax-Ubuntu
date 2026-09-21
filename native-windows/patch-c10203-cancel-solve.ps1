param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.3 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")

$oldEnum='internal enum AsterMaxSolveState { Idle, Preparing, ReadyToRun, Running, Postprocessing, SolutionCurrent, SolutionStale, Failed }'
$newEnum='internal enum AsterMaxSolveState { Idle, Preparing, ReadyToRun, Running, Postprocessing, Cancelling, Cancelled, SolutionCurrent, SolutionStale, Failed }'
$s=Replace-Required $s $oldEnum $newEnum

$runnerProperty='        public int? RunnerExitCode { get; private set; }'
$runnerFields=@'
        public int? RunnerExitCode { get; private set; }
        private readonly object _activeProcessSync=new object();
        private Process _activeProcess;
        private volatile bool _cancelRequested;
        public bool CancelRequested { get { return _cancelRequested; } }
'@
$s=Replace-Required $s $runnerProperty $runnerFields.TrimEnd()

$executeAnchor='        public void ExecuteConfiguredRunner(CaeModel.FeModel liveModel)'
$cancelHelpers=@'
        public void RequestCancel()
        {
            _cancelRequested=true;
            Process active=null;
            lock(_activeProcessSync) active=_activeProcess;
            if(active!=null) Task.Run(() => TryTerminateProcessTree(active));
        }

        private void ThrowIfCancellationRequested()
        {
            if(!_cancelRequested) return;
            State=AsterMaxSolveState.Cancelled;
            Message="CANCELLED: native Solve was cancelled by the user.";
            WriteFinalState();
            throw new OperationCanceledException(Message);
        }

        private static void TryTerminateProcessTree(Process process)
        {
            if(process==null) return;
            try { if(process.HasExited) return; } catch { }
            try
            {
                string taskkill=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"taskkill.exe");
                if(File.Exists(taskkill))
                {
                    var psi=new ProcessStartInfo {
                        FileName=taskkill,
                        Arguments="/PID "+process.Id.ToString(CultureInfo.InvariantCulture)+" /T /F",
                        UseShellExecute=false,
                        CreateNoWindow=true
                    };
                    using(var killer=Process.Start(psi))
                    {
                        if(killer!=null) killer.WaitForExit(10000);
                    }
                }
            }
            catch { }
            try { if(!process.HasExited) process.Kill(); } catch { }
        }

        private int RunTrackedProcess(ProcessStartInfo psi,string stdoutFile,string stderrFile)
        {
            ThrowIfCancellationRequested();
            using(var process=Process.Start(psi))
            {
                if(process==null) throw new InvalidOperationException("External process could not be started.");
                lock(_activeProcessSync) _activeProcess=process;
                try
                {
                    var stdoutTask=process.StandardOutput.ReadToEndAsync();
                    var stderrTask=process.StandardError.ReadToEndAsync();
                    if(_cancelRequested) TryTerminateProcessTree(process);
                    process.WaitForExit();
                    string stdout=stdoutTask.GetAwaiter().GetResult().Replace("\0","");
                    string stderr=stderrTask.GetAwaiter().GetResult().Replace("\0","");
                    File.WriteAllText(Path.Combine(Workspace,stdoutFile),stdout,new UTF8Encoding(false));
                    File.WriteAllText(Path.Combine(Workspace,stderrFile),stderr,new UTF8Encoding(false));
                    ThrowIfCancellationRequested();
                    return process.ExitCode;
                }
                finally
                {
                    lock(_activeProcessSync)
                    {
                        if(Object.ReferenceEquals(_activeProcess,process)) _activeProcess=null;
                    }
                }
            }
        }

'@
$s=Replace-Required $s $executeAnchor ($cancelHelpers+$executeAnchor)

$solverOld=@'
            using(var p=Process.Start(psi))
            {
                var stdoutTask=p.StandardOutput.ReadToEndAsync();
                var stderrTask=p.StandardError.ReadToEndAsync();
                p.WaitForExit();
                string stdout=stdoutTask.GetAwaiter().GetResult();
                string stderr=stderrTask.GetAwaiter().GetResult();
                RunnerExitCode=p.ExitCode;
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDOUT.log"),stdout,new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDERR.log"),stderr,new UTF8Encoding(false));
            }
'@
$solverNew=@'
            RunnerExitCode=RunTrackedProcess(psi,"CODE_ASTER_RUNNER_STDOUT.log","CODE_ASTER_RUNNER_STDERR.log");
'@
$solverOld=[regex]::Replace($solverOld,"\r\n?","`n")
$solverNew=[regex]::Replace($solverNew,"\r\n?","`n")
$s=Replace-Required $s $solverOld $solverNew

$handoffAnchor=@'
            if(State!=AsterMaxSolveState.Postprocessing)
                throw new InvalidOperationException("Solve transaction is not ready for postprocess handoff.");

            RequireUnchangedModel(liveModel);
'@
$handoffNew=@'
            if(State!=AsterMaxSolveState.Postprocessing)
                throw new InvalidOperationException("Solve transaction is not ready for postprocess handoff.");

            ThrowIfCancellationRequested();
            RequireUnchangedModel(liveModel);
'@
$handoffAnchor=[regex]::Replace($handoffAnchor,"\r\n?","`n")
$handoffNew=[regex]::Replace($handoffNew,"\r\n?","`n")
$s=Replace-Required $s $handoffAnchor $handoffNew

$capturedNew=@'
        private int RunCaptured(ProcessStartInfo psi,string stem)
        {
            return RunTrackedProcess(psi,stem+"_STDOUT.log",stem+"_STDERR.log");
        }
'@
$capturedNew=[regex]::Replace($capturedNew,"\\r\\n?","`n")

# C10.20.8a: match RunCaptured by method structure instead of one historical body.
# Earlier Windows-runtime patches are allowed to change sync/async pipe handling.
if($s.Contains($capturedNew.TrimEnd()))
{
    Write-Host 'C10.20.3 RunCaptured already uses tracked process execution.'
}
else
{
    $capturedPattern='(?ms)^        private int RunCaptured\\(ProcessStartInfo psi,string stem\\)\\s*\\{\\n.*?^        \\}\\n?'
    $capturedMatch=[regex]::Match($s,$capturedPattern)
    if(-not $capturedMatch.Success)
    {
        throw 'C10.20.3 structural anchor missing: RunCaptured(ProcessStartInfo psi,string stem)'
    }
    if($capturedMatch.Value -notmatch 'Process\\.Start|RunTrackedProcess')
    {
        throw 'C10.20.3 RunCaptured was found but has an unexpected implementation; refusing blind replacement.'
    }
    $s=$s.Substring(0,$capturedMatch.Index)+$capturedNew.TrimEnd()+"`n"+$s.Substring($capturedMatch.Index+$capturedMatch.Length)
}

$oldRibbon='                if(ribbon!=null) { _asterMaxSolveRibbonWasEnabled=ribbon.Enabled; ribbon.Enabled=false; }'
$newRibbon='                if(ribbon!=null) _asterMaxSolveRibbonWasEnabled=ribbon.Enabled;'
$s=Replace-Required $s $oldRibbon $newRibbon

$asyncSignature='        private async void RunAsterMaxNativeSolve()'
$cancelMethod=@'
        private void CancelAsterMaxNativeSolve()
        {
            if(!_asterMaxSolveInProgress || _asterMaxSolveTransaction==null)
            {
                tsslState.Text="AsterMax Solve: no active solve to cancel";
                return;
            }
            tsslState.Text="AsterMax Solve: CANCELLING";
            _asterMaxSolveTransaction.RequestCancel();
        }

'@
$s=Replace-Required $s $asyncSignature ($cancelMethod+$asyncSignature)

$catchOld=@'
            catch(Exception ex)
            {
                _asterMaxSolveLastError=ex;
                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";
                if(!_asterMaxUiAuditMode)
                    CaeGlobals.MessageBoxes.ShowError("AsterMax Solve blocked: "+ex.Message);
            }
'@
$catchNew=@'
            catch(OperationCanceledException ex)
            {
                _asterMaxSolveLastError=ex;
                tsslState.Text="AsterMax Solve: CANCELLED";
            }
            catch(Exception ex)
            {
                _asterMaxSolveLastError=ex;
                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";
                if(!_asterMaxUiAuditMode)
                    CaeGlobals.MessageBoxes.ShowError("AsterMax Solve blocked: "+ex.Message);
            }
'@
$catchOld=[regex]::Replace($catchOld,"\r\n?","`n")
$catchNew=[regex]::Replace($catchNew,"\r\n?","`n")
$s=Replace-Required $s $catchOld $catchNew
Set-Content $solvePath $s -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$solveTile='                CommandTile("Solve", "CODE_ASTER", () => RunAsterMaxNativeSolve(), true),'
$u=Replace-Required $u $solveTile ($solveTile+"`n"+'                CommandTile("Cancel Solve", "CODE_ASTER", () => CancelAsterMaxNativeSolve()),')
Set-Content $uiPath $u -Encoding UTF8

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxButtonAudit.cs'
$b=[regex]::Replace((Get-Content $auditPath -Raw),"\r\n?","`n")
$oldIcons='            {"Solve","Running"},{"Results Explorer","Field_output"},{"FEA Viewport","Color_contours"},'
$newIcons='            {"Solve","Running"},{"Cancel Solve","Running"},{"Results Explorer","Field_output"},{"FEA Viewport","Color_contours"},'
$b=Replace-Required $b $oldIcons $newIcons
$oldExpected='            {"Solution",new[]{"Export Solver Contract","Export Code_Aster Deck","Runtime","Solve"}},'
$newExpected='            {"Solution",new[]{"Export Solver Contract","Export Code_Aster Deck","Runtime","Solve","Cancel Solve"}},'
$b=Replace-Required $b $oldExpected $newExpected
$invokeAnchor=@'
        private void InvokeAsterMaxCommand(string caption, Action action)
        {
            try { if (!RouteAsterMaxIntegratedCommand(caption)) action(); RefreshAsterMaxResultAvailability(); }
'@
$invokeNew=@'
        private void InvokeAsterMaxCommand(string caption, Action action)
        {
            if(_asterMaxSolveInProgress && !String.Equals(caption,"Cancel Solve",StringComparison.Ordinal))
            {
                tsslState.Text="AsterMax Solve: model editing is locked while the solve is running";
                return;
            }
            try { if (!RouteAsterMaxIntegratedCommand(caption)) action(); RefreshAsterMaxResultAvailability(); }
'@
$invokeAnchor=[regex]::Replace($invokeAnchor,"\r\n?","`n")
$invokeNew=[regex]::Replace($invokeNew,"\r\n?","`n")
$b=Replace-Required $b $invokeAnchor $invokeNew
$tipOld='            if (caption == "Solve") tip += "\nCode_Aster nativo de Windows; requiere material, sección, malla, apoyo, carga y Runtime/PREFLIGHT válido.";'
$tipNew=$tipOld+"`n"+'            else if (caption == "Cancel Solve") tip += "\nCancela el cálculo activo y termina el árbol de procesos del runner.";'
$b=Replace-Required $b $tipOld $tipNew
Set-Content $auditPath $b -Encoding UTF8

Write-Host 'C10.20.3 cancellable tracked-process Solve hotfix applied.' -ForegroundColor Green
