param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Once([string]$Text,[string]$Old,[string]$New) {
    $Old=[regex]::Replace($Old,"\r\n?","`n").TrimEnd()
    $New=[regex]::Replace($New,"\r\n?","`n").TrimEnd()
    if(([regex]::Matches($Text,[regex]::Escape($Old))).Count -ne 1) {
        throw "C10.41 repair anchor must occur exactly once: $Old"
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

# C10.41 RC1: the reference-material catalogue grew from six to fifteen entries.
# Keep the native-dialog audit aligned with the packaged catalogue and validate all
# current entries instead of failing on the historical C10.10.1 count.
$statesPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowStates.cs'
$states=[regex]::Replace((Get-Content $statesPath -Raw),"\r\n?","`n")
$countOld=@'
            var materials=library.Items.SelectMany(category=>category.Items).Select(item=>item.Tag).ToArray();
            if(materials.Length!=6||materials.Any(m=>m==null)) throw new InvalidOperationException("The six reference materials did not load.");
'@
$countNew=@'
            var materials=library.Items.SelectMany(category=>category.Items).Select(item=>item.Tag).ToArray();
            const int expectedReferenceMaterialCount=15;
            if(materials.Length!=expectedReferenceMaterialCount||materials.Any(m=>m==null))
                throw new InvalidOperationException("The reference material catalogue did not load all "+expectedReferenceMaterialCount+" entries.");
'@
$states=Replace-Once $states $countOld $countNew
$copyOld=@'
                if(copied!=6||list.Items.Count-initial!=6||copiedNames.Select(n=>(string)n).Distinct().Count()!=6)
                    throw new InvalidOperationException("Native library copy-to-model buttons did not copy six distinct materials.");
'@
$copyNew=@'
                if(copied!=materials.Length||list.Items.Count-initial!=materials.Length||
                   copiedNames.Select(n=>(string)n).Distinct().Count()!=materials.Length)
                    throw new InvalidOperationException("Native library copy-to-model buttons did not copy every distinct reference material.");
'@
$states=Replace-Once $states $copyOld $copyNew

# The native material-library dialog deliberately renames a copied material when its
# name already exists in the model (for example the automatically assigned
# Acero_Estructural becomes Acero_Estructural_Library-1). The audit must verify that
# exact collision policy and the material properties, rather than incorrectly
# requiring the source and destination names to remain identical.
$nameOld=@'
                        tree.SelectedNode=node;
                        method.Invoke(dialog,new object[]{null,EventArgs.Empty});
                        var expected=(Material)node.Tag;
                        var actual=list.Items[list.Items.Count-1].Tag as Material;
                        if(actual==null||actual.Name!=expected.Name)
                            throw new InvalidOperationException("Library copied a different material than the selected node: "+expected.Name);
'@
$nameNew=@'
                        tree.SelectedNode=node;
                        var expected=(Material)node.Tag;
                        string expectedCopyName=expected.Name;
                        int copySuffix=1;
                        while(list.Items.ContainsKey(expectedCopyName))
                        {
                            expectedCopyName=expected.Name+"_Library-"+copySuffix;
                            copySuffix++;
                        }
                        method.Invoke(dialog,new object[]{null,EventArgs.Empty});
                        var actual=list.Items[list.Items.Count-1].Tag as Material;
                        if(actual==null||actual.Name!=expectedCopyName)
                            throw new InvalidOperationException("Library copy did not follow the native duplicate-name policy for: "+expected.Name+
                                " | expected="+expectedCopyName+" actual="+(actual==null?"<null>":actual.Name));
'@
$states=Replace-Once $states $nameOld $nameNew
Set-Content $statesPath $states -Encoding UTF8
Write-Host 'C10.41 material-library audit synchronized with the 15-entry catalogue and native duplicate-name policy.' -ForegroundColor Green

# C10.41 RC1: persisted PMX result restoration must run only after the model-open
# worker has completed. The earlier hook lived inside Controller.Open, which is called
# from OpenAsync through Task.Run. That made result recovery timing-dependent: a fast
# run could restore while Opening was active, while another run could miss recovery
# entirely. Move the hook to FrmMain.OpenAsync on the WinForms thread, after the model
# and result unit systems are initialized but before Opening is released.
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$controllerSource=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$legacyRestore='            if(extension==".pmx") _form.RestoreAsterMaxProjectResults(fileName);'
if(-not $controllerSource.Contains($legacyRestore)) {
    throw 'C10.41 legacy Controller.Open result-restore hook missing before UI-thread migration.'
}
$controllerSource=$controllerSource.Replace($legacyRestore+"`n",'')
if($controllerSource.Contains($legacyRestore)) {
    throw 'C10.41 Controller.Open result-restore hook survived UI-thread migration.'
}
Set-Content $controllerPath $controllerSource -Encoding UTF8

$frmPath=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$frm=[regex]::Replace((Get-Content $frmPath -Raw),"\r\n?","`n")
$openOld=@'
                // If the model space or the unit system are undefined
                if (_controller.ModelInitialized) IfNeededSelectAndSetNewModelProperties();
                if (_controller.ResultsInitialized) SelectResultsUnitSystem();
'@
$openNew=@'
                // If the model space or the unit system are undefined
                if (_controller.ModelInitialized) IfNeededSelectAndSetNewModelProperties();
                if (_controller.ResultsInitialized) SelectResultsUnitSystem();
                // Restore persisted AsterMax results only after the PMX worker has fully
                // reconstructed the model. This runs on the WinForms synchronization context.
                if (Path.GetExtension(fileName).Equals(".pmx", StringComparison.OrdinalIgnoreCase))
                    RestoreAsterMaxProjectResults(fileName);
'@
$frm=Replace-Once $frm $openOld $openNew
if(-not $frm.Contains('RestoreAsterMaxProjectResults(fileName);')) {
    throw 'C10.41 UI-thread result-restore hook was not installed.'
}
Set-Content $frmPath $frm -Encoding UTF8
Write-Host 'C10.41 PMX result restore migrated from Controller.Open worker to completed FrmMain.OpenAsync UI flow.' -ForegroundColor Green
