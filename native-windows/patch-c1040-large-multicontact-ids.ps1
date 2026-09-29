param([string]$Root)
$ErrorActionPreference='Stop'

$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1035Audit.cs'
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
foreach($p in @($bridgePath,$exporterPath,$auditPath,$globalsPath)){ if(!(Test-Path $p)){ throw "C10.40 missing: $p" } }

# Legacy IDs grew past 8 chars after face 9999. Code_Aster then truncated
# M00110000 to M0011000, colliding with the legitimate face 1000 ID.
# New layout is always exactly 8 chars:
# role[1] + contactIndex base36[2] + localFaceIndex base36[5].
$b=Get-Content $bridgePath -Raw
$b=[regex]::Replace($b,'public const string NativeBridgeVersion = "[^"]+";','public const string NativeBridgeVersion = "C10.40-large-multicontact-id-v1";',1)

$oldMaster='                JObject master = BuildCodeAsterContactSurface(model, cp.MasterRegionName, "AM_M" + suffix, "M" + suffix);'
$newMaster='                JObject master = BuildCodeAsterContactSurface(model, cp.MasterRegionName, "AM_M" + suffix, "M", contactIndex);'
if($b.Contains($oldMaster)){ $b=$b.Replace($oldMaster,$newMaster) }
elseif(-not $b.Contains($newMaster)){ throw 'C10.40 master contact ID anchor missing.' }

$oldSlave='                JObject slave = BuildCodeAsterContactSurface(model, cp.SlaveRegionName, "AM_S" + suffix, "S" + suffix);'
$newSlave='                JObject slave = BuildCodeAsterContactSurface(model, cp.SlaveRegionName, "AM_S" + suffix, "S", contactIndex);'
if($b.Contains($oldSlave)){ $b=$b.Replace($oldSlave,$newSlave) }
elseif(-not $b.Contains($newSlave)){ throw 'C10.40 slave contact ID anchor missing.' }

$oldSig='        private static JObject BuildCodeAsterContactSurface(FeModel model, string surfaceName, string groupName, string elementPrefix)'
$newSig='        private static JObject BuildCodeAsterContactSurface(FeModel model, string surfaceName, string groupName, string role, int contactIndex)'
if($b.Contains($oldSig)){ $b=$b.Replace($oldSig,$newSig) }
elseif(-not $b.Contains($newSig)){ throw 'C10.40 contact surface signature anchor missing.' }

$oldId='                    string syntheticId = elementPrefix + localId.ToString("0000");'
$newId='                    string syntheticId = CodeAsterSkinElementId(role, contactIndex, localId);'
if($b.Contains($oldId)){ $b=$b.Replace($oldId,$newId) }
elseif(-not $b.Contains($newId)){ throw 'C10.40 synthetic contact ID anchor missing.' }

$helperAnchor='        private static JObject BuildCodeAsterContactSurface('
$helpers=@'
        internal static string CodeAsterSkinElementId(string role, int contactIndex, int localFaceIndex)
        {
            if (!String.Equals(role, "M", StringComparison.Ordinal) &&
                !String.Equals(role, "S", StringComparison.Ordinal))
                throw new ArgumentException("C10.40 contact skin role must be M or S.", nameof(role));
            return role + CodeAsterBase36(contactIndex, 2, "contact index") +
                   CodeAsterBase36(localFaceIndex, 5, "local face index");
        }

        private static string CodeAsterBase36(int value, int width, string label)
        {
            if (value < 1) throw new ArgumentOutOfRangeException(label, "C10.40 Code_Aster identifiers are 1-based.");
            const string digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
            char[] chars = new char[width];
            int remaining = value;
            for (int i = width - 1; i >= 0; i--)
            {
                chars[i] = digits[remaining % 36];
                remaining /= 36;
            }
            if (remaining != 0)
                throw new NotSupportedException("C10.40 " + label + " exceeds the fixed Code_Aster 8-character identifier namespace.");
            return new string(chars);
        }

'@
if(-not $b.Contains('internal static string CodeAsterSkinElementId(')){
    $idx=$b.IndexOf($helperAnchor)
    if($idx -lt 0){ throw 'C10.40 helper insertion anchor missing.' }
    $b=$b.Substring(0,$idx)+$helpers+$b.Substring($idx)
}
Set-Content $bridgePath $b -Encoding UTF8

$e=Get-Content $exporterPath -Raw
$e=[regex]::Replace($e,'public const string Version = "[^"]+";','public const string Version = "C10.40-large-multicontact-id-v1";',1)
$manifestAnchor='                ["contact_pair_count"]=contacts.Count,'
$manifestNew=@'
                ["contact_pair_count"]=contacts.Count,
                ["contact_skin_id_scheme"]="ROLE1_CONTACT2_BASE36_FACE5_BASE36",
                ["contact_skin_id_max_length"]=8,
'@
if($e.Contains($manifestAnchor) -and -not $e.Contains('["contact_skin_id_scheme"]')){
    $e=$e.Replace($manifestAnchor,$manifestNew.TrimEnd())
}
elseif(-not $e.Contains('["contact_skin_id_scheme"]')){ throw 'C10.40 exporter manifest anchor missing.' }
Set-Content $exporterPath $e -Encoding UTF8

# Stress the exact field-failure domain: 30 pairs and >10,000 faces/surface.
$a=Get-Content $auditPath -Raw
$reportAnchor='                    report["codeaster_contact_contract_pass"]=contractOk;'
$stress=@'
                    const int stressPairs=30;
                    const int stressFacesPerSurface=12050;
                    HashSet<string> stressIds=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    bool skinIdStressPass=true;
                    int stressGenerated=0;
                    for(int ci=1;ci<=stressPairs && skinIdStressPass;ci++)
                    {
                        foreach(string role in new [] { "M", "S" })
                        {
                            for(int fi=1;fi<=stressFacesPerSurface;fi++)
                            {
                                string skinId=AsterMaxModelContractBridge.CodeAsterSkinElementId(role,ci,fi);
                                stressGenerated++;
                                if(skinId.Length>8 || !stressIds.Add(skinId))
                                {
                                    skinIdStressPass=false;
                                    break;
                                }
                            }
                            if(!skinIdStressPass) break;
                        }
                    }
                    string legacyFace1000="M001"+1000.ToString("0000");
                    string legacyFace10000="M001"+10000.ToString("0000");
                    bool legacyCollisionReproduced=legacyFace1000.Length==8 && legacyFace10000.Length>8 &&
                        legacyFace10000.Substring(0,8)==legacyFace1000;
                    string fixedFace1000=AsterMaxModelContractBridge.CodeAsterSkinElementId("M",1,1000);
                    string fixedFace10000=AsterMaxModelContractBridge.CodeAsterSkinElementId("M",1,10000);
                    bool boundaryPass=fixedFace1000.Length==8 && fixedFace10000.Length==8 &&
                        !String.Equals(fixedFace1000,fixedFace10000,StringComparison.OrdinalIgnoreCase);
                    skinIdStressPass &= legacyCollisionReproduced && boundaryPass;
                    contractOk &= skinIdStressPass;
                    report["codeaster_contact_contract_pass"]=contractOk;
                    report["codeaster_skin_id_stress_pass"]=skinIdStressPass;
                    report["codeaster_skin_id_legacy_collision_reproduced"]=legacyCollisionReproduced;
                    report["codeaster_skin_id_stress_pairs"]=stressPairs;
                    report["codeaster_skin_id_stress_faces_per_surface"]=stressFacesPerSurface;
                    report["codeaster_skin_id_stress_generated"]=stressGenerated;
                    report["codeaster_skin_id_boundary_face_1000"]=fixedFace1000;
                    report["codeaster_skin_id_boundary_face_10000"]=fixedFace10000;
'@
if($a.Contains($reportAnchor) -and -not $a.Contains('codeaster_skin_id_stress_pass')){
    $a=$a.Replace($reportAnchor,$stress.TrimEnd())
}
elseif(-not $a.Contains('codeaster_skin_id_stress_pass')){ throw 'C10.40 audit report anchor missing.' }
Set-Content $auditPath $a -Encoding UTF8

$g=Get-Content $globalsPath -Raw
$g=$g.Replace('AsterMax Mechanical C10.39','AsterMax Mechanical C10.40')
if(-not $g.Contains('AsterMax Mechanical C10.40')){ throw 'C10.40 Globals version anchor missing.' }
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.40: collision-free 8-character Code_Aster skin IDs for large multi-contact models applied.' -ForegroundColor Green
