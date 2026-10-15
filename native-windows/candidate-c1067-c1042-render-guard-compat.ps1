param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$designerPath = Join-Path $Root 'vtkControl/vtkControl.Designer.cs'
foreach($p in @($vtkPath,$designerPath)){ if(!(Test-Path $p)){ throw "C10.67 missing: $p" } }

$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$d=[regex]::Replace((Get-Content $designerPath -Raw),"\r\n?","`n")

$activeDecl='        private bool _asterMaxRenderRequestActive;'
$pendingDecl='        private bool _asterMaxRenderPending;'
$lockAnchor='        private object myLock = new object();'

$activeDeclCount=([regex]::Matches($v,[regex]::Escape($activeDecl))).Count
$pendingDeclCount=([regex]::Matches($v,[regex]::Escape($pendingDecl))).Count
$renderUsesActive=$v.Contains('if (_asterMaxRenderRequestActive)')
$renderSetsPending=$v.Contains('_asterMaxRenderPending = true;')
$paintUsesActive=$d.Contains('_asterMaxRenderRequestActive')
$paintUsesPending=$d.Contains('_asterMaxRenderPending')

# C10.30 must still be semantically present. Never manufacture a guard when its
# render/paint behavior has disappeared; that would hide a real regression.
if(-not ($renderUsesActive -and $renderSetsPending -and $paintUsesActive -and $paintUsesPending)){
    throw ('C10.67 C10.30 render guard behavior missing: RenderActive={0} RenderPending={1} PaintActive={2} PaintPending={3}' -f $renderUsesActive,$renderSetsPending,$paintUsesActive,$paintUsesPending)
}
if($activeDeclCount -gt 1 -or $pendingDeclCount -gt 1){
    throw "C10.67 duplicate render guard declarations: active=$activeDeclCount pending=$pendingDeclCount"
}
if(-not $v.Contains($lockAnchor)){ throw 'C10.67 vtk myLock anchor missing.' }

$normalized=$false
$pair=$activeDecl+"`n"+$pendingDecl
if(-not $v.Contains($pair)){
    # Later patches are allowed to insert fields between the C10.30 declarations.
    # C10.42 historically required textual adjacency. Normalize declarations only;
    # render behavior is required above and remains untouched.
    if($activeDeclCount -eq 1){ $v=$v.Replace($activeDecl+"`n",'').Replace($activeDecl,'') }
    if($pendingDeclCount -eq 1){ $v=$v.Replace($pendingDecl+"`n",'').Replace($pendingDecl,'') }
    $v=$v.Replace($lockAnchor,$lockAnchor+"`n"+$activeDecl+"`n"+$pendingDecl)
    $normalized=$true
}

# Recheck exact single declarations and semantic behavior after normalization.
if((([regex]::Matches($v,[regex]::Escape($activeDecl))).Count) -ne 1){ throw 'C10.67 active declaration normalization failed.' }
if((([regex]::Matches($v,[regex]::Escape($pendingDecl))).Count) -ne 1){ throw 'C10.67 pending declaration normalization failed.' }
if(-not $v.Contains($pair)){ throw 'C10.67 C10.42-compatible declaration pair not established.' }
Set-Content $vtkPath $v -Encoding UTF8

if($OutDir){
    New-Item -ItemType Directory -Force $OutDir | Out-Null
    [ordered]@{
        candidate='C10.67'
        purpose='C10.30/C10.42 render-guard composition compatibility'
        render_guard_behavior_verified=$true
        declarations_normalized=$normalized
        active_declarations_before=$activeDeclCount
        pending_declarations_before=$pendingDeclCount
        performance='NOT_RUN'
        benchmark_values_invented=$false
    } | ConvertTo-Json | Set-Content (Join-Path $OutDir 'evidence.json') -Encoding UTF8
}
Write-Host ("C10.67: C10.30 render guard semantic behavior verified; declarations normalized={0}." -f $normalized) -ForegroundColor Green
