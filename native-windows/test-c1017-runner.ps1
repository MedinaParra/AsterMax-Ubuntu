# Regression harness with command stubs only. No Code_Aster/FEA validation claim.
$ErrorActionPreference='Stop'
$runner=Join-Path $PSScriptRoot 'runtime/CodeAster/astermax-codeaster-runner.ps1'
$root=Join-Path ([IO.Path]::GetTempPath()) ('astermax-runner-tests-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$previous=$env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND
$stages=New-Object 'System.Collections.Generic.List[string]'
$passed=0
try {
    foreach($case in @('success','stale','unrelated','failure','exception','escape')) {
        $workspace=Join-Path $root ($case+' workspace')
        New-Item -ItemType Directory $workspace | Out-Null
        $export=Join-Path $workspace 'case.export'
        @('F mess /analysis/case.mess R 6','F rmed /analysis/case.rmed R 81') | Set-Content $export
        if($case -eq 'escape') { @('F mess ../escape.mess R 6','F rmed ./case.rmed R 81') | Set-Content $export }
        # Very recent stale outputs reproduce the old timestamp-based admission bug.
        'stale mess' | Set-Content (Join-Path $workspace 'case.mess')
        'stale rmed' | Set-Content (Join-Path $workspace 'case.rmed')
        $backend=Join-Path $root ($case+'.cmd')
        $lines=@('@echo off')
        if($case -eq 'success') { $lines+=@('echo current>case.mess','echo current>case.rmed') }
        if($case -eq 'unrelated') { $lines+=@('echo other>other.mess','echo other>other.rmed') }
        if($case -eq 'failure') { $lines+=@('echo diagnostic>case.mess','exit /b 9') }
        else { $lines+='exit /b 0' }
        $lines | Set-Content $backend -Encoding ASCII
        if($case -eq 'exception') { $backend=Join-Path $root 'invalid.txt'; 'invalid backend' | Set-Content $backend }
        $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND=$backend
        $p=New-Object System.Diagnostics.Process
        $p.StartInfo.FileName=Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $p.StartInfo.Arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$runner+'" "'+$export+'" "'+$workspace+'"'
        $p.StartInfo.UseShellExecute=$false
        $p.StartInfo.RedirectStandardOutput=$true
        $p.StartInfo.RedirectStandardError=$true
        try {
            [void]$p.Start()
            $out=$p.StandardOutput.ReadToEndAsync()
            $err=$p.StandardError.ReadToEndAsync()
            if(-not $p.WaitForExit(30000)) { $p.Kill(); throw "Test timed out: $case" }
            $code=$p.ExitCode
            $log=$out.Result+"`n"+$err.Result
        } finally { $p.Dispose() }
        if($case -eq 'success') {
            if($code -ne 0 -or $log -notmatch 'RUNNER=SUCCESS') { throw "Success rejected: $log" }
            if((Get-Content (Join-Path $workspace 'case.rmed') -Raw).Trim() -ne 'current') { throw 'Current output not promoted' }
            if($log -match 'ASTERMAX_CODE_ASTER_STAGE=([^\r\n]+)') {
                if(Test-Path -LiteralPath $Matches[1]) { throw 'Successful stage not cleaned up' }
            }
        } else {
            if($code -eq 0 -or $log -match 'RUNNER=SUCCESS') { throw "Invalid solve accepted: $case $log" }
            if($log -notmatch 'ASTERMAX_CODE_ASTER_FAILED_STAGE=([^\r\n]+)') { throw "Missing retained stage: $case $log" }
            $stage=$Matches[1]
            $stages.Add($stage)
            if(-not (Test-Path -LiteralPath $stage)) { throw 'Failed stage was deleted' }
            if((Get-Content (Join-Path $workspace 'case.rmed') -Raw).Trim() -ne 'stale rmed') { throw 'Failed output promoted' }
            if($case -eq 'failure') {
                $diagnostic=Get-ChildItem $workspace -Directory -Filter 'failed-*' | Select-Object -First 1
                if(-not $diagnostic -or (Get-Content (Join-Path $diagnostic.FullName 'case.mess') -Raw).Trim() -ne 'diagnostic') {
                    throw 'Solver failure diagnostics were lost'
                }
            }
        }
        $passed++
        Write-Host "PASS runner regression: $case (command stub; not solver evidence)"
    }
    Write-Host "C1017_RUNNER_REGRESSIONS=$passed/6 PASS"
} finally {
    $env:ASTERMAX_WINDOWS_CODE_ASTER_COMMAND=$previous
    foreach($stage in $stages) { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
