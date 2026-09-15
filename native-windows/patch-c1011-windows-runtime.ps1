param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $p -Raw
$s=$s.Replace('string stdout=process.StandardOutput.ReadToEnd();'+[Environment]::NewLine+'                    string stderr=process.StandardError.ReadToEnd();','var stdoutTask=process.StandardOutput.ReadToEndAsync();'+[Environment]::NewLine+'                    var stderrTask=process.StandardError.ReadToEndAsync();')
# Patch both LF and CRLF sources.
$s=$s.Replace("string stdout=process.StandardOutput.ReadToEnd();`n                    string stderr=process.StandardError.ReadToEnd();","var stdoutTask=process.StandardOutput.ReadToEndAsync();`n                    var stderrTask=process.StandardError.ReadToEndAsync();")
$s=$s.Replace('p["stdout"]=stdout==null?"":stdout.Trim();','p["stdout"]=stdoutTask.Result.Replace("\0", "").Trim();')
$s=$s.Replace('p["stderr"]=stderr==null?"":stderr.Trim();','p["stderr"]=stderrTask.Result.Replace("\0", "").Trim();')
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
foreach($name in @('PrePoMax/Forms/AsterMaxNativeUi.cs','PrePoMax/Globals.cs')) {
 $p=Join-Path $Root $name
 Set-Content $p ((Get-Content $p -Raw).Replace('C10.10.1','C10.11')) -Encoding UTF8
}
Write-Host 'C10.11 native Windows runtime and readable diagnostics applied.'
