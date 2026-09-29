param([string]$Root)
$ErrorActionPreference='Stop'

$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
foreach($p in @($bridgePath,$exporterPath,$auditPath,$globalsPath)){ if(!(Test-Path $p)){ throw "C10.36 missing: $p" } }

# ----------------------------------------------------------------------
# 1) Native FeModel -> solver contract: serialize real contact surfaces.
# ----------------------------------------------------------------------
$b=[regex]::Replace((Get-Content $bridgePath -Raw),"\r\n?","\n")
$legacyGuard='            if (model.ContactPairs != null && model.ContactPairs.Count > 0) throw new NotSupportedException("C10.35: contact pairs are present, but native Code_Aster contact translation is not yet certified. Solve is blocked to prevent a false no-contact result.");'
if($b.Contains($legacyGuard)){ $b=$b.Replace($legacyGuard,'') }

$contactAnchor='            root["postprocess"] = new JObject { ["displacement_probe_group"] = loads.Count > 0 ? (string)loads[0]["group"] : null };'
$contactBlock=@'
            JArray contacts = new JArray();
            int contactIndex = 0;
            foreach (var cpEntry in model.ContactPairs)
            {
                ContactPair cp = cpEntry.Value;
                if (cp == null) continue;
                contactIndex++;
                if (cp.MasterRegionType != RegionTypeEnum.SurfaceName || cp.SlaveRegionType != RegionTypeEnum.SurfaceName)
                    throw new NotSupportedException("C10.36 Code_Aster contact export requires named master/slave surfaces.");

                SurfaceInteraction interaction;
                if (!model.SurfaceInteractions.TryGetValue(cp.SurfaceInteractionName, out interaction) || interaction == null)
                    throw new InvalidOperationException("Contact interaction is missing: " + cp.SurfaceInteractionName);
                if (interaction.Properties != null && interaction.Properties.Any(x => x is Friction))
                    throw new NotSupportedException("C10.36 supports frictionless contact only. Remove friction or keep Solve blocked.");

                string suffix = contactIndex.ToString("000");
                JObject master = BuildCodeAsterContactSurface(model, cp.MasterRegionName, "AM_M" + suffix, "M" + suffix);
                JObject slave = BuildCodeAsterContactSurface(model, cp.SlaveRegionName, "AM_S" + suffix, "S" + suffix);
                contacts.Add(new JObject
                {
                    ["name"] = cp.Name,
                    ["surface_interaction"] = cp.SurfaceInteractionName,
                    ["method"] = cp.Method.ToString(),
                    ["small_sliding"] = cp.SmallSliding,
                    ["adjust"] = cp.Adjust,
                    ["formulation"] = "CONTINUE",
                    ["friction"] = "SANS",
                    ["contact_init"] = "INTERPENETRE",
                    ["master"] = master,
                    ["slave"] = slave
                });
            }
            root["contacts"] = contacts;
'@
if(-not $b.Contains('BuildCodeAsterContactSurface(')){
    if(-not $b.Contains($contactAnchor)){ throw 'C10.36 bridge postprocess anchor missing.' }
    $b=$b.Replace($contactAnchor,$contactBlock+$contactAnchor)
}

$helperAnchor='        private static string GetElementType(FeElement e)'
$helpers=@'
        private static JObject BuildCodeAsterContactSurface(FeModel model, string surfaceName, string groupName, string elementPrefix)
        {
            if (String.IsNullOrWhiteSpace(surfaceName) || !model.Mesh.Surfaces.ContainsKey(surfaceName))
                throw new InvalidOperationException("Contact surface not found: " + (surfaceName ?? "<null>"));
            FeSurface surface = model.Mesh.Surfaces[surfaceName];
            if (surface.Type != FeSurfaceType.Element)
                throw new NotSupportedException("C10.36 requires element-based contact surfaces: " + surfaceName);
            if (surface.ElementFaces == null || surface.ElementFaces.Count == 0)
                throw new InvalidOperationException("Contact surface has no element faces: " + surfaceName);

            JArray skin = new JArray();
            int localId = 0;
            foreach (var faceEntry in surface.ElementFaces.OrderBy(x => x.Key.ToString(), StringComparer.Ordinal))
            {
                string elementSetName = faceEntry.Value;
                if (String.IsNullOrWhiteSpace(elementSetName) || !model.Mesh.ElementSets.ContainsKey(elementSetName))
                    throw new InvalidOperationException("Contact surface element set is missing: " + elementSetName);
                FeElementSet set = model.Mesh.ElementSets[elementSetName];
                if (set.Labels == null || set.Labels.Length == 0)
                    throw new InvalidOperationException("Contact surface element set is empty: " + elementSetName);

                foreach (int elementId in set.Labels.OrderBy(x => x))
                {
                    if (!model.Mesh.Elements.ContainsKey(elementId))
                        throw new InvalidOperationException("Contact source element is missing: " + elementId);
                    FeElement volume = model.Mesh.Elements[elementId];
                    int[] nodeIds = volume.GetVtkCellFromFaceName(faceEntry.Key);
                    string faceType;
                    if (nodeIds.Length == 3) faceType = "TRIA3";
                    else if (nodeIds.Length == 4) faceType = "QUAD4";
                    else if (nodeIds.Length == 6) faceType = "TRIA6";
                    else if (nodeIds.Length == 8) faceType = "QUAD8";
                    else throw new NotSupportedException("Unsupported Code_Aster contact face node count: " + nodeIds.Length);

                    localId++;
                    string syntheticId = elementPrefix + localId.ToString("0000");
                    skin.Add(new JObject
                    {
                        ["id"] = syntheticId,
                        ["type"] = faceType,
                        ["source_element_id"] = "E" + elementId,
                        ["source_face"] = faceEntry.Key.ToString(),
                        ["nodes"] = new JArray(nodeIds.Select(x => "N" + x))
                    });
                }
            }
            if (skin.Count == 0) throw new InvalidOperationException("Contact surface produced no skin elements: " + surfaceName);
            return new JObject
            {
                ["source_surface"] = surfaceName,
                ["group"] = groupName,
                ["elements"] = skin
            };
        }

'@
if(-not $b.Contains('private static JObject BuildCodeAsterContactSurface(')){
    if(-not $b.Contains($helperAnchor)){ throw 'C10.36 bridge helper anchor missing.' }
    $b=$b.Replace($helperAnchor,$helpers+$helperAnchor)
}
Set-Content $bridgePath $b -Encoding UTF8


# ----------------------------------------------------------------------
# 2) Native Code_Aster exporter: emit contact skins + GROUP_MA and use
#    DEFI_CONTACT/STAT_NON_LINE whenever the contract contains contacts.
# ----------------------------------------------------------------------
$e=[regex]::Replace((Get-Content $exporterPath -Raw),"\r\n?","\n")
$e=$e.Replace('public const string Version = "C10.08-native-codeaster-tetra-v2";',
              'public const string Version = "C10.36-native-codeaster-contact-v1";')

$contractAnchor='            JArray mats=(JArray)contract["materials"];'
if(-not $e.Contains('JArray contacts=(JArray)contract["contacts"]')){
    if(-not $e.Contains($contractAnchor)){ throw 'C10.36 exporter contract anchor missing.' }
    $e=$e.Replace($contractAnchor,'            JArray contacts=(JArray)contract["contacts"] ?? new JArray();'+"\n"+$contractAnchor)
}

$mailAnchor='            JObject groups=(JObject)mesh["node_groups"];'
$mailBlock=@'
            // Keep volume and skin element roles explicit for Code_Aster.
            mail.Add("GROUP_MA NOM = AM_VOL");
            string[] volumeIds=elements.Cast<JObject>().Select(x=>(string)x["id"]).ToArray();
            const int volumeIdsPerRecord=8;
            for(int start=0;start<volumeIds.Length;start+=volumeIdsPerRecord)
                mail.Add(String.Join(" ",volumeIds.Skip(start).Take(volumeIdsPerRecord)));
            mail.Add("FINSF");

            // Contact skins are explicit 2D mesh elements derived from the real
            // PrePoMax master/slave surfaces. Synthetic IDs are solver-only.
            foreach (JObject contact in contacts.Cast<JObject>())
            {
                foreach (string role in new [] { "master", "slave" })
                {
                    JObject surface=(JObject)contact[role];
                    JArray skin=(JArray)surface["elements"];
                    string group=(string)surface["group"];
                    if(skin==null || skin.Count==0 || String.IsNullOrWhiteSpace(group))
                        throw new InvalidOperationException("C10.36 contact surface contract is incomplete.");

                    foreach(string skinType in skin.Cast<JObject>().Select(x=>(string)x["type"])
                        .Distinct(StringComparer.OrdinalIgnoreCase).OrderBy(x=>x,StringComparer.OrdinalIgnoreCase))
                    {
                        mail.Add(skinType);
                        foreach(JObject face in skin.Cast<JObject>()
                            .Where(x=>String.Equals((string)x["type"],skinType,StringComparison.OrdinalIgnoreCase))
                            .OrderBy(x=>(string)x["id"]))
                            mail.Add((string)face["id"]+" "+String.Join(" ",((JArray)face["nodes"]).Select(x=>(string)x)));
                        mail.Add("FINSF");
                    }

                    mail.Add("GROUP_MA NOM = "+group);
                    string[] faceIds=skin.Cast<JObject>().Select(x=>(string)x["id"]).ToArray();
                    const int faceIdsPerRecord=8;
                    for(int start=0;start<faceIds.Length;start+=faceIdsPerRecord)
                        mail.Add(String.Join(" ",faceIds.Skip(start).Take(faceIdsPerRecord)));
                    mail.Add("FINSF");
                }
            }
'@
if(-not $e.Contains('Contact skins are explicit 2D mesh elements')){
    if(-not $e.Contains($mailAnchor)){ throw 'C10.36 exporter mail anchor missing.' }
    $e=$e.Replace($mailAnchor,$mailBlock+$mailAnchor)
}

$commWriteAnchor='            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));'
$commContact=@'
            if(contacts.Count>0)
            {
                var orientationLines=new List<string>();
                foreach(JObject contact in contacts.Cast<JObject>())
                {
                    orientationLines.Add("_F(GROUP_MA='"+(string)contact["master"]["group"]+"')");
                    orientationLines.Add("_F(GROUP_MA='"+(string)contact["slave"]["group"]+"')");
                }
                string orientation=String.Join(",\n        ",orientationLines);
                string oldModel="model = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', PHENOMENE='MECANIQUE', MODELISATION='3D'))";
                string newModel="mesh = MODI_MAILLAGE(reuse=mesh, MAILLAGE=mesh, ORIE_PEAU_3D=(\n        "+orientation+",\n    ))\nmodel = AFFE_MODELE(MAILLAGE=mesh, AFFE=_F(GROUP_MA='AM_VOL', PHENOMENE='MECANIQUE', MODELISATION='3D'))";
                if(!comm.Contains(oldModel)) throw new InvalidOperationException("C10.36 modelisation anchor missing.");
                comm=comm.Replace(oldModel,newModel);
                comm=comm.Replace("matfield = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(TOUT='OUI', MATER=steel))",
                                  "matfield = AFFE_MATERIAU(MAILLAGE=mesh, AFFE=_F(GROUP_MA='AM_VOL', MATER=steel))");

                var zoneLines=new List<string>();
                foreach(JObject contact in contacts.Cast<JObject>())
                {
                    JObject master=(JObject)contact["master"];
                    JObject slave=(JObject)contact["slave"];
                    zoneLines.Add(String.Format(CultureInfo.InvariantCulture,
                        "_F(GROUP_MA_MAIT='{0}', GROUP_MA_ESCL='{1}', CONTACT_INIT='{2}')",
                        (string)master["group"],(string)slave["group"],(string)contact["contact_init"]));
                }
                string zones=String.Join(",
        ",zoneLines);
                string linearSolve="result = MECA_STATIQUE(MODELE=model, CHAM_MATER=matfield, EXCIT=(_F(CHARGE=fixed), _F(CHARGE=load)))";
                string nonlinear=String.Format(CultureInfo.InvariantCulture,@"times = DEFI_LIST_REEL(DEBUT=0.0, INTERVALLE=_F(JUSQU_A=1.0, NOMBRE=10))
contact = DEFI_CONTACT(
    MODELE=model,
    FORMULATION='CONTINUE',
    FROTTEMENT='SANS',
    ALGO_RESO_CONT='NEWTON',
    ZONE=(
        {0},
    ),
)
result = STAT_NON_LINE(
    MODELE=model,
    CHAM_MATER=matfield,
    EXCIT=(_F(CHARGE=fixed), _F(CHARGE=load)),
    CONTACT=contact,
    COMPORTEMENT=_F(RELATION='ELAS', DEFORMATION='PETIT', TOUT='OUI'),
    INCREMENT=_F(LIST_INST=times),
    NEWTON=_F(MATRICE='TANGENTE', REAC_ITER=1),
    CONVERGENCE=_F(ITER_GLOB_MAXI=30),
)",zones);
                if(!comm.Contains(linearSolve)) throw new InvalidOperationException("C10.36 linear solve anchor missing from generated command file.");
                comm=comm.Replace(linearSolve,nonlinear);
            }

'@
if(-not $e.Contains("contact = DEFI_CONTACT(")){
    if(-not $e.Contains($commWriteAnchor)){ throw 'C10.36 exporter comm write anchor missing.' }
    $e=$e.Replace($commWriteAnchor,$commContact+$commWriteAnchor)
}

$manifestAnchor='                ["load_nodes"]=loadNodes.Count,'
$manifestInsert=@'
                ["load_nodes"]=loadNodes.Count,
                ["contact_pair_count"]=contacts.Count,
                ["contact_solver_path"]=contacts.Count>0?"DEFI_CONTACT_CONTINUE_STAT_NON_LINE":"MECA_STATIQUE",
                ["contact_friction"]="SANS",
'@
if(-not $e.Contains('["contact_pair_count"]')){
    if(-not $e.Contains($manifestAnchor)){ throw 'C10.36 exporter manifest anchor missing.' }
    $e=$e.Replace($manifestAnchor,$manifestInsert.TrimEnd())
}
Set-Content $exporterPath $e -Encoding UTF8


# Multiple support records: first support remains the primary fixed block;
# later records become an auxiliary DDL_IMPO tuple with only defined DOFs.
$e=[regex]::Replace((Get-Content $exporterPath -Raw),"\r\n?","\n")
$e=$e.Replace('if(mats.Count!=1 || supports.Count!=1 || loads.Count!=1) throw new NotSupportedException("C9.61 native exporter v0 requires exactly one material, one support and one load.");',
              'if(mats.Count!=1 || supports.Count<1 || loads.Count!=1) throw new NotSupportedException("C10.36 native exporter requires one material, at least one support and exactly one load.");')
$writeAnchor='            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));'
$extra=@'
            if(supports.Count>1)
            {
                var ddl=new List<string>();
                for(int i=1;i<supports.Count;i++)
                {
                    JObject bc=(JObject)supports[i];
                    string group=RequireMappedGroup(asterGroupNames,(string)bc["group"],"support");
                    var terms=new List<string>();
                    if(bc["dx"]!=null && bc["dx"].Type!=JTokenType.Null) terms.Add("DX="+F(bc["dx"]));
                    if(bc["dy"]!=null && bc["dy"].Type!=JTokenType.Null) terms.Add("DY="+F(bc["dy"]));
                    if(bc["dz"]!=null && bc["dz"].Type!=JTokenType.Null) terms.Add("DZ="+F(bc["dz"]));
                    if(terms.Count==0) throw new InvalidOperationException("Directional support has no constrained translation: "+(string)bc["name"]);
                    ddl.Add("_F(GROUP_NO='"+group+"', "+String.Join(", ",terms)+")");
                }
                string stabilizer="stabilize = AFFE_CHAR_MECA(\\n    MODELE=model,\\n    DDL_IMPO=(\\n        "+String.Join(",\\n        ",ddl)+",\\n    ),\\n)\\n\\n";
                string loadAnchor="load = AFFE_CHAR_MECA(";
                if(!comm.Contains(loadAnchor)) throw new InvalidOperationException("C10.36 load anchor missing while adding directional supports.");
                comm=comm.Replace(loadAnchor,stabilizer+loadAnchor);
                comm=comm.Replace("_F(CHARGE=fixed), _F(CHARGE=load)","_F(CHARGE=fixed), _F(CHARGE=stabilize), _F(CHARGE=load)");
            }

'@
if(-not $e.Contains('Directional support has no constrained translation')){
    if(-not $e.Contains($writeAnchor)){ throw 'C10.36 exporter write anchor missing for extra supports.' }
    $e=$e.Replace($writeAnchor,$extra+$writeAnchor)
}
Set-Content $exporterPath $e -Encoding UTF8
# ----------------------------------------------------------------------
# 3) Extend the real C10.35 two-body runtime audit: once contacts exist,
#    build the native solver contract and verify that contact skins survive.
# ----------------------------------------------------------------------
$a=[regex]::Replace((Get-Content $auditPath -Raw),"\r\n?","\n")
$auditAnchor='                    report["contact_generator_runtime_pass"]=contactsValid;'
$auditInsert=@'
                    report["contact_generator_runtime_pass"]=contactsValid;

                    if(!model.StepCollection.StepsList.Any(x=>!(x is InitialStep)))
                        model.StepCollection.AddStep(new StaticStep("ContactAudit"), false);
                    JObject solverContract=AsterMaxModelContractBridge.Build(model);
                    JArray solverContacts=(JArray)solverContract["contacts"];
                    bool contractOk=solverContacts!=null && solverContacts.Count==contactNames.Length;
                    int skinElementCount=0;
                    if(contractOk)
                    {
                        foreach(JObject sc in solverContacts.Cast<JObject>())
                        {
                            JArray me=(JArray)sc["master"]?["elements"];
                            JArray se=(JArray)sc["slave"]?["elements"];
                            if(me==null || se==null || me.Count==0 || se.Count==0) contractOk=false;
                            skinElementCount+=(me==null?0:me.Count)+(se==null?0:se.Count);
                        }
                    }
                    report["codeaster_contact_contract_pass"]=contractOk;
                    report["codeaster_contact_skin_elements"]=skinElementCount;
                    File.WriteAllText(Path.Combine(directory,"contact-solver-contract.json"),
                                      solverContract.ToString(Formatting.Indented));
                    contactsValid &= contractOk;
'@
if(-not $a.Contains('codeaster_contact_contract_pass')){
    if(-not $a.Contains($auditAnchor)){ throw 'C10.36 runtime audit anchor missing.' }
    $a=$a.Replace($auditAnchor,$auditInsert.TrimEnd())
}
Set-Content $auditPath $a -Encoding UTF8

# ----------------------------------------------------------------------
# 4) Release identity.
# ----------------------------------------------------------------------
$g=[regex]::Replace((Get-Content $globalsPath -Raw),"\r\n?","\n")
$g=$g.Replace('AsterMax Mechanical C10.35','AsterMax Mechanical C10.36')
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.36: frictionless Code_Aster contact contract + native DEFI_CONTACT export applied.' -ForegroundColor Green
