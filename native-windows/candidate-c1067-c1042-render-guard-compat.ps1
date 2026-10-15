param(
    [Parameter(Mandatory=$true)][string]$Root,
    [string]$OutDir
)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$designerPath = Join-Path $Root 'vtkControl/vtkControl.Designer.cs'
foreach($p in @($vtkPath,$designerPath)){ if(!(Test-Path $p)){ throw "C10.69b missing: $p" } }

$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$d=[regex]::Replace((Get-Content $designerPath -Raw),"\r\n?","`n")

$activeDecl='        private bool _asterMaxRenderRequestActive;'
$pendingDecl='        private bool _asterMaxRenderPending;'
$scheduledDecl='        private bool _asterMaxRenderScheduled;'

$activeDeclCount=([regex]::Matches($v,[regex]::Escape($activeDecl))).Count
$pendingDeclCount=([regex]::Matches($v,[regex]::Escape($pendingDecl))).Count
$renderUsesActive=$v.Contains('if (_asterMaxRenderRequestActive)')
$renderSetsPending=$v.Contains('_asterMaxRenderPending = true;')
$paintUsesActive=$d.Contains('_asterMaxRenderRequestActive')
$paintUsesPending=$d.Contains('_asterMaxRenderPending')

if(-not ($renderUsesActive -and $renderSetsPending -and $paintUsesActive -and $paintUsesPending)){
    throw ('C10.69b C10.30 render guard behavior missing: RenderActive={0} RenderPending={1} PaintActive={2} PaintPending={3}' -f $renderUsesActive,$renderSetsPending,$paintUsesActive,$paintUsesPending)
}
if($activeDeclCount -ne 1 -or $pendingDeclCount -ne 1){
    throw "C10.69b render guard declarations invalid: active=$activeDeclCount pending=$pendingDeclCount"
}

# C10.42 historically matches an exact RenderSceene body. The cumulative chain can
# preserve the same C10.30 semantics with different whitespace/body layout. After
# proving the guard is present in both RenderSceene and OnPaint, normalize only this
# method to the verified C10.30 contract so C10.42 can safely add render coalescing.
$oldRender=@'
        private void RenderSceene()
        {
            if (!_renderingOn || IsDisposed || !IsHandleCreated) return;
            if (_asterMaxRenderRequestActive)
            {
                _asterMaxRenderPending = true;
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(new Action(RenderSceene));
                return;
            }
            Invalidate();
        }
'@
$methodPattern='(?ms)^        private void RenderSceene\(\)\n        \{.*?^        \}'
$matches=[regex]::Matches($v,$methodPattern)
if($matches.Count -ne 1){ throw "C10.69b expected exactly one RenderSceene method; found $($matches.Count)." }
$current=$matches[0].Value
$currentSemantics=($current.Contains('if (!_renderingOn || IsDisposed || !IsHandleCreated) return;') -and $current.Contains('if (_asterMaxRenderRequestActive)') -and $current.Contains('_asterMaxRenderPending = true;') -and $current.Contains('BeginInvoke(new Action(RenderSceene));') -and $current.Contains('Invalidate();'))
if(-not $currentSemantics){ throw 'C10.69b refuses to normalize RenderSceene because required C10.30 semantics are not all present.' }
$renderNormalized=$false
if($current -ne $oldRender.TrimEnd()){
    $v=$v.Substring(0,$matches[0].Index)+$oldRender.TrimEnd()+$v.Substring($matches[0].Index+$matches[0].Length)
    $renderNormalized=$true
}

# Establish the scheduling field C10.42 intends to add, after semantic verification.
$scheduledAdded=$false
if(-not $v.Contains('_asterMaxRenderScheduled')){
    $v=$v.Replace($pendingDecl,$pendingDecl+"`n"+$scheduledDecl)
    $scheduledAdded=$true
}
if((([regex]::Matches($v,[regex]::Escape($scheduledDecl))).Count) -ne 1){
    throw 'C10.69b scheduled render declaration establishment failed.'
}
Set-Content $vtkPath $v -Encoding UTF8

if($OutDir){
    New-Item -ItemType Directory -Force $OutDir | Out-Null
    [ordered]@{
        candidate='C10.69b'
        purpose='C10.30/C10.42 cumulative RenderSceene compatibility'
        render_guard_behavior_verified=$true
        render_body_normalized=$renderNormalized
        scheduled_field_added=$scheduledAdded
        performance='NOT_RUN'
        benchmark_values_invented=$false
    } | ConvertTo-Json | Set-Content (Join-Path $OutDir 'evidence.json') -Encoding UTF8
}
Write-Host ("C10.69b: C10.30 semantics verified; RenderSceene normalized={0}; scheduled field added={1}." -f $renderNormalized,$scheduledAdded) -ForegroundColor Green
