param([Parameter(Mandatory=$true)][string]$ScriptPath,[string]$OutDir)
$ErrorActionPreference='Stop'
if(!(Test-Path $ScriptPath)){ throw "C10.69c missing C10.42 script: $ScriptPath" }
$s=[regex]::Replace((Get-Content $ScriptPath -Raw),"\r\n?","`n")
$old=@'
if(-not $v.Contains('C10.42 large-assembly path: one queued paint')){
    if(-not $v.Contains($oldRender.TrimEnd())){ throw 'C10.42 C10.30 RenderSceene body not recognized.' }
    $v=$v.Replace($oldRender.TrimEnd(),$newRender.TrimEnd())
}
'@
$new=@'
if(-not $v.Contains('C10.42 large-assembly path: one queued paint')){
    # C10.69c: validate behavior rather than historical whitespace/body identity.
    $methodPattern='(?ms)^        private void RenderSceene\(\)\n        \{.*?^        \}'
    $renderMatches=[regex]::Matches($v,$methodPattern)
    if($renderMatches.Count -ne 1){ throw "C10.42 expected exactly one RenderSceene method; found $($renderMatches.Count)." }
    $renderBody=$renderMatches[0].Value
    $required=@(
        'if (!_renderingOn || IsDisposed || !IsHandleCreated) return;',
        'if (_asterMaxRenderRequestActive)',
        '_asterMaxRenderPending = true;',
        'BeginInvoke(new Action(RenderSceene));',
        'Invalidate();'
    )
    $missing=@($required | Where-Object { -not $renderBody.Contains($_) })
    if($missing.Count -gt 0){ throw ('C10.42 C10.30 RenderSceene semantics missing: '+($missing -join ' | ')) }
    $v=$v.Substring(0,$renderMatches[0].Index)+$newRender.TrimEnd()+$v.Substring($renderMatches[0].Index+$renderMatches[0].Length)
}
'@
if(-not $s.Contains($old.TrimEnd())){ throw 'C10.69c expected legacy C10.42 literal render check not found.' }
$s=$s.Replace($old.TrimEnd(),$new.TrimEnd())
Set-Content $ScriptPath $s -Encoding UTF8
if($OutDir){
  New-Item -ItemType Directory -Force $OutDir|Out-Null
  [ordered]@{candidate='C10.69c';target='C10.42';change='literal-to-semantic RenderSceene validation';performance='NOT_RUN';benchmark_values_invented=$false}|ConvertTo-Json|Set-Content (Join-Path $OutDir 'evidence.json') -Encoding UTF8
}
Write-Host 'C10.69c: C10.42 RenderSceene validation modernized from literal body match to required semantic tokens.' -ForegroundColor Green
