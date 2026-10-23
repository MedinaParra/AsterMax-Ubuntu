param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$source=[regex]::Replace((Get-Content -LiteralPath $path -Raw),"\r\n?","`n")

if(-not $source.Contains('// C1207_SOLVER_DIAGNOSTICS_BEGIN')) {
    $start=$source.IndexOf('        private static string BuildRunnerFailureDiagnostic(')
    $end=$source.IndexOf('        private static string TailText(', $start)
    if($start -lt 0 -or $end -le $start) { throw 'C12.07 solver diagnostics anchors missing.' }
    $replacement=@'
        // C1207_SOLVER_DIAGNOSTICS_BEGIN
        // Keep full logs on disk; the dialog explains the root cause and names
        // the affected exported contact zones instead of overflowing the screen.
        private static string BuildRunnerFailureDiagnostic(string workspace,int exitCode)
        {
            try
            {
                JObject diagnostic=ReadRunnerDiagnostic(workspace);
                string stderr=ReadDiagnosticText(Path.Combine(workspace,"CODE_ASTER_RUNNER_STDERR.log"));
                string messPath=FindLatestDiagnosticFile(workspace,"*.mess");
                string mess=ReadDiagnosticText(messPath);
                string evidence=stderr+"\n"+mess;
                string marker=(string)diagnostic?["marker"] ?? "";
                if(String.IsNullOrWhiteSpace(marker))
                {
                    var code=System.Text.RegularExpressions.Regex.Match(evidence,
                        @"(?:ASTERMAX_CODE_ASTER_FAILURE=|<(?:EXCEPTION|F)>\s*<)([A-Z][A-Z0-9]*_\d+)",
                        System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                    if(code.Success) marker=code.Groups[1].Value.ToUpperInvariant();
                }
                var b=new StringBuilder();
                if(String.Equals(marker,"CONTACT2_16",StringComparison.OrdinalIgnoreCase))
                {
                    int first=0,second=0,count=0;
                    JArray zones=diagnostic?["contact_zones"] as JArray;
                    if(zones!=null && zones.Count>=2)
                    {
                        Int32.TryParse(zones[0].ToString(),out first);
                        Int32.TryParse(zones[1].ToString(),out second);
                    }
                    Int32.TryParse((string)diagnostic?["shared_slave_nodes"],out count);
                    var stable=System.Text.RegularExpressions.Regex.Match(evidence,
                        @"contact_zones=(\d+),(\d+);shared_slave_nodes=(\d+)");
                    if(stable.Success)
                    {
                        first=Int32.Parse(stable.Groups[1].Value,CultureInfo.InvariantCulture);
                        second=Int32.Parse(stable.Groups[2].Value,CultureInfo.InvariantCulture);
                        count=Int32.Parse(stable.Groups[3].Value,CultureInfo.InvariantCulture);
                    }
                    if(first==0 || second==0)
                    {
                        var legacy=System.Text.RegularExpressions.Regex.Match(evidence,
                            @"zones? de contact[^\r\n]*?(\d+)[^\r\n]*?\bet\b[^\r\n]*?(\d+)[^\r\n]*?\bont\b\s+(\d+)",
                            System.Text.RegularExpressions.RegexOptions.IgnoreCase);
                        if(legacy.Success)
                        {
                            first=Int32.Parse(legacy.Groups[1].Value,CultureInfo.InvariantCulture);
                            second=Int32.Parse(legacy.Groups[2].Value,CultureInfo.InvariantCulture);
                            count=Int32.Parse(legacy.Groups[3].Value,CultureInfo.InvariantCulture);
                        }
                    }
                    b.AppendLine("CONTACT2_16: dos zonas de contacto comparten nodos esclavos.");
                    if(first>0 && second>0)
                        b.AppendLine("Zonas: "+ContactZoneLabel(workspace,first)+" y "+ContactZoneLabel(workspace,second)+".");
                    if(count>0) b.AppendLine("Nodos esclavos compartidos: "+count.ToString(CultureInfo.InvariantCulture)+".");
                    b.AppendLine("Esta formulación exige superficies esclavas sin nodos comunes entre zonas.");
                    b.AppendLine("Revise esos pares en Conexiones: sus regiones y la combinación maestro/esclavo deben ser compatibles.");
                }
                else
                {
                    if(!String.IsNullOrWhiteSpace(marker)) b.AppendLine("Code_Aster detuvo el cálculo: "+marker+".");
                    else if(exitCode==30) b.AppendLine("Code_Aster no produjo todos los archivos de resultado necesarios.");
                    else b.AppendLine("El proceso de cálculo terminó sin resultados aceptables.");
                    string detail=(string)diagnostic?["message"];
                    if(String.IsNullOrWhiteSpace(detail)) detail=FirstSolverFailureLine(evidence);
                    if(!String.IsNullOrWhiteSpace(detail)) b.AppendLine(ShortDiagnostic(detail,500));
                }
                b.AppendLine("No se han aceptado resultados de este intento.");
                b.AppendLine();
                b.AppendLine("Registros completos: "+workspace);
                return b.ToString().Trim();
            }
            catch(Exception ex)
            {
                return "El cálculo falló y no se pudo resumir su diagnóstico: "+ShortDiagnostic(ex.Message,250)+
                    "\nRegistros completos: "+workspace;
            }
        }

        private static string ShortDiagnostic(string text,int limit)
        {
            if(String.IsNullOrWhiteSpace(text)) return "";
            string cleaned=text.Replace("\0","").Trim();
            return cleaned.Length<=limit?cleaned:cleaned.Substring(0,limit)+"...";
        }

        private static string FirstSolverFailureLine(string text)
        {
            foreach(string raw in (text??"").Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries))
            {
                string line=raw.Trim();
                if(line.IndexOf("<EXCEPTION>",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("<F>",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("FATAL ERROR",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("ERREUR FATALE",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.StartsWith("ASTERMAX_CODE_ASTER_RUNNER:",StringComparison.Ordinal))
                    return ShortDiagnostic(line,500);
            }
            return "";
        }

        private static JObject ReadRunnerDiagnostic(string workspace)
        {
            string path=FindLatestDiagnosticFile(workspace,"astermax-runner-diagnostic.json");
            if(String.IsNullOrWhiteSpace(path)) return null;
            try
            {
                JObject result=JObject.Parse(File.ReadAllText(path));
                return (string)result["schema"]=="astermax-codeaster-runner-diagnostic/v1" &&
                       (string)result["status"]=="failed"?result:null;
            }
            catch { return null; }
        }

        private static string FindLatestDiagnosticFile(string workspace,string pattern)
        {
            if(String.IsNullOrWhiteSpace(workspace) || !Directory.Exists(workspace)) return null;
            var directories=new System.Collections.Generic.List<string>();
            directories.Add(workspace);
            directories.AddRange(Directory.GetDirectories(workspace,"failed-*",SearchOption.TopDirectoryOnly));
            string latest=null;
            DateTime modified=DateTime.MinValue;
            foreach(string directory in directories)
            {
                foreach(string file in Directory.GetFiles(directory,pattern,SearchOption.TopDirectoryOnly))
                {
                    DateTime time=File.GetLastWriteTimeUtc(file);
                    if(latest==null || time>modified) { latest=file;modified=time; }
                }
            }
            return latest;
        }

        private static string ReadDiagnosticText(string path)
        {
            if(String.IsNullOrWhiteSpace(path) || !File.Exists(path)) return "";
            // Very long traces remain on disk. Retain the beginning and tail for
            // summaries so a failed calculation cannot flood the dialog memory.
            using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite))
            {
                const int half=131072;
                if(stream.Length<=half*2)
                    using(var reader=new StreamReader(stream,Encoding.UTF8,true)) return reader.ReadToEnd();
                byte[] head=new byte[half];
                int headRead=stream.Read(head,0,head.Length);
                stream.Seek(-half,SeekOrigin.End);
                byte[] tail=new byte[half];
                int tailRead=stream.Read(tail,0,tail.Length);
                return Encoding.UTF8.GetString(head,0,headRead)+"\n[registro intermedio omitido en el resumen]\n"+
                       Encoding.UTF8.GetString(tail,0,tailRead);
            }
        }

        private static string ContactZoneLabel(string workspace,int index)
        {
            string label=index.ToString(CultureInfo.InvariantCulture);
            try
            {
                string path=Path.Combine(workspace,"ASTERMAX_SOLVE_TRANSACTION.json");
                if(!File.Exists(path)) return label;
                JObject transaction=JObject.Parse(File.ReadAllText(path));
                JArray zones=transaction["native_exporter_manifest"]?["contact_orientation_report"]?["zones"] as JArray;
                if(zones==null) return label;
                foreach(JObject zone in zones)
                {
                    if((int?)zone["zone_index"]!=index) continue;
                    string name=(string)zone["contact_name"];
                    if(!String.IsNullOrWhiteSpace(name)) label+=" ("+ShortDiagnostic(name,100).Replace("\r"," ").Replace("\n"," ")+")";
                    break;
                }
            }
            catch { }
            return label;
        }
        // C1207_SOLVER_DIAGNOSTICS_END

'@
    $source=$source.Substring(0,$start)+$replacement.Replace("`r",'')+$source.Substring($end)
    $old='Fail("Code_Aster solve failed (runner exit "+RunnerExitCode+")."+'
    $new='Fail("Code_Aster no pudo completar el cálculo (código del adaptador "+RunnerExitCode+")."+'
    if(-not $source.Contains($old)) { throw 'C12.07 failure message anchor missing.' }
    $source=$source.Replace($old,$new)
    $source=$source.Replace('"AsterMax Solve blocked: "+ex.Message','"Error de cálculo de AsterMax:\n\n"+ex.Message')

    $encodingAnchor=@'
            psi.RedirectStandardError=true;
            return psi;
'@
    $encodingNew=@'
            psi.RedirectStandardError=true;
            // The packaged adapter declares UTF-8 on its own process streams.
            // Leave third-party configured adapters at their existing encoding.
            string runnerName=Path.GetFileNameWithoutExtension(runner);
            if(String.Equals(runnerName,"astermax-codeaster-runner",StringComparison.OrdinalIgnoreCase))
            {
                psi.StandardOutputEncoding=new UTF8Encoding(false);
                psi.StandardErrorEncoding=new UTF8Encoding(false);
            }
            return psi;
'@
    # Windows checkouts use CRLF inside here-strings; the input was normalized
    # to LF above. Match and insert the same line endings on either platform.
    $encodingAnchor=$encodingAnchor.Replace("`r",'')
    if(-not $source.Contains($encodingAnchor)) { throw 'C12.07 runner encoding anchor missing.' }
    $source=$source.Replace($encodingAnchor,$encodingNew.Replace("`r",''))
    $fatalAnchor='                   line.IndexOf("FATAL ERROR",StringComparison.OrdinalIgnoreCase)>=0 ||'
    $fatalNew=@'
                   line.IndexOf("<EXCEPTION>",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("_ABNORMAL_ABORT",StringComparison.OrdinalIgnoreCase)>=0 ||
                   line.IndexOf("FATAL ERROR",StringComparison.OrdinalIgnoreCase)>=0 ||
'@
    # The summary helper contains the same line; patch only the evidence gate.
    $gateStart=$source.IndexOf('        private static string GetCodeAsterFailure(')
    if($gateStart -lt 0) { throw 'C12.07 evidence gate anchor missing.' }
    $head=$source.Substring(0,$gateStart)
    $gate=$source.Substring($gateStart)
    if(-not $gate.Contains($fatalAnchor)) { throw 'C12.07 fatal marker anchor missing.' }
    $source=$head+$gate.Replace($fatalAnchor,$fatalNew.Replace("`r",'').TrimEnd())
    [IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($false)))
}

if(-not $source.Contains('// C1207_CONTACT_ORIENTATION_INFO')) {
    $orientation=@'
        // C1207_CONTACT_ORIENTATION_INFO
        public static string DescribeContactOrientation(string workspace)
        {
            try
            {
                string path=Path.Combine(workspace,"ASTERMAX_SOLVE_TRANSACTION.json");
                if(!File.Exists(path)) return "";
                JObject transaction=JObject.Parse(File.ReadAllText(path));
                JObject report=transaction["native_exporter_manifest"]?["contact_orientation_report"] as JObject;
                int count=(int?)report?["swapped_count"] ?? 0;
                if(count<=0) return "";
                var names=new System.Collections.Generic.List<string>();
                JArray zones=report["zones"] as JArray;
                if(zones!=null)
                    foreach(JObject zone in zones)
                        if((bool?)zone["swapped"]==true)
                            names.Add(ShortDiagnostic((string)zone["contact_name"],100).Replace("\r"," ").Replace("\n"," "));
                return "Orientación de contactos: "+count.ToString(CultureInfo.InvariantCulture)+(count==1?" par reorientado":" pares reorientados")+" al exportar para evitar nodos esclavos repetidos.\r\n"+
                    "Pares: "+ShortDiagnostic(String.Join(", ",names),700)+".\r\n"+
                    "Se conservan las superficies y leyes; la orientación numérica maestro/esclavo cambió. Revise la convergencia y la calificación del resultado.";
            }
            catch { return "La auditoría de orientación de contactos no está disponible."; }
        }

'@
    $anchor='        // C1207_SOLVER_DIAGNOSTICS_END'
    if(-not $source.Contains($anchor)) { throw 'C12.07 orientation information anchor missing.' }
    $source=$source.Replace($anchor,$orientation.Replace("`r",'')+$anchor)
    [IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($false)))
}

$source=$source.Replace('count.ToString(CultureInfo.InvariantCulture)+" pares reorientados al exportar',
    'count.ToString(CultureInfo.InvariantCulture)+(count==1?" par reorientado":" pares reorientados")+" al exportar')
[IO.File]::WriteAllText($path,$source,(New-Object Text.UTF8Encoding($false)))

$informationPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$information=[regex]::Replace((Get-Content -LiteralPath $informationPath -Raw),"\r\n?","`n")
if(-not $information.Contains('// C1207_VISIBLE_CONTACT_ORIENTATION')) {
    $anchor='                text += "Workspace: " + _asterMaxSolveTransaction.Workspace + "\r\n";'
    $new=@'
                // C1207_VISIBLE_CONTACT_ORIENTATION
                string contactOrientation=AsterMaxNativeSolveTransaction.DescribeContactOrientation(_asterMaxSolveTransaction.Workspace);
                if(!String.IsNullOrWhiteSpace(contactOrientation)) text+="\r\n"+contactOrientation+"\r\n\r\n";
                text += "Workspace: " + _asterMaxSolveTransaction.Workspace + "\r\n";
'@
    if(-not $information.Contains($anchor)) { throw 'C12.07 Solution Information anchor missing.' }
    $information=$information.Replace($anchor,$new.Replace("`r",'').TrimEnd())
    [IO.File]::WriteAllText($informationPath,$information,(New-Object Text.UTF8Encoding($false)))
}

# Release labels follow the actual repair package rather than an inherited title.
foreach($relative in @('PrePoMax/Globals.cs','PrePoMax/Forms/AsterMaxC1034Audit.cs')) {
    $file=Join-Path $Root $relative
    if(Test-Path -LiteralPath $file) {
        $text=Get-Content -LiteralPath $file -Raw
        $text=$text.Replace('AsterMax Mechanical C12.06','AsterMax Mechanical C12.07')
        [IO.File]::WriteAllText($file,$text,(New-Object Text.UTF8Encoding($false)))
    }
}
Write-Host 'C12.07: concise contact failure diagnostics, UTF-8 adapter streams and fatal evidence guards applied.' -ForegroundColor Green
