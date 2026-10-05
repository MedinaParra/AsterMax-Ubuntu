param([string]$Root)
$ErrorActionPreference='Stop'

# C10.08 repairs the production ASTER .mail node-group encoding used by the
# native exporter. Large GUI selections must be emitted as explicit named,
# wrapped records and every original AsterMax name must map deterministically
# to a valid Code_Aster identifier.

$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporterPath)){ throw 'C10.08 requires the C10.04 native tetra exporter first.' }
$e=Get-Content $exporterPath -Raw

$e=$e.Replace('public const string Version = "C10.04-native-codeaster-tetra-v1";',
              'public const string Version = "C10.08-native-codeaster-tetra-v2";')

$old=@'
            JObject groups=(JObject)mesh["node_groups"];
            foreach(JProperty p in groups.Properties().OrderBy(p=>p.Name,StringComparer.Ordinal))
            {
                mail.Add("GROUP_NO");
                mail.Add(p.Name+" "+String.Join(" ",((JArray)p.Value).Select(x=>(string)x)));
                mail.Add("FINSF");
            }
'@
$new=@'
            JObject groups=(JObject)mesh["node_groups"];
            var asterGroupNames=new Dictionary<string,string>(StringComparer.Ordinal);
            var usedAsterGroupNames=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(JProperty p in groups.Properties().OrderBy(p=>p.Name,StringComparer.Ordinal))
            {
                JArray ids=p.Value as JArray;
                if(ids==null || ids.Count==0) continue;
                string asterName=CreateAsterGroupName(p.Name,usedAsterGroupNames);
                asterGroupNames[p.Name]=asterName;
                mail.Add("GROUP_NO NOM = "+asterName);
                const int idsPerRecord=8;
                for(int start=0;start<ids.Count;start+=idsPerRecord)
                    mail.Add(String.Join(" ",ids.Skip(start).Take(idsPerRecord).Select(x=>(string)x)));
                mail.Add("FINSF");
            }
'@
if(-not $e.Contains($old)){ throw 'C10.08 legacy GROUP_NO exporter anchor missing.' }
$e=$e.Replace($old,$new)

$old=@'
            JObject mat=(JObject)mats[0], sup=(JObject)supports[0], load=(JObject)loads[0];
            string loadGroup=(string)load["group"];
            JArray loadNodes=(JArray)groups[loadGroup];
            if(loadNodes==null || loadNodes.Count<1) throw new InvalidOperationException("Load group is empty or missing: "+loadGroup);
            double fx=GetDouble(load,"fx_total_n")/loadNodes.Count;
            double fy=GetDouble(load,"fy_total_n")/loadNodes.Count;
            double fz=GetDouble(load,"fz_total_n")/loadNodes.Count;
            string probeGroup=(string)contract["postprocess"]?["displacement_probe_group"] ?? loadGroup;
'@
$new=@'
            JObject mat=(JObject)mats[0], sup=(JObject)supports[0], load=(JObject)loads[0];
            string supportGroup=(string)sup["group"];
            string loadGroup=(string)load["group"];
            string probeGroup=(string)contract["postprocess"]?["displacement_probe_group"] ?? loadGroup;
            JArray loadNodes=(JArray)groups[loadGroup];
            if(loadNodes==null || loadNodes.Count<1) throw new InvalidOperationException("Load group is empty or missing: "+loadGroup);
            string supportGroupAster=RequireMappedGroup(asterGroupNames,supportGroup,"support");
            string loadGroupAster=RequireMappedGroup(asterGroupNames,loadGroup,"load");
            string probeGroupAster=RequireMappedGroup(asterGroupNames,probeGroup,"result probe");
            double fx=GetDouble(load,"fx_total_n")/loadNodes.Count;
            double fy=GetDouble(load,"fy_total_n")/loadNodes.Count;
            double fz=GetDouble(load,"fz_total_n")/loadNodes.Count;
'@
if(-not $e.Contains($old)){ throw 'C10.08 group-consumer mapping anchor missing.' }
$e=$e.Replace($old,$new)

$old='",F(mat["young_modulus_mpa"]),F(mat["poisson"]),(string)sup["group"],F(sup["dx"]),F(sup["dy"]),F(sup["dz"]),loadGroup,F(fx),F(fy),F(fz),probeGroup);'
$new='",F(mat["young_modulus_mpa"]),F(mat["poisson"]),supportGroupAster,F(sup["dx"]),F(sup["dy"]),F(sup["dz"]),loadGroupAster,F(fx),F(fy),F(fz),probeGroupAster);'
if(-not $e.Contains($old)){ throw 'C10.08 .comm mapped-group argument anchor missing.' }
$e=$e.Replace($old,$new)

$anchor='                ["load_nodes"]=loadNodes.Count,'
$insert=@'
                ["load_nodes"]=loadNodes.Count,
                ["node_group_name_map"]=JObject.FromObject(asterGroupNames),
                ["group_record_encoding"]="GROUP_NO_NOM_WRAPPED_8",
'@
if(-not $e.Contains('["group_record_encoding"]')){
    if(-not $e.Contains($anchor)){ throw 'C10.08 exporter manifest group-map anchor missing.' }
    $e=$e.Replace($anchor,$insert.TrimEnd())
}

$anchor='        private static double GetDouble(JObject o,string name)'
$helpers=@'
        private static string CreateAsterGroupName(string source,HashSet<string> used)
        {
            string raw=String.IsNullOrWhiteSpace(source)?"GROUP":source.Trim().ToUpperInvariant();
            char[] chars=raw.ToCharArray();
            for(int i=0;i<chars.Length;i++)
            {
                char c=chars[i];
                bool asciiLetter=(c>='A' && c<='Z');
                bool digit=(c>='0' && c<='9');
                if(!asciiLetter && !digit && c!='_') chars[i]='_';
            }
            string stem=new string(chars).Trim('_');
            if(String.IsNullOrWhiteSpace(stem)) stem="GROUP";
            if(stem[0]>='0' && stem[0]<='9') stem="G_"+stem;
            if(stem.Length>24) stem=stem.Substring(0,24);
            string candidate=stem;
            int suffix=2;
            while(!used.Add(candidate))
            {
                string tail="_"+suffix.ToString(CultureInfo.InvariantCulture);
                int keep=Math.Max(1,24-tail.Length);
                candidate=(stem.Length>keep?stem.Substring(0,keep):stem)+tail;
                suffix++;
            }
            return candidate;
        }

        private static string RequireMappedGroup(Dictionary<string,string> map,string original,string role)
        {
            string mapped;
            if(String.IsNullOrWhiteSpace(original) || !map.TryGetValue(original,out mapped))
                throw new InvalidOperationException("The "+role+" node group is missing or empty: "+(original??"<null>"));
            return mapped;
        }

'@
if(-not $e.Contains('private static string CreateAsterGroupName(')){
    if(-not $e.Contains($anchor)){ throw 'C10.08 exporter helper insertion anchor missing.' }
    $e=$e.Replace($anchor,$helpers+$anchor)
}

Set-Content $exporterPath $e -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $uiPath){
    $u=Get-Content $uiPath -Raw
    $u=$u.Replace('Code_Aster | verified runtime + MED','Code_Aster | real TET solve + MED verified')
    Set-Content $uiPath $u -Encoding UTF8
}

$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
if(Test-Path $globalsPath){
    $g=Get-Content $globalsPath -Raw
    $g=$g.Replace('AsterMax Mechanical C10.04','AsterMax Mechanical C10.08')
    Set-Content $globalsPath $g -Encoding UTF8
}

Write-Host 'C10.08 ASTER named/wrapped node-group records injected.' -ForegroundColor Green
