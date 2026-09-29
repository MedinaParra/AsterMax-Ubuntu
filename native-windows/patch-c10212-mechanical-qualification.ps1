param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){throw "C10.21 anchor missing: $Old"}
    return $Text.Replace($Old,$New)
}

$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
if(!(Test-Path $project)){throw 'C10.21 PrePoMax.csproj missing.'}
$p=Get-Content $project -Raw
if(-not $p.Contains('Forms\AsterMaxMechanicalQualification.cs')) {
    $anchor='<Compile Include="Forms\AsterMaxIntegratedResults.cs" />'
    if(-not $p.Contains($anchor)){throw 'C10.21 integrated-results compile anchor missing.'}
    $p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxMechanicalQualification.cs" />')
    Set-Content $project $p -Encoding UTF8
}

Copy-Item (Join-Path $PSScriptRoot 'AsterMaxMechanicalQualification.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxMechanicalQualification.cs') -Force

$integrated=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
if(!(Test-Path $integrated)){throw 'C10.21 integrated results source missing.'}
$s=Get-Content $integrated -Raw
$old='            if (_asterMaxLoadedResults != null) text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;'
$new=@'
            if (_asterMaxLoadedResults != null)
            {
                text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
                try
                {
                    text += "\r\n\r\n" + AsterMaxMechanicalQualification.Evaluate(_asterMaxLoadedResults).Describe();
                }
                catch(Exception ex)
                {
                    text += "\r\n\r\nMechanical Qualification: unavailable\r\n" + ex.Message;
                }
            }
'@
if($s.Contains($old)) {
    $s=$s.Replace($old,$new.TrimEnd())
} elseif(-not $s.Contains('AsterMaxMechanicalQualification.Evaluate(_asterMaxLoadedResults)')) {
    throw 'C10.21 solution-information anchor missing.'
}
Set-Content $integrated $s -Encoding UTF8

Write-Host 'C10.21 in-app Mechanical Qualification summary applied.' -ForegroundColor Green
