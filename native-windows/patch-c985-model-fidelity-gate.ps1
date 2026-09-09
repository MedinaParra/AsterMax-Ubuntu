param([string]$Root)
$ErrorActionPreference='Stop'
$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.85.'}
$s=Get-Content $workspace -Raw
if(-not $s.Contains('internal static class AsterMaxModelFidelityGate')){
$anchor='    public partial class FrmMain'
$code=@'
    internal static class AsterMaxModelFidelityGate
    {
        public static bool Verify(CaeModel.FeModel model, string expectedSha256)
        {
            if (model == null) throw new ArgumentNullException("model");
            if (String.IsNullOrWhiteSpace(expectedSha256)) throw new ArgumentException("Expected fingerprint is required.", "expectedSha256");
            var current=AsterMaxModelFingerprint.Extract(model);
            return String.Equals(current.Sha256, expectedSha256.Trim(), StringComparison.OrdinalIgnoreCase);
        }

        public static string Require(CaeModel.FeModel model, string expectedSha256)
        {
            var current=AsterMaxModelFingerprint.Extract(model);
            if (!String.Equals(current.Sha256, expectedSha256 == null ? null : expectedSha256.Trim(), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("MODEL FIDELITY BLOCKED: FeModel changed after the verified fingerprint was captured. Re-run readiness/export before Solve.");
            return current.Sha256;
        }
    }

    public partial class FrmMain
'@
if(-not $s.Contains($anchor)){throw 'C9.85 FrmMain anchor missing.'}
$s=$s.Replace($anchor,$code)
}
Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.85 native FeModel stale-model fidelity gate injected.' -ForegroundColor Green
