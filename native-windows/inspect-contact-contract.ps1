param([Parameter(Mandatory=$true)][string]$ContractPath, [Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
# Read-only inspection of an exported JSON contract, never a PMX deserializer
# or solver launcher. Keep the audit and proposed role plan outside the input.
$inputPath=(Resolve-Path -LiteralPath $ContractPath).Path
$auditPath=[IO.Path]::GetFullPath((Join-Path $OutDir 'contact-preflight.json'))
$planPath=[IO.Path]::GetFullPath((Join-Path $OutDir 'planned-contacts.json'))
if($inputPath -eq $auditPath -or $inputPath -eq $planPath) { throw 'Output would overwrite the source contract.' }
$contract=[Newtonsoft.Json.Linq.JObject]::Parse([IO.File]::ReadAllText($inputPath))
if($contract['unit_system'].ToString() -ne 'MM_N_S_MPA') { throw 'Expected explicit MM_N_S_MPA contract; no unit conversion is performed.' }
if($null -ne $contract['contacts'] -and $contract['contacts'] -isnot [Newtonsoft.Json.Linq.JArray]) { throw 'contacts must be an array.' }
Add-Type -Path (Join-Path $PSScriptRoot 'AsterMaxContactTopology.cs') -ReferencedAssemblies @([Newtonsoft.Json.Linq.JObject].Assembly.Location,'System.Runtime','System.Collections','System.Linq','System.Linq.Expressions','System.IO.FileSystem','System.ComponentModel.TypeConverter','System.ObjectModel') -CompilerOptions '/nowarn:1701,1702'
$report=$null
$plan=$null
try {
    $plan=[PrePoMax.AsterMaxContactTopology]::Normalize($contract['contacts'],$contract['mesh']['nodes'],[ref]$report)
}
catch {
    $failure=$_.Exception
    while($null -ne $failure.InnerException) { $failure=$failure.InnerException }
    if($null -eq $failure.Data['contact_topology_report']) { throw }
    $report=[Newtonsoft.Json.Linq.JObject]::Parse([string]$failure.Data['contact_topology_report'])
}
# Never reuse an output directory: a failed inspection must not leave an older
# successful plan beside the new failure report.
if(Test-Path -LiteralPath $OutDir) { throw 'Choose a new audit directory to preserve previous evidence.' }
New-Item -ItemType Directory -Path $OutDir | Out-Null
[IO.File]::WriteAllText($auditPath,$report.ToString())
if($null -ne $plan) { [IO.File]::WriteAllText($planPath,$plan.ToString()) }
Write-Host ('Contact preflight: '+$report['status'].ToString()+'. '+$auditPath+'. Solver NOT_RUN. Source unchanged.')
if($report['status'].ToString() -eq 'BLOCKED') { exit 2 }
