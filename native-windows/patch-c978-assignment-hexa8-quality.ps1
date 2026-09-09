param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.78.'}
$s=Get-Content $workspace -Raw
if(-not $s.Contains('internal sealed class AsterMaxAssignmentQualityGate')){
$anchor='    public partial class FrmMain'
$code=@'
    internal sealed class AsterMaxAssignmentQualityGate
    {
        public string Status { get; private set; }
        public int SectionCount { get; private set; }
        public int AssignedElementCount { get; private set; }
        public int UnassignedElementCount { get; private set; }
        public int MultiplyAssignedElementCount { get; private set; }
        public int MissingMaterialReferenceCount { get; private set; }
        public int MissingSectionRegionCount { get; private set; }
        public int NonPositiveCenterJacobianCount { get; private set; }
        public double MinimumCenterJacobian { get; private set; }
        public List<string> Issues { get; private set; }

        private AsterMaxAssignmentQualityGate()
        {
            Status = "BLOCKED";
            Issues = new List<string>();
            MinimumCenterJacobian = Double.PositiveInfinity;
        }

        public static AsterMaxAssignmentQualityGate Evaluate(CaeModel.FeModel model)
        {
            var r = new AsterMaxAssignmentQualityGate();
            if (model == null || model.Mesh == null || model.Mesh.Elements == null)
            {
                r.Issues.Add("BLOCK:model_or_mesh_missing");
                return r;
            }

            var assignmentCounts = new Dictionary<int, int>();
            if (model.Sections != null)
            {
                r.SectionCount = model.Sections.Count;
                foreach (var kv in model.Sections)
                {
                    var section = kv.Value;
                    if (section == null) continue;
                    if (String.IsNullOrWhiteSpace(section.MaterialName) || model.Materials == null || !model.Materials.ContainsKey(section.MaterialName))
                    {
                        r.MissingMaterialReferenceCount++;
                        continue;
                    }
                    if (section.RegionType != CaeGlobals.RegionTypeEnum.ElementSetName ||
                        model.Mesh.ElementSets == null || String.IsNullOrWhiteSpace(section.RegionName) ||
                        !model.Mesh.ElementSets.ContainsKey(section.RegionName))
                    {
                        r.MissingSectionRegionCount++;
                        continue;
                    }
                    var set = model.Mesh.ElementSets[section.RegionName];
                    if (set == null || set.Labels == null)
                    {
                        r.MissingSectionRegionCount++;
                        continue;
                    }
                    foreach (int id in set.Labels)
                    {
                        if (!model.Mesh.Elements.ContainsKey(id))
                        {
                            r.MissingSectionRegionCount++;
                            continue;
                        }
                        int count;
                        assignmentCounts.TryGetValue(id, out count);
                        assignmentCounts[id] = count + 1;
                    }
                }
            }

            r.AssignedElementCount = assignmentCounts.Count;
            r.MultiplyAssignedElementCount = assignmentCounts.Count(x => x.Value > 1);
            r.UnassignedElementCount = model.Mesh.Elements.Keys.Count(id => !assignmentCounts.ContainsKey(id));
            if (r.SectionCount == 0) r.Issues.Add("BLOCK:no_sections_defined");
            if (r.MissingMaterialReferenceCount > 0) r.Issues.Add("BLOCK:section_material_reference_missing=" + r.MissingMaterialReferenceCount.ToString(CultureInfo.InvariantCulture));
            if (r.MissingSectionRegionCount > 0) r.Issues.Add("BLOCK:section_region_invalid=" + r.MissingSectionRegionCount.ToString(CultureInfo.InvariantCulture));
            if (r.UnassignedElementCount > 0) r.Issues.Add("BLOCK:elements_without_section=" + r.UnassignedElementCount.ToString(CultureInfo.InvariantCulture));
            if (r.MultiplyAssignedElementCount > 0) r.Issues.Add("BLOCK:elements_with_multiple_sections=" + r.MultiplyAssignedElementCount.ToString(CultureInfo.InvariantCulture));

            foreach (var kv in model.Mesh.Elements)
            {
                var hex = kv.Value as CaeMesh.LinearHexaElement;
                if (hex == null || hex.NodeIds == null || hex.NodeIds.Length != 8) continue;
                bool nodesPresent = true;
                var nodes = new CaeMesh.FeNode[8];
                for (int i = 0; i < 8; i++)
                {
                    if (model.Mesh.Nodes == null || !model.Mesh.Nodes.TryGetValue(hex.NodeIds[i], out nodes[i]))
                    {
                        nodesPresent = false;
                        break;
                    }
                }
                if (!nodesPresent) continue;
                double det = CenterJacobianDeterminant(nodes);
                if (det < r.MinimumCenterJacobian) r.MinimumCenterJacobian = det;
                if (!(det > 0.0)) r.NonPositiveCenterJacobianCount++;
            }
            if (Double.IsPositiveInfinity(r.MinimumCenterJacobian)) r.MinimumCenterJacobian = Double.NaN;
            if (r.NonPositiveCenterJacobianCount > 0)
                r.Issues.Add("BLOCK:hexa8_nonpositive_center_jacobian=" + r.NonPositiveCenterJacobianCount.ToString(CultureInfo.InvariantCulture));

            r.Status = r.Issues.Any(x => x.StartsWith("BLOCK:", StringComparison.Ordinal)) ? "BLOCKED" : "READY";
            return r;
        }

        public static double CenterJacobianDeterminant(CaeMesh.FeNode[] n)
        {
            if (n == null || n.Length != 8) throw new ArgumentException("HEXA8 requires exactly eight nodes.");
            int[,] natural = new int[,] {
                {-1,-1,-1},{ 1,-1,-1},{ 1, 1,-1},{-1, 1,-1},
                {-1,-1, 1},{ 1,-1, 1},{ 1, 1, 1},{-1, 1, 1}
            };
            double[,] j = new double[3,3];
            for (int i = 0; i < 8; i++)
            {
                double dXi   = natural[i,0] / 8.0;
                double dEta  = natural[i,1] / 8.0;
                double dZeta = natural[i,2] / 8.0;
                j[0,0] += n[i].X*dXi;   j[0,1] += n[i].X*dEta;   j[0,2] += n[i].X*dZeta;
                j[1,0] += n[i].Y*dXi;   j[1,1] += n[i].Y*dEta;   j[1,2] += n[i].Y*dZeta;
                j[2,0] += n[i].Z*dXi;   j[2,1] += n[i].Z*dEta;   j[2,2] += n[i].Z*dZeta;
            }
            return j[0,0]*(j[1,1]*j[2,2]-j[1,2]*j[2,1])
                 - j[0,1]*(j[1,0]*j[2,2]-j[1,2]*j[2,0])
                 + j[0,2]*(j[1,0]*j[2,1]-j[1,1]*j[2,0]);
        }

        public string AuditSummary()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | {1} sections | {2} assigned / {3} unassigned | min HEXA8 center detJ {4:R} | nonpositive {5} | issues {6}",
                Status, SectionCount, AssignedElementCount, UnassignedElementCount, MinimumCenterJacobian,
                NonPositiveCenterJacobianCount, Issues.Count);
        }
    }

    public partial class FrmMain
'@
if(-not $s.Contains($anchor)){throw 'C9.78 FrmMain anchor missing.'}
$s=$s.Replace($anchor,$code)
}
Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.78 material assignment + HEXA8 center-Jacobian quality gate injected.' -ForegroundColor Green
