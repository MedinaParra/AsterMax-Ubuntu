param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Once([string]$Text,[string]$Old,[string]$New) {
    $Old=[regex]::Replace($Old,"\r\n?","`n").TrimEnd()
    $New=[regex]::Replace($New,"\r\n?","`n").TrimEnd()
    if(([regex]::Matches($Text,[regex]::Escape($Old))).Count -ne 1) {
        throw "C10.41 asynchronous mesh audit anchor must occur exactly once: $Old"
    }
    return $Text.Replace($Old,$New)
}

$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$source=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")

# ImportGeneratedMesh synchronously dispatches tree/viewport updates to WinForms.
# Waiting on its terminal signal on that same UI thread deadlocks the import.
# Await the worker signal from the timer callback all the way down to the mesh
# command. The real message loop stays available; generation/import postconditions
# and the 180-second deadline remain mandatory.
$source=Replace-Once $source '            timer.Tick += (s, e) =>' '            timer.Tick += async (s, e) =>'
$source=Replace-Once $source '                    ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);' '                    await ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);'
$source=Replace-Once $source '        private void ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)' '        private async Task ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)'
$source=Replace-Once $source '            C10208RecordCommandSmoke(directory, commandSmoke, C10208ExerciseRealGenerateMesh(directory, model));' '            C10208RecordCommandSmoke(directory, commandSmoke, await C10208ExerciseRealGenerateMesh(directory, model));'
$source=Replace-Once $source '        private JObject C10208ExerciseRealGenerateMesh(string directory,FeModel model)' '        private async Task<JObject> C10208ExerciseRealGenerateMesh(string directory,FeModel model)'

$old=@'
            bool terminalObserved=_controller.AsterMaxWaitMeshAudit(180000);
            monotonic.Stop();

            // Pump once after the worker terminal signal so the async WinForms continuation can
            // publish its final UI state. This is not the synchronization primitive.
            Application.DoEvents();
'@
$new=@'
            bool terminalObserved=await Task.Run(() => _controller.AsterMaxWaitMeshAudit(180000));

            // The controller terminal signal precedes CreatePartMeshes' UI continuation.
            // Let that continuation run its finally/SetStateReady before later commands.
            long readyDeadline=monotonic.ElapsedMilliseconds+5000;
            while(terminalObserved && IsStateWorking() && monotonic.ElapsedMilliseconds<readyDeadline)
                await Task.Delay(25);
            bool uiReadyObserved=terminalObserved && !IsStateWorking();
            monotonic.Stop();
'@
$source=Replace-Once $source $old $new
$source=Replace-Once $source '                      generationSucceeded && importSucceeded && ribbonProducedMesh;' '                      generationSucceeded && importSucceeded && ribbonProducedMesh && uiReadyObserved;'
$source=Replace-Once $source '                ["terminal_signal_observed"]=terminalObserved,' @'
                ["terminal_signal_observed"]=terminalObserved,
                ["ui_ready_observed"]=uiReadyObserved,
                ["ui_thread_released_during_wait"]=true,
'@
$source=Replace-Once $source '                ["synchronization"]="CONTROLLER_TERMINAL_SIGNAL",' '                ["synchronization"]="ASYNC_CONTROLLER_TERMINAL_SIGNAL",'
Set-Content $path $source -Encoding UTF8
Write-Host 'C10.41 mesh audit awaits terminal completion without blocking the WinForms dispatcher.' -ForegroundColor Green
