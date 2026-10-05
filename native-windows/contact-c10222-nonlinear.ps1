param([string]$Root)
$ErrorActionPreference='Stop'

# C10.29.2 — nonlinear surface contact candidate for native Code_Aster.
# Supported in this stage:
#   - SurfaceBehavior=Tied -> existing Bonded/LIAISON_MAIL path
#   - SurfaceBehavior=Hard, no Friction -> DEFI_CONTACT frictionless
#   - SurfaceBehavior=Hard + Friction(mu) -> DEFI_CONTACT Coulomb
# Still fail-closed:
#   - Linear/Exponential/Tabular pressure-overclosure
#   - non Surface-to-Surface method, SmallSliding, Adjust, custom StickSlope
# Nonlinear modes use STAT_NON_LINE. They are not marked solver-certified until native Windows
# Code_Aster execution evidence is produced.

$contract=Join-Path $Root 'PrePoMax/AsterMaxSurfaceMechanicsContract.cs'
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$ui=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($contract,$exporter,$solve,$ui)){ if(!(Test-Path $p)){ throw "Required patched file missing: $p" } }

# ------------------------- Contract classification -------------------------
$c=Get-Content $contract -Raw
if(-not $c.Contains('BuildNonlinearContacts(model)')) {
    $rootAnchor='            root["bonded_contacts"]=BuildBondedContacts(model);'
    if(-not $c.Contains($rootAnchor)){ throw 'Nonlinear contact requires Bonded/Tied contract first.' }
    $c=$c.Replace($rootAnchor,$rootAnchor+[Environment]::NewLine+'            root["nonlinear_contacts"]=BuildNonlinearContacts(model);')

    $methodAnchor='        private static string ResolveAmplitude(FeModel model,string name)'
    if(-not $c.Contains($methodAnchor)){ throw 'Nonlinear contact contract method anchor missing.' }
    $methods=@'
        public static string[] UnsupportedNativeContactPairsV2(FeModel model)
        {
            if(model==null || model.ContactPairs==null) return new string[0];
            var issues=new List<string>();
            foreach(ContactPair pair in model.ContactPairs.Values)
            {
                if(pair==null || !pair.Active) continue;
                string reason;
                if(IsBondedContactPair(model,pair,out reason)) continue;
                string mode; double coefficient;
                if(IsHardNonlinearContactPair(model,pair,out mode,out coefficient,out reason)) continue;
                issues.Add(pair.Name+": "+reason);
            }
            return issues.ToArray();
        }

        private static bool IsHardNonlinearContactPair(FeModel model,ContactPair pair,
                                                        out string mode,out double coefficient,out string reason)
        {
            mode=null; coefficient=Double.NaN; reason=null;
            if(pair.MasterRegionType!=RegionTypeEnum.SurfaceName || pair.SlaveRegionType!=RegionTypeEnum.SurfaceName)
            {
                reason="Hard contact requires named master and slave surfaces.";
                return false;
            }
            if(String.IsNullOrWhiteSpace(pair.MasterRegionName) || String.IsNullOrWhiteSpace(pair.SlaveRegionName))
            {
                reason="Hard contact master/slave surface is missing.";
                return false;
            }
            RequireSurface(model,pair.MasterRegionName);
            RequireSurface(model,pair.SlaveRegionName);
            if(pair.Method!=ContactPairMethod.SurfaceToSurface)
            {
                reason="nonlinear Code_Aster contact currently requires ContactPairMethod.SurfaceToSurface.";
                return false;
            }
            if(pair.SmallSliding)
            {
                reason="SmallSliding is not mapped by the current native Code_Aster contact backend.";
                return false;
            }
            if(pair.Adjust)
            {
                reason="Adjust must be disabled for the first certified nonlinear contact path; geometric adjustment is not silently approximated.";
                return false;
            }
            if(String.IsNullOrWhiteSpace(pair.SurfaceInteractionName) || model.SurfaceInteractions==null ||
               !model.SurfaceInteractions.ContainsKey(pair.SurfaceInteractionName))
            {
                reason="missing surface interaction.";
                return false;
            }
            SurfaceInteraction interaction=model.SurfaceInteractions[pair.SurfaceInteractionName];
            SurfaceBehavior behavior=interaction==null || interaction.Properties==null ? null :
                interaction.Properties.OfType<SurfaceBehavior>().FirstOrDefault();
            if(behavior==null)
            {
                reason="Surface Behavior is required.";
                return false;
            }
            if(behavior.PressureOverclosureType!=PressureOverclosureEnum.Hard)
            {
                reason="supported pressure-overclosure modes are Tied/Bonded and Hard; Linear/Exponential/Tabular remain blocked.";
                return false;
            }
            Friction friction=interaction.Properties.OfType<Friction>().FirstOrDefault();
            if(friction==null)
            {
                mode="HARD_FRICTIONLESS";
                return true;
            }
            if(!(friction.Coefficient>0) || Double.IsNaN(friction.Coefficient) || Double.IsInfinity(friction.Coefficient))
            {
                reason="Coulomb friction coefficient must be finite and greater than zero.";
                return false;
            }
            if(!Double.IsNaN(friction.StickSlope))
            {
                reason="custom Friction.StickSlope is not mapped to Code_Aster and is therefore blocked.";
                return false;
            }
            coefficient=friction.Coefficient;
            mode="HARD_COULOMB";
            return true;
        }

        private static JArray BuildNonlinearContacts(FeModel model)
        {
            var result=new JArray();
            if(model==null || model.ContactPairs==null) return result;
            foreach(ContactPair pair in model.ContactPairs.Values)
            {
                if(pair==null || !pair.Active) continue;
                string mode,reason; double coefficient;
                if(!IsHardNonlinearContactPair(model,pair,out mode,out coefficient,out reason)) continue;
                var item=new JObject {
                    ["name"]=pair.Name,
                    ["interaction"]=pair.SurfaceInteractionName,
                    ["mode"]=mode,
                    ["master_surface"]=pair.MasterRegionName,
                    ["slave_surface"]=pair.SlaveRegionName,
                    ["contact_init"]="INTERPENETRE"
                };
                if(mode=="HARD_COULOMB") item["friction_coefficient"]=coefficient;
                result.Add(item);
            }
            return result;
        }

'@
    $c=$c.Replace($methodAnchor,$methods+$methodAnchor)
    Set-Content $contract $c -Encoding UTF8
}

# ------------------------- Exporter / solver deck -------------------------
$e=Get-Content $exporter -Raw
if(-not $e.Contains('nonlinearContacts=(JArray)contract["nonlinear_contacts"]')) {
    $parseAnchor='            JArray bondedContacts=(JArray)contract["bonded_contacts"] ?? new JArray();'
    if(-not $e.Contains($parseAnchor)){ throw 'Nonlinear exporter requires Bonded parser anchor.' }
    $e=$e.Replace($parseAnchor,$parseAnchor+[Environment]::NewLine+'            JArray nonlinearContacts=(JArray)contract["nonlinear_contacts"] ?? new JArray();')

    # Replace only the linear solve statement; all existing BC/load concepts and Bonded ties stay intact.
    $solveAnchor='            comm.AppendLine("result=MECA_STATIQUE(MODELE=model,CHAM_MATER=matfield,EXCIT=("+String.Join(",",excitations)+",)"+listInstArg+")");'
    if(-not $e.Contains($solveAnchor)){ throw 'MECA_STATIQUE exporter anchor missing.' }
    $nonlinearSolve=@'
            if(nonlinearContacts.Count>0)
            {
                // Contact/friction is a nonlinear problem in Code_Aster: DEFI_CONTACT + STAT_NON_LINE.
                // If no user history exists, provide a deterministic pseudo-time interval. Constant loads
                // remain constant; users should use AmplitudeTabular when gradual load application is needed.
                if(!historyEnabled)
                    comm.AppendLine("linst=DEFI_LIST_REEL(DEBUT=0.0,INTERVALLE=_F(JUSQU_A=1.0,NOMBRE=10))");

                bool hasCoulomb=nonlinearContacts.Cast<JObject>().Any(x=>(string)x["mode"]=="HARD_COULOMB");
                var zones=new List<string>();
                foreach(JObject contactItem in nonlinearContacts.Cast<JObject>())
                {
                    string master=RequireMapped(surfaceNameMap,(string)contactItem["master_surface"],"contact master surface");
                    string slave=RequireMapped(surfaceNameMap,(string)contactItem["slave_surface"],"contact slave surface");
                    var zoneTerms=new List<string>{
                        "GROUP_MA_MAIT='"+master+"'",
                        "GROUP_MA_ESCL='"+slave+"'",
                        "CONTACT_INIT='INTERPENETRE'"
                    };
                    if(hasCoulomb)
                    {
                        double mu=(string)contactItem["mode"]=="HARD_COULOMB" ?
                            GetDouble(contactItem,"friction_coefficient") : 0.0;
                        zoneTerms.Add("COULOMB="+F(mu));
                    }
                    zones.Add("_F("+String.Join(",",zoneTerms)+")");
                }
                string frictionArgs=hasCoulomb ? ",FROTTEMENT='COULOMB',ALGO_RESO_FROT='NEWTON'" : ",FROTTEMENT='SANS'";
                comm.AppendLine("contact=DEFI_CONTACT(MODELE=model,FORMULATION='CONTINUE',ALGO_RESO_CONT='NEWTON',LISSAGE='OUI'"+
                    frictionArgs+",ZONE=("+String.Join(",",zones)+",))");
                comm.AppendLine("result=STAT_NON_LINE(MODELE=model,CHAM_MATER=matfield,CONTACT=contact,"+
                    "EXCIT=("+String.Join(",",excitations)+",),"+
                    "COMPORTEMENT=_F(RELATION='ELAS',DEFORMATION='PETIT',TOUT='OUI'),"+
                    "INCREMENT=_F(LIST_INST=linst),METHODE='NEWTON',"+
                    "NEWTON=_F(MATRICE='TANGENTE',REAC_INCR=1,REAC_ITER=1),"+
                    "CONVERGENCE=_F(ITER_GLOB_MAXI=30))");
            }
            else
            {
                comm.AppendLine("result=MECA_STATIQUE(MODELE=model,CHAM_MATER=matfield,EXCIT=("+String.Join(",",excitations)+",)"+listInstArg+")");
            }
'@
    $e=$e.Replace($solveAnchor,$nonlinearSolve.TrimEnd())

    $manifestAnchor='                ["bonded_contact_count"]=bondedContacts.Count,["bonded_contact_mode"]=bondedContacts.Count>0?"LIAISON_MAIL_MASSIF":"NONE",'
    if(-not $e.Contains($manifestAnchor)){ throw 'Nonlinear contact manifest anchor missing.' }
    $manifestInsert=$manifestAnchor+[Environment]::NewLine+
        '                ["nonlinear_contact_count"]=nonlinearContacts.Count,'+[Environment]::NewLine+
        '                ["nonlinear_contact_modes"]=new JArray(nonlinearContacts.Cast<JObject>().Select(x=>(string)x["mode"]).Distinct().OrderBy(x=>x)),'+[Environment]::NewLine+
        '                ["analysis_operator"]=nonlinearContacts.Count>0?"STAT_NON_LINE":"MECA_STATIQUE",'+[Environment]::NewLine+
        '                ["nonlinear_contact_solver_certification"]=nonlinearContacts.Count>0?"NOT_RUN_NATIVE_WINDOWS":"NOT_APPLICABLE",'
    $e=$e.Replace($manifestAnchor,$manifestInsert)
    Set-Content $exporter $e -Encoding UTF8
}

# ------------------------- Solve fail-closed policy -------------------------
$s=Get-Content $solve -Raw
if($s.Contains('UnsupportedNativeContactPairs(model)'))
    { $s=$s.Replace('UnsupportedNativeContactPairs(model)','UnsupportedNativeContactPairsV2(model)') }
if($s.Contains('native Code_Aster contact is currently certified only for Bonded/Tied pairs. '))
    { $s=$s.Replace('native Code_Aster contact is currently certified only for Bonded/Tied pairs. ',
                    'native Code_Aster contact supports Bonded/Tied and the first Hard-contact candidate set. ') }
Set-Content $solve $s -Encoding UTF8

# ------------------------- UI disclosure -------------------------
$u=Get-Content $ui -Raw
if(-not $u.Contains('Hard Frictionless')) {
    $anchor='                InfoCard("Bonded/Tied • Code_Aster LIAISON_MAIL • Static Structural"),'
    if($u.Contains($anchor))
    {
        $u=$u.Replace($anchor,$anchor+[Environment]::NewLine+
            '                InfoCard("Hard Frictionless / Coulomb • DEFI_CONTACT + STAT_NON_LINE • Adjust OFF"),')
        Set-Content $ui $u -Encoding UTF8
    }
}

Write-Host 'C10.29.2 nonlinear contact candidate applied: Hard frictionless + Coulomb via DEFI_CONTACT/STAT_NON_LINE; unsupported laws stay blocked.' -ForegroundColor Green
