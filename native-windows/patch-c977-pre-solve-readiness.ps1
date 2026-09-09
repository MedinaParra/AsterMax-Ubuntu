param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.77.'}
$s=Get-Content $workspace -Raw
if(-not $s.Contains('internal sealed class AsterMaxPreSolveReadiness')){
$anchor='    public partial class FrmMain'
$code=@'
    internal sealed class AsterMaxPreSolveReadiness
    {
        public string Status { get; private set; }
        public string ModelFingerprintSha256 { get; private set; }
        public int NodeCount { get; private set; }
        public int ElementCount { get; private set; }
        public int UnsupportedElementCount { get; private set; }
        public int MissingNodeReferenceCount { get; private set; }
        public int DegenerateConnectivityCount { get; private set; }
        public int MaterialCount { get; private set; }
        public int StepCount { get; private set; }
        public int BoundaryConditionCount { get; private set; }
        public int LoadCount { get; private set; }
        public List<string> Issues { get; private set; }

        private AsterMaxPreSolveReadiness()
        {
            Issues = new List<string>();
            Status = "BLOCKED";
        }

        public static AsterMaxPreSolveReadiness Evaluate(CaeModel.FeModel model)
        {
            var r = new AsterMaxPreSolveReadiness();
            if (model == null) { r.Issues.Add("BLOCK:model_missing"); return r; }

            try
            {
                var fp = AsterMaxModelFingerprint.Extract(model);
                r.ModelFingerprintSha256 = fp.Sha256;
            }
            catch (Exception ex)
            {
                r.Issues.Add("BLOCK:unit_or_fingerprint_contract:" + ex.Message);
                return r;
            }

            if (model.Mesh == null)
            {
                r.Issues.Add("BLOCK:mesh_missing");
                return r;
            }

            r.NodeCount = model.Mesh.Nodes == null ? 0 : model.Mesh.Nodes.Count;
            r.ElementCount = model.Mesh.Elements == null ? 0 : model.Mesh.Elements.Count;
            if (r.NodeCount == 0) r.Issues.Add("BLOCK:mesh_has_no_nodes");
            if (r.ElementCount == 0) r.Issues.Add("BLOCK:mesh_has_no_elements");

            if (model.Mesh.Elements != null)
            {
                foreach (var kv in model.Mesh.Elements)
                {
                    var e = kv.Value;
                    if (!(e is CaeMesh.LinearHexaElement))
                    {
                        r.UnsupportedElementCount++;
                        continue;
                    }
                    if (e.NodeIds == null || e.NodeIds.Length != 8)
                    {
                        r.DegenerateConnectivityCount++;
                        continue;
                    }
                    if (e.NodeIds.Distinct().Count() != e.NodeIds.Length)
                        r.DegenerateConnectivityCount++;
                    foreach (int nodeId in e.NodeIds)
                        if (model.Mesh.Nodes == null || !model.Mesh.Nodes.ContainsKey(nodeId))
                            r.MissingNodeReferenceCount++;
                }
            }
            if (r.UnsupportedElementCount > 0)
                r.Issues.Add("BLOCK:unsupported_elements_for_current_code_aster_pmv=" + r.UnsupportedElementCount.ToString(CultureInfo.InvariantCulture));
            if (r.MissingNodeReferenceCount > 0)
                r.Issues.Add("BLOCK:element_node_references_missing=" + r.MissingNodeReferenceCount.ToString(CultureInfo.InvariantCulture));
            if (r.DegenerateConnectivityCount > 0)
                r.Issues.Add("BLOCK:degenerate_element_connectivity=" + r.DegenerateConnectivityCount.ToString(CultureInfo.InvariantCulture));

            r.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;
            if (r.MaterialCount == 0) r.Issues.Add("BLOCK:no_material_defined");

            if (model.StepCollection != null && model.StepCollection.StepsList != null)
            {
                r.StepCount = model.StepCollection.StepsList.Count;
                foreach (var step in model.StepCollection.StepsList)
                {
                    if (step.BoundaryConditions != null) r.BoundaryConditionCount += step.BoundaryConditions.Count;
                    if (step.Loads != null) r.LoadCount += step.Loads.Count;
                }
            }
            if (r.StepCount == 0) r.Issues.Add("BLOCK:no_analysis_step");
            if (r.BoundaryConditionCount == 0) r.Issues.Add("BLOCK:no_boundary_conditions");
            if (r.LoadCount == 0) r.Issues.Add("BLOCK:no_loads");

            // C9.77 deliberately does not invent geometric quality metrics. Jacobian/aspect/skewness
            // become separate gates only after validated algorithms exist for each supported element family.
            r.Status = r.Issues.Any(x => x.StartsWith("BLOCK:", StringComparison.Ordinal)) ? "BLOCKED" :
                       (r.Issues.Count > 0 ? "WARNING" : "READY");
            return r;
        }

        public string AuditSummary()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | {1} nodes / {2} HEXA8 elements | {3} materials | {4} steps | {5} BC / {6} loads | fingerprint {7} | issues {8}",
                Status, NodeCount, ElementCount, MaterialCount, StepCount, BoundaryConditionCount, LoadCount,
                String.IsNullOrEmpty(ModelFingerprintSha256) ? "none" : ModelFingerprintSha256.Substring(0, 12), Issues.Count);
        }
    }

    public partial class FrmMain
'@
if(-not $s.Contains($anchor)){throw 'C9.77 FrmMain anchor missing.'}
$s=$s.Replace($anchor,$code)
}
Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.77 engineering pre-solve readiness gate injected.' -ForegroundColor Green
