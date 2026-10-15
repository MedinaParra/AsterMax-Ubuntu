param([string]$Root)
$ErrorActionPreference='Stop'
$src=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(-not (Test-Path $src)){throw "Missing $src"}
$s=Get-Content $src -Raw
$old='RunnerExecutable=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");
            if(String.IsNullOrWhiteSpace(RunnerExecutable) || !File.Exists(RunnerExecutable))'
$new='RunnerExecutable=ResolveRunnerExecutable();
            if(String.IsNullOrWhiteSpace(RunnerExecutable) || !File.Exists(RunnerExecutable))'
if(-not $s.Contains($old)){throw 'C10.74 runner assignment anchor missing.'}
$s=$s.Replace($old,$new)
$anchor='        private static string Quote(string s){ return "\\\""+(s??"").Replace("\\\"","\\\\\\\"")+"\\\""; }'
if(-not $s.Contains($anchor)){throw 'C10.74 Quote anchor missing.'}
$helper=@'
        private static string ResolveRunnerExecutable()
        {
            string configured=Environment.GetEnvironmentVariable("ASTERMAX_CODE_ASTER_RUNNER");
            if(!String.IsNullOrWhiteSpace(configured) && File.Exists(configured)) return configured;
            string baseDir=AppDomain.CurrentDomain.BaseDirectory;
            string[] candidates=new string[]
            {
                Path.Combine(baseDir,"CodeAster","astermax-codeaster-runner.cmd"),
                Path.Combine(baseDir,"CodeAster","astermax-codeaster-runner.ps1"),
                Path.Combine(baseDir,"runtime","CodeAster","astermax-codeaster-runner.cmd"),
                Path.Combine(baseDir,"runtime","CodeAster","astermax-codeaster-runner.ps1")
            };
            foreach(string candidate in candidates) if(File.Exists(candidate)) return candidate;
            return configured;
        }

'@
$s=$s.Replace($anchor,$helper+$anchor)
Set-Content $src $s -Encoding UTF8
Write-Host 'C10.74 packaged Code_Aster runner autodiscovery injected.' -ForegroundColor Green
