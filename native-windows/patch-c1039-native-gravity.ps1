param([string]$Root)
$ErrorActionPreference='Stop'
$NL=[Environment]::NewLine

$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
foreach($p in @($bridgePath,$exporterPath,$auditPath,$globalsPath)){ if(!(Test-Path $p)){ throw "C10.39 missing: $p" } }

# Bridge: density + GravityLoad.
$b=Get-Content $bridgePath -Raw
$b=[regex]::Replace($b,'public const string NativeBridgeVersion = "[^"]+";','public const string NativeBridgeVersion = "C10.39-native-gravity-v1";',1)

$anchor='                ElasticWithDensity elasticDensity = m.GetProperty<ElasticWithDensity>() as ElasticWithDensity;'
if(-not $b.Contains('Density density = m.GetProperty<Density>() as Density;')){
  if(-not $b.Contains($anchor)){ throw 'C10.39 density declaration anchor missing.' }
  $b=$b.Replace($anchor,$anchor+$NL+'                Density density = m.GetProperty<Density>() as Density;')
}
$anchor='                materials.Add(item);'
$insert=@'
                double densityValue = Double.NaN;
                if (density != null && density.DensityTemp != null && density.DensityTemp.Length > 0 &&
                    density.DensityTemp[0] != null && density.DensityTemp[0].Length > 0)
                    densityValue = density.DensityTemp[0][0];
                else if (elasticDensity != null)
                    densityValue = elasticDensity.Density;
                if (!Double.IsNaN(densityValue) && !Double.IsInfinity(densityValue) && densityValue > 0)
                    item["density_tonne_per_mm3"] = densityValue;
'@
if(-not $b.Contains('density_tonne_per_mm3')){
  if(-not $b.Contains($anchor)){ throw 'C10.39 material anchor missing.' }
  $b=$b.Replace($anchor,$insert+$anchor)
}

$old='                    else loads.Add(new JObject { ["name"] = loadEntry.Value.Name, ["type"] = loadEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });'
$new=@'
                    else
                    {
                        GravityLoad gravityLoad = loadEntry.Value as GravityLoad;
                        if (gravityLoad != null)
                        {
                            if (gravityLoad.RegionType != RegionTypeEnum.ElementSetName)
                                throw new NotSupportedException("C10.39 gravity requires ElementSetName scope for certified coverage.");
                            if (!model.Mesh.ElementSets.ContainsKey(gravityLoad.RegionName))
                                throw new InvalidOperationException("C10.39 gravity element set is missing: " + gravityLoad.RegionName);
                            FeElementSet gravitySet = model.Mesh.ElementSets[gravityLoad.RegionName];
                            HashSet<int> gravityIds = new HashSet<int>(gravitySet.Labels ?? new int[0]);
                            if (gravityIds.Count != model.Mesh.Elements.Count || model.Mesh.Elements.Keys.Any(id => !gravityIds.Contains(id)))
                                throw new NotSupportedException("C10.39 certifies gravity only over the complete FE model.");
                            double gmag=Math.Sqrt(gravityLoad.F1*gravityLoad.F1+gravityLoad.F2*gravityLoad.F2+gravityLoad.F3*gravityLoad.F3);
                            if(Double.IsNaN(gmag) || Double.IsInfinity(gmag) || gmag<=0)
                                throw new InvalidOperationException("C10.39 gravity vector must be finite and non-zero.");
                            loads.Add(new JObject {
                                ["name"]=gravityLoad.Name,
                                ["type"]="gravity_acceleration",
                                ["scope"]="all_model",
                                ["source_element_set"]=gravityLoad.RegionName,
                                ["ax_mm_s2"]=gravityLoad.F1,
                                ["ay_mm_s2"]=gravityLoad.F2,
                                ["az_mm_s2"]=gravityLoad.F3
                            });
                        }
                        else loads.Add(new JObject { ["name"] = loadEntry.Value.Name, ["type"] = loadEntry.Value.GetType().Name, ["unsupported_for_code_aster_adapter_v0"] = true });
                    }
'@
if($b.Contains($old)){ $b=$b.Replace($old,$new.TrimEnd()) }
elseif(-not $b.Contains('C10.39 gravity requires ElementSetName scope')){ throw 'C10.39 load fallback anchor missing.' }

$old='            root["postprocess"] = new JObject { ["displacement_probe_group"] = loads.Count > 0 ? (string)loads[0]["group"] : null };'
$new='            root["postprocess"] = new JObject { ["displacement_probe_group"] = loads.Cast<JObject>().Where(x => x["group"] != null).Select(x => (string)x["group"]).FirstOrDefault() };'
if($b.Contains($old)){ $b=$b.Replace($old,$new) }
Set-Content $bridgePath $b -Encoding UTF8

# Exporter: one nodal force + optional gravity.
$e=Get-Content $exporterPath -Raw
$e=[regex]::Replace($e,'public const string Version = "[^"]+";','public const string Version = "C10.39-native-codeaster-gravity-v1";',1)
$old='if(mats.Count!=1 || supports.Count<1 || loads.Count!=1) throw new NotSupportedException("C10.38 native exporter requires one material, at least one support and exactly one load.");'
$new='if(mats.Count!=1 || supports.Count<1 || loads.Count<1 || loads.Count>2) throw new NotSupportedException("C10.39 requires one material, at least one support, one nodal force and optional gravity.");'
if($e.Contains($old)){ $e=$e.Replace($old,$new) }
elseif(-not $e.Contains('C10.39 requires one material')){ throw 'C10.39 exporter guard anchor missing.' }

$old='            JObject mat=(JObject)mats[0], sup=(JObject)supports[0], load=(JObject)loads[0];'
$new=@'
            JObject mat=(JObject)mats[0], sup=(JObject)supports[0];
            JObject load=loads.Cast<JObject>().FirstOrDefault(x =>
                String.Equals((string)x["type"],"nodal_force_per_node",StringComparison.OrdinalIgnoreCase) ||
                String.Equals((string)x["type"],"nodal_force_total",StringComparison.OrdinalIgnoreCase));
            JObject gravity=loads.Cast<JObject>().FirstOrDefault(x =>
                String.Equals((string)x["type"],"gravity_acceleration",StringComparison.OrdinalIgnoreCase));
            if(load==null) throw new NotSupportedException("C10.39 requires one nodal CLoad contract.");
            if(loads.Count != 1 + (gravity==null ? 0 : 1))
                throw new NotSupportedException("C10.39 encountered an unsupported additional load.");
            double gravityMagnitude=0.0, gravityDx=0.0, gravityDy=0.0, gravityDz=0.0;
'@
if($e.Contains($old)){ $e=$e.Replace($old,$new.TrimEnd()) }
elseif(-not $e.Contains('JObject gravity=loads.Cast<JObject>().FirstOrDefault')){ throw 'C10.39 load assignment anchor missing.' }

$write='            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));'
$gravity=@'
            if(gravity!=null)
            {
                JToken densityToken=mat["density_tonne_per_mm3"];
                if(densityToken==null || densityToken.Type==JTokenType.Null)
                    throw new InvalidDataException("C10.39 gravity requires material density.");
                double rho=densityToken.Value<double>();
                if(Double.IsNaN(rho) || Double.IsInfinity(rho) || rho<=0)
                    throw new InvalidDataException("C10.39 gravity density is invalid.");

                double gx=GetDouble(gravity,"ax_mm_s2");
                double gy=GetDouble(gravity,"ay_mm_s2");
                double gz=GetDouble(gravity,"az_mm_s2");
                gravityMagnitude=Math.Sqrt(gx*gx+gy*gy+gz*gz);
                if(Double.IsNaN(gravityMagnitude) || Double.IsInfinity(gravityMagnitude) || gravityMagnitude<=0)
                    throw new InvalidDataException("C10.39 gravity acceleration is invalid.");
                gravityDx=gx/gravityMagnitude; gravityDy=gy/gravityMagnitude; gravityDz=gz/gravityMagnitude;

                string oldMaterial="steel = DEFI_MATERIAU(ELAS=_F(E="+F(mat["young_modulus_mpa"])+", NU="+F(mat["poisson"])+"))";
                string newMaterial="steel = DEFI_MATERIAU(ELAS=_F(E="+F(mat["young_modulus_mpa"])+", NU="+F(mat["poisson"])+", RHO="+F(rho)+"))";
                if(!comm.Contains(oldMaterial)) throw new InvalidOperationException("C10.39 material anchor missing for RHO.");
                comm=comm.Replace(oldMaterial,newMaterial);

                string gravityDefinition="gravity = AFFE_CHAR_MECA(\n    MODELE=model,\n    PESANTEUR=_F(GRAVITE="+F(gravityMagnitude)+", DIRECTION=("+F(gravityDx)+", "+F(gravityDy)+", "+F(gravityDz)+")),\n)\n\n";
                string loadAnchor="load = AFFE_CHAR_MECA(";
                if(!comm.Contains(loadAnchor)) throw new InvalidOperationException("C10.39 nodal load anchor missing.");
                comm=comm.Replace(loadAnchor,gravityDefinition+loadAnchor);
                comm=comm.Replace("_F(CHARGE=load)","_F(CHARGE=load), _F(CHARGE=gravity)");
            }

'@
if(-not $e.Contains('C10.39 gravity requires material density')){
  if(-not $e.Contains($write)){ throw 'C10.39 exporter write anchor missing.' }
  $e=$e.Replace($write,$gravity+$write)
}
$anchor='                ["generated_mail"]=Path.GetFileName(mailPath),'
$insert=@'
                ["material_density_tonne_per_mm3"]=mat["density_tonne_per_mm3"],
                ["gravity_enabled"]=gravity!=null,
                ["gravity_magnitude_mm_s2"]=gravityMagnitude,
                ["gravity_direction_x"]=gravityDx,
                ["gravity_direction_y"]=gravityDy,
                ["gravity_direction_z"]=gravityDz,
'@
if(-not $e.Contains('["gravity_enabled"]')){
  if(-not $e.Contains($anchor)){ throw 'C10.39 manifest anchor missing.' }
  $e=$e.Replace($anchor,$insert+$anchor)
}
Set-Content $exporterPath $e -Encoding UTF8

# Runtime audit: real all-volume GravityLoad on the existing real STEP model.
$a=Get-Content $auditPath -Raw
$anchor='                    JObject solverContract=AsterMaxModelContractBridge.Build(model);'
$insert=@'
                    int[] gravityElementIds=model.Mesh.Elements.Keys.OrderBy(x=>x).ToArray();
                    if(gravityElementIds.Length==0) throw new InvalidOperationException("C10.39 gravity audit has no FE elements.");
                    if(!model.Mesh.ElementSets.ContainsKey("C1039_ALL_VOLUME"))
                        model.Mesh.AddElementSet(new FeElementSet("C1039_ALL_VOLUME",gravityElementIds));
                    if(!liveStep.Loads.ContainsKey("C1039_Gravity"))
                    {
                        GravityLoad liveGravity=new GravityLoad("C1039_Gravity","C1039_ALL_VOLUME",RegionTypeEnum.ElementSetName,
                                                               0.0,-9810.0,0.0,false,false,0);
                        if(!liveStep.AddLoad(liveGravity))
                            throw new InvalidOperationException("C10.39 GravityLoad was rejected by StaticStep.");
                    }

                    JObject solverContract=AsterMaxModelContractBridge.Build(model);
'@
if($a.Contains($anchor) -and -not $a.Contains('C1039_Gravity')){ $a=$a.Replace($anchor,$insert.TrimEnd()) }
elseif(-not $a.Contains('C1039_Gravity')){ throw 'C10.39 audit insertion anchor missing.' }

$old='                    contractOk &= directionalBcContract && realLoadContract;'
$new=@'
                    JObject gravityContract=solverLoads==null ? null : solverLoads.Cast<JObject>()
                        .FirstOrDefault(x=>String.Equals((string)x["name"],"C1039_Gravity",StringComparison.Ordinal));
                    bool gravityContractOk=gravityContract!=null &&
                        String.Equals((string)gravityContract["type"],"gravity_acceleration",StringComparison.OrdinalIgnoreCase) &&
                        String.Equals((string)gravityContract["scope"],"all_model",StringComparison.OrdinalIgnoreCase) &&
                        Math.Abs(((double?)gravityContract["ay_mm_s2"] ?? Double.NaN)+9810.0)<1e-12;
                    JObject materialContract=((JArray)solverContract["materials"])?.Cast<JObject>().FirstOrDefault();
                    double rhoContract=(double?)materialContract?["density_tonne_per_mm3"] ?? Double.NaN;
                    bool densityContractOk=!Double.IsNaN(rhoContract) && !Double.IsInfinity(rhoContract) && rhoContract>0;
                    contractOk &= directionalBcContract && realLoadContract && gravityContractOk && densityContractOk;
'@
if($a.Contains($old)){ $a=$a.Replace($old,$new.TrimEnd()) }
elseif(-not $a.Contains('gravityContractOk')){ throw 'C10.39 audit validation anchor missing.' }

$anchor='                    report["codeaster_live_load_fz_total_n"]=100.0;'
$insert=@'
                    report["codeaster_live_load_fz_total_n"]=100.0;
                    report["codeaster_gravity_contract_pass"]=gravityContractOk;
                    report["codeaster_gravity_scope"]="all_model";
                    report["codeaster_gravity_ay_mm_s2"]=-9810.0;
                    report["codeaster_density_contract_pass"]=densityContractOk;
                    report["codeaster_density_tonne_per_mm3"]=rhoContract;
'@
if($a.Contains($anchor) -and -not $a.Contains('codeaster_gravity_contract_pass')){ $a=$a.Replace($anchor,$insert.TrimEnd()) }
elseif(-not $a.Contains('codeaster_gravity_contract_pass')){ throw 'C10.39 audit report anchor missing.' }
Set-Content $auditPath $a -Encoding UTF8

$g=Get-Content $globalsPath -Raw
$g=$g.Replace('AsterMax Mechanical C10.38','AsterMax Mechanical C10.39')
if(-not $g.Contains('AsterMax Mechanical C10.39')){ throw 'C10.39 Globals version anchor missing.' }
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.39 live GravityLoad + density + Code_Aster PESANTEUR applied.' -ForegroundColor Green
