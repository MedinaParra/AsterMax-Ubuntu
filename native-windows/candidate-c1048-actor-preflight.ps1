param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'vtkControl/vtkMax/Actor/vtkMaxActor.cs'
if(!(Test-Path $path)){throw "C10.48 preflight missing: $path"}
$t=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")
function Normalize-Header([string]$text,[string]$pattern,[string]$replacement,[string]$name){
  $rx=[regex]::new($pattern,[System.Text.RegularExpressions.RegexOptions]::Singleline)
  $m=$rx.Matches($text)
  if($m.Count -ne 1){throw "C10.48 preflight $name expected 1 match, got $($m.Count)."}
  return $rx.Replace($text,$replacement,1)
}
$t=Normalize-Header $t '        public vtkMaxActor\(vtkMaxActorData data, bool extractVisualizationSurface, bool createNodalActor\)\s*:\s*this\(\)\s*\{' @'
        public vtkMaxActor(vtkMaxActorData data, bool extractVisualizationSurface, bool createNodalActor)
            : this()
        {
'@ 'three-argument actor constructor'
$t=Normalize-Header $t '        public vtkMaxActor\(vtkMaxActor sourceActor\)\s*:\s*this\(\)\s*\{' @'
        public vtkMaxActor(vtkMaxActor sourceActor)
          : this()
        {
'@ 'copy constructor'
$t=Normalize-Header $t '        public void SetAnimationFrame\(vtkMaxActorData data, int frameNumber\)\s*\{' @'
        public void SetAnimationFrame(vtkMaxActorData data, int frameNumber)
        {
'@ 'animation method'
Set-Content $path $t -Encoding UTF8
Write-Host 'C10.48 vtkMaxActor structural preflight PASS.' -ForegroundColor Green
