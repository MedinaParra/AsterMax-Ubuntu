param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'CaeModel/FileInOut/Input/VisFileReader/VisFileReader.cs'
if(!(Test-Path $path)){throw "C10.86 missing: $path"}
$c=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")

# Runtime evidence from C10.85 proves FormatException -> ParseInt32 -> ReadEdges.
# Locate ReadEdges structurally and repair only its tokenizer. This avoids a
# fragile exact-line dependency on earlier patches while preserving strict ints.
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

# Match the assignment structurally rather than requiring the original line.
$pattern='allIds\s*=\s*data\[i\]\.Split\([^;]+;'
$replacement="allIds = data[i].Split(new char[] { ' ', '\t', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);"
$matches=[regex]::Matches($segment,$pattern)
if($matches.Count -ne 1){throw "C10.86 expected exactly one ReadEdges Split assignment, found $($matches.Count)."}
$segment=[regex]::Replace($segment,$pattern,$replacement,1)

# Keep precise diagnostics if a genuinely non-integer edge token is encountered.
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
Write-Host 'C10.86: structurally repaired ReadEdges whitespace tokenization; strict Int32 diagnostics retained.' -ForegroundColor Green
