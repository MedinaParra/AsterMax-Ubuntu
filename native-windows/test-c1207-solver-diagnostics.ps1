param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference='Stop'
$source=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs') -Raw
$match=[regex]::Match($source,'(?s)// C1207_SOLVER_DIAGNOSTICS_BEGIN\s*(.*?)\s*// C1207_SOLVER_DIAGNOSTICS_END')
if(-not $match.Success) { throw 'C12.07 production diagnostic methods missing.' }
$core=$match.Groups[1].Value.Replace('private static','public static')
$gateStart=$source.IndexOf('        private static bool TryReadCodeAsterExitCode(')
$gateEnd=$source.IndexOf('        private void Fail(', $gateStart)
if($gateStart -lt 0 -or $gateEnd -le $gateStart) { throw 'Production solver evidence methods missing.' }
$core+=$source.Substring($gateStart,$gateEnd-$gateStart).Replace('private static','public static')
$jsonAssembly=[Newtonsoft.Json.Linq.JObject].Assembly.Location
$references=@($jsonAssembly,'System.Runtime','System.Collections','System.Text.RegularExpressions')
# PowerShell's bundled Newtonsoft targets an earlier compatible .NET runtime.
# Suppress only that assembly-unification warning, not compilation errors.
Add-Type -ReferencedAssemblies $references -CompilerOptions '/nowarn:1701,1702' -TypeDefinition ("using System;`nusing System.IO;`nusing System.Text;`nusing System.Globalization;`nusing Newtonsoft.Json.Linq;`npublic static class AsterMaxC1207DiagnosticTestHarness {`n"+$core+"`n}")
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('AsterMax C1207 diagnostics '+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $scratch | Out-Null
$checks=New-Object 'System.Collections.Generic.List[object]'
function Check([string]$Name,[bool]$Pass) {
    $checks.Add([ordered]@{name=$Name;status=$(if($Pass){'PASS'}else{'FAIL'})})
    if(-not $Pass) { throw "C12.07 diagnostic check failed: $Name" }
}
function Write-Utf8([string]$Path,[string]$Text) {
    [IO.File]::WriteAllText($Path,$Text,(New-Object Text.UTF8Encoding($false)))
}
function Summary([int]$ExitCode) {
    return [AsterMaxC1207DiagnosticTestHarness]::BuildRunnerFailureDiagnostic($scratch,$ExitCode)
}
try {
    # Fixture diagnostics only: these are never used as FEA result evidence.
    $failed=Join-Path $scratch 'failed-solve-fixture'
    New-Item -ItemType Directory -Path $failed | Out-Null
    $diag=Join-Path $failed 'astermax-runner-diagnostic.json'
    $stderr=Join-Path $scratch 'CODE_ASTER_RUNNER_STDERR.log'
    Write-Utf8 $diag '{"schema":"astermax-codeaster-runner-diagnostic/v1","status":"failed","marker":"CONTACT2_16","contact_zones":[13,28],"shared_slave_nodes":12,"message":"fixture"}'
    Write-Utf8 (Join-Path $scratch 'ASTERMAX_SOLVE_TRANSACTION.json') '{"native_exporter_manifest":{"contact_orientation_report":{"swapped_count":1,"zones":[{"zone_index":13,"contact_name":"Viga izquierda / placa","swapped":false},{"zone_index":28,"contact_name":"Unión soporte Ñ","swapped":true}]}}}'
    $text=Summary 31
    Check 'structured fatal identifies CONTACT2_16' $text.Contains('CONTACT2_16')
    Check 'preserved failed stage is searched' ($text.Contains('13 (Viga izquierda / placa)') -and $text.Contains('28 (Unión soporte Ñ)'))
    Check 'shared node count explained' $text.Contains('Nodos esclavos compartidos: 12')
    Check 'Spanish Unicode contact names preserved' $text.Contains('Unión soporte Ñ')
    Check 'failed result not represented as accepted' $text.Contains('No se han aceptado resultados')
    Check 'log location retained' $text.Contains($scratch)
    Check 'contact error fits bounded dialog' ($text.Length -lt 1600)
    $orientation=[AsterMaxC1207DiagnosticTestHarness]::DescribeContactOrientation($scratch)
    Check 'orientation audit identifies changed pair' ($orientation.Contains('1 par reorientado') -and $orientation.Contains('Unión soporte Ñ') -and -not $orientation.Contains('Viga izquierda'))
    Check 'orientation audit distinguishes numerical change from geometry' ($orientation.Contains('orientación numérica') -and $orientation.Contains('Se conservan las superficies y leyes'))

    Remove-Item -LiteralPath $diag
    Write-Utf8 $stderr (('irrelevant trace line'+[Environment]::NewLine)*1500+'ASTERMAX_CODE_ASTER_FAILURE=CONTACT2_16;contact_zones=13,28;shared_slave_nodes=12')
    $text=Summary 30
    Check 'stable ASCII marker works without JSON' ($text.Contains('CONTACT2_16') -and $text.Contains('compartidos: 12'))
    Check 'long trace does not overflow dialog' ($text.Length -lt 1600 -and -not $text.Contains('irrelevant trace line'))

    Write-Utf8 $stderr '<EXCEPTION> <CONTACT2_16>'
    $mess=Join-Path $failed 'contact-fixture.mess'
    Write-Utf8 $mess "<EXCEPTION> <CONTACT2_16>`nLes zones de contact numéro 13 et numéro 28 ont 12 noeuds communs à leurs surfaces esclaves.`n"
    $text=Summary 30
    Check 'legacy French message parsed from failed-stage mess' ($text.Contains('13 (Viga') -and $text.Contains('28 (Unión') -and $text.Contains('compartidos: 12'))
    Write-Utf8 $diag '{malformed JSON'
    Check 'corrupt diagnostic falls back to real text evidence' ((Summary 30).Contains('CONTACT2_16'))

    Remove-Item -LiteralPath $diag,$mess
    Write-Utf8 $stderr '<F> <FACTOR_55> matrix factorization failed'
    $text=Summary 31
    Check 'generic fatal keeps native marker' $text.Contains('FACTOR_55')
    Check 'generic fatal does not invent contacts' (-not $text.Contains('Nodos esclavos compartidos'))
    Write-Utf8 $stderr ''
    $text=Summary 30
    Check 'missing output has accurate distinct explanation' $text.Contains('no produjo todos los archivos de resultado necesarios')
    Check 'missing output is not called installation failure' (-not $text.Contains('Instalar motor'))

    $huge=Join-Path $failed 'bounded.mess'
    Write-Utf8 $huge ('HEAD'+('x'*400000)+'TAIL')
    $bounded=[AsterMaxC1207DiagnosticTestHarness]::ReadDiagnosticText($huge)
    Check 'large file reader keeps beginning and ending' ($bounded.StartsWith('HEAD') -and $bounded.EndsWith('TAIL'))
    Check 'large file reader is bounded' ($bounded.Length -lt 263000)

    Check 'production evidence rejects exception even after normal marker' (-not [string]::IsNullOrWhiteSpace([AsterMaxC1207DiagnosticTestHarness]::GetCodeAsterFailure("ARRET NORMAL`n<EXCEPTION> <CONTACT2_16>")))
    Check 'production evidence rejects abnormal abort' (-not [string]::IsNullOrWhiteSpace([AsterMaxC1207DiagnosticTestHarness]::GetCodeAsterFailure("EXIT_CODE=0`n_ABNORMAL_ABORT")))
    Check 'production evidence accepts warning without fatal' ([string]::IsNullOrWhiteSpace([AsterMaxC1207DiagnosticTestHarness]::GetCodeAsterFailure("Code_Aster`n<A> <CONTACT_1> warning`nARRET NORMAL`nEXIT_CODE=0")))
    Check 'production evidence rejects explicit nonzero marker' (-not [string]::IsNullOrWhiteSpace([AsterMaxC1207DiagnosticTestHarness]::GetCodeAsterFailure('EXECUTION_CODE_ASTER_EXIT_1=4')))

    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    [ordered]@{candidate='C12.07';test='compiled production failure summaries';checks=$checks;diagnostics='PASS';native_solver_execution='NOT_RUN';gui_execution='NOT_RUN';synthetic_fea_results=$false} |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutDir 'solver-diagnostics.json') -Encoding UTF8
    Write-Host ('C12.07 solver diagnostics PASS: '+$checks.Count+' checks; diagnostic fixtures only.')
}
finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
