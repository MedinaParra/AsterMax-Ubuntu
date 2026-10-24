param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
if(!(Test-Path $controllerPath)){ throw "C10.42 controller preflight missing: $controllerPath" }
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

# Import transaction depth state.
if(-not $c.Contains('_asterMaxCadImportDepth')){
    $state='        [NonSerialized] protected bool _animating;'
    if(-not $c.Contains($state)){ throw 'C10.42 controller preflight: state anchor missing.' }
    $c=$c.Replace($state,$state+"`n        [NonSerialized] private int _asterMaxCadImportDepth;")
}

# Structurally wrap ImportCADAssemblyFile in a depth-tracked transaction while
# retaining whatever the C10.41 patch chain has added inside the method.
if(-not $c.Contains('bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;')){
    $sig='        public string[] ImportCADAssemblyFile(string assemblyFileName, string splitCommand)'
    $start=$c.IndexOf($sig)
    if($start -lt 0){ throw 'C10.42 controller preflight: ImportCADAssemblyFile missing.' }
    $brace=$c.IndexOf('{',$start)
    if($brace -lt 0){ throw 'C10.42 controller preflight: import opening brace missing.' }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $c.Length; $n++){
        if($c[$n] -eq '{'){ $depth++ }
        elseif($c[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $end=$n; break }
        }
    }
    if($end -lt 0){ throw 'C10.42 controller preflight: import closing brace missing.' }
    $method=$c.Substring($start,$end-$start+1)
    $localBrace=$method.IndexOf('{')
    $inject=@'

            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;
            _asterMaxCadImportDepth++;
            var asterMaxCadImportWatch = System.Diagnostics.Stopwatch.StartNew();
            try
            {
'@
    $method=$method.Substring(0,$localBrace+1)+$inject+$method.Substring($localBrace+1)

    $returnToken='            return allAddedPartNames.ToArray();'
    $returnPos=$method.LastIndexOf($returnToken)
    if($returnPos -lt 0){ throw 'C10.42 controller preflight: final imported-parts return missing.' }
    $returnNew=@'
                asterMaxCadImportWatch.Stop();
                if (asterMaxTopLevelCadImport)
                    _form.WriteDataToOutput("AsterMax CAD import: " + allAddedPartNames.Count +
                        " pieza(s) preparadas en " + asterMaxCadImportWatch.ElapsedMilliseconds +
                        " ms. Visualización final diferida hasta completar el conjunto.");
                return allAddedPartNames.ToArray();
'@
    $method=$method.Substring(0,$returnPos)+$returnNew.TrimEnd()+$method.Substring($returnPos+$returnToken.Length)

    # The final brace is still the original method brace. Close try/finally immediately before it.
    $lastBrace=$method.LastIndexOf('}')
    $finish=@'

            }
            finally
            {
                _asterMaxCadImportDepth--;
            }
'@
    $method=$method.Substring(0,$lastBrace)+$finish+$method.Substring($lastBrace)
    $c=$c.Substring(0,$start)+$method+$c.Substring($end+1)
}

# Suppress nested redraw/tree regeneration from ImportBrepCompoundPart.
$compoundSig='        private void ImportBrepCompoundPart('
$compoundStart=$c.IndexOf($compoundSig)
if($compoundStart -lt 0){ throw 'C10.42 controller preflight: ImportBrepCompoundPart missing.' }
$compoundBrace=$c.IndexOf('{',$compoundStart)
$depth=0; $compoundEnd=-1
for($n=$compoundBrace; $n -lt $c.Length; $n++){
    if($c[$n] -eq '{'){ $depth++ }
    elseif($c[$n] -eq '}'){
        $depth--
        if($depth -eq 0){ $compoundEnd=$n; break }
    }
}
if($compoundEnd -lt 0){ throw 'C10.42 controller preflight: compound closing brace missing.' }
$compound=$c.Substring($compoundStart,$compoundEnd-$compoundStart+1)
if(-not $compound.Contains('if (_asterMaxCadImportDepth == 0)')){
    $rx='(?m)^(\s*)UpdateAfterImport\("\.brep"\);'
    if(-not [regex]::IsMatch($compound,$rx)){ throw 'C10.42 controller preflight: compound update call missing.' }
    $compound=[regex]::Replace($compound,$rx,'$1if (_asterMaxCadImportDepth == 0)' + "`n" + '$1    UpdateAfterImport(".brep");',1)
    $c=$c.Substring(0,$compoundStart)+$compound+$c.Substring($compoundEnd+1)
}

# Large assembly display policy: inject immediately before the geometry branch's
# DrawGeometry call, independent of surrounding C10.41 formatting.
if(-not $c.Contains('ASTERMAX_LARGE_ASSEMBLY_PARTS')){
    $updateSig='        private void UpdateAfterImport(string extension)'
    $updateStart=$c.IndexOf($updateSig)
    if($updateStart -lt 0){ throw 'C10.42 controller preflight: UpdateAfterImport missing.' }
    $updateBrace=$c.IndexOf('{',$updateStart)
    $depth=0; $updateEnd=-1
    for($n=$updateBrace; $n -lt $c.Length; $n++){
        if($c[$n] -eq '{'){ $depth++ }
        elseif($c[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $updateEnd=$n; break }
        }
    }
    if($updateEnd -lt 0){ throw 'C10.42 controller preflight: UpdateAfterImport closing brace missing.' }
    $method=$c.Substring($updateStart,$updateEnd-$updateStart+1)
    $draw='                DrawGeometry(false);'
    $drawPos=$method.IndexOf($draw)
    if($drawPos -lt 0){ throw 'C10.42 controller preflight: geometry DrawGeometry call missing.' }
    $policy=@'
                // Keep the CAD/BREP exact; only simplify the initial graphics path.
                int asterMaxLargeAssemblyThreshold = 80;
                string asterMaxThresholdText = Environment.GetEnvironmentVariable("ASTERMAX_LARGE_ASSEMBLY_PARTS");
                int asterMaxConfiguredThreshold;
                if (!String.IsNullOrWhiteSpace(asterMaxThresholdText) &&
                    Int32.TryParse(asterMaxThresholdText, out asterMaxConfiguredThreshold) &&
                    asterMaxConfiguredThreshold > 1)
                    asterMaxLargeAssemblyThreshold = asterMaxConfiguredThreshold;

                int asterMaxGeometryPartCount = (_model != null && _model.Geometry != null && _model.Geometry.Parts != null)
                    ? _model.Geometry.Parts.Count : 0;
                if (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold)
                    CurrentEdgesVisibility = vtkEdgesVisibility.NoEdges;

                if (_asterMaxCadImportDepth == 0)
                    _form.WriteDataToOutput("AsterMax visualización CAD: " + asterMaxGeometryPartCount +
                        " pieza(s); render inicial " +
                        (asterMaxGeometryPartCount >= asterMaxLargeAssemblyThreshold ? "sin aristas." : "normal."));
'@
    $method=$method.Substring(0,$drawPos)+$policy.TrimEnd()+"`n"+$method.Substring($drawPos)
    $c=$c.Substring(0,$updateStart)+$method+$c.Substring($updateEnd+1)
}

Set-Content $controllerPath $c -Encoding UTF8
Write-Host 'C10.42 controller structural preflight applied.' -ForegroundColor Green
