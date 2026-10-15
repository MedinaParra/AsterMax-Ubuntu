param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$designerPath = Join-Path $Root 'vtkControl/vtkControl.Designer.cs'
foreach($p in @($vtkPath,$designerPath)){ if(!(Test-Path $p)){ throw "C10.69 missing: $p" } }

$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$d=[regex]::Replace((Get-Content $designerPath -Raw),"\r\n?","`n")

$activeDecl='        private bool _asterMaxRenderRequestActive;'
$pendingDecl='        private bool _asterMaxRenderPending;'
$scheduledDecl='        private bool _asterMaxRenderScheduled;'
$lockAnchor='        private object myLock = new object();'

$activeDeclCount=([regex]::Matches($v,[regex]::Escape($activeDecl))).Count
$pendingDeclCount=([regex]::Matches($v,[regex]::Escape($pendingDecl))).Count
$renderUsesActive=$v.Contains('if (_asterMaxRenderRequestActive)')
$renderSetsPending=$v.Contains('_asterMaxRenderPending = true;')
$paintUsesActive=$d.Contains('_asterMaxRenderRequestActive')
$paintUsesPending=$d.Contains('_asterMaxRenderPending')

if(-not ($renderUsesActive -and $renderSetsPending -and $paintUsesActive -and $paintUsesPending)){
    throw ('C10.69 C10.30 render guard behavior missing: RenderActive={0} RenderPending={1} PaintActive={2} PaintPending={3}' -f $renderUsesActive,$renderSetsPending,$paintUsesActive,$paintUsesPending)
}
if($activeDeclCount -ne 1 -or $pendingDeclCount -ne 1){
    throw "C10.69 render guard declarations invalid: active=$activeDeclCount pending=$pendingDeclCount"
}
if(-not $v.Contains($lockAnchor)){ throw 'C10.69 vtk myLock anchor missing.' }

# C10.42's historical textual anchor is brittle after the cumulative patch chain.
# Establish only the scheduling field it intends to add, after proving C10.30 behavior.
# C10.42 then skips its fragile declaration replacement and continues with its render logic.
$scheduledAdded=$false
if(-not $v.Contains('_asterMaxRenderScheduled')){
    $v=$v.Replace($pendingDecl,$pendingDecl+"`n"+$scheduledDecl)
    $scheduledAdded=$true
}
if((([regex]::Matches($v,[regex]::Escape($scheduledDecl))).Count) -ne 1){
    throw 'C10.69 scheduled render declaration establishment failed.'
}
Set-Content $vtkPath $v -Encoding UTF8

if($OutDir){
    New-Item -ItemType Directory -Force $OutDir | Out-Null
    [ordered]@{
        candidate='C10.69'
        purpose='C10.30/C10.42 cumulative render-guard compatibility'
        render_guard_behavior_verified=$true
        scheduled_field_added=$scheduledAdded
        active_declarations_before=$activeDeclCount
        pending_declarations_before=$pendingDeclCount
        performance='NOT_RUN'
        benchmark_values_invented=$false
    } | ConvertTo-Json | Set-Content (Join-Path $OutDir 'evidence.json') -Encoding UTF8
}
Write-Host ("C10.69: C10.30 behavior verified; C10.42 scheduling field ready; added={0}." -f $scheduledAdded) -ForegroundColor Green
