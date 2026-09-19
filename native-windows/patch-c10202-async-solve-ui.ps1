param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.2 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=(Get-Content $solvePath -Raw).Replace("`r`n","`n")

if(-not $s.Contains('using System.Threading.Tasks;')) {
    $s=Replace-Required $s 'using System.Text;' "using System.Text;`nusing System.Threading.Tasks;"
}

# Avoid same-second transaction-folder collisions.
$oldTx='string txDir=Path.Combine(rootWorkspace,"Solve-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss",CultureInfo.InvariantCulture));'
$newTx='string txDir=Path.Combine(rootWorkspace,"Solve-"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fffffff",CultureInfo.InvariantCulture)+"-"+Guid.NewGuid().ToString("N").Substring(0,8));'
$s=Replace-Required $s $oldTx $newTx

$pattern='(?s)        private void RunAsterMaxNativeSolve\(\)\s*\{.*?\n        \}\n    \}\n\}'
if(-not [regex]::IsMatch($s,$pattern)){ throw 'C10.20.2 RunAsterMaxNativeSolve structural anchor missing.' }

$replacement=@'
        private bool _asterMaxSolveInProgress;
        private Exception _asterMaxSolveLastError;
        private int _asterMaxSolveUiHeartbeatCount;
        private int _asterMaxSolveUiThreadId;
        private int _asterMaxSolveWorkerThreadId;
        private int _asterMaxSolveDuplicateRequestsRejected;
        private bool _asterMaxSolveRibbonWasEnabled;
        private bool _asterMaxSolveTreeWasEnabled;
        private bool _asterMaxSolveMenuWasEnabled;

        private void SetAsterMaxSolveUiBusy(bool busy)
        {
            TabControl ribbon=Controls["asterMaxRibbon"] as TabControl;
            if(busy)
            {
                if(ribbon!=null) { _asterMaxSolveRibbonWasEnabled=ribbon.Enabled; ribbon.Enabled=false; }
                if(_modelTree!=null) { _asterMaxSolveTreeWasEnabled=_modelTree.Enabled; _modelTree.Enabled=false; }
                if(MainMenuStrip!=null) { _asterMaxSolveMenuWasEnabled=MainMenuStrip.Enabled; MainMenuStrip.Enabled=false; }
            }
            else
            {
                if(ribbon!=null) ribbon.Enabled=_asterMaxSolveRibbonWasEnabled;
                if(_modelTree!=null) _modelTree.Enabled=_asterMaxSolveTreeWasEnabled;
                if(MainMenuStrip!=null) MainMenuStrip.Enabled=_asterMaxSolveMenuWasEnabled;
            }
        }

        private async void RunAsterMaxNativeSolve()
        {
            if(_asterMaxSolveInProgress)
            {
                _asterMaxSolveDuplicateRequestsRejected++;
                tsslState.Text="AsterMax Solve: already running";
                return;
            }

            System.Windows.Forms.Timer heartbeat=null;
            bool uiBusySet=false;
            AsterMaxNativeSolveTransaction transaction=null;
            CaeModel.FeModel solveModel=null;
            try
            {
                if(_controller==null || _controller.Model==null)
                    throw new InvalidOperationException("No active FeModel is available.");

                solveModel=_controller.Model;
                string work=_controller.Settings.GetWorkDirectory();
                transaction=AsterMaxNativeSolveTransaction.Prepare(solveModel,work,"astermax-analysis");
                _asterMaxSolveTransaction=transaction;
                _asterMaxSolveLastError=null;
                _asterMaxSolveUiThreadId=System.Threading.Thread.CurrentThread.ManagedThreadId;
                _asterMaxSolveWorkerThreadId=0;
                _asterMaxSolveUiHeartbeatCount=0;
                _asterMaxSolveInProgress=true;
                SetAsterMaxSolveUiBusy(true);
                uiBusySet=true;

                heartbeat=new System.Windows.Forms.Timer { Interval=25 };
                heartbeat.Tick += (sender,args) => {
                    _asterMaxSolveUiHeartbeatCount++;
                    if(transaction!=null)
                        tsslState.Text="AsterMax Solve: "+transaction.State.ToString().ToUpperInvariant()+" (background)";
                };
                heartbeat.Start();
                tsslState.Text="AsterMax Solve: READY_TO_RUN (background)";

                AsterMaxResultsBundle completedBundle=await Task.Run(() => {
                    _asterMaxSolveWorkerThreadId=System.Threading.Thread.CurrentThread.ManagedThreadId;
                    transaction.ExecuteConfiguredRunner(solveModel);
                    return transaction.CompleteVerifiedResultsHandoff(solveModel);
                });

                if(!Object.ReferenceEquals(_asterMaxSolveTransaction,transaction))
                    throw new InvalidOperationException("Active solve transaction changed while the background solve was running.");

                _asterMaxLoadedResults=completedBundle;
                tsslState.Text="AsterMax Solve: SOLUTION_CURRENT";
                ShowAsterMaxIntegratedResult(null);
            }
            catch(Exception ex)
            {
                _asterMaxSolveLastError=ex;
                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";
                if(!_asterMaxUiAuditMode)
                    CaeGlobals.MessageBoxes.ShowError("AsterMax Solve blocked: "+ex.Message);
            }
            finally
            {
                if(heartbeat!=null)
                {
                    heartbeat.Stop();
                    heartbeat.Dispose();
                }
                _asterMaxSolveInProgress=false;
                if(uiBusySet && !IsDisposed && !Disposing) SetAsterMaxSolveUiBusy(false);
            }
        }
    }
}
'@
$s=[regex]::Replace($s,$pattern,$replacement.TrimEnd(),1)
Set-Content $solvePath $s -Encoding UTF8

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=(Get-Content $auditPath -Raw).Replace("`r`n","`n")
$old=@'
            C1020ClickRibbonButton("Solve");
            Application.DoEvents();
            C1020CaptureStage(directory, rows, previousStates, 8, "solution", "Solution", "ax-solution",
'@
$new=@'
            C1020ClickRibbonButton("Solve");
            RunAsterMaxNativeSolve(); // second request must be rejected while the first solve is active
            C1020WaitForSolveCompletion(600);
            Application.DoEvents();
            C1020CaptureStage(directory, rows, previousStates, 8, "solution", "Solution", "ax-solution",
'@
$old=$old.Replace("`r`n","`n"); $new=$new.Replace("`r`n","`n")
$a=Replace-Required $a $old $new

$waitAnchor='        private int C1020State(string key)'
$waitMethod=@'
        private void C1020WaitForSolveCompletion(int timeoutSeconds)
        {
            DateTime deadline=DateTime.UtcNow.AddSeconds(timeoutSeconds);
            while(_asterMaxSolveInProgress && DateTime.UtcNow<deadline)
            {
                Application.DoEvents();
                System.Threading.Thread.Sleep(25);
            }
            if(_asterMaxSolveInProgress)
                throw new TimeoutException("Native background Solve did not complete within "+timeoutSeconds+" seconds.");
            if(_asterMaxSolveLastError!=null)
                throw new InvalidOperationException("Native background Solve failed.",_asterMaxSolveLastError);
        }

'@
$a=Replace-Required $a $waitAnchor ($waitMethod+$waitAnchor)
$a=$a.Replace('["release"] = "C10.20.1"','["release"] = "C10.20.2"')
Set-Content $auditPath $a -Encoding UTF8

$crossPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceCrossChecks.cs'
$c=(Get-Content $crossPath -Raw).Replace("`r`n","`n")
$crossAnchor='            try'+"`n"+'            {'+"`n"+'                string solveWorkspace = _asterMaxSolveTransaction == null ? null : _asterMaxSolveTransaction.Workspace;'
$cross=@'
            try
            {
                bool workerSeparated=_asterMaxSolveUiThreadId!=0 && _asterMaxSolveWorkerThreadId!=0 &&
                                     _asterMaxSolveUiThreadId!=_asterMaxSolveWorkerThreadId;
                bool responsive=_asterMaxSolveUiHeartbeatCount>0;
                bool duplicateGuard=_asterMaxSolveDuplicateRequestsRejected>0;
                bool completed=!_asterMaxSolveInProgress && _asterMaxSolveLastError==null;
                var asyncEvidence=new JObject {
                    ["ui_thread_id"]=_asterMaxSolveUiThreadId,
                    ["worker_thread_id"]=_asterMaxSolveWorkerThreadId,
                    ["ui_heartbeat_count"]=_asterMaxSolveUiHeartbeatCount,
                    ["duplicate_requests_rejected"]=_asterMaxSolveDuplicateRequestsRejected,
                    ["worker_separated_from_ui"]=workerSeparated,
                    ["ui_events_processed_during_solve"]=responsive,
                    ["solve_completed_without_async_error"]=completed
                };
                File.WriteAllText(Path.Combine(directory,"async-solve-ui.json"),asyncEvidence.ToString(Formatting.Indented));
                bool pass=workerSeparated && responsive && duplicateGuard && completed;
                add("async_solve_ui",pass ? "PASS" : "FAIL",
                    pass ? "Solver/postprocess ran on a worker thread while the WinForms UI processed heartbeat events; duplicate Solve was rejected." :
                           "Background Solve responsiveness or duplicate-request guard did not satisfy the runtime contract.",
                    new JObject { ["file"]="async-solve-ui.json" });
            }
            catch(Exception ex)
            {
                add("async_solve_ui","FAIL",ex.Message,null);
            }

'@
$c=Replace-Required $c $crossAnchor ($cross+$crossAnchor)
Set-Content $crossPath $c -Encoding UTF8

Write-Host 'C10.20.2 asynchronous native Solve UI hotfix applied.' -ForegroundColor Green
