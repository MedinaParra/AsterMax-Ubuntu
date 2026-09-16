param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $p)){throw 'C10.14 requires AsterMaxNativeSolveTransaction.cs.'}
$s=Get-Content $p -Raw

# Refined meshes need more realistic standalone Windows Code_Aster limits.
# memjeveux is expressed in Mwords by the Windows standalone launcher.
$s=$s.Replace('A tpmax 300\nA memjeveux 256\n','A tpmax 900\nA memjeveux 512\n')

# Replace the generic runner exit message with diagnostics captured by the runner and .mess tail.
$old=@'
            if(RunnerExitCode!=0)
            {
                State=AsterMaxSolveState.Failed;
                Message="Code_Aster runner returned non-zero exit code: "+RunnerExitCode;
                WriteFinalState();
                throw new InvalidOperationException(Message);
            }
'@
$new=@'
            if(RunnerExitCode!=0)
            {
                State=AsterMaxSolveState.Failed;
                string details=BuildRunnerFailureDiagnostic(Workspace,RunnerExitCode.Value);
                Message="Code_Aster solve failed (runner exit "+RunnerExitCode+")."+
                    (String.IsNullOrWhiteSpace(details)?"":"\n\n"+details);
                WriteFinalState();
                throw new InvalidOperationException(Message);
            }
'@
if($s.Contains($old)){$s=$s.Replace($old,$new)}
elseif(-not $s.Contains('BuildRunnerFailureDiagnostic(Workspace,RunnerExitCode.Value)')){throw 'Generic runner-exit block anchor missing.'}

$anchor='        private static bool TryReadCodeAsterExitCode(string line, out int code)'
$helper=@'
        private static string BuildRunnerFailureDiagnostic(string workspace,int exitCode)
        {
            try
            {
                var b=new StringBuilder();
                if(exitCode==30)
                    b.AppendLine("AsterMax runner code 30: Code_Aster returned control but a fresh non-empty .mess or .rmed output was not produced.");
                string stderrPath=Path.Combine(workspace,"CODE_ASTER_RUNNER_STDERR.log");
                string stdoutPath=Path.Combine(workspace,"CODE_ASTER_RUNNER_STDOUT.log");
                if(File.Exists(stderrPath))
                {
                    string text=File.ReadAllText(stderrPath).Trim();
                    if(text.Length>0) b.AppendLine("Runner stderr:\n"+TailText(text,18));
                }
                string[] messFiles=Directory.Exists(workspace)?Directory.GetFiles(workspace,"*.mess"):new string[0];
                if(messFiles.Length>0)
                {
                    string latest=messFiles.OrderByDescending(File.GetLastWriteTimeUtc).First();
                    string mess=File.ReadAllText(latest);
                    string fatal=GetCodeAsterFailure(mess);
                    b.AppendLine("Code_Aster .mess: "+Path.GetFileName(latest));
                    if(!String.IsNullOrWhiteSpace(fatal)) b.AppendLine(fatal);
                    else b.AppendLine("Last .mess lines:\n"+TailText(mess,18));
                }
                else if(File.Exists(stdoutPath))
                {
                    string text=File.ReadAllText(stdoutPath).Trim();
                    if(text.Length>0) b.AppendLine("Runner stdout:\n"+TailText(text,18));
                }
                return b.ToString().Trim();
            }
            catch(Exception ex){return "Unable to read solver diagnostics: "+ex.Message;}
        }

        private static string TailText(string text,int maxLines)
        {
            if(String.IsNullOrWhiteSpace(text)) return "";
            string[] lines=text.Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries);
            var b=new StringBuilder();
            for(int i=Math.Max(0,lines.Length-maxLines);i<lines.Length;i++)
            {
                string line=(lines[i]??"").Trim();
                if(line.Length>320) line=line.Substring(0,320)+"...";
                if(line.Length>0) b.AppendLine(line);
            }
            return b.ToString().Trim();
        }

'@
if(-not $s.Contains('private static string BuildRunnerFailureDiagnostic(')){
    if(-not $s.Contains($anchor)){throw 'C10.14 diagnostic helper anchor missing.'}
    $s=$s.Replace($anchor,$helper+$anchor)
}

if(-not $s.Contains('A tpmax 900\nA memjeveux 512\n')){throw 'C10.14 refined-mesh resource budget not applied.'}
if(-not $s.Contains('AsterMax runner code 30:')){throw 'C10.14 code-30 diagnostic not applied.'}
Set-Content $p $s -Encoding UTF8

# Patch the packaged Windows-native runner too. Code 30 is AsterMax's evidence code,
# not a Code_Aster solver status. Ensure stale outputs cannot satisfy evidence checks and
# print the real .mess tail when a refined solve returns no RMED.
$runner=Join-Path $PSScriptRoot 'runtime\CodeAster\astermax-codeaster-runner.ps1'
if(!(Test-Path $runner)){throw 'C10.14 packaged Code_Aster runner missing.'}
$r=Get-Content $runner -Raw
$copyAnchor='    Copy-Workspace $resolvedWorkspace $stage'
$copyNew=@'
    Copy-Workspace $resolvedWorkspace $stage
    # Never allow stale solver evidence copied from a previous solve to satisfy this transaction.
    Get-ChildItem -LiteralPath $stage -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -in @('.mess','.rmed','.resu') } |
        Remove-Item -Force -ErrorAction SilentlyContinue
'@
if($r.Contains($copyAnchor) -and -not $r.Contains('Never allow stale solver evidence')){$r=$r.Replace($copyAnchor,$copyNew.TrimEnd())}

$evidenceOld=@'
    foreach ($extension in @('mess','rmed')) {
        $output = Get-ChildItem -LiteralPath $stage -Filter "*.$extension" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 0 -and $_.LastWriteTimeUtc -ge $started.AddSeconds(-2) } |
            Select-Object -First 1
        if (-not $output) { Fail "Native solver did not produce a fresh non-empty .$extension file." 30 }
    }
'@
$evidenceNew=@'
    $missing = New-Object 'System.Collections.Generic.List[string]'
    foreach ($extension in @('mess','rmed')) {
        $output = Get-ChildItem -LiteralPath $stage -Filter "*.$extension" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Length -gt 0 -and $_.LastWriteTimeUtc -ge $started.AddSeconds(-2) } |
            Select-Object -First 1
        if (-not $output) { $missing.Add('.' + $extension) }
    }
    if ($missing.Count -gt 0) {
        [Console]::Error.WriteLine('ASTERMAX_CODE_ASTER_EVIDENCE_MISSING=' + ($missing -join ','))
        $latestMess = Get-ChildItem -LiteralPath $stage -Filter '*.mess' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($latestMess -and $latestMess.Length -gt 0) {
            [Console]::Error.WriteLine('ASTERMAX_CODE_ASTER_MESS=' + $latestMess.FullName)
            [Console]::Error.WriteLine('--- CODE_ASTER .mess TAIL ---')
            Get-Content -LiteralPath $latestMess.FullName -Tail 24 -ErrorAction SilentlyContinue |
                ForEach-Object { [Console]::Error.WriteLine($_) }
            [Console]::Error.WriteLine('--- END .mess TAIL ---')
        }
        elseif ($result.Stderr) {
            [Console]::Error.WriteLine('--- CODE_ASTER STDERR TAIL ---')
            ($result.Stderr -split "`r?`n" | Select-Object -Last 24) |
                ForEach-Object { [Console]::Error.WriteLine($_) }
            [Console]::Error.WriteLine('--- END STDERR TAIL ---')
        }
        elseif ($result.Stdout) {
            [Console]::Error.WriteLine('--- CODE_ASTER STDOUT TAIL ---')
            ($result.Stdout -split "`r?`n" | Select-Object -Last 24) |
                ForEach-Object { [Console]::Error.WriteLine($_) }
            [Console]::Error.WriteLine('--- END STDOUT TAIL ---')
        }
        Fail ('Native solver did not produce fresh non-empty result evidence. Missing: ' + ($missing -join ', ')) 30
    }
'@
if($r.Contains($evidenceOld)){$r=$r.Replace($evidenceOld,$evidenceNew)}
elseif(-not $r.Contains('ASTERMAX_CODE_ASTER_EVIDENCE_MISSING=')){throw 'C10.14 runner evidence block anchor missing.'}
if(-not $r.Contains('Never allow stale solver evidence')){throw 'C10.14 stale evidence cleanup missing.'}
if(-not $r.Contains('ASTERMAX_CODE_ASTER_EVIDENCE_MISSING=')){throw 'C10.14 runner diagnostics missing.'}
Set-Content $runner $r -Encoding UTF8

Write-Host 'C10.14 refined-mesh resources + actionable runner/.mess diagnostics applied.' -ForegroundColor Green
