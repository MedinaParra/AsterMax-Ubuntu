param([string]$Root)
$ErrorActionPreference='Stop'

$src=Join-Path $PSScriptRoot 'c1029'
$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $contract) -or !(Test-Path $exporter)){ throw 'C10.29 requires C10.27 multi-material backend first.' }

Copy-Item (Join-Path $src 'AsterMaxSurfaceMechanicsContract.cs') $contract -Force
$e=Get-Content (Join-Path $src 'AsterMaxCodeAsterLoadHistoryExporter.cs') -Raw
$e=$e.Replace('AsterMaxCodeAsterLoadHistoryExporter','AsterMaxCodeAsterNativeExporter')
Set-Content $exporter $e -Encoding UTF8

# C10.29.1 — first certified contact mode: Bonded/Tied -> Code_Aster LIAISON_MAIL.
# Only explicitly Tied SurfaceBehavior contact pairs are admitted. Hard/frictional/etc remain blocked.
$c=Get-Content $contract -Raw
if(-not $c.Contains('BuildBondedContacts(model)')) {
    $rootAnchor='            root["postprocess"]=new JObject { ["displacement_probe_group"]=probeGroup };'
    if(-not $c.Contains($rootAnchor)){ throw 'Bonded contract root anchor missing.' }
    $c=$c.Replace($rootAnchor,'            root["bonded_contacts"]=BuildBondedContacts(model);'+[Environment]::NewLine+$rootAnchor)

    $methodAnchor='        private static string ResolveAmplitude(FeModel model,string name)'
    if(-not $c.Contains($methodAnchor)){ throw 'Bonded contract method anchor missing.' }
    $bondedMethods=@'
        public static string[] UnsupportedNativeContactPairs(FeModel model)
        {
            if(model==null || model.ContactPairs==null) return new string[0];
            var issues=new List<string>();
            foreach(ContactPair pair in model.ContactPairs.Values)
            {
                if(pair==null || !pair.Active) continue;
                string reason;
                if(!IsBondedContactPair(model,pair,out reason))
                    issues.Add(pair.Name+": "+reason);
            }
            return issues.ToArray();
        }

        private static bool IsBondedContactPair(FeModel model,ContactPair pair,out string reason)
        {
            reason=null;
            if(pair.MasterRegionType!=RegionTypeEnum.SurfaceName || pair.SlaveRegionType!=RegionTypeEnum.SurfaceName)
            {
                reason="Bonded requires named master and slave surfaces.";
                return false;
            }
            if(String.IsNullOrWhiteSpace(pair.MasterRegionName) || String.IsNullOrWhiteSpace(pair.SlaveRegionName))
            {
                reason="Bonded master/slave surface is missing.";
                return false;
            }
            RequireSurface(model,pair.MasterRegionName);
            RequireSurface(model,pair.SlaveRegionName);
            if(String.IsNullOrWhiteSpace(pair.SurfaceInteractionName) || model.SurfaceInteractions==null ||
               !model.SurfaceInteractions.ContainsKey(pair.SurfaceInteractionName))
            {
                reason="missing surface interaction.";
                return false;
            }
            SurfaceInteraction interaction=model.SurfaceInteractions[pair.SurfaceInteractionName];
            SurfaceBehavior behavior=interaction==null || interaction.Properties==null ? null :
                interaction.Properties.OfType<SurfaceBehavior>().FirstOrDefault();
            if(behavior==null || behavior.PressureOverclosureType!=PressureOverclosureEnum.Tied)
            {
                reason="set Surface Behavior / Pressure-overclosure to Tied (Bonded); nonlinear native contact is not certified yet.";
                return false;
            }
            return true;
        }

        private static JArray BuildBondedContacts(FeModel model)
        {
            var result=new JArray();
            if(model==null || model.ContactPairs==null) return result;
            foreach(ContactPair pair in model.ContactPairs.Values)
            {
                if(pair==null || !pair.Active) continue;
                string reason;
                if(!IsBondedContactPair(model,pair,out reason)) continue;
                result.Add(new JObject {
                    ["name"]=pair.Name,
                    ["interaction"]=pair.SurfaceInteractionName,
                    ["mode"]="BONDED_LIAISON_MAIL",
                    ["master_surface"]=pair.MasterRegionName,
                    ["slave_surface"]=pair.SlaveRegionName
                });
            }
            return result;
        }

'@
    $c=$c.Replace($methodAnchor,$bondedMethods+$methodAnchor)
    Set-Content $contract $c -Encoding UTF8
}

$e=Get-Content $exporter -Raw
if(-not $e.Contains('bondedContacts=(JArray)contract["bonded_contacts"]')) {
    $parseAnchor='            JObject volumeGroups=(JObject)mesh["volume_groups"] ?? new JObject();'
    if(-not $e.Contains($parseAnchor)){ throw 'Bonded exporter parse anchor missing.' }
    $e=$e.Replace($parseAnchor,$parseAnchor+[Environment]::NewLine+'            JArray bondedContacts=(JArray)contract["bonded_contacts"] ?? new JArray();')

    $mailAnchor='            mail.Add("FIN");'
    if(-not $e.Contains($mailAnchor)){ throw 'Bonded exporter MAIL anchor missing.' }
    $masterGroups=@'
            // LIAISON_MAIL in a 3D solid model needs the master side as adjacent volume elements.
            var bondedMasterNameMap=new Dictionary<string,string>(StringComparer.Ordinal);
            foreach(JObject bonded in bondedContacts.Cast<JObject>())
            {
                string masterSurface=(string)bonded["master_surface"];
                if(String.IsNullOrWhiteSpace(masterSurface) || bondedMasterNameMap.ContainsKey(masterSurface)) continue;
                JObject master=surfaces[masterSurface] as JObject;
                if(master==null) throw new InvalidOperationException("Bonded master surface not found: "+masterSurface);
                JArray skin=master["elements"] as JArray;
                string[] parentIds=skin==null ? new string[0] : skin.Cast<JObject>()
                    .Select(x=>(string)x["parent_element"])
                    .Where(x=>!String.IsNullOrWhiteSpace(x))
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(x=>x,StringComparer.Ordinal).ToArray();
                if(parentIds.Length==0)
                    throw new InvalidOperationException("Bonded master surface has no adjacent volume elements: "+masterSurface);
                string mapped=CreateAsterGroupName("BM_"+masterSurface,usedNames);
                bondedMasterNameMap[masterSurface]=mapped;
                WriteGroup(mail,"GROUP_MA",mapped,parentIds);
            }
'@
    $e=$e.Replace($mailAnchor,$masterGroups+$mailAnchor)

    $conceptAnchor='            var loadConcepts=new StringBuilder();'
    if(-not $e.Contains($conceptAnchor)){ throw 'Bonded exporter load concept anchor missing.' }
    $bondedConcept=@'
            if(bondedContacts.Count>0)
            {
                var liaisonMail=new List<string>();
                foreach(JObject bonded in bondedContacts.Cast<JObject>())
                {
                    string slaveOriginal=(string)bonded["slave_surface"];
                    string masterOriginal=(string)bonded["master_surface"];
                    string slave=RequireMapped(surfaceNameMap,slaveOriginal,"bonded slave surface");
                    string master=RequireMapped(bondedMasterNameMap,masterOriginal,"bonded master volume");
                    liaisonMail.Add("_F(GROUP_MA_ESCL='"+slave+"',GROUP_MA_MAIT='"+master+"',TYPE_RACCORD='MASSIF')");
                }
                loadConcepts.AppendLine("bonded=AFFE_CHAR_MECA(MODELE=model,LIAISON_MAIL=("+String.Join(",",liaisonMail)+",))");
                excitations.Add("_F(CHARGE=bonded)");
            }
'@
    $e=$e.Replace($conceptAnchor,$conceptAnchor+[Environment]::NewLine+$bondedConcept.TrimEnd())

    $manifestAnchor='                ["support_count"]=supports.Count,["load_count"]=loads.Count,["surface_group_count"]=surfaces.Count,'
    if(-not $e.Contains($manifestAnchor)){ throw 'Bonded exporter manifest anchor missing.' }
    $manifestNew=$manifestAnchor+[Environment]::NewLine+'                ["bonded_contact_count"]=bondedContacts.Count,["bonded_contact_mode"]=bondedContacts.Count>0?"LIAISON_MAIL_MASSIF":"NONE",'
    $e=$e.Replace($manifestAnchor,$manifestNew)
    Set-Content $exporter $e -Encoding UTF8
}

$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $solve -Raw
if(-not $s.Contains('ASTERMAX_MED_STEP_SELECTION')) {
    $anchor='            bridgePsi.EnvironmentVariables["ASTERMAX_MED_BRIDGE_MODE"]="production";'
    if(-not $s.Contains($anchor)){ throw 'C10.29 MED bridge environment anchor missing.' }
    $insert=$anchor+[Environment]::NewLine+'            bridgePsi.EnvironmentVariables["ASTERMAX_MED_STEP_SELECTION"]="last";'
    $s=$s.Replace($anchor,$insert)
}

# Replace the old C10.35 blanket no-contact safety stop if it is present in an upstream/worktree.
# The new guard below admits only explicit Bonded/Tied pairs and keeps every other contact type blocked.
$legacyPhrase='contact pairs are present, but native Code_Aster contact translation is not yet certified'
if($s.Contains($legacyPhrase)) {
    $legacyPattern='(?ms)^[ \t]*if\s*\([^\r\n]*ContactPairs[^\r\n]*\)\s*\{?\s*throw new InvalidOperationException\("AsterMax Solve blocked: C10\.35: contact pairs are present, but native Code_Aster contact translation is not yet certified\. Solve is blocked to prevent a false no-contact result\."\);\s*\}?\s*'
    $s=[regex]::Replace($s,$legacyPattern,'')
    if($s.Contains($legacyPhrase)){ throw 'Legacy C10.35 blanket contact blocker could not be replaced safely.' }
}
if(-not $s.Contains('UnsupportedNativeContactPairs(model)')) {
    $exportAnchor='            JObject exportManifest=AsterMaxCodeAsterNativeExporter.Export(model,txDir,safe);'
    if(-not $s.Contains($exportAnchor)){ throw 'Bonded solve guard exporter anchor missing.' }
    $guard=@'
            string[] unsupportedContacts=AsterMaxSurfaceMechanicsContract.UnsupportedNativeContactPairs(model);
            if(unsupportedContacts.Length>0)
                throw new InvalidOperationException("AsterMax Solve blocked: native Code_Aster contact is currently certified only for Bonded/Tied pairs. "+String.Join("; ",unsupportedContacts));
'@
    $s=$s.Replace($exportAnchor,$guard+$exportAnchor)
}
Set-Content $solve $s -Encoding UTF8

$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $ui -Raw
if(-not $u.Contains('Load History')) {
    $anchor='                InfoCard("Quadratic solids by default • scope fingerprint • reaction equilibrium • component-first von Mises"),'
    if($u.Contains($anchor)){
        $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+'                InfoCard("Load History • AmplitudeTabular → DEFI_FONCTION / FONC_MULT"),')
    }
}
if(-not $u.Contains('Bonded/Tied')) {
    $anchor='                InfoCard("Load History • AmplitudeTabular → DEFI_FONCTION / FONC_MULT"),'
    if($u.Contains($anchor)){
        $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+'                InfoCard("Bonded/Tied • Code_Aster LIAISON_MAIL • Static Structural"),')
    }
}
Set-Content $ui $u -Encoding UTF8

# Static Structural history v2: expose existing native editors, preserving undo/redo.
$u=Get-Content $ui -Raw
if(-not $u.Contains('CommandTile("Tablas de carga"')) {
    $anchor='                CommandTile("Pressure", "LOAD", () => CreateAsterMaxPressure()),'
    if(-not $u.Contains($anchor)){ throw 'Static history UI anchor missing.' }
    $insert=@'
                CommandTile("Tablas de carga", "AMPLITUDE", () => tsmiCreateAmplitude_Click(null, EventArgs.Empty)),
                CommandTile("Desplazamiento", "SUPPORT", () => tsmiCreateBC_Click(null, new CaeGlobals.EventArgs<int>(1))),
'@
    $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+$insert.TrimEnd())
    Set-Content $ui $u -Encoding UTF8
}

# A nonzero prescribed displacement is an excitation even without force objects.
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$w=Get-Content $workspace -Raw
$old='            if (r.LoadCount == 0) r.Issues.Add("BLOCK:no_loads");'
$new=@'
            bool imposedExcitation=model.StepCollection.StepsList
                .Where(step=>!(step is CaeModel.InitialStep) && step.Active && step.Valid)
                .SelectMany(step=>step.BoundaryConditions.Values).OfType<CaeModel.DisplacementRotation>()
                .Any(bc=>bc.Active && bc.Valid && new[]{bc.U1,bc.U2,bc.U3}.Any(value=>!Double.IsNaN(value) && !Double.IsInfinity(value) && value!=0));
            if (r.LoadCount == 0 && !imposedExcitation) r.Issues.Add("BLOCK:no_loads");
'@
if($w.Contains($old)){ $w=$w.Replace($old,$new.TrimEnd()); Set-Content $workspace $w -Encoding UTF8 }
elseif(-not $w.Contains('bool imposedExcitation=')){ throw 'Static history readiness anchor missing.' }

Write-Host 'Static Structural history v2 + Bonded/Tied LIAISON_MAIL backend applied. Non-Bonded contact remains blocked.' -ForegroundColor Green

Copy-Item (Join-Path $src 'AsterMaxStaticHistoryWorkflowStates.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowStates.cs') -Force
