using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using CaeModel;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal static class AsterMaxCodeAsterLoadHistoryExporter
    {
        public const string Version="C10.29-static-history-v2";

        public static JObject Export(FeModel model,string outDir,string baseName)
        {
            if(model==null) throw new ArgumentNullException(nameof(model));
            var assignment=AsterMaxAssignmentQualityGate.Evaluate(model);
            if(assignment.Status!="READY")
                throw new InvalidOperationException("Material assignment incomplete: "+String.Join("; ",assignment.Issues));
            if(model.Materials.Values.Any(m=>!m.Active || !m.Valid))
                throw new InvalidOperationException("Material must be active and valid before export.");
            return ExportContract(AsterMaxSurfaceMechanicsContract.Build(model),outDir,baseName);
        }

        public static JObject ExportContract(JObject contract,string outDir,string baseName)
        {
            if((string)contract["schema"]!="astermax-model-contract/v0") throw new NotSupportedException("Unsupported model contract.");
            if((string)contract["unit_system"]!="MM_N_S_MPA") throw new NotSupportedException("Expected mm-N-MPa contract.");
            JObject mesh=(JObject)contract["mesh"];
            JArray nodes=(JArray)mesh["nodes"];
            JArray elements=(JArray)mesh["elements"];
            JObject nodeGroups=(JObject)mesh["node_groups"] ?? new JObject();
            JObject surfaces=(JObject)mesh["surface_groups"] ?? new JObject();
            JObject volumeGroups=(JObject)mesh["volume_groups"] ?? new JObject();
            JArray materials=(JArray)contract["materials"];
            JArray materialAssignments=(JArray)contract["material_assignments"] ?? new JArray();
            JObject amplitudes=(JObject)contract["amplitudes"] ?? new JObject();
            JArray supports=(JArray)contract["supports"];
            JArray loads=(JArray)contract["loads"];
            // Each excitation owns its multiplier; constant loads must remain constant.
            var amplitudeSymbols=new Dictionary<string,string>(StringComparer.Ordinal);
            var historyTimes=new SortedSet<double>();
            foreach(JObject item in loads.Concat(supports).Cast<JObject>())
            {
                string name=(string)item["amplitude"];
                if(String.IsNullOrWhiteSpace(name) || amplitudeSymbols.ContainsKey(name)) continue;
                JObject amplitude=amplitudes[name] as JObject;
                ValidateAmplitude(amplitude,name);
                amplitudeSymbols[name]="amp"+amplitudeSymbols.Count.ToString(CultureInfo.InvariantCulture);
                foreach(JArray point in ((JArray)amplitude["points"]).Cast<JArray>()) historyTimes.Add(point[0].Value<double>());
            }
            if(supports.Count==0) throw new InvalidOperationException("Static analysis requires displacement constraints.");
            bool historyEnabled=amplitudeSymbols.Count>0;
            double finalTime=historyEnabled?historyTimes.Max:0.0;
            JArray analysisTimes=historyEnabled?new JArray(historyTimes):null;
            var historyFunctions=new StringBuilder();
            foreach(var pair in amplitudeSymbols)
            {
                var flat=((JArray)amplitudes[pair.Key]["points"]).Cast<JArray>()
                    .SelectMany(point=>new[]{F(point[0]),F(point[1])});
                historyFunctions.AppendLine(pair.Value+"=DEFI_FONCTION(NOM_PARA='INST',VALE=("+String.Join(",",flat)+",),PROL_GAUCHE='CONSTANT',PROL_DROITE='CONSTANT')");
            }
            if(historyEnabled)
            {
                double[] times=historyTimes.ToArray();
                var intervals=times.Skip(1).Select(time=>"_F(JUSQU_A="+F(time)+",NOMBRE=1)");
                historyFunctions.AppendLine("linst=DEFI_LIST_REEL(DEBUT="+F(times[0])+",INTERVALLE=("+String.Join(",",intervals)+",))");
            }

            if(materials==null || materials.Count<1) throw new InvalidOperationException("At least one material is required.");
            if(materials.Count>1 && materialAssignments.Count==0)
                throw new InvalidOperationException("Multiple materials require explicit SolidSection material assignments.");

            Directory.CreateDirectory(outDir);
            if(String.IsNullOrWhiteSpace(baseName)) baseName="astermax-model";
            string mailPath=Path.Combine(outDir,baseName+".mail");
            string commPath=Path.Combine(outDir,baseName+".comm");
            string manifestPath=Path.Combine(outDir,baseName+".native-export.json");

            var mail=new List<string>{"TITRE","ASTERMAX C10.27 MULTI MATERIAL","FINSF","COOR_3D"};
            foreach(JObject n in nodes.Cast<JObject>().OrderBy(x=>(string)x["id"]))
                mail.Add(String.Format(CultureInfo.InvariantCulture,"{0} {1} {2} {3}",(string)n["id"],F(n["x"]),F(n["y"]),F(n["z"])));
            mail.Add("FINSF");

            string[] volumeTypes=elements.Cast<JObject>().Select(x=>(string)x["type"]).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(x=>x).ToArray();
            var allowedVolume=new HashSet<string>(StringComparer.OrdinalIgnoreCase){"TETRA4","TETRA10","HEXA8"};
            var volumeIds=new List<string>();
            foreach(string type in volumeTypes)
            {
                if(!allowedVolume.Contains(type)) throw new NotSupportedException("Unsupported volume element: "+type);
                mail.Add(type);
                foreach(JObject e in elements.Cast<JObject>().Where(x=>String.Equals((string)x["type"],type,StringComparison.OrdinalIgnoreCase)).OrderBy(x=>(string)x["id"]))
                {
                    JArray conn=(JArray)e["nodes"];
                    int expected=type=="TETRA4"?4:type=="TETRA10"?10:8;
                    ValidateConnectivity(e,conn,expected);
                    string id=(string)e["id"]; volumeIds.Add(id);
                    mail.Add(id+" "+String.Join(" ",conn.Select(x=>(string)x)));
                }
                mail.Add("FINSF");
            }

            var usedNames=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var nodeNameMap=new Dictionary<string,string>(StringComparer.Ordinal);
            foreach(JProperty p in nodeGroups.Properties().OrderBy(x=>x.Name,StringComparer.Ordinal))
            {
                JArray ids=p.Value as JArray; if(ids==null || ids.Count==0) continue;
                string mapped=CreateAsterGroupName("N_"+p.Name,usedNames); nodeNameMap[p.Name]=mapped;
                WriteGroup(mail,"GROUP_NO",mapped,ids.Select(x=>(string)x));
            }
            string volumeGroup=CreateAsterGroupName("ASTERMAX_VOLUME",usedNames);
            WriteGroup(mail,"GROUP_MA",volumeGroup,volumeIds);

            var volumeNameMap=new Dictionary<string,string>(StringComparer.Ordinal);
            foreach(JProperty p in volumeGroups.Properties().OrderBy(x=>x.Name,StringComparer.Ordinal))
            {
                JArray ids=p.Value as JArray; if(ids==null || ids.Count==0) continue;
                string mapped=CreateAsterGroupName("V_"+p.Name,usedNames); volumeNameMap[p.Name]=mapped;
                WriteGroup(mail,"GROUP_MA",mapped,ids.Select(x=>(string)x));
            }

            var surfaceNameMap=new Dictionary<string,string>(StringComparer.Ordinal);
            foreach(JProperty p in surfaces.Properties().OrderBy(x=>x.Name,StringComparer.Ordinal))
            {
                JObject s=(JObject)p.Value; JArray skin=(JArray)s["elements"];
                if(skin==null || skin.Count==0) continue;
                foreach(string type in skin.Cast<JObject>().Select(x=>(string)x["type"]).Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(x=>x))
                {
                    if(type!="TRIA3" && type!="TRIA6" && type!="QUAD4") throw new NotSupportedException("Unsupported skin element: "+type);
                    mail.Add(type);
                    foreach(JObject e in skin.Cast<JObject>().Where(x=>String.Equals((string)x["type"],type,StringComparison.OrdinalIgnoreCase)).OrderBy(x=>(string)x["id"]))
                    {
                        JArray conn=(JArray)e["nodes"]; int expected=type=="TRIA3"?3:type=="TRIA6"?6:4;
                        ValidateConnectivity(e,conn,expected);
                        mail.Add((string)e["id"]+" "+String.Join(" ",conn.Select(x=>(string)x)));
                    }
                    mail.Add("FINSF");
                }
                string mapped=CreateAsterGroupName("S_"+p.Name,usedNames); surfaceNameMap[p.Name]=mapped;
                WriteGroup(mail,"GROUP_MA",mapped,skin.Cast<JObject>().Select(x=>(string)x["id"]));
            }
            mail.Add("FIN");
            File.WriteAllLines(mailPath,mail,new UTF8Encoding(false));

            var ddl=new List<string>();
            var faceImpo=new List<string>();
            var variableSupports=new List<Tuple<string,string>>();
            var constrainedDofs=new HashSet<string>(StringComparer.Ordinal);
            var excitations=new List<string>();
            foreach(JObject s in supports.Cast<JObject>())
            {
                string type=(string)s["type"];
                if(type=="fixed" || type=="displacement")
                {
                    string group=RequireMapped(nodeNameMap,(string)s["group"],"support");
                    var terms=new List<string>{"GROUP_NO='"+group+"'"};
                    AddTerm(terms,"DX",s["dx"]); AddTerm(terms,"DY",s["dy"]); AddTerm(terms,"DZ",s["dz"]);
                    if(terms.Count==1) throw new InvalidOperationException("Displacement support has no constrained DOF.");
                    // Duplicate node/DOF constraints cause redundant Lagrange multipliers.
                    foreach(string dof in new[]{"dx","dy","dz"})
                        if(s[dof]!=null && s[dof].Type!=JTokenType.Null)
                            foreach(JToken id in (JArray)nodeGroups[(string)s["group"]])
                                if(!constrainedDofs.Add((string)id+":"+dof))
                                    throw new InvalidOperationException("Overlapping displacement constraints at "+id+" "+dof);
                    string factor="_F("+String.Join(",",terms)+")";
                    string amplitude=(string)s["amplitude"];
                    if(String.IsNullOrWhiteSpace(amplitude)) ddl.Add(factor);
                    else variableSupports.Add(Tuple.Create(factor,amplitudeSymbols[amplitude]));
                }
                else if(type=="frictionless_normal")
                {
                    if(!String.IsNullOrWhiteSpace((string)s["amplitude"]))
                        throw new NotSupportedException("Tabular normal displacement is not supported on frictionless surfaces.");
                    string group=RequireMapped(surfaceNameMap,(string)s["surface"],"frictionless surface");
                    faceImpo.Add("_F(GROUP_MA='"+group+"',DNOR="+F(s["dnor"])+")");
                }
                else throw new NotSupportedException("Unsupported support type: "+type);
            }

            double[] external=new double[]{0,0,0};
            double[] finalExternal=new double[]{0,0,0};
            double[] externalMoment=new double[]{0,0,0};
            double[] finalExternalMoment=new double[]{0,0,0};
            bool hasBodyLoad=false;
            var loadConcepts=new StringBuilder();
            var loadHistoryGroups=new JArray();
            JObject nodesById=new JObject(); foreach(JObject n in nodes.Cast<JObject>()) nodesById[(string)n["id"]]=n;
            int loadIndex=0;
            foreach(var batch in loads.Cast<JObject>().GroupBy(x=>(string)x["amplitude"] ?? "",StringComparer.Ordinal))
            {
            var nodalForces=new List<string>();
            var pressures=new List<string>();
            var surfaceForces=new List<string>();
            string gravityTerm=null;
            string rotationTerm=null;
            double[] batchExternal=new double[]{0,0,0};
            double[] batchMoment=new double[]{0,0,0};
            foreach(JObject l in batch)
            {
                string type=(string)l["type"];
                if(type=="nodal_force_per_node")
                {
                    string original=(string)l["group"]; string group=RequireMapped(nodeNameMap,original,"nodal load");
                    JArray ids=(JArray)nodeGroups[original]; if(ids==null || ids.Count==0) throw new InvalidOperationException("Empty load group: "+original);
                    double fx=GetDouble(l,"fx_per_node_n"),fy=GetDouble(l,"fy_per_node_n"),fz=GetDouble(l,"fz_per_node_n");
                    nodalForces.Add(String.Format(CultureInfo.InvariantCulture,"_F(GROUP_NO='{0}',FX={1},FY={2},FZ={3})",group,F(fx),F(fy),F(fz)));
                    batchExternal[0]+=fx*ids.Count; batchExternal[1]+=fy*ids.Count; batchExternal[2]+=fz*ids.Count;
                    foreach(JToken id in ids)
                    {
                        double[] m=Cross(Point(nodesById,(string)id),new double[]{fx,fy,fz});
                        for(int i=0;i<3;i++) batchMoment[i]+=m[i];
                    }
                }
                else if(type=="pressure")
                {
                    string original=(string)l["surface"]; string group=RequireMapped(surfaceNameMap,original,"pressure surface");
                    double p=GetDouble(l,"pressure_mpa"); pressures.Add("_F(GROUP_MA='"+group+"',PRES="+F(p)+")");
                    double[] r=PressureResultant((JObject)surfaces[original],nodesById,p);
                    double[] m=PressureMoment((JObject)surfaces[original],nodesById,p);
                    for(int i=0;i<3;i++) { batchExternal[i]+=r[i]; batchMoment[i]+=m[i]; }
                }
                else if(type=="surface_traction")
                {
                    string original=(string)l["surface"]; string group=RequireMapped(surfaceNameMap,original,"surface traction");
                    double fx=GetDouble(l,"fx_n_per_mm2"),fy=GetDouble(l,"fy_n_per_mm2"),fz=GetDouble(l,"fz_n_per_mm2");
                    surfaceForces.Add("_F(GROUP_MA='"+group+"',FX="+F(fx)+",FY="+F(fy)+",FZ="+F(fz)+")");
                    double area=SurfaceArea((JObject)surfaces[original],nodesById);
                    double[] m=SurfaceTractionMoment((JObject)surfaces[original],nodesById,new double[]{fx,fy,fz});
                    batchExternal[0]+=fx*area; batchExternal[1]+=fy*area; batchExternal[2]+=fz*area;
                    for(int i=0;i<3;i++) batchMoment[i]+=m[i];
                }
                else if(type=="gravity")
                {
                    if(gravityTerm!=null) throw new NotSupportedException("Code_Aster backend currently permits one PESANTEUR definition per mechanical load.");
                    string group=RequireMapped(volumeNameMap,(string)l["volume_group"],"gravity volume");
                    JArray d=(JArray)l["direction"];
                    if(d==null || d.Count!=3) throw new InvalidOperationException("Gravity direction vector is invalid.");
                    gravityTerm="_F(GROUP_MA='"+group+"',GRAVITE="+F(l["gravity_mm_s2"])+
                                ",DIRECTION=("+F(d[0])+","+F(d[1])+","+F(d[2])+"))";
                }
                else if(type=="rotation")
                {
                    if(rotationTerm!=null) throw new NotSupportedException("Code_Aster backend currently permits one ROTATION definition per mechanical load.");
                    string group=RequireMapped(volumeNameMap,(string)l["volume_group"],"rotation volume");
                    JArray axis=(JArray)l["axis"]; JArray center=(JArray)l["center_mm"];
                    if(axis==null || axis.Count!=3 || center==null || center.Count!=3)
                        throw new InvalidOperationException("Rotation axis/center definition is invalid.");
                    rotationTerm="_F(GROUP_MA='"+group+"',VITESSE="+F(l["omega_rad_s"])+
                                 ",AXE=("+F(axis[0])+","+F(axis[1])+","+F(axis[2])+")"+
                                 ",CENTRE=("+F(center[0])+","+F(center[1])+","+F(center[2])+"))";
                }
                else throw new NotSupportedException("Unsupported load type: "+type);
            }

            hasBodyLoad |= gravityTerm!=null || rotationTerm!=null;
            var loadArgs=new List<string>();
            if(nodalForces.Count>0) loadArgs.Add("FORCE_NODALE=("+String.Join(",",nodalForces)+",)");
            if(pressures.Count>0) loadArgs.Add("PRES_REP=("+String.Join(",",pressures)+",)");
            if(surfaceForces.Count>0) loadArgs.Add("FORCE_FACE=("+String.Join(",",surfaceForces)+",)");
            if(gravityTerm!=null) loadArgs.Add("PESANTEUR="+gravityTerm);
            if(rotationTerm!=null) loadArgs.Add("ROTATION="+rotationTerm);
            string symbol="load"+(loadIndex++).ToString(CultureInfo.InvariantCulture);
            loadConcepts.AppendLine(symbol+"=AFFE_CHAR_MECA(MODELE=model,"+String.Join(",",loadArgs)+")");
            bool constant=String.IsNullOrWhiteSpace(batch.Key);
            excitations.Add("_F(CHARGE="+symbol+(constant?"":",FONC_MULT="+amplitudeSymbols[batch.Key])+")");
            double multiplier=constant?1.0:AmplitudeValue((JArray)amplitudes[batch.Key]["points"],finalTime);
            for(int i=0;i<3;i++)
            {
                external[i]+=batchExternal[i]; finalExternal[i]+=batchExternal[i]*multiplier;
                externalMoment[i]+=batchMoment[i]; finalExternalMoment[i]+=batchMoment[i]*multiplier;
            }
            loadHistoryGroups.Add(new JObject { ["amplitude"]=constant?(JToken)JValue.CreateNull():batch.Key,
                ["final_multiplier"]=multiplier,["base_external_resultant_n"]=new JArray(batchExternal),
                ["base_external_moment_n_mm"]=new JArray(batchMoment) });
            }
            var materialsByName=new Dictionary<string,JObject>(StringComparer.Ordinal);
            int materialIndex=0;
            foreach(JObject mat in materials.Cast<JObject>())
            {
                string name=(string)mat["name"];
                if(String.IsNullOrWhiteSpace(name)) throw new InvalidOperationException("Material name is missing.");
                if(materialsByName.ContainsKey(name)) throw new InvalidOperationException("Duplicate material name: "+name);
                materialsByName[name]=mat;
                materialIndex++;
            }

            var assignedNames=new HashSet<string>(StringComparer.Ordinal);
            foreach(JObject a in materialAssignments.Cast<JObject>())
            {
                string name=(string)a["material"];
                if(String.IsNullOrWhiteSpace(name) || !materialsByName.ContainsKey(name))
                    throw new InvalidOperationException("Material assignment refers to an unknown material: "+(name??"<null>"));
                assignedNames.Add(name);
            }
            if(materialAssignments.Count==0 && materials.Count==1)
                assignedNames.Add((string)((JObject)materials[0])["name"]);

            if(hasBodyLoad)
            {
                foreach(string name in assignedNames)
                {
                    JObject mat=materialsByName[name];
                    JToken rhoToken=mat["density_tonne_per_mm3"];
                    double rho=rhoToken==null?0.0:rhoToken.Value<double>();
                    if(!(rho>0) || double.IsNaN(rho) || double.IsInfinity(rho))
                        throw new InvalidOperationException("Gravity/rotation requires positive material density (RHO) for assigned material: "+name);
                }
            }

            var comm=new StringBuilder();
            comm.AppendLine("DEBUT()");
            comm.Append(historyFunctions);
            comm.AppendLine("mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)");
            comm.AppendLine("model=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(GROUP_MA='"+volumeGroup+"',PHENOMENE='MECANIQUE',MODELISATION='3D'))");

            var matSymbols=new Dictionary<string,string>(StringComparer.Ordinal);
            materialIndex=0;
            foreach(JObject mat in materials.Cast<JObject>())
            {
                string name=(string)mat["name"];
                string symbol="mat"+materialIndex.ToString(CultureInfo.InvariantCulture);
                matSymbols[name]=symbol;
                string elas="E="+F(mat["young_modulus_mpa"])+",NU="+F(mat["poisson"]);
                JToken rhoToken=mat["density_tonne_per_mm3"];
                if(rhoToken!=null)
                {
                    double rho=rhoToken.Value<double>();
                    if(rho>0) elas+=",RHO="+F(rho);
                }
                comm.AppendLine(symbol+"=DEFI_MATERIAU(ELAS=_F("+elas+"))");
                materialIndex++;
            }

            var materialFactors=new List<string>();
            if(materialAssignments.Count>0)
            {
                foreach(JObject a in materialAssignments.Cast<JObject>())
                {
                    string materialName=(string)a["material"];
                    string group=RequireMapped(volumeNameMap,(string)a["volume_group"],"material assignment");
                    string symbol;
                    if(!matSymbols.TryGetValue(materialName,out symbol))
                        throw new InvalidOperationException("No Code_Aster material symbol for: "+materialName);
                    materialFactors.Add("_F(GROUP_MA='"+group+"',MATER="+symbol+")");
                }
            }
            else
            {
                string onlyName=(string)((JObject)materials[0])["name"];
                materialFactors.Add("_F(GROUP_MA='"+volumeGroup+"',MATER="+matSymbols[onlyName]+")");
            }
            comm.AppendLine("matfield=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=("+String.Join(",",materialFactors)+",))");
            var bcArgs=new List<string>();
            if(ddl.Count>0) bcArgs.Add("DDL_IMPO=("+String.Join(",",ddl)+",)");
            if(faceImpo.Count>0) bcArgs.Add("FACE_IMPO=("+String.Join(",",faceImpo)+",)");
            if(bcArgs.Count>0)
            {
                comm.AppendLine("bc=AFFE_CHAR_MECA(MODELE=model,"+String.Join(",",bcArgs)+")");
                excitations.Add("_F(CHARGE=bc)");
            }
            for(int i=0;i<variableSupports.Count;i++)
            {
                string symbol="bct"+i.ToString(CultureInfo.InvariantCulture);
                comm.AppendLine(symbol+"=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=("+variableSupports[i].Item1+",))");
                excitations.Add("_F(CHARGE="+symbol+",FONC_MULT="+variableSupports[i].Item2+")");
            }
            comm.Append(loadConcepts);
            string listInstArg=historyEnabled?",LIST_INST=linst":"";
            comm.AppendLine("result=MECA_STATIQUE(MODELE=model,CHAM_MATER=matfield,EXCIT=("+String.Join(",",excitations)+",)"+listInstArg+")");
            comm.AppendLine("result=CALC_CHAMP(reuse=result,RESULTAT=result,CONTRAINTE=('SIGM_ELNO',),CRITERES=('SIEQ_ELNO',),FORCE=('REAC_NODA',))");
            string probeOriginal=(string)contract["postprocess"]?["displacement_probe_group"];
            if(!String.IsNullOrWhiteSpace(probeOriginal) && nodeNameMap.ContainsKey(probeOriginal))
            {
                string probe=nodeNameMap[probeOriginal];
                comm.AppendLine("probe=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='ASTERMAX_PROBE',RESULTAT=result,NOM_CHAM='DEPL',GROUP_NO='"+probe+"',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))");
                comm.AppendLine("IMPR_TABLE(TABLE=probe,UNITE=80)");
            }
            comm.AppendLine("IMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=result))");
            comm.AppendLine("FIN()");
            File.WriteAllText(commPath,comm.ToString(),new UTF8Encoding(false));

            JObject manifest=new JObject {
                ["exporter"]=Version,["unit_system"]=(string)contract["unit_system"],
                ["nodes"]=nodes.Count,["volume_elements"]=elements.Count,["element_types"]=new JArray(volumeTypes),
                ["support_count"]=supports.Count,["load_count"]=loads.Count,["surface_group_count"]=surfaces.Count,
                ["pressure_uses_pres_rep"]=loads.Cast<JObject>().Any(x=>(string)x["type"]=="pressure"),["frictionless_uses_face_impo_dnor"]=faceImpo.Count>0,
                ["surface_traction_uses_force_face"]=loads.Cast<JObject>().Any(x=>(string)x["type"]=="surface_traction"),
                ["gravity_uses_pesanteur"]=loads.Cast<JObject>().Any(x=>(string)x["type"]=="gravity"),["rotation_uses_rotation"]=loads.Cast<JObject>().Any(x=>(string)x["type"]=="rotation"),
                ["material_count"]=materials.Count,["material_assignment_count"]=materialAssignments.Count,
                ["material_density_tonne_per_mm3"]=materials.Count==1?
                    ((JObject)materials[0])["density_tonne_per_mm3"]:null,
                ["material_assignment_mode"]=materialAssignments.Count>0?"SOLID_SECTION_GROUPS":"SINGLE_MATERIAL_ALL_VOLUME",
                ["expected_external_resultant_n"]=new JArray(finalExternal),
                ["expected_external_moment_n_mm"]=new JArray(finalExternalMoment),
                ["base_external_resultant_n"]=new JArray(external[0],external[1],external[2]),
                ["base_external_moment_n_mm"]=new JArray(externalMoment),
                ["load_history_enabled"]=historyEnabled,
                ["displacement_history_count"]=variableSupports.Count,
                ["load_history_groups"]=loadHistoryGroups,
                ["load_history_amplitude"]=loadHistoryGroups.Count==1?loadHistoryGroups[0]["amplitude"]:(JToken)JValue.CreateNull(),
                ["load_history_final_multiplier"]=loadHistoryGroups.Count==1?loadHistoryGroups[0]["final_multiplier"]:(JToken)JValue.CreateNull(),
                ["analysis_times"]=analysisTimes==null?(JToken)JValue.CreateNull():analysisTimes,
                ["result_selection"]="LAST_AVAILABLE_INSTANT",
                ["external_resultant_complete"]=!hasBodyLoad,
                ["external_resultant_note"]=hasBodyLoad?
                    "Nodal-force/pressure/surface-traction force and moment resultants only; gravity/rotation body-load resultants are intentionally not inferred.":
                    "Independent force and moment resultants include all supported applied loads; moments are about the global origin.",
                ["volume_group_name_map"]=JObject.FromObject(volumeNameMap),
                ["scope_binding"]=new JObject { ["mode"]="model_fingerprint_mesh_scope",["verified"]=true,["mesh_scope_membership_in_fingerprint"]=true },
                ["generated_mail"]=Path.GetFileName(mailPath),["generated_comm"]=Path.GetFileName(commPath),
                ["solver_execution"]="NOT_RUN",["fea_values_claimed"]=false,
                ["requested_postprocess"]=new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","REAC_NODA","MED")
            };
            File.WriteAllText(manifestPath,manifest.ToString(Formatting.Indented),new UTF8Encoding(false));
            return manifest;
        }

        private static void ValidateAmplitude(JObject amplitude,string name)
        {
            if(amplitude==null) throw new InvalidOperationException("Missing amplitude: "+name);
            JArray points=amplitude["points"] as JArray;
            if(points==null || points.Count<2) throw new InvalidOperationException("Amplitude needs at least two points: "+name);
            foreach(string key in new[]{"interpolation","extrapolation_left","extrapolation_right"})
            {
                string expected=key=="interpolation"?"LINEAR":"CONSTANT";
                if(amplitude[key]!=null && (string)amplitude[key]!=expected)
                    throw new NotSupportedException("Unsupported amplitude "+key+": "+name);
            }
            double previous=Double.NegativeInfinity;
            foreach(JToken token in points)
            {
                JArray point=token as JArray;
                if(point==null || point.Count!=2) throw new InvalidOperationException("Invalid amplitude point: "+name);
                foreach(JToken value in point)
                    if(value.Type!=JTokenType.Integer && value.Type!=JTokenType.Float)
                        throw new InvalidOperationException("Amplitude values must be numeric: "+name);
                double time=point[0].Value<double>(), factor=point[1].Value<double>();
                if(Double.IsNaN(time)||Double.IsInfinity(time)||Double.IsNaN(factor)||Double.IsInfinity(factor)||time<=previous)
                    throw new InvalidOperationException("Amplitude needs finite values and increasing times: "+name);
                previous=time;
            }
        }
        private static double AmplitudeValue(JArray points,double time)
        {
            if(time<=points[0][0].Value<double>()) return points[0][1].Value<double>();
            for(int i=1;i<points.Count;i++)
            {
                double t=points[i][0].Value<double>();
                if(time<=t)
                {
                    double start=points[i-1][0].Value<double>(), a=points[i-1][1].Value<double>();
                    return a+(points[i][1].Value<double>()-a)*(time-start)/(t-start);
                }
            }
            return points[points.Count-1][1].Value<double>();
        }
        private static double SurfaceArea(JObject surface,JObject nodes)
        {
            if(surface==null) throw new InvalidOperationException("Surface traction metadata missing.");
            JArray skin=(JArray)surface["elements"];
            if(skin==null || skin.Count==0) throw new InvalidOperationException("Surface traction has no skin elements.");
            double total=0.0;
            foreach(JObject e in skin.Cast<JObject>())
            {
                JArray ids=(JArray)e["nodes"];
                double[][] p=ids.Select(x=>Point(nodes,(string)x)).ToArray();
                string type=(string)e["type"];
                if(type=="TRIA3" || type=="TRIA6")
                    total+=0.5*Norm(Cross(Sub(p[1],p[0]),Sub(p[2],p[0])));
                else if(type=="QUAD4")
                {
                    total+=0.5*Norm(Cross(Sub(p[1],p[0]),Sub(p[2],p[0])));
                    total+=0.5*Norm(Cross(Sub(p[2],p[0]),Sub(p[3],p[0])));
                }
                else throw new NotSupportedException("Unsupported surface traction skin: "+type);
            }
            return total;
        }

        private static double[] PressureResultant(JObject surface,JObject nodes,double pressure)
        {
            if(surface==null) throw new InvalidOperationException("Pressure surface metadata missing.");
            JArray skin=(JArray)surface["elements"]; double[] sum=new double[]{0,0,0};
            foreach(JObject e in skin.Cast<JObject>())
            {
                JArray ids=(JArray)e["nodes"]; double[][] p=ids.Select(x=>Point(nodes,(string)x)).ToArray();
                double[] area;
                if((string)e["type"]=="TRIA3" || (string)e["type"]=="TRIA6") area=Scale(Cross(Sub(p[1],p[0]),Sub(p[2],p[0])),0.5);
                else if((string)e["type"]=="QUAD4") area=Add(Scale(Cross(Sub(p[1],p[0]),Sub(p[2],p[0])),0.5),Scale(Cross(Sub(p[2],p[0]),Sub(p[3],p[0])),0.5));
                else throw new NotSupportedException("Unsupported pressure skin: "+(string)e["type"]);
                sum[0]-=pressure*area[0]; sum[1]-=pressure*area[1]; sum[2]-=pressure*area[2];
            }
            return sum;
        }

        private static double[] PressureMoment(JObject surface,JObject nodes,double pressure)
        {
            if(surface==null) throw new InvalidOperationException("Pressure surface metadata missing.");
            JArray skin=(JArray)surface["elements"]; double[] sum=new double[]{0,0,0};
            foreach(JObject e in skin.Cast<JObject>())
            {
                JArray ids=(JArray)e["nodes"]; double[][] p=ids.Select(x=>Point(nodes,(string)x)).ToArray();
                foreach(int[] tri in SurfaceTriangles((string)e["type"]))
                {
                    double[] area=Scale(Cross(Sub(p[tri[1]],p[tri[0]]),Sub(p[tri[2]],p[tri[0]])),0.5);
                    double[] force=Scale(area,-pressure);
                    double[] center=Scale(Add(Add(p[tri[0]],p[tri[1]]),p[tri[2]]),1.0/3.0);
                    sum=Add(sum,Cross(center,force));
                }
            }
            return sum;
        }
        private static double[] SurfaceTractionMoment(JObject surface,JObject nodes,double[] traction)
        {
            if(surface==null) throw new InvalidOperationException("Surface traction metadata missing.");
            JArray skin=(JArray)surface["elements"]; double[] sum=new double[]{0,0,0};
            foreach(JObject e in skin.Cast<JObject>())
            {
                JArray ids=(JArray)e["nodes"]; double[][] p=ids.Select(x=>Point(nodes,(string)x)).ToArray();
                foreach(int[] tri in SurfaceTriangles((string)e["type"]))
                {
                    double area=0.5*Norm(Cross(Sub(p[tri[1]],p[tri[0]]),Sub(p[tri[2]],p[tri[0]])));
                    double[] force=Scale(traction,area);
                    double[] center=Scale(Add(Add(p[tri[0]],p[tri[1]]),p[tri[2]]),1.0/3.0);
                    sum=Add(sum,Cross(center,force));
                }
            }
            return sum;
        }
        private static IEnumerable<int[]> SurfaceTriangles(string type)
        {
            if(type=="TRIA3" || type=="TRIA6") return new[]{new[]{0,1,2}};
            if(type=="QUAD4") return new[]{new[]{0,1,2},new[]{0,2,3}};
            throw new NotSupportedException("Unsupported surface skin: "+type);
        }
        private static double[] Point(JObject nodes,string id){JObject n=(JObject)nodes[id]; if(n==null) throw new InvalidOperationException("Missing node: "+id); return new double[]{GetDouble(n,"x"),GetDouble(n,"y"),GetDouble(n,"z")};}
        private static double[] Sub(double[] a,double[] b){return new double[]{a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
        private static double[] Add(double[] a,double[] b){return new double[]{a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
        private static double[] Scale(double[] a,double s){return new double[]{a[0]*s,a[1]*s,a[2]*s};}
        private static double[] Cross(double[] a,double[] b){return new double[]{a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
        private static double Norm(double[] a){return Math.Sqrt(a[0]*a[0]+a[1]*a[1]+a[2]*a[2]);}
        private static void AddTerm(List<string> terms,string name,JToken value){if(value!=null && value.Type!=JTokenType.Null) terms.Add(name+"="+F(value));}
        private static void ValidateConnectivity(JObject e,JArray c,int expected){if(c==null || c.Count!=expected) throw new InvalidOperationException("Invalid connectivity: "+(string)e["id"]); if(c.Select(x=>(string)x).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=expected) throw new InvalidOperationException("Duplicate nodes: "+(string)e["id"]);}
        private static void WriteGroup(List<string> mail,string kind,string name,IEnumerable<string> ids){string[] a=ids.Where(x=>!String.IsNullOrWhiteSpace(x)).ToArray(); if(a.Length==0) return; mail.Add(kind+" NOM = "+name); for(int i=0;i<a.Length;i+=8) mail.Add(String.Join(" ",a.Skip(i).Take(8))); mail.Add("FINSF");}
        private static string RequireMapped(Dictionary<string,string> map,string original,string role){string x; if(String.IsNullOrWhiteSpace(original) || !map.TryGetValue(original,out x)) throw new InvalidOperationException("Missing "+role+" group: "+(original??"<null>")); return x;}
        private static string CreateAsterGroupName(string source,HashSet<string> used){string raw=String.IsNullOrWhiteSpace(source)?"GROUP":source.Trim().ToUpperInvariant(); char[] c=raw.ToCharArray(); for(int i=0;i<c.Length;i++){bool l=c[i]>='A'&&c[i]<='Z',d=c[i]>='0'&&c[i]<='9'; if(!l&&!d&&c[i]!='_') c[i]='_';} string stem=new string(c).Trim('_'); if(String.IsNullOrWhiteSpace(stem)) stem="GROUP"; if(stem[0]>='0'&&stem[0]<='9') stem="G_"+stem; if(stem.Length>24) stem=stem.Substring(0,24); string candidate=stem; int n=2; while(!used.Add(candidate)){string tail="_"+n.ToString(CultureInfo.InvariantCulture); int keep=Math.Max(1,24-tail.Length); candidate=(stem.Length>keep?stem.Substring(0,keep):stem)+tail; n++;} return candidate;}
        private static double GetDouble(JObject o,string name){JToken t=o[name]; return t==null?0.0:t.Value<double>();}
        private static string F(JToken t){return t==null?"0":F(t.Value<double>());}
        private static string F(double v){if(Double.IsNaN(v)||Double.IsInfinity(v)) throw new InvalidOperationException("Non-finite mechanical value."); return v.ToString("0.###############",CultureInfo.InvariantCulture);}
    }
}
