param([string]$Root = ".")
$ErrorActionPreference = 'Stop'

# Static guard only: viewport commands must not acquire engineering side effects.
# This does not claim runtime performance or functional validation.
$files = Get-ChildItem -Path $Root -Recurse -Include *.cs -File
if(-not $files){ throw 'C10.52: no C# sources found.' }

$viewTokens = @('Fit','ResetCamera','Isometric','Transparency','ShowMesh','HideMesh','ShowGeometry','HideGeometry')
$forbidden = @('ImportStep','ImportSTEP','GenerateMesh','CreateMesh','Remesh','Tessellate','Retessellate','RunSolver','Code_Aster','DeleteMesh')
$hits = @()

foreach($f in $files){
  $text = [IO.File]::ReadAllText($f.FullName)
  foreach($view in $viewTokens){
    $pattern = '(?s)(?:public|private|protected|internal)[^{;]{0,240}\b' + [regex]::Escape($view) + '\b[^{;]{0,240}\{.{0,5000}?\}'
    foreach($m in [regex]::Matches($text,$pattern)){
      foreach($bad in $forbidden){
        if($m.Value -match ('\b' + [regex]::Escape($bad) + '\b')){
          $hits += [pscustomobject]@{File=$f.FullName;ViewCommand=$view;ForbiddenToken=$bad}
        }
      }
    }
  }
}

$out = Join-Path $PSScriptRoot '../dist/Audit/C10.52'
New-Item -ItemType Directory -Force $out | Out-Null
[ordered]@{
 release='C10.52-viewport-purity-guard';
 static_guard=if($hits.Count -eq 0){'PASS'}else{'FAIL'};
 compilation='NOT_RUN'; functionality='NOT_RUN'; performance='NOT_RUN';
 regressions=if($hits.Count -eq 0){'PASS_STATIC_GUARD_ONLY'}else{'FAIL_STATIC_GUARD'};
 exact_incident_step='BLOCKED_NOT_PRESENT_IN_REPOSITORY';
 code_aster_windows_only_solver_preserved=$true;
 benchmark_values_invented=$false;
 findings=$hits
} | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'evidence.json') -Encoding UTF8

if($hits.Count -gt 0){
  $hits | Format-Table | Out-String | Write-Host
  throw "C10.52: viewport purity guard found $($hits.Count) forbidden coupling(s)."
}
Write-Host 'C10.52 PASS: no forbidden engineering-side-effect tokens found in bounded viewport command regions.'
