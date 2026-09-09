param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.75.'}

$s=Get-Content $workspace -Raw
if(-not $s.Contains('internal sealed class AsterMaxAnalysisManifest')){
$anchor='    public partial class FrmMain'
$code=@'
    internal sealed class AsterMaxAnalysisManifest
    {
        public string ManifestFile { get; private set; }
        public string AnalysisId { get; private set; }
        public string ManifestSha256 { get; private set; }
        public string CadFile { get; private set; }
        public string MeshFile { get; private set; }
        public string SolverInputFile { get; private set; }
        public string MedFile { get; private set; }
        public string ResultsBundleFile { get; private set; }
        public string MaterialName { get; private set; }
        public string CodeAsterVersion { get; private set; }
        public int BoundaryConditionCount { get; private set; }
        public int LoadCount { get; private set; }

        public static AsterMaxAnalysisManifest Load(string path)
        {
            JObject root = JObject.Parse(File.ReadAllText(path));
            if ((string)root["schema"] != "astermax-analysis-provenance/v0")
                throw new InvalidDataException("Unsupported AsterMax analysis provenance schema.");
            if ((bool?)root["integrity"]?["fea_values_invented"] != false)
                throw new InvalidDataException("Analysis provenance rejects synthetic FEA values.");
            if ((string)root["units"]?["length"] != "mm" ||
                (string)root["units"]?["force"] != "N" ||
                (string)root["units"]?["stress"] != "MPa")
                throw new InvalidDataException("C9.75 requires the verified mm / N / MPa unit contract.");

            var m = new AsterMaxAnalysisManifest();
            m.ManifestFile = Path.GetFullPath(path);
            m.AnalysisId = (string)root["analysis_id"];
            m.MaterialName = (string)root["material"]?["name"];
            m.CodeAsterVersion = (string)root["solver"]?["code_aster_version"];
            m.BoundaryConditionCount = root["boundary_conditions"] == null ? 0 : root["boundary_conditions"].Count();
            m.LoadCount = root["loads"] == null ? 0 : root["loads"].Count();
            if (String.IsNullOrWhiteSpace(m.AnalysisId)) throw new InvalidDataException("analysis_id is required.");
            if (String.IsNullOrWhiteSpace(m.MaterialName)) throw new InvalidDataException("material.name is required.");
            if (String.IsNullOrWhiteSpace(m.CodeAsterVersion)) throw new InvalidDataException("solver.code_aster_version is required.");
            if (m.BoundaryConditionCount < 1) throw new InvalidDataException("At least one boundary condition is required.");
            if (m.LoadCount < 1) throw new InvalidDataException("At least one load is required.");

            string dir = Path.GetDirectoryName(m.ManifestFile);
            m.CadFile = VerifyArtifact(dir, root["cad"], "STEP CAD", "file", "sha256");
            if ((string)root["cad"]?["declared_length_unit"] != "mm")
                throw new InvalidDataException("STEP CAD must be explicitly declared in mm.");
            m.MeshFile = VerifyArtifact(dir, root["mesh"], "mesh", "file", "sha256");
            m.SolverInputFile = VerifyArtifact(dir, root["solver"], "Code_Aster input", "input_file", "input_sha256");
            m.MedFile = VerifyArtifact(dir, root["results"], "Code_Aster MED", "med_file", "med_sha256");
            m.ResultsBundleFile = VerifyArtifact(dir, root["results"], "results bundle", "bundle_file", "bundle_sha256");

            if ((string)root["mesh"]?["element_type"] != "HEXA8")
                throw new InvalidDataException("C9.75 PMV provenance currently admits the validated HEXA8 route only.");
            if ((int?)root["mesh"]?["node_count"] <= 0 || (int?)root["mesh"]?["element_count"] <= 0)
                throw new InvalidDataException("Mesh provenance requires positive node and element counts.");

            using (var sha = SHA256.Create())
                m.ManifestSha256 = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(m.ManifestFile))).Replace("-", "").ToLowerInvariant();
            return m;
        }

        private static string VerifyArtifact(string manifestDir, JToken section, string label, string fileKey, string hashKey)
        {
            string rel = (string)section?[fileKey];
            string expected = ((string)section?[hashKey] ?? "").ToLowerInvariant();
            if (String.IsNullOrWhiteSpace(rel) || expected.Length != 64)
                throw new InvalidDataException(label + " provenance is incomplete.");
            string full = Path.GetFullPath(Path.Combine(manifestDir, rel));
            if (!File.Exists(full)) throw new FileNotFoundException(label + " artifact missing.", full);
            string actual;
            using (var sha = SHA256.Create())
                actual = BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(full))).Replace("-", "").ToLowerInvariant();
            if (!String.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(label + " SHA-256 mismatch.");
            return full;
        }

        public string AuditSummary()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | STEP(mm) -> mesh -> {1} -> {2} BC / {3} loads -> Code_Aster {4} -> MED -> bundle | manifest SHA256 {5}",
                AnalysisId, MaterialName, BoundaryConditionCount, LoadCount, CodeAsterVersion, ManifestSha256);
        }
    }

    public partial class FrmMain
'@
if(-not $s.Contains($anchor)){throw 'C9.75 FrmMain anchor missing.'}
$s=$s.Replace($anchor,$code)
}
Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.75 analysis provenance manifest + full digital-thread hash gates injected.' -ForegroundColor Green
