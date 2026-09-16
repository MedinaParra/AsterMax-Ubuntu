param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $p)){throw 'C10.14 requires AsterMaxNativeSolveTransaction.cs.'}
$s=Get-Content $p -Raw

# Refined meshes need more realistic standalone Windows Code_Aster limits.
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
Write-Host 'C10.14 refined-mesh resources + runner/.mess diagnostics applied.' -ForegroundColor Green
