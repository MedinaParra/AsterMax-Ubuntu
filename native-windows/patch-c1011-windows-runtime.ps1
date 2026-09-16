param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $p -Raw

# C10.10.1 hotfix: the runner probe is now a real Windows-native DEBUT/FIN solve,
# therefore the old 15 s WSL-era timeout is too short.
$s=$s.Replace('process.WaitForExit(15000)','process.WaitForExit(120000)')
$s=$s.Replace('Runner probe timed out after 15 seconds.','Native Windows Code_Aster probe timed out after 120 seconds.')
$s=$s.Replace('ASTERMAX_C1005_REAL_BACKEND_PROBE_V1','ASTERMAX_C10101_WINDOWS_NATIVE_CODE_ASTER_V1')

$s=$s.Replace('string stdout=process.StandardOutput.ReadToEnd();'+[Environment]::NewLine+'                    string stderr=process.StandardError.ReadToEnd();','var stdoutTask=process.StandardOutput.ReadToEndAsync();'+[Environment]::NewLine+'                    var stderrTask=process.StandardError.ReadToEndAsync();')
# Patch both LF and CRLF sources.
$s=$s.Replace("string stdout=process.StandardOutput.ReadToEnd();`n                    string stderr=process.StandardError.ReadToEnd();","var stdoutTask=process.StandardOutput.ReadToEndAsync();`n                    var stderrTask=process.StandardError.ReadToEndAsync();")
$s=$s.Replace('p["stdout"]=stdout==null?"":stdout.Trim();','p["stdout"]=stdoutTask.Result.Replace("\0", "").Trim();')
$s=$s.Replace('p["stderr"]=stderr==null?"":stderr.Trim();','p["stderr"]=stderrTask.Result.Replace("\0", "").Trim();')

$transportAnchor='                ["code_aster_runner_source"]=String.IsNullOrWhiteSpace(runner)?"missing":(runner.IndexOf("AsterMaxRuntime",StringComparison.OrdinalIgnoreCase)>=0?"packaged":"environment"),'
if($s.Contains($transportAnchor) -and -not $s.Contains('["code_aster_transport"]="WINDOWS_NATIVE"')) {
    $s=$s.Replace($transportAnchor,$transportAnchor+[Environment]::NewLine+'                ["code_aster_transport"]="WINDOWS_NATIVE",'+[Environment]::NewLine+'                ["wsl_required"]=false,')
}

# Make the transaction itself emit a Windows-native .export. C10.05 already
# rewrites the historical 15.2 token to stable, so match the export structurally
# rather than depending on one exact previous release string.
$s=$s.Replace('["release"]="C10.00"','["release"]="C10.10.1"')
$s=$s.Replace('["release"]="C10.05"','["release"]="C10.10.1"')
$exportPattern='P actions make_etude\\nP version [^\\]+\\nP mode interactif\\nP time_limit 300\\nP memory_limit 2048\\nP ncpus 1\\nP mpi_nbcpu 1\\n\\n'
$windowsExport='A tpmax 300\nA memjeveux 256\nP ncpus 1\nP mpi_nbcpu 1\nP mpi_nbnoeud 1\nP version stable\nP actions make_etude\n\n'
$rewritten=[regex]::Replace($s,$exportPattern,$windowsExport,1)
if($rewritten -eq $s){ throw 'C10.10.1 Windows export structure was not found.' }
$s=$rewritten
$s=$s.Replace('/analysis/','./')

# C10.10.1 Windows solve evidence hotfix.
# Do not reject a genuine Windows solve only because one historical French
# marker is absent. The native runner already requires exit code 0 plus fresh,
# non-empty .mess and .rmed outputs. Here we additionally reject fatal markers
# and non-zero Code_Aster exit markers, while accepting the documented normal
# stop marker or explicit EXIT_CODE=0 evidence.
$terminationPattern='(?ms)^\s*string mess=File\.ReadAllText\(MessFile\);\s*\r?\n\s*if\(mess\.IndexOf\("<I> <FIN> ARRET NORMAL",StringComparison\.OrdinalIgnoreCase\)<0 && mess\.IndexOf\("ARRET NORMAL",StringComparison\.OrdinalIgnoreCase\)<0\)\s*\r?\n\s*Fail\("Code_Aster normal termination marker was not found in \.mess\."\);'
$terminationReplacement=@'
            string mess=File.ReadAllText(MessFile);
            string codeAsterFailure=GetCodeAsterFailure(mess);
            if(!String.IsNullOrWhiteSpace(codeAsterFailure))
                Fail("Code_Aster reported a failed solve.\n\n"+codeAsterFailure);

            bool explicitNormalStop=HasCodeAsterNormalStop(mess);
            string solveEvidence=explicitNormalStop?"NORMAL_STOP_OR_EXIT0_MARKER":"RUNNER_EXIT_0_FRESH_MESS_RMED";
'@
$terminationRewritten=[regex]::Replace($s,$terminationPattern,$terminationReplacement,1)
if($terminationRewritten -eq $s){ throw 'C10.10.1 historical Code_Aster termination gate was not found.' }
$s=$terminationRewritten

$s=$s.Replace('Message="SOLUTION_CURRENT: real solver evidence accepted. MED postprocess bridge is the next transaction stage.";','Message="SOLUTION_CURRENT: Code_Aster evidence accepted ("+solveEvidence+"). MED result is ready for postprocess.";')
$s=$s.Replace('Code_Aster finished with verified normal-stop + non-empty MED evidence.','Code_Aster finished with verified Windows-native runner + fresh .mess/.rmed evidence.')

# Prevent stdout/stderr pipe deadlocks while the native Windows runner is active.
$solveIoOld=@'
                string stdout=p.StandardOutput.ReadToEnd();
                string stderr=p.StandardError.ReadToEnd();
                p.WaitForExit();
                RunnerExitCode=p.ExitCode;
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDOUT.log"),stdout,new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDERR.log"),stderr,new UTF8Encoding(false));
'@
$solveIoNew=@'
                var stdoutTask=p.StandardOutput.ReadToEndAsync();
                var stderrTask=p.StandardError.ReadToEndAsync();
                p.WaitForExit();
                string stdout=stdoutTask.Result.Replace("\0", "");
                string stderr=stderrTask.Result.Replace("\0", "");
                RunnerExitCode=p.ExitCode;
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDOUT.log"),stdout,new UTF8Encoding(false));
                File.WriteAllText(Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDERR.log"),stderr,new UTF8Encoding(false));
'@
if($s.Contains($solveIoOld)) { $s=$s.Replace($solveIoOld,$solveIoNew) }

$failAnchor='        private void Fail(string message)'
$evidenceHelpers=@'
        private static bool TryReadCodeAsterExitCode(string line, out int code)
        {
            code=0;
            if(String.IsNullOrWhiteSpace(line)) return false;
            string value=line.Trim();
            bool marker=value.StartsWith("EXECUTION_CODE_ASTER_EXIT_",StringComparison.OrdinalIgnoreCase) ||
                        value.StartsWith("EXIT_CODE=",StringComparison.OrdinalIgnoreCase);
            if(!marker) return false;
            int equals=value.LastIndexOf('=');
            if(equals<0 || equals>=value.Length-1) return false;
            return Int32.TryParse(value.Substring(equals+1).Trim(),NumberStyles.Integer,CultureInfo.InvariantCulture,out code);
        }

        private static bool HasCodeAsterNormalStop(string mess)
        {
            if(String.IsNullOrWhiteSpace(mess)) return false;
            if(mess.IndexOf("ARRET NORMAL",StringComparison.OrdinalIgnoreCase)>=0) return true;
            string[] lines=mess.Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries);
            foreach(string raw in lines)
            {
                int code;
                if(TryReadCodeAsterExitCode(raw,out code) && code==0) return true;
            }
            return false;
        }

        private static string GetCodeAsterFailure(string mess)
        {
            if(String.IsNullOrWhiteSpace(mess)) return "The .mess file is empty.";
            string[] lines=mess.Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries);
            foreach(string raw in lines)
            {
                string line=(raw??"").Trim();
                int code;
                if(TryReadCodeAsterExitCode(line,out code) && code!=0)
                    return "Code_Aster exit marker: "+line+"\n\nLast .mess lines:\n"+BuildCodeAsterDiagnostic(mess);
                if(line.StartsWith("<F>",StringComparison.OrdinalIgnoreCase) ||
                   line.StartsWith("<F>_",StringComparison.OrdinalIgnoreCase) ||
                   line.IndexOf("<F> <",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("FATAL ERROR",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("ERREUR FATALE",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("Traceback (most recent call last)",StringComparison.OrdinalIgnoreCase)>=0)
                    return "Code_Aster fatal marker: "+line+"\n\nLast .mess lines:\n"+BuildCodeAsterDiagnostic(mess);
            }
            return null;
        }

        private static string BuildCodeAsterDiagnostic(string mess)
        {
            if(String.IsNullOrWhiteSpace(mess)) return "No .mess diagnostic text is available.";
            string[] lines=mess.Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries);
            var tail=new StringBuilder();
            int first=Math.Max(0,lines.Length-14);
            for(int i=first;i<lines.Length;i++)
            {
                string line=(lines[i]??"").Trim();
                if(line.Length==0) continue;
                if(line.Length>260) line=line.Substring(0,260)+"...";
                tail.AppendLine(line);
            }
            return tail.ToString().Trim();
        }

'@
if(-not $s.Contains($failAnchor)){ throw 'C10.10.1 solve failure helper anchor missing.' }
$s=$s.Replace($failAnchor,$evidenceHelpers+$failAnchor)

if($s.Contains('Code_Aster normal termination marker was not found in .mess.')) { throw 'Legacy rigid .mess marker gate is still present.' }
if(-not $s.Contains('RUNNER_EXIT_0_FRESH_MESS_RMED')) { throw 'Windows solver evidence fallback was not injected.' }
if(-not $s.Contains('BuildCodeAsterDiagnostic')) { throw 'Code_Aster diagnostic tail helper was not injected.' }

$anchor='        public static JObject RequireRuntimeReady()'
$helper=@'
        public static string RuntimeSummary(JObject d)
        {
            string directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"AsterMax","Diagnostics");
            Directory.CreateDirectory(directory);
            string log=Path.Combine(directory,"runtime-preflight.json");
            File.WriteAllText(log,d.ToString(Formatting.Indented));
            JObject backend=null;
            try { backend=JObject.Parse((string)d["code_aster_runner_probe"]?["stdout"]??"{}"); } catch { }
            string transport=(string)backend?["transport"]??"No detectado";
            string path=(string)backend?["backend"]??"No detectado";
            string detail=(string)backend?["message"]??"";
            if(detail.Length>400) detail=detail.Substring(0,400)+"...";
            return "Code_Aster: "+((bool?)d["code_aster_backend_ready"]==true?"DISPONIBLE":"NO DISPONIBLE")+
                "\nModo: "+transport+"\nLanzador: "+path+
                "\nPython de resultados: "+((bool?)d["python_ready"]==true?"Disponible":"No disponible")+
                "\n"+detail+"\n\nDetección nativa: %LOCALAPPDATA%\\code_aster.\nUse Runtime para seleccionar otra carpeta de instalación.\n\nRegistro: "+log;
        }

'@
if(-not $s.Contains($anchor)){throw 'Runtime readiness anchor missing'}
$s=$s.Replace($anchor,$helper+$anchor)
$s=$s.Replace('"Runtime preflight BLOCKED. "+d.ToString(Formatting.None)','"No se puede iniciar el cálculo.\n"+RuntimeSummary(d)')
$s=$s.Replace('MessageBox.Show(this,d.ToString(Formatting.Indented),',@'
                if ((bool?)d["code_aster_backend_ready"]!=true && MessageBox.Show(this,
                    AsterMaxNativeSolveTransaction.RuntimeSummary(d)+"\n\n¿Seleccionar carpeta de Code_Aster para Windows?",
                    "Configurar Code_Aster",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes) {
                    using(var folder=new FolderBrowserDialog { Description="Seleccione code_aster, su versión, o la carpeta que contiene install\\bin\\as_run.bat" }) {
                        if(folder.ShowDialog(this)==DialogResult.OK) {
                            string configDir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"AsterMax");
                            Directory.CreateDirectory(configDir);
                            File.WriteAllText(Path.Combine(configDir,"code-aster-windows.json"),new JObject{["installation"]=folder.SelectedPath}.ToString());
                            d=AsterMaxNativeSolveTransaction.RuntimeDiagnostic();
                        }
                    }
                }
                MessageBox.Show(this,AsterMaxNativeSolveTransaction.RuntimeSummary(d),
'@)
# A new diagnostic obtained after configuring a folder has no runtime_ready field.
$s=$s.Replace('(bool)d["runtime_ready"]?MessageBoxIcon.Information:MessageBoxIcon.Warning','((bool?)d["code_aster_backend_ready"]==true && (bool?)d["python_ready"]==true)?MessageBoxIcon.Information:MessageBoxIcon.Warning')
# Show the actual runner failure (including the retained diagnostic folder)
# instead of hiding it behind a generic non-zero exit-code message.
$oldFailure='Message="Code_Aster runner returned non-zero exit code: "+RunnerExitCode;'
$newFailure=@'
Message="Code_Aster runner returned non-zero exit code: "+RunnerExitCode;
                string stderrLog=Path.Combine(Workspace,"CODE_ASTER_RUNNER_STDERR.log");
                if(File.Exists(stderrLog)) Message+="\n\n"+BuildCodeAsterDiagnostic(File.ReadAllText(stderrLog));
'@
if(-not $s.Contains($oldFailure)){ throw 'Runner failure diagnostic anchor missing.' }
$s=$s.Replace($oldFailure,$newFailure)

# Isolate rapid consecutive solves; second-resolution names can reuse stale files.
$oldTx='DateTime.UtcNow.ToString("yyyyMMdd-HHmmss",CultureInfo.InvariantCulture)'
if(-not $s.Contains($oldTx)){ throw 'Solve workspace identity anchor missing.' }
$s=$s.Replace($oldTx,$oldTx+'+"-"+Guid.NewGuid().ToString("N")')

# C10.09 already drains process pipes concurrently. Keep a fail-closed guard
# against accidentally losing that patch when changing the integration chain.
if($s.Contains('string stdout=p.StandardOutput.ReadToEnd();')) {
    throw 'Sequential subprocess pipe read remains after C10.09.'
}

Set-Content $p $s -Encoding UTF8

# C10.10.1 is retained as the user-facing release while the runtime hotfix is stabilized.
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $uiPath -Raw
$u=$u.Replace('Code_Aster | WSL verified solve','Code_Aster | Windows native solve')
$u=$u.Replace('Code_Aster | native solve','Code_Aster | Windows native solve')
$u=$u.Replace('C10.11','C10.10.1')
Set-Content $uiPath $u -Encoding UTF8

$globals=Join-Path $Root 'PrePoMax/Globals.cs'
Set-Content $globals ((Get-Content $globals -Raw).Replace('C10.11','C10.10.1')) -Encoding UTF8

Write-Host 'C10.10.1 native Windows runtime, robust solver evidence, Windows export contract, 120 s real probe and readable diagnostics applied.'
