$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$tests = @(Get-ChildItem -LiteralPath $here -Filter 'test-c1082-*.ps1' -File | Sort-Object Name)
if ($tests.Count -eq 0) { throw 'C10.82 contract runner found no test-c1082-*.ps1 files.' }

Write-Host ("C10.82 contract runner: {0} tests" -f $tests.Count)
$passed = 0
foreach ($test in $tests) {
    Write-Host ("RUN {0}" -f $test.Name)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $test.FullName
    if ($LASTEXITCODE -ne 0) { throw ("FAIL {0} exit={1}" -f $test.Name, $LASTEXITCODE) }
    $passed++
}

Write-Host ("PASS C10.82 contracts {0}/{1}." -f $passed, $tests.Count) -ForegroundColor Green
