param([string]$Root)
$ErrorActionPreference='Stop'

$src=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$code=@'
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using CaeModel;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    /// <summary>
    /// Native in-process Code_Aster input exporter for AsterMax.
    /// Model definition only: generates ASTER .mail/.comm files and an integrity manifest.
    /// It never executes a solver and never fabricates FEA results.
    /// </summary>
    public static class AsterMaxCodeAsterNativeExporter
    {
        public const string Version = "C9.61-native-codeaster-v0";

        public static JObject Export(FeModel model, string outDir, string baseName)
        {
            if(model==null) throw new ArgumentNullException(nameof(model));
            JObject contract=AsterMaxModelContractBridge.Build(model);
            return ExportContract(contract,outDir,baseName);
        }

        public static JObject ExportContract(JObject contract,string outDir,string baseName)
        {
            if(contract==null) throw new ArgumentNullException(nameof(contract));
            if((string)contract["schema"]!="astermax-model-contract/v0") throw new NotSupportedException("Unsupported AsterMax model contract schema.");
            if((string)contract["unit_system"]!="MM_N_S_MPA") throw new NotSupportedException("Code_Aster native exporter v0 requires MM_N_S_MPA.");
            if((string)contract["analysis"]?["type"]!="static_structural") throw new NotSupportedException("Code_Aster native exporter v0 supports static_structural only.");

            JObject mesh=(JObject)contract["mesh"];
            JArray nodes=(JArray)mesh["nodes"];
            JArray elements=(JArray)mesh["elements"];
            string elementType=(string)mesh["element_type"];
            if(elementType!="HEXA8") throw new NotSupportedException("C9.61 native exporter v0 currently supports HEXA8 only.");
            JArray mats=(JArray)contract["materials"];
            JArray supports=(JArray)contract["supports"];
            JArray loads=(JArray)contract["loads"];
            if(mats.Count!=1 || supports.Count!=1 || loads.Count!=1) throw new NotSupportedException("C9.61 native exporter v0 requires exactly one material, one support and one load.");

            Directory.CreateDirectory(outDir);
            if(String.IsNullOrWhiteSpace(baseName)) baseName="astermax-model";
            string mailPath=Path.Combine(outDir,baseName+".mail");
            string commPath=Path.Combine(outDir,baseName+".comm");
            string manifestPath=Path.Combine(outDir,baseName+".native-export.json");

            var mail=new List<string>{"TITRE","ASTERMAX C9.61 NATIVE - "+((string)contract["name"]??"AsterMax Model"),"FINSF","COOR_3D"};
            foreach(JObject n in nodes.Cast<JObject>().OrderBy(n=>(string)n["id"]))
                mail.Add(String.Format(CultureInfo.InvariantCulture,"{0}  {1}  {2}  {3}",(string)n["id"],F(n["x"]),F(n["y"]),F(n["z"])));
            mail.Add("FINSF"); mail.Add(elementType);
            foreach(JObject e in elements.Cast<JObject>().OrderBy(e=>(string)e["id"]))
                mail.Add((string)e["id"]+" "+String.Join(" ",((JArray)e["nodes"]).Select(x=>(string)x)));
            mail.Add("FINSF");
            JObject groups=(JObject)mesh["node_groups"];
            foreach(JProperty p in groups.Properties().OrderBy(p=>p.Name,StringComparer.Ordinal))
            {
                mail.Add("GROUP_NO");
                mail.Add(p.Name+" "+String.Join(" ",((JArray)p.Value).Select(x=>(string)x)));
                mail.Add("FINSF");
            }
            mail.Add("FIN");
            File.WriteAllLines(mailPath,mail,new System.Text.UTF8Encoding(false));

            JObject mat=(JObject)mats[0], sup=(JObject)supports[0], load=(JObject)loads[0];
            string loadGroup=(string)load["group"];
            JArray loadNodes=(JArray)groups[loadGroup];
            if(loadNodes==null || loadNodes.Count<1) throw new InvalidOperationException("Load group is empty or missing: "+loadGroup);
            double fx=GetDouble(load,"fx_total_n")/loadNodes.Count;
            double fy=GetDouble(load,"fy_total_n")/loadNodes.Count;
            double fz=GetDouble(load,"fz_total_n")/loadNodes.Count;
            string probeGroup=(string)contract["postprocess"]?["displacement_probe_group"] ?? loadGroup;

            string comm=String.Format(CultureInfo.InvariantCulture,@"DEBUT()

mesh = LIRE_MAILLAGE(FORMAT='ASTER', UNITE=20)
model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'))
steel = DEFI_MATERIAU(ELAS=_F(E={0}, NU={1}))
matfield = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', MATER=steel))
fixed = AFFE_CHAR_MECA(MODELE=model, DDL_IMPO=_F(GROUP_NO='{2}', DX={3}, DY={4}, DZ={5}))
load = AFFE_CHAR_MECA(MODELE=model, FORCE_NODALE=_F(GROUP_NO='{6}', FX={7}, FY={8}, FZ={9}))
result = MECA_STATIQUE(MODELE=model, CHAM_MATER=matfield, EXCIT=(_F(CHARGE=fixed), _F(CHARGE=load)))
result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',))
probe = POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION', INTITULE='LOAD_FACE_DISPLACEMENT', RESULTAT=result, NOM_CHAM='DEPL', GROUP_NO='{10}', NOM_CMP=('DX','DY','DZ'), TOUT_ORDRE='OUI'))
IMPR_TABLE(TABLE=probe, UNITE=80)
IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result))
FIN()
",F(mat["young_modulus_mpa"]),F(mat["poisson"]),(string)sup["group"],F(sup["dx"]),F(sup["dy"]),F(sup["dz"]),loadGroup,F(fx),F(fy),F(fz),probeGroup);
            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));

            JObject manifest=new JObject
            {
                ["exporter"]=Version,
                ["source_schema"]=(string)contract["schema"],
                ["unit_system"]=(string)contract["unit_system"],
                ["nodes"]=nodes.Count,
                ["elements"]=elements.Count,
                ["element_type"]=elementType,
                ["load_nodes"]=loadNodes.Count,
                ["fx_per_node_n"]=fx,
                ["fy_per_node_n"]=fy,
                ["fz_per_node_n"]=fz,
                ["generated_mail"]=Path.GetFileName(mailPath),
                ["generated_comm"]=Path.GetFileName(commPath),
                ["solver_execution"]="NOT_RUN",
                ["fea_results_claimed"]=false,
                ["requested_postprocess"]=new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","MED")
            };
            File.WriteAllText(manifestPath,manifest.ToString(Formatting.Indented),new System.Text.UTF8Encoding(false));
            return manifest;
        }

        private static double GetDouble(JObject o,string name){ JToken t=o[name]; if(t==null) return 0.0; return t.Value<double>(); }
        private static string F(JToken token){ return token==null?"0":F(token.Value<double>()); }
        private static string F(double v){ return v.ToString("0.###############",CultureInfo.InvariantCulture); }
    }
}
'@
Set-Content $src $code -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/AsterMaxModelContractUi.cs'
$ui=Get-Content $uiPath -Raw
if(-not $ui.Contains('ExportAsterMaxCodeAsterDeck')){
$anchor='        private void ExportAsterMaxModelContract()'
if(-not $ui.Contains($anchor)){ throw 'C9.61 UI anchor missing.' }
$method=@'
        private void ExportAsterMaxCodeAsterDeck()
        {
            try
            {
                if (_controller == null || _controller.Model == null)
                {
                    MessageBoxes.ShowError("No active AsterMax model is available.");
                    return;
                }
                using (FolderBrowserDialog dlg = new FolderBrowserDialog())
                {
                    dlg.Description = "Select folder for native Code_Aster input deck";
                    if (dlg.ShowDialog(this) != DialogResult.OK) return;
                    AsterMaxCodeAsterNativeExporter.Export(_controller.Model, dlg.SelectedPath, "astermax-model");
                    tsslState.Text = "Native Code_Aster deck exported (.mail/.comm)";
                }
            }
            catch (Exception ex) { ExceptionTools.Show(this, ex); }
        }

'@
$ui=$ui.Replace($anchor,$method+$anchor)
Set-Content $uiPath $ui -Encoding UTF8
}

$projPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$proj=Get-Content $projPath -Raw
if(-not $proj.Contains('AsterMaxCodeAsterNativeExporter.cs')){
  $anchor='<Compile Include="AsterMaxModelContractBridge.cs" />'
  if(-not $proj.Contains($anchor)){ throw 'C9.61 project bridge anchor missing.' }
  $proj=$proj.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="AsterMaxCodeAsterNativeExporter.cs" />')
  Set-Content $projPath $proj -Encoding UTF8
}

$nativeUi=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$t=Get-Content $nativeUi -Raw
if(-not $t.Contains('Export Code_Aster Deck')){
  $anchor='CommandButton("Export Solver Contract", () => ExportAsterMaxModelContract()),'
  if(-not $t.Contains($anchor)){ throw 'C9.61 Solution ribbon command anchor missing.' }
  $t=$t.Replace($anchor,$anchor+[Environment]::NewLine+'                CommandButton("Export Code_Aster Deck", () => ExportAsterMaxCodeAsterDeck()),')
  Set-Content $nativeUi $t -Encoding UTF8
}
Write-Host 'C9.61 native in-process Code_Aster exporter injected.' -ForegroundColor Green
