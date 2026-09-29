param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){throw "C10.21 anchor missing: $Old"}
    return $Text.Replace($Old,$New)
}

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

$integrated=Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
if(!(Test-Path $integrated)){throw 'C10.21 integrated results source missing.'}
$s=Get-Content $integrated -Raw
$old='            if (_asterMaxLoadedResults != null) text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;'
$new=@'
            if (_asterMaxLoadedResults != null)
            {
                text += "\r\nBundle: " + _asterMaxLoadedResults.SourceFile;
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
if($s.Contains($old)) {
    $s=$s.Replace($old,$new.TrimEnd())
} elseif(-not $s.Contains('AsterMaxMechanicalQualification.Evaluate(_asterMaxLoadedResults)')) {
    throw 'C10.21 solution-information anchor missing.'
}
Set-Content $integrated $s -Encoding UTF8


# Add real support reactions and the independently assembled load resultant to the native exporter.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporter)){throw 'C10.21 native Code_Aster exporter missing.'}
$e=Get-Content $exporter -Raw
$calcOld="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',))"
$calcNew="result = CALC_CHAMP(reuse=result, RESULTAT=result, CONTRAINTE=('SIGM_ELNO',), CRITERES=('SIEQ_ELNO',), FORCE=('REAC_NODA',))"
if($e.Contains($calcOld)){$e=$e.Replace($calcOld,$calcNew)}
elseif(-not $e.Contains("FORCE=('REAC_NODA',)")){throw 'C10.21 CALC_CHAMP reaction anchor missing.'}

$manifestAnchor='                ["fz_per_node_n"]=fz,'
$manifestInsert=@'
                ["fz_per_node_n"]=fz,
                ["expected_external_resultant_n"]=new JArray(
                    GetDouble(load,"fx_total_n"),
                    GetDouble(load,"fy_total_n"),
                    GetDouble(load,"fz_total_n")),
'@
if(-not $e.Contains('["expected_external_resultant_n"]')){
    if(-not $e.Contains($manifestAnchor)){throw 'C10.21 exporter load-resultant manifest anchor missing.'}
    $e=$e.Replace($manifestAnchor,$manifestInsert.TrimEnd())
}
$e=$e.Replace('new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","MED")',
              'new JArray("DEPL","SIGM_ELNO","SIEQ_ELNO","REAC_NODA","MED")')
Set-Content $exporter $e -Encoding UTF8

# Execute qualification after the real MED bridge and current-model fingerprint binding.
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
if(!(Test-Path $solve)){throw 'C10.21 native solve transaction missing.'}
$t=Get-Content $solve -Raw
$handoffOld=@'
            var bundle=AsterMaxResultsBundle.Load(ResultBundleFile);
            bundle.RequireCurrentModel(liveModel);

            State=AsterMaxSolveState.SolutionCurrent;
'@
$handoffNew=@'
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

            State=AsterMaxSolveState.SolutionCurrent;
'@
if($t.Contains($handoffOld)){$t=$t.Replace($handoffOld,$handoffNew)}
elseif(-not $t.Contains('ASTERMAX_MECHANICAL_QUALIFICATION')){throw 'C10.21 verified handoff anchor missing.'}
Set-Content $solve $t -Encoding UTF8

Write-Host 'C10.21 Mechanical Qualification + reaction/equilibrium handoff applied.' -ForegroundColor Green
