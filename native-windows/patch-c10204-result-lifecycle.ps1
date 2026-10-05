param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.4 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$resultsPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$r=[regex]::Replace((Get-Content $resultsPath -Raw),"\r\n?","`n")

$fieldAnchor='        private bool _axRefreshingResults;'
$r=Replace-Required $r $fieldAnchor ($fieldAnchor+"`n"+'        private bool _asterMaxPreviousResultsRetained;')

$noResultsOld=@'
                if (_asterMaxLoadedResults == null)
                {
                    _modelTree.SetAsterMaxResultFields(new string[0], "Not solved", false);
                    return;
                }
'@
$noResultsNew=@'
                if (_asterMaxLoadedResults == null)
                {
                    _modelTree.SetAsterMaxResultFields(new string[0],
                        _asterMaxSolveInProgress ? "Solving..." : "Not solved", false);
                    return;
                }
'@
$noResultsOld=[regex]::Replace($noResultsOld,"\r\n?","`n")
$noResultsNew=[regex]::Replace($noResultsNew,"\r\n?","`n")
$r=Replace-Required $r $noResultsOld $noResultsNew

$currentOld='                    _modelTree.SetAsterMaxResultFields(_asterMaxLoadedResults.AvailableFields(), "Current", true);'
$currentNew=@'
                    string currentLabel=_asterMaxSolveInProgress ? "Previous solution - new solve running" :
                        (_asterMaxPreviousResultsRetained ? "Previous successful solution retained" : "Current");
                    _modelTree.SetAsterMaxResultFields(_asterMaxLoadedResults.AvailableFields(),currentLabel,!_asterMaxSolveInProgress);
'@
$currentNew=[regex]::Replace($currentNew,"\r\n?","`n").TrimEnd()
$r=Replace-Required $r $currentOld $currentNew

$manualOld='                        _asterMaxLoadedResults = candidate;'
$manualNew=$manualOld+"`n"+'                        _asterMaxPreviousResultsRetained = false;'
$r=Replace-Required $r $manualOld $manualNew

$infoOld='            if (_asterMaxLoadedResults != null) text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;'
$infoNew=@'
            if (_asterMaxLoadedResults != null)
            {
                text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
                if (_asterMaxPreviousResultsRetained)
                    text += "\r\nStatus: previous successful result retained after a later Solve did not complete successfully.";
            }
'@
$infoNew=[regex]::Replace($infoNew,"\r\n?","`n").TrimEnd()
$r=Replace-Required $r $infoOld $infoNew

$resetOld='            _asterMaxLoadedResults=null;'
$resetNew=$resetOld+"`n"+'            _asterMaxPreviousResultsRetained=false;'
$r=Replace-Required $r $resetOld $resetNew
Set-Content $resultsPath $r -Encoding UTF8

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")

$localAnchor='            CaeModel.FeModel solveModel=null;'
$s=Replace-Required $s $localAnchor ($localAnchor+"`n"+'            AsterMaxResultsBundle previousResults=_asterMaxLoadedResults;')

$busyAnchor=@'
                SetAsterMaxSolveUiBusy(true);
                uiBusySet=true;

                heartbeat=
'@
$busyNew=@'
                SetAsterMaxSolveUiBusy(true);
                uiBusySet=true;
                _asterMaxPreviousResultsRetained=previousResults!=null;
                ShowAsterMaxModelWorkspace();
                RefreshAsterMaxResultAvailability();

                heartbeat=
'@
$busyAnchor=[regex]::Replace($busyAnchor,"\r\n?","`n")
$busyNew=[regex]::Replace($busyNew,"\r\n?","`n")
$s=Replace-Required $s $busyAnchor $busyNew

$successAnchor='                _asterMaxLoadedResults=completedBundle;'
$successNew='                _asterMaxLoadedResults=completedBundle;'+"`n"+'                _asterMaxPreviousResultsRetained=false;'
$s=Replace-Required $s $successAnchor $successNew

$finallyAnchor=@'
                _asterMaxSolveInProgress=false;
                if(uiBusySet && !IsDisposed && !Disposing) SetAsterMaxSolveUiBusy(false);
'@
$finallyNew=@'
                _asterMaxSolveInProgress=false;
                if(uiBusySet && !IsDisposed && !Disposing) SetAsterMaxSolveUiBusy(false);
                if(!IsDisposed && !Disposing) RefreshAsterMaxResultAvailability();
'@
$finallyAnchor=[regex]::Replace($finallyAnchor,"\r\n?","`n")
$finallyNew=[regex]::Replace($finallyNew,"\r\n?","`n")
$s=Replace-Required $s $finallyAnchor $finallyNew
Set-Content $solvePath $s -Encoding UTF8

Write-Host 'C10.20.4 previous-result lifecycle hotfix applied.' -ForegroundColor Green
