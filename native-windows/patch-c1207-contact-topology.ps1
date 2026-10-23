param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'

function Replace-C1207Required([string]$Text,[string]$Old,[string]$New) {
    $Old=[regex]::Replace($Old,"\r\n?","`n")
    $New=[regex]::Replace($New,"\r\n?","`n")
    if(-not $Text.Contains($Old)) { throw "C12.07 contact topology anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$bridgePath=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$projectPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$exporter=[regex]::Replace((Get-Content -LiteralPath $exporterPath -Raw),"\r\n?","`n")
$bridge=[regex]::Replace((Get-Content -LiteralPath $bridgePath -Raw),"\r\n?","`n")
$project=Get-Content -LiteralPath $projectPath -Raw

if(-not $exporter.Contains('// ASTERMAX_C1207_CONTACT_TOPOLOGY')) {
    $oldContacts='            JArray contacts=(JArray)contract["contacts"] ?? new JArray();'
    $newContacts=@'
            // ASTERMAX_C1207_CONTACT_TOPOLOGY
            // Plan before creating output files. The source contract and FeModel
            // remain unchanged; every exported face/node/contact law is retained.
            JObject contactOrientationReport;
            JArray contacts=AsterMaxContactTopology.Normalize(
                contract["contacts"] as JArray,nodes,out contactOrientationReport);
'@
    $exporter=Replace-C1207Required $exporter $oldContacts $newContacts
    $manifest=@'
                ["contact_pair_count"]=contacts.Count,
                ["contact_orientation_report"]=contactOrientationReport,
                ["exported_result_time"]=contacts.Count>0?new JValue(1.0):JValue.CreateNull(),
'@
    $exporter=Replace-C1207Required $exporter '                ["contact_pair_count"]=contacts.Count,' $manifest
}
if(-not $exporter.Contains('// C1207_CONTACT_ARRAY_REQUIRED')) {
    $arrayGuard=@'
            // C1207_CONTACT_ARRAY_REQUIRED
            // Absence means no contacts. A present malformed/null token must not
            // silently erase the contact model from a requested solve.
            JToken contactToken=contract["contacts"];
            if(contactToken!=null && !(contactToken is JArray))
                throw new InvalidDataException("El campo contacts debe ser una lista de contactos. Revise el contrato del modelo antes de resolver.");
            JObject contactOrientationReport;
'@
    $exporter=Replace-C1207Required $exporter '            JObject contactOrientationReport;' $arrayGuard
    $exporter=Replace-C1207Required $exporter 'contract["contacts"] as JArray,nodes,out contactOrientationReport' 'contactToken as JArray,nodes,out contactOrientationReport'
}

# Some development trees predate C10.41. Keep its marker so applying the complete
# historical chain afterwards cannot introduce a second output-selection block.
$writeAnchor='            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));'
if(-not $exporter.Contains('C1041_STATIC_CONTACT_FINAL_RESULT')) {
    $finalMed=@'
            // C1041_STATIC_CONTACT_FINAL_RESULT
            if(contacts.Count>0)
            {
                string allStates="IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result))";
                string finalState="IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result, INST=1.0))";
                if(comm.Contains(allStates)) comm=comm.Replace(allStates,finalState);
                else if(!comm.Contains(finalState)) throw new InvalidOperationException("C12.07 final MED output anchor missing.");
            }
'@
    $exporter=Replace-C1207Required $exporter $writeAnchor ($finalMed+"`n"+$writeAnchor)
}
if(-not $exporter.Contains('C1207_STATIC_CONTACT_FINAL_TABLES')) {
    $finalTables=@'
            // C1207_STATIC_CONTACT_FINAL_TABLES
            // Solve all ten increments, then publish the one final static state
            // consumed by the production MED bridge, including table probes.
            if(contacts.Count>0)
            {
                comm=comm.Replace("TOUT_ORDRE='OUI'","INST=1.0");
                if(!comm.Contains("IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result, INST=1.0))"))
                    throw new InvalidOperationException("C12.07 expected final contact result at INST=1.0.");
            }
'@
    $exporter=Replace-C1207Required $exporter $writeAnchor ($finalTables+"`n"+$writeAnchor)
}
if(-not $bridge.Contains('// ASTERMAX_C1207_ACTIVE_CONTACTS')) {
    $oldActive=@'
                ContactPair cp = cpEntry.Value;
                if (cp == null) continue;
                contactIndex++;
'@
    $newActive=@'
                ContactPair cp = cpEntry.Value;
                // ASTERMAX_C1207_ACTIVE_CONTACTS
                if (cp == null || !cp.Active) continue;
                if (!cp.Valid)
                    throw new InvalidOperationException("El contacto activo '" + cp.Name + "' no es válido. Revise sus superficies antes de resolver.");
                contactIndex++;
'@
    $bridge=Replace-C1207Required $bridge $oldActive $newActive
}

$exporter=[regex]::Replace($exporter,'public const string Version = "[^"]+";','public const string Version = "C12.07-contact-topology-v1";')
$bridge=[regex]::Replace($bridge,'public const string NativeBridgeVersion = "[^"]+";','public const string NativeBridgeVersion = "C12.07-contact-topology-v1";')
if(-not $project.Contains('<Compile Include="AsterMaxContactTopology.cs" />')) {
    $project=Replace-C1207Required $project '<Compile Include="AsterMaxCodeAsterNativeExporter.cs" />' ('<Compile Include="AsterMaxCodeAsterNativeExporter.cs" />'+"`n"+'    <Compile Include="AsterMaxContactTopology.cs" />')
}
$helper=Join-Path $PSScriptRoot 'AsterMaxContactTopology.cs'
if(-not (Test-Path -LiteralPath $helper -PathType Leaf)) { throw "C12.07 production contact topology helper missing: $helper" }
Copy-Item -LiteralPath $helper -Destination (Join-Path $Root 'PrePoMax/AsterMaxContactTopology.cs') -Force
Set-Content -LiteralPath $exporterPath -Value $exporter -Encoding UTF8 -NoNewline
Set-Content -LiteralPath $bridgePath -Value $bridge -Encoding UTF8 -NoNewline
Set-Content -LiteralPath $projectPath -Value $project -Encoding UTF8 -NoNewline
Write-Host 'C12.07 contact topology, active-pair validation and explicit final contact output applied.'
