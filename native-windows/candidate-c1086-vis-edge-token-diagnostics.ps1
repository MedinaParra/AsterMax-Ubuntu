param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'CaeModel/FileInOut/Input/VisFileReader/VisFileReader.cs'
if(!(Test-Path $path)){throw "C10.86 missing: $path"}
$c=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")

# Runtime evidence from C10.85 proves FormatException -> ParseInt32 -> ReadEdges.
# Instrument only ReadEdges integer parsing; do not accept/repair malformed data.
$start=$c.IndexOf('ReadEdges(')
if($start -lt 0){throw 'C10.86 ReadEdges anchor missing.'}
$methodStart=$c.LastIndexOf('private', $start)
if($methodStart -lt 0){$methodStart=$c.LastIndexOf('static', $start)}
if($methodStart -lt 0){throw 'C10.86 ReadEdges method start missing.'}
$next=$c.IndexOf("`n        private", $start)
if($next -lt 0){$next=$c.IndexOf("`n        static", $start)}
if($next -lt 0){throw 'C10.86 next method anchor missing.'}
$segment=$c.Substring($methodStart,$next-$methodStart)
$before=$segment
$segment=$segment.Replace('Int32.Parse(', 'AsterMaxParseVisEdgeInt32(')
$segment=$segment.Replace('int.Parse(', 'AsterMaxParseVisEdgeInt32(')
if($segment -eq $before){throw 'C10.86 found no Int32.Parse/int.Parse inside ReadEdges.'}

$helper=@'
        // C10.86 diagnostic only: preserve Int32.Parse semantics while exposing
        // the exact VIS edge token that causes the proven FormatException.
        private static int AsterMaxParseVisEdgeInt32(string token)
        {
            try
            {
                return Int32.Parse(token);
            }
            catch (FormatException ex)
            {
                string safe = token == null ? "<null>" : token.Replace("\r", "\\r").Replace("\n", "\\n").Replace("\t", "\\t");
                throw new FormatException("ASTERMAX_VIS_EDGE_INT32 token=[" + safe + "] length=" + (token == null ? -1 : token.Length), ex);
            }
        }

'@
$c=$c.Substring(0,$methodStart)+$helper+$segment+$c.Substring($next)
Set-Content $path $c -Encoding UTF8
Write-Host 'C10.86: ReadEdges Int32 token diagnostics applied; parser acceptance semantics unchanged.' -ForegroundColor Green
