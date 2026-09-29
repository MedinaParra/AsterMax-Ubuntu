param([string]$Root)
$ErrorActionPreference='Stop'

$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
foreach($p in @($bridgePath,$exporterPath,$auditPath,$globalsPath)){ if(!(Test-Path $p)){ throw "C10.37 missing: $p" } }

# ----------------------------------------------------------------------
# 1) Preserve PrePoMax Friction in the native solver contract.
# ----------------------------------------------------------------------
$b=[regex]::Replace((Get-Content $bridgePath -Raw),"\r\n?","`n")
$oldFriction=@'
                if (interaction.Properties != null && interaction.Properties.Any(x => x is Friction))
                    throw new NotSupportedException("C10.36 supports frictionless contact only. Remove friction or keep Solve blocked.");

                string suffix = contactIndex.ToString("000");
'@
$newFriction=@'
                Friction friction = interaction.Properties == null
                    ? null
                    : interaction.Properties.OfType<Friction>().FirstOrDefault();
                if (friction != null && (!(friction.Coefficient > 0) || Double.IsInfinity(friction.Coefficient) || Double.IsNaN(friction.Coefficient)))
                    throw new InvalidOperationException("C10.37 Coulomb friction coefficient must be finite and greater than zero.");

                string suffix = contactIndex.ToString("000");
'@
if($b.Contains($oldFriction)){ $b=$b.Replace($oldFriction,$newFriction) }
elseif(-not $b.Contains('C10.37 Coulomb friction coefficient')){ throw 'C10.37 friction bridge anchor missing.' }

$oldContract=@'
                    ["formulation"] = "CONTINUE",
                    ["friction"] = "SANS",
                    ["contact_init"] = "INTERPENETRE",
'@
$newContract=@'
                    ["formulation"] = "CONTINUE",
                    ["friction"] = friction == null ? "SANS" : "COULOMB",
                    ["friction_coefficient"] = friction == null ? 0.0 : friction.Coefficient,
                    ["friction_stick_slope"] = friction == null || Double.IsNaN(friction.StickSlope)
                        ? JValue.CreateNull()
                        : new JValue(friction.StickSlope),
                    ["contact_init"] = "INTERPENETRE",
'@
if($b.Contains($oldContract)){ $b=$b.Replace($oldContract,$newContract) }
elseif(-not $b.Contains('["friction_coefficient"]')){ throw 'C10.37 contact contract friction anchor missing.' }
Set-Content $bridgePath $b -Encoding UTF8

# ----------------------------------------------------------------------
# 2) Translate mixed frictionless/Coulomb contact sets to DEFI_CONTACT.
#    When any zone uses friction, Code_Aster receives FROTTEMENT='COULOMB';
#    frictionless zones receive COULOMB=0 and frictional zones their real mu.
# ----------------------------------------------------------------------
$e=[regex]::Replace((Get-Content $exporterPath -Raw),"\r\n?","`n")
$version=[regex]::Match($e,'public const string Version = "[^"]+";').Value
if([string]::IsNullOrWhiteSpace($version)){ throw 'C10.37 exporter version anchor missing.' }
$e=$e.Replace($version,'public const string Version = "C10.37-native-codeaster-coulomb-v1";')

$oldZones=@'
                var zoneLines=new List<string>();
                foreach(JObject contact in contacts.Cast<JObject>())
                {
                    JObject master=(JObject)contact["master"];
                    JObject slave=(JObject)contact["slave"];
                    zoneLines.Add(String.Format(CultureInfo.InvariantCulture,
                        "_F(GROUP_MA_MAIT='{0}', GROUP_MA_ESCL='{1}', CONTACT_INIT='{2}')",
                        (string)master["group"],(string)slave["group"],(string)contact["contact_init"]));
                }
                string zones=String.Join(",\n        ",zoneLines);
'@
$newZones=@'
                bool hasCoulomb=contacts.Cast<JObject>().Any(x =>
                    String.Equals((string)x["friction"],"COULOMB",StringComparison.OrdinalIgnoreCase));
                string frictionMode=hasCoulomb ? "COULOMB" : "SANS";
                var zoneLines=new List<string>();
                foreach(JObject contact in contacts.Cast<JObject>())
                {
                    JObject master=(JObject)contact["master"];
                    JObject slave=(JObject)contact["slave"];
                    string frictionClause=hasCoulomb ? ", COULOMB="+F(contact["friction_coefficient"]) : "";
                    zoneLines.Add(String.Format(CultureInfo.InvariantCulture,
                        "_F(GROUP_MA_MAIT='{0}', GROUP_MA_ESCL='{1}', CONTACT_INIT='{2}'{3})",
                        (string)master["group"],(string)slave["group"],(string)contact["contact_init"],frictionClause));
                }
                string zones=String.Join(",\n        ",zoneLines);
'@
if($e.Contains($oldZones)){ $e=$e.Replace($oldZones,$newZones) }
elseif(-not $e.Contains('string frictionMode=hasCoulomb ? "COULOMB" : "SANS";')){ throw 'C10.37 exporter zone anchor missing.' }

$oldMode="    FROTTEMENT='SANS',"
$newMode="    FROTTEMENT='{1}',"
if($e.Contains($oldMode)){ $e=$e.Replace($oldMode,$newMode) }
elseif(-not $e.Contains($newMode)){ throw 'C10.37 DEFI_CONTACT friction mode anchor missing.' }

$oldFormat=')",zones);'
$newFormat=')",zones,frictionMode);'
if($e.Contains($oldFormat)){ $e=$e.Replace($oldFormat,$newFormat) }
elseif(-not $e.Contains($newFormat)){ throw 'C10.37 nonlinear String.Format anchor missing.' }

$oldManifest='                ["contact_friction"]="SANS",'
$newManifest=@'
                ["contact_friction"]=contacts.Count==0?"SANS":
                    (contacts.Cast<JObject>().Any(x=>String.Equals((string)x["friction"],"COULOMB",StringComparison.OrdinalIgnoreCase))?"COULOMB":"SANS"),
                ["contact_coulomb_coefficients"]=new JArray(contacts.Cast<JObject>()
                    .Where(x=>String.Equals((string)x["friction"],"COULOMB",StringComparison.OrdinalIgnoreCase))
                    .Select(x=>(double?)x["friction_coefficient"] ?? 0.0)),
'@
if($e.Contains($oldManifest)){ $e=$e.Replace($oldManifest,$newManifest.TrimEnd()) }
elseif(-not $e.Contains('["contact_coulomb_coefficients"]')){ throw 'C10.37 manifest friction anchor missing.' }
Set-Content $exporterPath $e -Encoding UTF8

# ----------------------------------------------------------------------
# 3) Runtime audit: turn the automatically generated real contact into
#    Coulomb mu=0.20 before the bridge is exercised. This proves that the
#    FeModel -> contract path carries real PrePoMax friction, not synthetic JSON.
# ----------------------------------------------------------------------
$a=[regex]::Replace((Get-Content $auditPath -Raw),"\r\n?","`n")
$auditAnchor='                    JObject solverContract=AsterMaxModelContractBridge.Build(model);'
$auditInsert=@'
                    foreach(string contactName in contactNames)
                    {
                        ContactPair frictionPair=_controller.GetContactPair(contactName);
                        if(frictionPair==null) continue;
                        SurfaceInteraction frictionInteraction;
                        if(!model.SurfaceInteractions.TryGetValue(frictionPair.SurfaceInteractionName,out frictionInteraction) || frictionInteraction==null)
                            throw new InvalidOperationException("C10.37 audit contact interaction missing: "+frictionPair.SurfaceInteractionName);
                        if(frictionInteraction.Properties==null || !frictionInteraction.Properties.Any(x=>x is Friction))
                            frictionInteraction.AddProperty(new Friction(0.20));
                    }
                    JObject solverContract=AsterMaxModelContractBridge.Build(model);
'@
if($a.Contains($auditAnchor) -and -not $a.Contains('new Friction(0.20)')){
    $a=$a.Replace($auditAnchor,$auditInsert.TrimEnd())
}
elseif(-not $a.Contains('new Friction(0.20)')){ throw 'C10.37 audit bridge anchor missing.' }

$contractAnchor='                    report["codeaster_contact_contract_pass"]=contractOk;'
$contractNew=@'
                    bool coulombContract=solverContacts!=null && solverContacts.Count>0 &&
                        solverContacts.Cast<JObject>().All(x =>
                            String.Equals((string)x["friction"],"COULOMB",StringComparison.OrdinalIgnoreCase) &&
                            Math.Abs(((double?)x["friction_coefficient"] ?? 0.0)-0.20)<1e-12);
                    contractOk &= coulombContract;
                    report["codeaster_contact_contract_pass"]=contractOk;
                    report["codeaster_coulomb_contract_pass"]=coulombContract;
                    report["codeaster_coulomb_mu"]=0.20;
'@
if($a.Contains($contractAnchor) -and -not $a.Contains('codeaster_coulomb_contract_pass')){
    $a=$a.Replace($contractAnchor,$contractNew.TrimEnd())
}
elseif(-not $a.Contains('codeaster_coulomb_contract_pass')){ throw 'C10.37 runtime friction report anchor missing.' }
Set-Content $auditPath $a -Encoding UTF8

# ----------------------------------------------------------------------
# 4) Release identity.
# ----------------------------------------------------------------------
$g=[regex]::Replace((Get-Content $globalsPath -Raw),"\r\n?","`n")
$g=$g.Replace('AsterMax Mechanical C10.36','AsterMax Mechanical C10.37')
if(-not $g.Contains('AsterMax Mechanical C10.37')){ throw 'C10.37 Globals version anchor missing.' }
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.37: native Coulomb friction bridge + Code_Aster DEFI_CONTACT translation applied.' -ForegroundColor Green
