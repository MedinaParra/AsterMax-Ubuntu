param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$Fixture,
  [Parameter(Mandatory=$true)][string]$Artifact,
  [ValidateSet('offscreen','astermax')][string]$Mode='offscreen'
)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Force $Artifact | Out-Null
$progress=Join-Path $Artifact ("C9.73_{0}_PROGRESS.json" -f $Mode)
function Stage([string]$name,[hashtable]$extra=@{}) {
  $o=[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');mode=$Mode;stage=$name;pid=$PID}
  foreach($k in $extra.Keys){$o[$k]=$extra[$k]}
  $o|ConvertTo-Json -Depth 5|Set-Content $progress -Encoding UTF8
  Write-Host ("C9.73 [{0}] {1}" -f $Mode,$name)
}

Stage 'worker_start'
$exe=Get-ChildItem $Root -Recurse -Filter 'AsterMax Mechanical.exe' | Where-Object {$_.FullName -match 'bin\\x64\\Release'} | Select-Object -First 1
if(-not $exe){throw 'AsterMax Mechanical.exe missing'}
$bin=$exe.Directory.FullName
[Environment]::CurrentDirectory=$bin
$global:c973root=$Root; $global:c973bin=$bin
[AppDomain]::CurrentDomain.add_AssemblyResolve({
  param($s,$a)
  $d=([Reflection.AssemblyName]$a.Name).Name+'.dll'
  $p=Join-Path $global:c973bin $d
  if(Test-Path $p){return [Reflection.Assembly]::LoadFrom($p)}
  $c=Get-ChildItem $global:c973root -Recurse -Filter $d -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match 'bin\\(x64\\)?Release|packages'} | Select-Object -First 1
  if($c){return [Reflection.Assembly]::LoadFrom($c.FullName)}
  return $null
})
Stage 'assembly_resolver_ready'

if($Mode -eq 'offscreen') {
  $vtkDll=Get-ChildItem $Root -Recurse -Filter 'Kitware.VTK.dll' -ErrorAction SilentlyContinue | Where-Object {$_.FullName -match 'packages|bin\\x64\\Release'} | Select-Object -First 1
  if(-not $vtkDll){throw 'Kitware.VTK.dll missing'}
  [Reflection.Assembly]::LoadFrom($vtkDll.FullName) | Out-Null
  Stage 'vtk_managed_loaded' @{vtk=$vtkDll.FullName}

  $ren=[Kitware.VTK.vtkRenderer]::New()
  $win=[Kitware.VTK.vtkRenderWindow]::New()
  $src=[Kitware.VTK.vtkCubeSource]::New()
  $map=[Kitware.VTK.vtkPolyDataMapper]::New()
  $actor=[Kitware.VTK.vtkActor]::New()
  $w2i=[Kitware.VTK.vtkWindowToImageFilter]::New()
  $writer=[Kitware.VTK.vtkPNGWriter]::New()
  try {
    Stage 'vtk_objects_created'
    $win.SetOffScreenRendering(1)
    $win.SetSize(640,480)
    $win.AddRenderer($ren)
    $map.SetInputConnection($src.GetOutputPort())
    $actor.SetMapper($map)
    $ren.AddActor($actor)
    $ren.ResetCamera()
    Stage 'offscreen_scene_ready'
    $win.Render()
    Stage 'offscreen_render_returned'
    $png=Join-Path $Artifact 'C9.73_VTK_OFFSCREEN.png'
    $w2i.SetInput($win)
    $w2i.SetInputBufferTypeToRGB()
    $w2i.ReadFrontBufferOff()
    $w2i.Update()
    $writer.SetInputConnection($w2i.GetOutputPort())
    $writer.SetFileName($png)
    $writer.Write()
    Stage 'offscreen_png_written' @{png=$png;bytes=(Get-Item $png).Length}
  }
  finally {
    foreach($x in @($writer,$w2i,$actor,$map,$src,$win,$ren)){if($null-ne$x){$x.Dispose()}}
  }
  exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Stage 'winforms_loaded'
$asm=[Reflection.Assembly]::LoadFrom($exe.FullName)
$bt=$asm.GetType('PrePoMax.AsterMaxResultsBundle',$true)
$ft=$asm.GetType('PrePoMax.AsterMaxResultsViewportForm',$true)
Stage 'astermax_assembly_loaded'
$bundle=$bt.GetMethod('Load',[Reflection.BindingFlags]'Public,Static').Invoke($null,@((Resolve-Path $Fixture).Path))
Stage 'bundle_loaded'
$form=[Activator]::CreateInstance($ft,[Reflection.BindingFlags]'Instance,NonPublic,Public',$null,@($bundle),$null)
Stage 'form_constructed'
try {
  $form.Show()
  Stage 'form_show_returned'
  [System.Windows.Forms.Application]::DoEvents()
  Stage 'doevents_1_returned'
  Start-Sleep -Milliseconds 750
  [System.Windows.Forms.Application]::DoEvents()
  Stage 'doevents_2_returned'
  $png=Join-Path $Artifact 'C9.73_ASTERMAX_FRAMEBUFFER.png'
  $contract=$ft.GetMethod('NativeFramebufferEvidenceContract',[Reflection.BindingFlags]'Instance,Public').Invoke($form,@())
  Stage 'contract_read' @{contract=$contract}
  $ft.GetMethod('CaptureNativeFramebuffer',[Reflection.BindingFlags]'Instance,Public').Invoke($form,@($png))
  Stage 'astermax_capture_returned' @{png=$png;bytes=(Get-Item $png).Length}
}
finally {
  try{$form.Close()}catch{}
  try{$form.Dispose()}catch{}
}
exit 0
