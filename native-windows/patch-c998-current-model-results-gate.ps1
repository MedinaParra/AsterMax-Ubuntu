param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.98.'}
$s=Get-Content $workspace -Raw

# Use a bundle-specific symbol. ModelFingerprintSha256 already exists in other C9.x
# support classes, so a global text probe on that generic name can produce a false hit.
if(-not $s.Contains('public string ResultModelFingerprintSha256 { get; private set; }')){
  $anchor='        public string StressUnit { get; private set; }'
  if(-not $s.Contains($anchor)){throw 'C9.98 results bundle property anchor missing.'}
  $s=$s.Replace($anchor,$anchor + [Environment]::NewLine + '        public string ResultModelFingerprintSha256 { get; private set; }')
}

if(-not $s.Contains('b.ResultModelFingerprintSha256 = ((string)root["integrity"]?["model_fingerprint_sha256"] ?? "").ToLowerInvariant();')){
  $anchor='            b.StressUnit = (string)root["units"]["stress"];'
  if(-not $s.Contains($anchor)){throw 'C9.98 results loader anchor missing.'}
  $s=$s.Replace($anchor,$anchor + [Environment]::NewLine + '            b.ResultModelFingerprintSha256 = ((string)root["integrity"]?["model_fingerprint_sha256"] ?? "").ToLowerInvariant();')
}

if(-not $s.Contains('C9.98 requires results bound to an AsterMax FeModel SHA-256 fingerprint.')){
  $anchor='            if (LengthUnit != "mm" || StressUnit != "MPa")'
  $code=@'
            if (String.IsNullOrWhiteSpace(ResultModelFingerprintSha256) || ResultModelFingerprintSha256.Length != 64 ||
                ResultModelFingerprintSha256.Any(c => !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))))
                throw new InvalidDataException("C9.98 requires results bound to an AsterMax FeModel SHA-256 fingerprint.");

'@
  if(-not $s.Contains($anchor)){throw 'C9.98 validation anchor missing.'}
  $s=$s.Replace($anchor,$code + $anchor)
}

if(-not $s.Contains('public void RequireCurrentModel(CaeModel.FeModel model)')){
  $anchor='        public string[] AvailableFields()'
  $code=@'
        public void RequireCurrentModel(CaeModel.FeModel model)
        {
            if (model == null)
                throw new InvalidDataException("No active FeModel is available for result identity validation.");
            var active = AsterMaxModelFingerprint.Extract(model);
            if (!String.Equals(ResultModelFingerprintSha256, active.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("STALE results rejected: result fingerprint does not match the active FeModel.");
            if (NodeCount != active.NodeCount || ElementCount != active.ElementCount)
                throw new InvalidDataException("STALE results rejected: result mesh counts do not match the active FeModel.");
        }

'@
  if(-not $s.Contains($anchor)){throw 'C9.98 field selector anchor missing.'}
  $s=$s.Replace($anchor,$code + $anchor)
}

$old='                    _asterMaxLoadedResults = AsterMaxResultsBundle.Load(dlg.FileName);'
$new=@'
                    _asterMaxLoadedResults = AsterMaxResultsBundle.Load(dlg.FileName);
                    _asterMaxLoadedResults.RequireCurrentModel(_controller == null ? null : _controller.Model);
'@
if($s.Contains($old) -and -not $s.Contains('_asterMaxLoadedResults.RequireCurrentModel(')){
  $s=$s.Replace($old,$new.TrimEnd())
}
if(-not $s.Contains('_asterMaxLoadedResults.RequireCurrentModel(')){throw 'C9.98 active-model result gate was not inserted.'}

Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.98 current FeModel <-> real results identity gate injected.' -ForegroundColor Green
