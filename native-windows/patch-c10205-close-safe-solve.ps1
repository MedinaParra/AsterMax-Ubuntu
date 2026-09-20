param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.5 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$resultsPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$r=[regex]::Replace((Get-Content $resultsPath -Raw),"\r\n?","`n")

$fieldAnchor='        private bool _asterMaxPreviousResultsRetained;'
$r=Replace-Required $r $fieldAnchor ($fieldAnchor+"`n"+'        private bool _asterMaxCloseAfterSolveCancel;')

$initOld=@'
            _modelTree.AsterMaxModelTreeChanged += RefreshAsterMaxResultAvailability;
            Disposed += (s,e) => ResetAsterMaxIntegratedResults();
'@
$initNew=@'
            _modelTree.AsterMaxModelTreeChanged += RefreshAsterMaxResultAvailability;
            FormClosing += AsterMaxFormClosingDuringSolve;
            Disposed += (s,e) => ResetAsterMaxIntegratedResults();
'@
$initOld=[regex]::Replace($initOld,"\r\n?","`n")
$initNew=[regex]::Replace($initNew,"\r\n?","`n")
$r=Replace-Required $r $initOld $initNew

$methodAnchor='        private void RefreshAsterMaxResultAvailability()'
$closeMethod=@'
        private void AsterMaxFormClosingDuringSolve(object sender, FormClosingEventArgs e)
        {
            if(!_asterMaxSolveInProgress) return;
            e.Cancel=true;
            _asterMaxCloseAfterSolveCancel=true;
            tsslState.Text="AsterMax Solve: cancelling before close";
            if(_asterMaxSolveTransaction!=null)
                _asterMaxSolveTransaction.RequestCancel();
        }

'@
$r=Replace-Required $r $methodAnchor ($closeMethod+$methodAnchor)

$resetOld=@'
            _asterMaxLoadedResults=null;
            _asterMaxPreviousResultsRetained=false;
            _asterMaxSolveTransaction=null;
'@
$resetNew=@'
            _asterMaxLoadedResults=null;
            _asterMaxPreviousResultsRetained=false;
            _asterMaxCloseAfterSolveCancel=false;
            _asterMaxSolveTransaction=null;
'@
$resetOld=[regex]::Replace($resetOld,"\r\n?","`n")
$resetNew=[regex]::Replace($resetNew,"\r\n?","`n")
$r=Replace-Required $r $resetOld $resetNew
Set-Content $resultsPath $r -Encoding UTF8

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")

$finallyOld=@'
                _asterMaxSolveInProgress=false;
                if(uiBusySet && !IsDisposed && !Disposing) SetAsterMaxSolveUiBusy(false);
                if(!IsDisposed && !Disposing) RefreshAsterMaxResultAvailability();
'@
$finallyNew=@'
                bool closeAfterSolveCancel=_asterMaxCloseAfterSolveCancel;
                _asterMaxCloseAfterSolveCancel=false;
                _asterMaxSolveInProgress=false;
                if(uiBusySet && !IsDisposed && !Disposing) SetAsterMaxSolveUiBusy(false);
                if(!IsDisposed && !Disposing) RefreshAsterMaxResultAvailability();
                if(closeAfterSolveCancel && !IsDisposed && !Disposing)
                    BeginInvoke(new Action(Close));
'@
$finallyOld=[regex]::Replace($finallyOld,"\r\n?","`n")
$finallyNew=[regex]::Replace($finallyNew,"\r\n?","`n")
$s=Replace-Required $s $finallyOld $finallyNew

Set-Content $solvePath $s -Encoding UTF8

Write-Host 'C10.20.5 close-safe Solve lifecycle hotfix applied.' -ForegroundColor Green
