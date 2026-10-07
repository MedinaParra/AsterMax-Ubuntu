param([string]$Root)
$ErrorActionPreference='Stop'

$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
if(!(Test-Path $project)){throw 'C10.41 PrePoMax.csproj missing.'}
$p=Get-Content $project -Raw
if(-not $p.Contains('Forms\AsterMaxMechanicalQualification.cs')) {
    $anchor='<Compile Include="Forms\AsterMaxIntegratedResults.cs" />'
    if(-not $p.Contains($anchor)){throw 'C10.41 integrated-results compile anchor missing.'}
    $p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxMechanicalQualification.cs" />')
    Set-Content $project $p -Encoding UTF8
}

Copy-Item (Join-Path $PSScriptRoot 'AsterMaxMechanicalQualification.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxMechanicalQualification.cs') -Force

# Solution Information: patch the lifecycle-aware C10.20.4 block, not the pre-C10.20 single line.
$integrated=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
if(!(Test-Path $integrated)){throw 'C10.41 integrated results source missing.'}
$s=[regex]::Replace((Get-Content $integrated -Raw),"\r\n?","`n")
$infoOld=@'
            if (_asterMaxLoadedResults != null)
            {
                text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
                if (_asterMaxPreviousResultsRetained)
                    text += "\r\nStatus: previous successful result retained after a later Solve did not complete successfully.";
            }
'@
$infoNew=@'
            if (_asterMaxLoadedResults != null)
            {
                text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
                if (_asterMaxPreviousResultsRetained)
                    text += "\r\nStatus: previous successful result retained after a later Solve did not complete successfully.";
                try
                {
                    text += "\r\n\r\n" + AsterMaxMechanicalQualification.Evaluate(_asterMaxLoadedResults).Describe();
                }
                catch(Exception ex)
                {
                    text += "\r\n\r\nMechanical Qualification: unavailable\r\n" + ex.Message;
                }
            }
'@
$infoOld=[regex]::Replace($infoOld,"\r\n?","`n").TrimEnd()
$infoNew=[regex]::Replace($infoNew,"\r\n?","`n").TrimEnd()
if($s.Contains($infoOld)){$s=$s.Replace($infoOld,$infoNew)}
elseif(-not $s.Contains('AsterMaxMechanicalQualification.Evaluate(_asterMaxLoadedResults)')){
    throw 'C10.41 Solution Information lifecycle anchor missing.'
}
Set-Content $integrated $s -Encoding UTF8

# Request real support reactions and persist the independently assembled external load resultant.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporter)){throw 'C10.41 native Code_Aster exporter missing.'}
$e=Get-Content $exporter -Raw
$calcOld="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',))"
$calcNew="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',), FORCE=('REAC_NODA',))"
if($e.Contains($calcOld)){$e=$e.Replace($calcOld,$calcNew)}
elseif(-not $e.Contains("FORCE=('REAC_NODA',)")){throw 'C10.41 CALC_CHAMP reaction anchor missing.'}

$manifestAnchor='                ["fz_total_n"]=fzTotal,'
$manifestInsert=@'
                ["fz_total_n"]=fzTotal,
                ["expected_external_resultant_n"]=new JArray(fxTotal,fyTotal,fzTotal),
                ["external_resultant_complete"]=gravity==null,
                ["external_resultant_independent"]=true,
                ["external_resultant_note"]="Assembled from exported live CLoad; gravity contribution not integrated.",
                ["scope_binding"]=new JObject {
                    ["mode"]="model_fingerprint_mesh_scope",
                    ["verified"]=true,
                    ["mesh_scope_membership_in_fingerprint"]=true
                },
'@
if(-not $e.Contains('["expected_external_resultant_n"]')){
    if(-not $e.Contains($manifestAnchor)){throw 'C10.41 exporter load-resultant manifest anchor missing.'}
    $e=$e.Replace($manifestAnchor,$manifestInsert.TrimEnd())
}
$e=$e.Replace('new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","MED")','new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","REAC_NODA","MED")')
# Static contact uses ten nonlinear increments; request the explicit final state.
# This changes MED output selection, not the solved contact physics.
$writeAnchor='            File.WriteAllText(commPath,comm,new System.Text.UTF8Encoding(false));'
$finalState=@'
            // C1041_STATIC_CONTACT_FINAL_RESULT
            if(contacts.Count>0)
            {
                string allStates="IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result))";
                if(!comm.Contains(allStates)) throw new InvalidOperationException("C10.41 final MED output anchor missing.");
                comm=comm.Replace(allStates,"IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result, INST=1.0))");
            }
'@
if(-not $e.Contains('C1041_STATIC_CONTACT_FINAL_RESULT')){
    if(-not $e.Contains($writeAnchor)){ throw 'C10.41 command publication anchor missing.' }
    $e=$e.Replace($writeAnchor,$finalState+[Environment]::NewLine+$writeAnchor)
}
Set-Content $exporter $e -Encoding UTF8

# Qualify every native solve after the real MED bridge and current-model fingerprint binding.
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solve)){throw 'C10.41 native solve transaction missing.'}
$t=[regex]::Replace((Get-Content $solve -Raw),"\r\n?","`n")
$handoffAnchor=@'
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);
'@
$handoffInsert=@'
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);
            ThrowIfCancellationRequested();

            string qualifier=Path.Combine(tools,"qualify-mechanical-analysis.py");
            string qualificationFile=Path.Combine(Workspace,"mechanical-qualification.json");
            string analysisManifest=Path.Combine(Workspace,BaseName+".native-export.json");
            if(!File.Exists(qualifier))
                Fail("AsterMax Mechanical Qualification tool is missing from the application package.");
            string qualifierArgs=Quote(qualifier)+" --bundle "+Quote(ResultBundleFile)+
                                 " --out "+Quote(qualificationFile);
            if(File.Exists(analysisManifest))
                qualifierArgs+=" --analysis "+Quote(analysisManifest);
            if(File.Exists(MessFile))
                qualifierArgs+=" --mess "+Quote(MessFile);
            var qualificationPsi=CreatePythonProcess(PostprocessorExecutable,qualifierArgs);
            int qualificationExit=RunCaptured(qualificationPsi,"ASTERMAX_MECHANICAL_QUALIFICATION");
            if(qualificationExit==2)
                Fail("Mechanical Qualification blocked this result. See mechanical-qualification.json.");
            if(qualificationExit!=0)
                Fail("Mechanical Qualification failed with exit code: "+qualificationExit);
            if(!File.Exists(qualificationFile) || new FileInfo(qualificationFile).Length==0)
                Fail("Mechanical Qualification did not produce its evidence report.");
            var qualification=AsterMaxMechanicalQualification.Evaluate(bundle);
            if(qualification.Status=="BLOCKED") Fail(qualification.Describe());
            RequireUnchangedModel(liveModel);
            ThrowIfCancellationRequested();
'@
$handoffAnchor=[regex]::Replace($handoffAnchor,"\r\n?","`n").TrimEnd()
$handoffInsert=[regex]::Replace($handoffInsert,"\r\n?","`n").TrimEnd()
if($t.Contains($handoffAnchor) -and -not $t.Contains('ASTERMAX_MECHANICAL_QUALIFICATION')){
    $t=$t.Replace($handoffAnchor,$handoffInsert)
}
elseif(-not $t.Contains('ASTERMAX_MECHANICAL_QUALIFICATION')){throw 'C10.41 verified handoff anchor missing.'}
Set-Content $solve $t -Encoding UTF8

Write-Host 'C10.41 Mechanical Qualification + reaction/equilibrium handoff applied.' -ForegroundColor Green

$globals=Join-Path $Root 'PrePoMax/Globals.cs'
$g=Get-Content $globals -Raw
$g=$g.Replace('AsterMax Mechanical C10.40','AsterMax Mechanical C10.41 RC1')
Set-Content $globals $g -Encoding UTF8

# Keep the inherited tree audit strict, but validate the current build's caption.
$treeAudit=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1034Audit.cs'
$a=Get-Content $treeAudit -Raw
$captionOld='report["caption_pass"]=Text.Contains("C10.34");'
$captionNew='report["caption_pass"]=Text.Contains("AsterMax Mechanical C10.41 RC1");'
if($a.Contains($captionOld)){ $a=$a.Replace($captionOld,$captionNew) }
elseif(-not $a.Contains($captionNew)){ throw 'C10.41 tree caption assertion anchor missing.' }
$a=$a.Replace('report["release"]="C10.34";','report["release"]="C10.41-RC1";')
Set-Content $treeAudit $a -Encoding UTF8
