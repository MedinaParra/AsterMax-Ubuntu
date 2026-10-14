param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){throw "C10.44 missing: $controllerPath"}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# ----------------------------------------------------------------------
# Adaptive graphics-only tessellation for large assemblies.
# Exact BREP/CAD data remains unchanged; only the temporary .vis preview mesh
# uses a larger deflection while the assembly is being displayed.
# ----------------------------------------------------------------------
$field='        [NonSerialized] private int _asterMaxCadImportDepth;'
if(-not $c.Contains('_asterMaxCadVisualizationDeflectionOverride')){
    if(-not $c.Contains($field)){throw 'C10.44 CAD import depth field missing.'}
    $c=$c.Replace($field,$field+"`n        [NonSerialized] private double? _asterMaxCadVisualizationDeflectionOverride;")
}

if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_DEFLECTION')){
    $split='                    int splitCount = filesToImport == null ? 0 : filesToImport.Length;'
    if(-not $c.Contains($split)){ $split='                int splitCount = filesToImport == null ? 0 : filesToImport.Length;' }
    if(-not $c.Contains($split)){throw 'C10.44 splitCount anchor missing after C10.43.'}
    $indent=$split.Substring(0,$split.IndexOf('int splitCount'))
    $adapt=@"
${split}
${indent}int asterMaxPreviewThreshold = 80;
${indent}string asterMaxPreviewThresholdText = Environment.GetEnvironmentVariable("ASTERMAX_LARGE_ASSEMBLY_PARTS");
${indent}int asterMaxConfiguredPreviewThreshold;
${indent}if (!String.IsNullOrWhiteSpace(asterMaxPreviewThresholdText) &&
${indent}    Int32.TryParse(asterMaxPreviewThresholdText, out asterMaxConfiguredPreviewThreshold) &&
${indent}    asterMaxConfiguredPreviewThreshold > 1)
${indent}    asterMaxPreviewThreshold = asterMaxConfiguredPreviewThreshold;
${indent}if (splitCount >= asterMaxPreviewThreshold)
${indent}{
${indent}    double asterMaxPreviewDeflection = Math.Min(0.1, Math.Max(_settings.Graphics.GeometryDeflection, 0.04));
${indent}    string asterMaxPreviewDeflectionText = Environment.GetEnvironmentVariable("ASTERMAX_LARGE_ASSEMBLY_DEFLECTION");
${indent}    double asterMaxConfiguredPreviewDeflection;
${indent}    if (!String.IsNullOrWhiteSpace(asterMaxPreviewDeflectionText) &&
${indent}        Double.TryParse(asterMaxPreviewDeflectionText, System.Globalization.NumberStyles.Float,
${indent}                        System.Globalization.CultureInfo.InvariantCulture, out asterMaxConfiguredPreviewDeflection) &&
${indent}        asterMaxConfiguredPreviewDeflection > 0 && asterMaxConfiguredPreviewDeflection <= 0.1)
${indent}        asterMaxPreviewDeflection = asterMaxConfiguredPreviewDeflection;
${indent}    _asterMaxCadVisualizationDeflectionOverride = asterMaxPreviewDeflection;
${indent}    _form.WriteDataToOutput("AsterMax CAD large-assembly preview: deflection=" +
${indent}                            asterMaxPreviewDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture) +
${indent}                            ", split=" + splitCount + ". Exact BREP retained.");
${indent}}
"@
    $c=$c.Replace($split,$adapt.TrimEnd())
}

if(-not $c.Contains('double asterMaxVisualDeflection = _asterMaxCadVisualizationDeflectionOverride')){
    $arg='                string argument = "BREP_VISUALIZATION " +'
    if(-not $c.Contains($arg)){throw 'C10.44 BREP visualization argument anchor missing.'}
    $prep=@'
                double asterMaxVisualDeflection = _asterMaxCadVisualizationDeflectionOverride ??
                                                   _settings.Graphics.GeometryDeflection;
                string asterMaxVisualDeflectionText = asterMaxVisualDeflection.ToString(System.Globalization.CultureInfo.InvariantCulture);

                string argument = "BREP_VISUALIZATION " +
'@
    $c=$c.Replace($arg,$prep.TrimEnd())
    $old='                                  _settings.Graphics.GeometryDeflection.ToString();'
    if(-not $c.Contains($old)){throw 'C10.44 BREP deflection value anchor missing.'}
    $c=$c.Replace($old,'                                  asterMaxVisualDeflectionText;')
}

$passOld='                                        " pieza(s), VIS=" + visualizationBytes + " bytes, job=" + jobName + ".");'
if($c.Contains($passOld) -and -not $c.Contains('deflection=" + asterMaxVisualDeflectionText')){
    $passNew='                                        " pieza(s), VIS=" + visualizationBytes + " bytes, deflection=" +'+"`n"+
             '                                        asterMaxVisualDeflectionText + ", job=" + jobName + ".");'
    $c=$c.Replace($passOld,$passNew)
}

# Reset the graphics-only override when the top-level CAD transaction ends.
if(-not $c.Contains('if (asterMaxTopLevelCadImport) _asterMaxCadVisualizationDeflectionOverride = null;')){
    $depthLine='                _asterMaxCadImportDepth--;'
    if(-not $c.Contains($depthLine)){ $depthLine='            _asterMaxCadImportDepth--;' }
    if(-not $c.Contains($depthLine)){throw 'C10.44 CAD import finally depth anchor missing.'}
    $indent=$depthLine.Substring(0,$depthLine.IndexOf('_asterMax'))
    $c=$c.Replace($depthLine,$indent+'if (asterMaxTopLevelCadImport) _asterMaxCadVisualizationDeflectionOverride = null;'+"`n"+$depthLine)
}

Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.44: adaptive large-assembly visualization deflection applied; exact BREP retained.' -ForegroundColor Green
