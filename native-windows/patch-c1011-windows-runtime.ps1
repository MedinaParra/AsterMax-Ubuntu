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
                    using(var folder=new FolderBrowserDialog { Description="Seleccione code_aster, su versión, o la carpeta que contiene bin\\run_aster.bat" }) {
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

Write-Host 'C10.10.1 native Windows runtime, 120 s real probe and readable diagnostics applied.'
