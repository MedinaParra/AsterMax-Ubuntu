param([string]$Root)
$ErrorActionPreference='Stop'
$path=Join-Path $Root 'CaeModel/FileInOut/Input/VisFileReader/VisFileReader.cs'
if(!(Test-Path $path)){throw "C10.86 missing: $path"}
$c=[regex]::Replace((Get-Content $path -Raw),"\r\n?","`n")

# Runtime evidence from C10.85 proves FormatException -> ParseInt32 -> ReadEdges.
# NetGen VIS edge records are whitespace-delimited. The upstream reader splits
# only on a literal ASCII space, so tabs/other whitespace remain attached to
# integer fields and Int32.Parse fails. Repair only ReadEdges tokenization;
# integer acceptance remains strict and malformed numeric data still fails.
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

# Split on the whitespace characters used by VIS records. Avoid the ambiguous
# Split(null, ...) overload so this compiles against the repository's .NET target.
$old='allIds = data[i].Split(spaceSplitter, StringSplitOptions.RemoveEmptyEntries);'
$new='allIds = data[i].Split(new char[] { '' '', ''\t'', ''\r'', ''\n'' }, StringSplitOptions.RemoveEmptyEntries);'
if(-not $segment.Contains($old)){throw 'C10.86 ReadEdges tokenization anchor missing.'}
$segment=$segment.Replace($old,$new)

# Keep precise diagnostics if a genuinely non-integer token is encountered.
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
$c=$c.Substring(0,$methodStart)+$helper+$segment+$c.Substring($next)
Set-Content $path $c -Encoding UTF8
Write-Host 'C10.86: repaired ReadEdges whitespace tokenization; strict Int32 diagnostics retained.' -ForegroundColor Green
