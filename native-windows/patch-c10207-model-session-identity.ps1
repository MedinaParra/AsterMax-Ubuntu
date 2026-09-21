param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.7 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$resultsPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$r=[regex]::Replace((Get-Content $resultsPath -Raw),"\r\n?","`n")

$fieldAnchor='        private bool _asterMaxCloseAfterSolveCancel;'
$r=Replace-Required $r $fieldAnchor ($fieldAnchor+"`n"+'        private long _asterMaxModelSessionRevision;')

$resetAnchor=@'
        private void ResetAsterMaxIntegratedResults()
        {
            ShowAsterMaxModelWorkspace();
'@
$resetNew=@'
        private void ResetAsterMaxIntegratedResults()
        {
            System.Threading.Interlocked.Increment(ref _asterMaxModelSessionRevision);
            ShowAsterMaxModelWorkspace();
'@
$resetAnchor=[regex]::Replace($resetAnchor,"\r\n?","`n")
$resetNew=[regex]::Replace($resetNew,"\r\n?","`n")
$r=Replace-Required $r $resetAnchor $resetNew
Set-Content $resultsPath $r -Encoding UTF8

$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")

$auditField='        private int _asterMaxSolveDuplicateRequestsRejected;'
$auditFields=@'
        private int _asterMaxSolveDuplicateRequestsRejected;
        private CaeModel.FeModel _asterMaxSolveFrozenModelInstance;
        private long _asterMaxSolveFrozenSessionRevision;
        private bool _asterMaxSolveModelSessionPreserved;
'@
$s=Replace-Required $s $auditField $auditFields.TrimEnd()

$captureOld=@'
                solveModel=_controller.Model;
                string work=_controller.Settings.GetWorkDirectory();
'@
$captureNew=@'
                solveModel=_controller.Model;
                _asterMaxSolveFrozenModelInstance=solveModel;
                _asterMaxSolveFrozenSessionRevision=_asterMaxModelSessionRevision;
                _asterMaxSolveModelSessionPreserved=false;
                string work=_controller.Settings.GetWorkDirectory();
'@
$captureOld=[regex]::Replace($captureOld,"\r\n?","`n")
$captureNew=[regex]::Replace($captureNew,"\r\n?","`n")
$s=Replace-Required $s $captureOld $captureNew

$publishOld=@'
                if(!Object.ReferenceEquals(_asterMaxSolveTransaction,transaction))
                    throw new InvalidOperationException("Active solve transaction changed while the background solve was running.");

                _asterMaxLoadedResults=completedBundle;
'@
$publishNew=@'
                if(!Object.ReferenceEquals(_asterMaxSolveTransaction,transaction))
                    throw new InvalidOperationException("Active solve transaction changed while the background solve was running.");
                if(_controller==null || !Object.ReferenceEquals(_controller.Model,solveModel))
                    throw new InvalidOperationException("Active model instance changed while the background solve was running; results were not published.");
                if(_asterMaxModelSessionRevision!=_asterMaxSolveFrozenSessionRevision)
                    throw new InvalidOperationException("Active model session changed while the background solve was running; results were not published.");

                _asterMaxSolveModelSessionPreserved=true;
                _asterMaxLoadedResults=completedBundle;
'@
$publishOld=[regex]::Replace($publishOld,"\r\n?","`n")
$publishNew=[regex]::Replace($publishNew,"\r\n?","`n")
$s=Replace-Required $s $publishOld $publishNew
Set-Content $solvePath $s -Encoding UTF8

$crossPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceCrossChecks.cs'
$c=[regex]::Replace((Get-Content $crossPath -Raw),"\r\n?","`n")

$cloadAnchor=@'
            try
            {
                string solveWorkspace = _asterMaxSolveTransaction == null ? null : _asterMaxSolveTransaction.Workspace;
'@
$sessionCheck=@'
            try
            {
                bool sameInstance=_asterMaxSolveFrozenModelInstance!=null && _controller!=null &&
                                  Object.ReferenceEquals(_controller.Model,_asterMaxSolveFrozenModelInstance);
                bool sameRevision=_asterMaxModelSessionRevision==_asterMaxSolveFrozenSessionRevision;
                bool publicationGuard=_asterMaxSolveModelSessionPreserved;
                var sessionEvidence=new JObject {
                    ["same_model_instance"]=sameInstance,
                    ["same_session_revision"]=sameRevision,
                    ["publication_guard_passed"]=publicationGuard,
                    ["active_session_revision"]=_asterMaxModelSessionRevision,
                    ["frozen_session_revision"]=_asterMaxSolveFrozenSessionRevision
                };
                File.WriteAllText(Path.Combine(directory,"model-session-identity.json"),sessionEvidence.ToString(Formatting.Indented));
                bool pass=sameInstance && sameRevision && publicationGuard;
                add("model_session_identity",pass ? "PASS" : "FAIL",
                    pass ? "Result publication stayed bound to the same FeModel instance and model-session revision." :
                           "The active model instance/session no longer matches the frozen Solve session.",
                    new JObject { ["file"]="model-session-identity.json" });
            }
            catch(Exception ex)
            {
                add("model_session_identity","FAIL",ex.Message,null);
            }

'@
$cloadAnchor=[regex]::Replace($cloadAnchor,"\r\n?","`n")
$sessionCheck=[regex]::Replace($sessionCheck,"\r\n?","`n")
if($c.Contains('add("model_session_identity"'))
{
    Write-Host 'C10.20.7 model-session cross-check already present.'
}
else
{
    $cloadIndex=$c.IndexOf($cloadAnchor,[StringComparison]::Ordinal)
    if($cloadIndex -lt 0)
    {
        throw 'C10.20.7 structural anchor missing: cload_semantics cross-check entry'
    }
    $c=$c.Substring(0,$cloadIndex)+$sessionCheck+$c.Substring($cloadIndex)
}
Set-Content $crossPath $c -Encoding UTF8

Write-Host 'C10.20.7 model-session identity publication guard applied.' -ForegroundColor Green
