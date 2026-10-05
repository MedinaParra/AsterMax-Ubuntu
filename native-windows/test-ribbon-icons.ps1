param([Parameter(Mandatory=$true)][string]$Dist,
      [Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$distPath=(Resolve-Path $Dist).Path
$script:iconAssemblyRoots=@($distPath)
$script:iconAssemblyRoots += Get-ChildItem $distPath -Directory -Recurse | Select-Object -ExpandProperty FullName
[AppDomain]::CurrentDomain.add_AssemblyResolve({
    param($sender,$args)
    $file=(New-Object Reflection.AssemblyName($args.Name)).Name+'.dll'
    foreach($root in $script:iconAssemblyRoots){
        $candidate=Join-Path $root $file
        if(Test-Path $candidate){return [Reflection.Assembly]::LoadFrom($candidate)}
    }
    return $null
})
$assembly=[Reflection.Assembly]::LoadFrom((Join-Path $distPath 'AsterMax Mechanical.exe'))
$flags=[Reflection.BindingFlags]'Static,NonPublic,Public'
$form=$assembly.GetType('PrePoMax.FrmMain',$true)
$icons=$form.GetField('AxCommandIcons',$flags).GetValue($null)
$resources=$assembly.GetType('PrePoMax.Properties.Resources',$true)
$manager=$resources.GetProperty('ResourceManager',$flags).GetValue($null,$null)
$captions=@([regex]::Matches((Get-Content $Source -Raw),'CommandTile\("([^"]+)"') | ForEach-Object {$_.Groups[1].Value} | Select-Object -Unique)
if($captions.Count -eq 0){throw 'Final ribbon source did not expose any commands.'}
foreach($required in @('Pressure','Frictionless','Gravity','Surface Traction','Tablas de carga','Desplazamiento')){
    if($required -notin $captions){throw "Repaired ribbon command absent: $required"}
}
$rows=@()
foreach($caption in $captions){
    if(-not $icons.ContainsKey($caption)){throw "Command icon mapping missing: $caption"}
    $icon=$manager.GetObject($icons[$caption])
    if($icon -isnot [Drawing.Image]){throw "Native icon missing for $caption"}
    $rendered=$form.GetMethod('CreateAsterMaxCommandIcon',$flags).Invoke($null,@($icon,$caption,'MODEL'))
    if($rendered.Width -ne 32 -or $rendered.Height -ne 32){throw "Invalid command bitmap: $caption"}
    $rendered.Dispose()
    $rows += [ordered]@{caption=$caption;resource=$icons[$caption];status='PASS'}
}
$out=Join-Path $distPath 'Validation'
New-Item -ItemType Directory -Force $out | Out-Null
[ordered]@{scope='Compiled ribbon resource resolution and bitmap creation; GUI verified separately';status='PASS';commands=$rows} |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'ribbon-icons.json') -Encoding UTF8
Write-Host "PASS: $($rows.Count) compiled ribbon icons"
