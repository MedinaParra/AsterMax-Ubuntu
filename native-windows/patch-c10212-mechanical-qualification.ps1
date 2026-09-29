param([string]$Root)
$ErrorActionPreference='Stop'

$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
if(!(Test-Path $project)){throw 'C10.21 PrePoMax.csproj missing.'}
$p=Get-Content $project -Raw
if(-not $p.Contains('Forms\AsterMaxMechanicalQualification.cs')) {
    $anchor='<Compile Include="Forms\AsterMaxIntegratedResults.cs" />'
    if(-not $p.Contains($anchor)){throw 'C10.21 integrated-results compile anchor missing.'}
    $p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxMechanicalQualification.cs" />')
    Set-Content $project $p -Encoding UTF8
}

Copy-Item (Join-Path $PSScriptRoot 'AsterMaxMechanicalQualification.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxMechanicalQualification.cs') -Force

# Solution Information: patch the lifecycle-aware C10.20.4 block, not the pre-C10.20 single line.
$integrated=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
if(!(Test-Path $integrated)){throw 'C10.21 integrated results source missing.'}
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
    throw 'C10.21 Solution Information lifecycle anchor missing.'
}
Set-Content $integrated $s -Encoding UTF8

# Request real support reactions and persist the independently assembled external load resultant.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporter)){throw 'C10.21 native Code_Aster exporter missing.'}
$e=Get-Content $exporter -Raw
$calcOld="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',))"
$calcNew="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',), FORCE=('REAC_NODA',))"
if($e.Contains($calcOld)){$e=$e.Replace($calcOld,$calcNew)}
elseif(-not $e.Contains("FORCE=('REAC_NODA',)")){throw 'C10.21 CALC_CHAMP reaction anchor missing.'}

$manifestAnchor='                ["fz_total_n"]=fzTotal,'
$manifestInsert=@'
                ["fz_total_n"]=fzTotal,
                ["expected_external_resultant_n"]=new JArray(fxTotal,fyTotal,fzTotal),
'@
if(-not $e.Contains('["expected_external_resultant_n"]')){
    if(-not $e.Contains($manifestAnchor)){throw 'C10.21 exporter load-resultant manifest anchor missing.'}
    $e=$e.Replace($manifestAnchor,$manifestInsert.TrimEnd())
}
$e=$e.Replace('new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","MED")','new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","REAC_NODA","MED")')
Set-Content $exporter $e -Encoding UTF8

# Qualify every native solve after the real MED bridge and current-model fingerprint binding.
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solve)){throw 'C10.21 native solve transaction missing.'}
$t=[regex]::Replace((Get-Content $solve -Raw),"\r\n?","`n")
$handoffAnchor=@'
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);
'@
$handoffInsert=@'
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);

            string qualifier=Path.Combine(tools,"qualify-mechanical-analysis.py");
            string qualificationFile=Path.Combine(Workspace,"mechanical-qualification.json");
            string analysisManifest=Path.Combine(Workspace,BaseName+".native-export.json");
            if(!File.Exists(qualifier))
                Fail("AsterMax Mechanical Qualification tool is missing from the application package.");
            string qualifierArgs=Quote(qualifier)+" --bundle "+Quote(ResultBundleFile)+
                                 " --out "+Quote(qualificationFile);
            if(File.Exists(analysisManifest))
                qualifierArgs+=" --analysis "+Quote(analysisManifest);
            var qualificationPsi=CreatePythonProcess(PostprocessorExecutable,qualifierArgs);
            int qualificationExit=RunCaptured(qualificationPsi,"ASTERMAX_MECHANICAL_QUALIFICATION");
            if(qualificationExit==2)
                Fail("Mechanical Qualification blocked this result. See mechanical-qualification.json.");
            if(qualificationExit!=0)
                Fail("Mechanical Qualification failed with exit code: "+qualificationExit);
            if(!File.Exists(qualificationFile) || new FileInfo(qualificationFile).Length==0)
                Fail("Mechanical Qualification did not produce its evidence report.");
'@
$handoffAnchor=[regex]::Replace($handoffAnchor,"\r\n?","`n").TrimEnd()
$handoffInsert=[regex]::Replace($handoffInsert,"\r\n?","`n").TrimEnd()
if($t.Contains($handoffAnchor) -and -not $t.Contains('ASTERMAX_MECHANICAL_QUALIFICATION')){
    $t=$t.Replace($handoffAnchor,$handoffInsert)
}
elseif(-not $t.Contains('ASTERMAX_MECHANICAL_QUALIFICATION')){throw 'C10.21 verified handoff anchor missing.'}
Set-Content $solve $t -Encoding UTF8

Write-Host 'C10.21 Mechanical Qualification + reaction/equilibrium handoff applied.' -ForegroundColor Green
