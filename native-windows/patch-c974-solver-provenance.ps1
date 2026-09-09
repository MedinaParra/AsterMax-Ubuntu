param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$viewport=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.74.'}
if(!(Test-Path $viewport)){throw 'C9.67 VTK binding must exist before C9.74.'}

$s=Get-Content $workspace -Raw
if(-not $s.Contains('using System.Security.Cryptography;')){
  $s=$s.Replace('using System.Linq;','using System.Linq;'+[Environment]::NewLine+'using System.Security.Cryptography;')
}
if(-not $s.Contains('public string SourceKind { get; private set; }')){
  $anchor='        public string StressUnit { get; private set; }'
  $insert=@'
        public string StressUnit { get; private set; }
        public string SourceKind { get; private set; }
        public string SourceName { get; private set; }
        public string ElementType { get; private set; }
        public string BundleSha256 { get; private set; }
        public bool DerivedNodalStressDeclared { get; private set; }
'@
  if(-not $s.Contains($anchor)){throw 'C9.74 property anchor missing.'}
  $s=$s.Replace($anchor,$insert)
}

$loadAnchor='            b.StressUnit = (string)root["units"]["stress"];'
if(-not $s.Contains('b.SourceKind = (string)root["source"]?["kind"];')){
  $loadInsert=@'
            b.StressUnit = (string)root["units"]["stress"];
            b.SourceKind = (string)root["source"]?["kind"];
            b.SourceName = (string)root["source"]?["file"];
            b.ElementType = (string)root["mesh"]?["element_type"];
            b.DerivedNodalStressDeclared = (bool?)root["integrity"]?["derived_nodal_stress_average_declared"] == true;
            using (var sha = SHA256.Create())
                b.BundleSha256 = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant();
'@
  if(-not $s.Contains($loadAnchor)){throw 'C9.74 load anchor missing.'}
  $s=$s.Replace($loadAnchor,$loadInsert)
}

$validateAnchor='            if (LengthUnit != "mm" || StressUnit != "MPa")'
if(-not $s.Contains('SourceKind != "REAL_CODE_ASTER_MED"')){
  $validation=@'
            if (SourceKind != "REAL_CODE_ASTER_MED")
                throw new InvalidDataException("C9.74 provenance gate requires source.kind=REAL_CODE_ASTER_MED.");
            if (String.IsNullOrWhiteSpace(SourceName))
                throw new InvalidDataException("C9.74 provenance gate requires the original MED source filename.");
            if (ElementType != "HEXA8")
                throw new InvalidDataException("C9.74 PMV currently validates the proven HEXA8 result route only.");
            if (!DerivedNodalStressDeclared)
                throw new InvalidDataException("C9.74 requires explicit declaration of nodal stress averaging provenance.");
            if (String.IsNullOrWhiteSpace(BundleSha256) || BundleSha256.Length != 64)
                throw new InvalidDataException("C9.74 could not fingerprint the result bundle.");
            if (LengthUnit != "mm" || StressUnit != "MPa")
'@
  if(-not $s.Contains($validateAnchor)){throw 'C9.74 validation anchor missing.'}
  $s=$s.Replace($validateAnchor,$validation)
}

if(-not $s.Contains('public string ProvenanceSummary()')){
  $anchor='        public string Describe(string field)'
  $method=@'
        public string ProvenanceSummary()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | {1} | {2} nodes / {3} {4} | mm/N/MPa | SHA256 {5}",
                SourceKind, SourceName, NodeCount, ElementCount, ElementType, BundleSha256);
        }

        public string Describe(string field)
'@
  if(-not $s.Contains($anchor)){throw 'C9.74 provenance method anchor missing.'}
  $s=$s.Replace($anchor,$method)
}
Set-Content $workspace $s -Encoding UTF8

$v=Get-Content $viewport -Raw
$old='Text="SOURCE: real Code_Aster results bundle\r\nSynthetic FEA values: rejected"'
$new='Text="SOURCE: "+bundle.SourceKind+"\r\nSHA256: "+bundle.BundleSha256.Substring(0,12)+"…"'
if($v.Contains($old)){$v=$v.Replace($old,$new)}
$oldStatus='_status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" HEXA8";'
$newStatus='_status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" "+_bundle.ElementType+" • verified provenance";'
if($v.Contains($oldStatus)){$v=$v.Replace($oldStatus,$newStatus)}
Set-Content $viewport $v -Encoding UTF8

Write-Host 'C9.74 solver provenance + SHA256 audit trail injected.' -ForegroundColor Green
