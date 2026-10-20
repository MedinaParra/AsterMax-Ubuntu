param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'CaeModel/FileInOut/Input/VisFileReader/VisFileReader.cs'
if(!(Test-Path $path)){throw "C10.86 missing: $path"}
$c=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")

# Runtime evidence from the exact failing STEP proves that NetGen VIS edge
# records may be numeric-first (legacy) or descriptor-first (Line, Circle,
# BSplineCurve, and potentially other curve kinds). The descriptor is metadata;
# the first integer token is the edge id and the remaining integer tokens are
# node ids. Detect that grammar structurally instead of maintaining a curve-name
# allow-list. Integer fields remain strict once their start position is found.
$sig='private static int ReadEdges('
$methodStart=$c.IndexOf($sig)
if($methodStart -lt 0){throw 'C10.86 ReadEdges signature missing.'}
$brace=$c.IndexOf('{',$methodStart)
if($brace -lt 0){throw 'C10.86 ReadEdges opening brace missing.'}
$depth=0; $methodEnd=-1
for($n=$brace; $n -lt $c.Length; $n++){
    if($c[$n] -eq '{'){$depth++}
    elseif($c[$n] -eq '}'){
        $depth--
        if($depth -eq 0){$methodEnd=$n+1; break}
    }
}
if($methodEnd -lt 0){throw 'C10.86 ReadEdges closing brace missing.'}
$segment=$c.Substring($methodStart,$methodEnd-$methodStart)
$before=$segment

# VIS records are whitespace-delimited; accept space/tab/CR/LF.
$pattern='allIds\s*=\s*data\[i\]\.Split\([^;]+;'
$replacement="allIds = data[i].Split(new char[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);"
$matches=[regex]::Matches($segment,$pattern)
if($matches.Count -ne 1){throw "C10.86 expected exactly one ReadEdges Split assignment, found $($matches.Count)."}
$segment=[regex]::Replace($segment,$pattern,$replacement,1)

# NetGen VIS compatibility: find the first strict integer token. Legacy records
# start at zero; descriptor-first records start later. Initialize parsedEdgeId so
# the C# definite-assignment analysis remains valid after the guarded scan.
$old='edgeId = int.Parse(allIds[0]);'
$new=@'
                int firstIdIndex = 0;
                int parsedEdgeId = 0;
                while (firstIdIndex < allIds.Length &&
                       !Int32.TryParse(allIds[firstIdIndex], System.Globalization.NumberStyles.Integer,
                                       System.Globalization.CultureInfo.InvariantCulture, out parsedEdgeId))
                    firstIdIndex++;
                if (firstIdIndex >= allIds.Length || allIds.Length <= firstIdIndex + 1)
                    throw new FormatException("ASTERMAX_VIS_EDGE_RECORD no numeric edge grammar=[" + data[i] + "]");
                edgeId = parsedEdgeId;
'@
if(-not $segment.Contains($old)){throw 'C10.86 edgeId grammar anchor missing.'}
$segment=$segment.Replace($old,$new.TrimEnd())
$oldLoop='for (int j = 1; j < allIds.Length - 1; j++)'
$newLoop='for (int j = firstIdIndex + 1; j < allIds.Length - 1; j++)'
if(-not $segment.Contains($oldLoop)){throw 'C10.86 edge node loop anchor missing.'}
$segment=$segment.Replace($oldLoop,$newLoop)
$oldFirst='if (j == 1) vertexNodeIds.Add(nodeIds[0]);'
$newFirst='if (j == firstIdIndex + 1) vertexNodeIds.Add(nodeIds[0]);'
if(-not $segment.Contains($oldFirst)){throw 'C10.86 first vertex anchor missing.'}
$segment=$segment.Replace($oldFirst,$newFirst)

# Keep precise diagnostics for genuinely invalid numeric node fields.
$segment=$segment.Replace('Int32.Parse(', 'AsterMaxParseVisEdgeInt32(')
$segment=$segment.Replace('int.Parse(', 'AsterMaxParseVisEdgeInt32(')
if($segment -eq $before){throw 'C10.86 ReadEdges was not modified.'}

$helper=@'
        // C10.86: strict VIS edge integer parser with exact-token diagnostics.
        private static int AsterMaxParseVisEdgeInt32(string token)
        {
            try
            {
                return Int32.Parse(token, System.Globalization.NumberStyles.Integer,
                                   System.Globalization.CultureInfo.InvariantCulture);
            }
            catch (FormatException ex)
            {
                string safe = token == null ? "<null>" : token.Replace("\r", "\\r").Replace("\n", "\\n").Replace("\t", "\\t");
                throw new FormatException("ASTERMAX_VIS_EDGE_INT32 token=[" + safe + "] length=" + (token == null ? -1 : token.Length), ex);
            }
        }

'@
$c=$c.Substring(0,$methodStart)+$helper+$segment+$c.Substring($methodEnd)
Set-Content $path $c -Encoding UTF8
Write-Host 'C10.86: repaired descriptor-first NetGen VIS edge grammar generically; legacy numeric-first compatibility retained.' -ForegroundColor Green
