param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$OutDir
)
$ErrorActionPreference='Stop'
$source=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs') -Raw
$match=[regex]::Match($source,'(?s)// C1206_DISCOVERY_CORE_BEGIN\s*(.*?)\s*// C1206_DISCOVERY_CORE_END')
if(-not $match.Success){ throw 'C12.06 production discovery methods are missing.' }

# Compile the actual production methods, changing visibility only so the test
# can invoke them. Fixture files represent adapter presence, never solver output.
$core=$match.Groups[1].Value.Replace('private static','public static')
Add-Type -TypeDefinition ("using System;`nusing System.IO;`npublic static class AsterMaxC1206DiscoveryTestHarness {`n"+$core+"`n}")
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('AsterMax C1206 discovery '+[Guid]::NewGuid().ToString('N'))
$package=Join-Path $scratch 'Package with spaces'
$canonical=Join-Path $package 'AsterMaxRuntime/CodeAster'
$legacy=Join-Path $package 'CodeAster'
New-Item -ItemType Directory -Force $canonical,$legacy | Out-Null
$checks=New-Object 'System.Collections.Generic.List[object]'

function Check([string]$Name,[object]$Actual,[object]$Expected) {
    $ok=($Actual -ceq $Expected)
    $checks.Add([ordered]@{name=$Name;status=$(if($ok){'PASS'}else{'FAIL'})})
    if(-not $ok){ throw "C12.06 $Name failed: actual=[$Actual], expected=[$Expected]" }
}
function Resolve([string]$Configured) {
    return [AsterMaxC1206DiscoveryTestHarness]::ResolveCodeAsterRunnerFrom($package,$Configured)
}
try {
    Check 'empty package reports no adapter' (Resolve '') $null
    $canonicalCmd=Join-Path $canonical 'astermax-codeaster-runner.cmd'
    $canonicalPs=Join-Path $canonical 'astermax-codeaster-runner.ps1'
    [IO.File]::WriteAllText($canonicalCmd,'@rem discovery fixture; never executed')
    Check 'cmd without PowerShell companion is rejected' (Resolve '') $null
    [IO.File]::WriteAllText($canonicalPs,'# discovery fixture; never executed')
    Check 'complete canonical adapter auto-detected without environment' (Resolve '') $canonicalCmd
    $configuredExe=Join-Path $scratch 'external-runner.exe'
    [IO.File]::WriteAllText($configuredExe,'discovery fixture; never executed')
    Check 'complete packaged adapter takes precedence' (Resolve $configuredExe) $canonicalCmd
    Remove-Item -LiteralPath $canonicalPs
    Check 'broken packaged adapter falls back to explicit adapter' (Resolve $configuredExe) $configuredExe
    Check 'broken packaged adapter still rejected without fallback' (Resolve '') $null
    $legacyCmd=Join-Path $legacy 'astermax-codeaster-runner.cmd'
    $legacyPs=Join-Path $legacy 'astermax-codeaster-runner.ps1'
    [IO.File]::WriteAllText($legacyCmd,'@rem discovery fixture; never executed')
    Check 'legacy cmd alone is rejected' (Resolve '') $null
    [IO.File]::WriteAllText($legacyPs,'# discovery fixture; never executed')
    Check 'complete historical package folder auto-detected' (Resolve '') $legacyCmd
    Remove-Item -LiteralPath $legacyCmd,$legacyPs
    $configuredScript=Join-Path $scratch 'configured runner.ps1'
    [IO.File]::WriteAllText($configuredScript,'# discovery fixture; never executed')
    Check 'quoted explicit path with spaces is normalized' (Resolve ('"'+$configuredScript+'"')) $configuredScript
    $invalid=Join-Path $scratch 'runner.txt'
    [IO.File]::WriteAllText($invalid,'not an executable adapter')
    Check 'unsupported executable extension rejected' (Resolve $invalid) $null
    Check 'missing explicit adapter rejected' (Resolve (Join-Path $scratch 'missing.exe')) $null
    Check 'explicit packaged cmd also requires its companion' (Resolve $canonicalCmd) $null

    $tools=Join-Path $package 'AsterMaxTools'
    New-Item -ItemType Directory -Force $tools | Out-Null
    Check 'absent result tools are not ready' ([AsterMaxC1206DiscoveryTestHarness]::HasCodeAsterPostprocessTools($package)) $false
    [IO.File]::WriteAllText((Join-Path $tools 'bridge-c964-med-results.py'),'# discovery fixture')
    [IO.File]::WriteAllText((Join-Path $tools 'bind-c998-results-fingerprint.py'),'# discovery fixture')
    Check 'bridge and binder without mechanical qualifier are not ready' ([AsterMaxC1206DiscoveryTestHarness]::HasCodeAsterPostprocessTools($package)) $false
    [IO.File]::WriteAllText((Join-Path $tools 'qualify-mechanical-analysis.py'),'# discovery fixture')
    Check 'all three postprocess tools are required and detected' ([AsterMaxC1206DiscoveryTestHarness]::HasCodeAsterPostprocessTools($package)) $true

    $ui=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs') -Raw
    $globals=Get-Content -LiteralPath (Join-Path $Root 'PrePoMax/Globals.cs') -Raw
    Check 'obsolete environment-only instruction removed' $source.Contains('Set ASTERMAX_CODE_ASTER_RUNNER to a validated runner executable/script.') $false
    Check 'native setup action exposed on Solution ribbon' $ui.Contains('CommandTile("Instalar motor", "CODE_ASTER_SETUP", () => StartAsterMaxCodeAsterSetup(), true)') $true
    Check 'installed-folder selection remains available' $source.Contains('code-aster-windows.json') $true
    Check 'application identifies repaired build' $globals.Contains('AsterMax Mechanical C12.06') $true
    Check 'native runner probe still exists' $source.Contains('ProbeCodeAsterRunner(runner)') $true
    Check 'no solver result evidence gate removed' $source.Contains('GetCodeAsterFailure(mess)') $true

    New-Item -ItemType Directory -Force $OutDir | Out-Null
    [ordered]@{
        candidate='C12.06'
        test='production C# runner discovery methods against filesystem fixtures'
        checks=$checks
        discovery='PASS'
        native_solver_execution='NOT_RUN'
        gui_execution='NOT_RUN'
        synthetic_solver_outputs=$false
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutDir 'runner-discovery.json') -Encoding UTF8
    Write-Host ('C12.06 runner discovery PASS: '+$checks.Count+' checks; no solver/GUI execution claimed.')
}
finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
}
