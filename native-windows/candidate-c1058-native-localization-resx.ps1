param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$pre=Join-Path $Root 'PrePoMax'
$loc=Join-Path $pre 'Localization'
New-Item -ItemType Directory -Force $loc | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'AsterMaxLocalization.cs') (Join-Path $pre 'AsterMaxLocalization.cs') -Force
Copy-Item (Join-Path $PSScriptRoot 'Localization\Strings.es-CL.resx') (Join-Path $loc 'Strings.es-CL.resx') -Force
$proj=Join-Path $pre 'PrePoMax.csproj'
[xml]$xml=Get-Content $proj
$ns=$xml.Project.NamespaceURI
function HasInclude($inc){ @($xml.Project.ItemGroup.Compile + $xml.Project.ItemGroup.EmbeddedResource) | Where-Object { $_.Include -eq $inc } }
$ig=$xml.CreateElement('ItemGroup',$ns)
if(-not (HasInclude 'AsterMaxLocalization.cs')) { $n=$xml.CreateElement('Compile',$ns); $n.SetAttribute('Include','AsterMaxLocalization.cs'); $ig.AppendChild($n)|Out-Null }
if(-not (HasInclude 'Localization\Strings.es-CL.resx')) { $n=$xml.CreateElement('EmbeddedResource',$ns); $n.SetAttribute('Include','Localization\Strings.es-CL.resx'); $n.SetAttribute('LogicalName','PrePoMax.Localization.Strings.es-CL.resources'); $ig.AppendChild($n)|Out-Null }
if($ig.ChildNodes.Count -gt 0){ $xml.Project.AppendChild($ig)|Out-Null; $xml.Save($proj) }
Write-Host 'C10.58 native es-CL ResourceManager resources installed.'
