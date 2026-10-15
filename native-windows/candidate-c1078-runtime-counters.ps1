param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.cs'
foreach($p in @($controllerPath,$vtkPath)){if(!(Test-Path $p)){throw "C10.78 missing: $p"}}
$c=[regex]::Replace((Get-Content $controllerPath -Raw),'\r\n?',"`n")
$v=[regex]::Replace((Get-Content $vtkPath -Raw),'\r\n?',"`n")
if(!$c.Contains('_asterMaxCadImportDepth')){throw 'C10.78 requires C10.42 CAD transaction.'}
if(!$v.Contains('_asterMaxRenderScheduled')){throw 'C10.78 requires C10.42 render coalescing.'}
# Diagnostic-only import transaction markers. No control-flow or graphics behavior is changed.
$importAnchor='            bool asterMaxTopLevelCadImport = _asterMaxCadImportDepth == 0;'
if(!$c.Contains('ASTERMAX_PERF_IMPORT')){
 if(!$c.Contains($importAnchor)){throw 'C10.78 import anchor missing.'}
 $c=$c.Replace($importAnchor,$importAnchor+"`n            if (asterMaxTopLevelCadImport && Environment.GetEnvironmentVariable(\"ASTERMAX_PERF_TRACE\") == \"1\") _form.WriteDataToOutput(\"ASTERMAX_PERF_IMPORT begin\");")
 $endAnchor='                if (asterMaxTopLevelCadImport)'
 $endPos=$c.IndexOf($endAnchor,$c.IndexOf('asterMaxCadImportWatch.Stop();'))
 if($endPos -lt 0){throw 'C10.78 import end anchor missing.'}
 $c=$c.Insert($endPos,'                if (asterMaxTopLevelCadImport && Environment.GetEnvironmentVariable("ASTERMAX_PERF_TRACE") == "1") _form.WriteDataToOutput("ASTERMAX_PERF_IMPORT end parts=" + allAddedPartNames.Count);'+"`n")
}
# vtkControl counters count requests/actors; they intentionally do not alter scheduling.
$fieldAnchor='        private bool _asterMaxRenderScheduled;'
if(!$v.Contains('ASTERMAX_PERF_RENDER')){
 if(!$v.Contains($fieldAnchor)){throw 'C10.78 render field anchor missing.'}
 $fields=@'
        private long _asterMaxPerfRenderRequests;
        private long _asterMaxPerfActorAdds;
        private bool AsterMaxPerfTraceEnabled { get { return Environment.GetEnvironmentVariable("ASTERMAX_PERF_TRACE") == "1"; } }
        private void AsterMaxPerfTrace(string text) { if (AsterMaxPerfTraceEnabled) System.Diagnostics.Trace.WriteLine(text); }
'@
 $v=$v.Replace($fieldAnchor,$fieldAnchor+"`n"+$fields.TrimEnd())
 $renderSig='        private void RenderSceene()'
 $renderBrace=$v.IndexOf('{',$v.IndexOf($renderSig)); if($renderBrace -lt 0){throw 'C10.78 RenderSceene anchor missing.'}
 $v=$v.Insert($renderBrace+1,"`n            _asterMaxPerfRenderRequests++;`n            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace(\"ASTERMAX_PERF_RENDER request=\" + _asterMaxPerfRenderRequests + \" scheduled=\" + _asterMaxRenderScheduled + \" active=\" + _asterMaxRenderRequestActive); ")
}
if(!$v.Contains('ASTERMAX_PERF_ACTOR')){
 $actorSig='        public void AddActorGeometry('
 $actorStart=$v.IndexOf($actorSig)
 if($actorStart -lt 0){$actorSig='        private void AddActorGeometry('; $actorStart=$v.IndexOf($actorSig)}
 if($actorStart -lt 0){throw 'C10.78 AddActorGeometry method anchor missing.'}
 $actorBrace=$v.IndexOf('{',$actorStart); if($actorBrace -lt 0){throw 'C10.78 AddActorGeometry brace missing.'}
 $v=$v.Insert($actorBrace+1,"`n            _asterMaxPerfActorAdds++;`n            if (AsterMaxPerfTraceEnabled) AsterMaxPerfTrace(\"ASTERMAX_PERF_ACTOR add=\" + _asterMaxPerfActorAdds); ")
}
Set-Content $controllerPath $c -Encoding UTF8
Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.78 diagnostic-only runtime counters applied; rendering semantics unchanged.' -ForegroundColor Green
