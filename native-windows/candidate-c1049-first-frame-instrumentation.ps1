param([string]$Root)
$ErrorActionPreference='Stop'

$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
foreach($p in @($vtkPath)){ if(!(Test-Path $p)){ throw "C10.49 missing: $p" } }

function Normalize-Lf([string]$text){ return [regex]::Replace($text,"\r\n?","`n") }
function Replace-CSharpMethod([string]$text,[string]$signature,[scriptblock]$transform){
    $start=$text.IndexOf($signature)
    if($start -lt 0){ throw "C10.49 method missing: $signature" }
    $brace=$text.IndexOf('{',$start)
    if($brace -lt 0){ throw "C10.49 opening brace missing: $signature" }
    $depth=0; $end=-1
    for($n=$brace; $n -lt $text.Length; $n++){
        if($text[$n] -eq '{'){ $depth++ }
        elseif($text[$n] -eq '}'){
            $depth--
            if($depth -eq 0){ $end=$n+1; break }
        }
    }
    if($end -lt 0){ throw "C10.49 closing brace missing: $signature" }
    $existing=$text.Substring($start,$end-$start)
    $replacement=& $transform $existing
    return $text.Substring(0,$start)+$replacement.TrimEnd()+$text.Substring($end)
}

$v=Normalize-Lf (Get-Content $vtkPath -Raw)
$fieldAnchor='        private long _asterMaxSceneBatchCameraFlushes;'
if(-not $v.Contains('_asterMaxSceneBatchAddCells')){
    if(-not $v.Contains($fieldAnchor)){ throw 'C10.49 C10.47 telemetry anchor missing.' }
    $fields=@'
        private long _asterMaxSceneBatchCameraFlushes;
        private long _asterMaxSceneBatchAddCells;
        private long _asterMaxSceneBatchRenderRequests;
        private long _asterMaxSceneBatchStartedUtcTicks;
        private long _asterMaxSceneBatchEndedUtcTicks;
'@
    $v=$v.Replace($fieldAnchor,$fields.TrimEnd())
}

$apiAnchor='        public int AsterMaxSceneBatchDepth { get { return _asterMaxSceneBatchDepth; } }'
if(-not $v.Contains('AsterMaxSceneBatchAddCells {')){
    if(-not $v.Contains($apiAnchor)){ throw 'C10.49 scene-batch API anchor missing.' }
    $api=@'
        public int AsterMaxSceneBatchDepth { get { return _asterMaxSceneBatchDepth; } }
        public long AsterMaxSceneBatchAddCells { get { return _asterMaxSceneBatchAddCells; } }
        public long AsterMaxSceneBatchRenderRequests { get { return _asterMaxSceneBatchRenderRequests; } }
        public long AsterMaxSceneBatchStartedUtcTicks { get { return _asterMaxSceneBatchStartedUtcTicks; } }
        public long AsterMaxSceneBatchEndedUtcTicks { get { return _asterMaxSceneBatchEndedUtcTicks; } }
'@
    $v=$v.Replace($apiAnchor,$api.TrimEnd())
}

if(-not $v.Contains('_asterMaxSceneBatchStartedUtcTicks = DateTime.UtcNow.Ticks;')){
    $v=Replace-CSharpMethod $v '        public void AsterMaxBeginSceneBatch()' {
        param($existing)
        $anchor='                _asterMaxSceneBatchCameraFlushes = 0;'
        if(-not $existing.Contains($anchor)){ throw 'C10.49 begin-batch reset anchor missing.' }
        $extra=$anchor+"`n"+
               '                _asterMaxSceneBatchAddCells = 0;'+"`n"+
               '                _asterMaxSceneBatchRenderRequests = 0;'+"`n"+
               '                _asterMaxSceneBatchStartedUtcTicks = DateTime.UtcNow.Ticks;'+"`n"+
               '                _asterMaxSceneBatchEndedUtcTicks = 0;'
        return $existing.Replace($anchor,$extra)
    }
}

if(-not $v.Contains('_asterMaxSceneBatchEndedUtcTicks = DateTime.UtcNow.Ticks;')){
    $v=Replace-CSharpMethod $v '        public void AsterMaxEndSceneBatch()' {
        param($existing)
        $anchor='            _asterMaxSceneBatchDepth--;'
        if(-not $existing.Contains($anchor)){ throw 'C10.49 end-batch depth anchor missing.' }
        $replacement=$anchor+"`n"+
                     '            if (_asterMaxSceneBatchDepth == 0)'+"`n"+
                     '                _asterMaxSceneBatchEndedUtcTicks = DateTime.UtcNow.Ticks;'
        return $existing.Replace($anchor,$replacement)
    }
}

if(-not $v.Contains('_asterMaxSceneBatchAddCells++;')){
    $v=Replace-CSharpMethod $v '        public void AddCells(vtkMaxActorData data)' {
        param($existing)
        $brace=$existing.IndexOf('{')
        if($brace -lt 0){ throw 'C10.49 AddCells opening brace missing.' }
        $insert="`n            if (_asterMaxSceneBatchDepth > 0) _asterMaxSceneBatchAddCells++;"
        return $existing.Insert($brace+1,$insert)
    }
}

# Count requested scene flushes at the same semantic point where C10.47 performs
# its single camera/redraw flush. This is deliberately not a claimed GPU-render
# count; it is a first-frame scene-flush request counter.
if(-not $v.Contains('_asterMaxSceneBatchRenderRequests++;')){
    $v=Replace-CSharpMethod $v '        public void AsterMaxEndSceneBatch()' {
        param($existing)
        $anchor='                _asterMaxSceneBatchCameraFlushes++;'
        if(-not $existing.Contains($anchor)){ throw 'C10.49 camera-flush telemetry anchor missing.' }
        return $existing.Replace($anchor,$anchor+"`n                _asterMaxSceneBatchRenderRequests++;")
    }
}

Set-Content $vtkPath $v -Encoding UTF8
Write-Host 'C10.49: first-frame scene instrumentation added (AddCells, flush requests, UTC batch interval).' -ForegroundColor Green
