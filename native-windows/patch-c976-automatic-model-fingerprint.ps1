param([string]$Root)
$ErrorActionPreference='Stop'

$workspace=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $workspace)){throw 'C9.65 results workspace must exist before C9.76.'}
$s=Get-Content $workspace -Raw
if(-not $s.Contains('internal sealed class AsterMaxModelFingerprint')){
$anchor='    public partial class FrmMain'
$code=@'
    internal sealed class AsterMaxModelFingerprint
    {
        public string Canonical { get; private set; }
        public string Sha256 { get; private set; }
        public string UnitSystem { get; private set; }
        public int NodeCount { get; private set; }
        public int ElementCount { get; private set; }
        public int MaterialCount { get; private set; }
        public int StepCount { get; private set; }
        public int BoundaryConditionCount { get; private set; }
        public int LoadCount { get; private set; }

        public static AsterMaxModelFingerprint Extract(CaeModel.FeModel model)
        {
            if (model == null) throw new ArgumentNullException("model");
            if (model.UnitSystem == null) throw new InvalidDataException("Model unit system is missing.");
            string length = model.UnitSystem.LengthUnitAbbreviation;
            string force = model.UnitSystem.ForceUnitAbbreviation;
            string stress = model.UnitSystem.PressureUnitAbbreviation;
            if (!String.Equals(length, "mm", StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(force, "N", StringComparison.OrdinalIgnoreCase) ||
                !String.Equals(stress, "MPa", StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("C9.76 automatic fingerprint requires the mm / N / MPa model unit contract.");

            var f = new AsterMaxModelFingerprint();
            f.UnitSystem = model.UnitSystem.UnitSystemType.ToString();
            var lines = new List<string>();
            lines.Add("schema=astermax-model-fingerprint/v0");
            lines.Add("units=mm|N|MPa");
            lines.Add("unit_system=" + f.UnitSystem);

            if (model.Mesh == null) throw new InvalidDataException("Model mesh is missing.");
            f.NodeCount = model.Mesh.Nodes == null ? 0 : model.Mesh.Nodes.Count;
            f.ElementCount = model.Mesh.Elements == null ? 0 : model.Mesh.Elements.Count;
            lines.Add("mesh.nodes=" + f.NodeCount.ToString(CultureInfo.InvariantCulture));
            lines.Add("mesh.elements=" + f.ElementCount.ToString(CultureInfo.InvariantCulture));
            if (model.Mesh.Nodes != null)
            {
                foreach (var kv in model.Mesh.Nodes.OrderBy(x => x.Key))
                    lines.Add(String.Format(CultureInfo.InvariantCulture, "node|{0}|{1:R}|{2:R}|{3:R}", kv.Key, kv.Value.X, kv.Value.Y, kv.Value.Z));
            }
            if (model.Mesh.Elements != null)
            {
                foreach (var kv in model.Mesh.Elements.OrderBy(x => x.Key))
                    lines.Add("element|" + kv.Key.ToString(CultureInfo.InvariantCulture) + "|" + kv.Value.GetType().FullName + "|" + String.Join(",", kv.Value.NodeIds.Select(x => x.ToString(CultureInfo.InvariantCulture))));
            }

            f.MaterialCount = model.Materials == null ? 0 : model.Materials.Count;
            lines.Add("materials=" + f.MaterialCount.ToString(CultureInfo.InvariantCulture));
            if (model.Materials != null)
            {
                foreach (var kv in model.Materials.OrderBy(x => x.Key, StringComparer.Ordinal))
                {
                    lines.Add("material|" + Escape(kv.Key) + "|" + kv.Value.GetType().FullName);
                    AppendSimpleProperties(lines, "material." + Escape(kv.Key), kv.Value);
                }
            }

            if (model.StepCollection != null && model.StepCollection.StepsList != null)
            {
                f.StepCount = model.StepCollection.StepsList.Count;
                foreach (var step in model.StepCollection.StepsList)
                {
                    lines.Add("step|" + Escape(step.Name) + "|" + step.GetType().FullName);
                    if (step.BoundaryConditions != null)
                    {
                        foreach (var kv in step.BoundaryConditions.OrderBy(x => x.Key, StringComparer.Ordinal))
                        {
                            f.BoundaryConditionCount++;
                            lines.Add("bc|" + Escape(step.Name) + "|" + Escape(kv.Key) + "|" + kv.Value.GetType().FullName);
                            AppendSimpleProperties(lines, "bc." + Escape(step.Name) + "." + Escape(kv.Key), kv.Value);
                        }
                    }
                    if (step.Loads != null)
                    {
                        foreach (var kv in step.Loads.OrderBy(x => x.Key, StringComparer.Ordinal))
                        {
                            f.LoadCount++;
                            lines.Add("load|" + Escape(step.Name) + "|" + Escape(kv.Key) + "|" + kv.Value.GetType().FullName);
                            AppendSimpleProperties(lines, "load." + Escape(step.Name) + "." + Escape(kv.Key), kv.Value);
                        }
                    }
                }
            }
            lines.Add("steps=" + f.StepCount.ToString(CultureInfo.InvariantCulture));
            lines.Add("boundary_conditions=" + f.BoundaryConditionCount.ToString(CultureInfo.InvariantCulture));
            lines.Add("loads=" + f.LoadCount.ToString(CultureInfo.InvariantCulture));

            f.Canonical = String.Join("\n", lines);
            using (var sha = SHA256.Create())
                f.Sha256 = BitConverter.ToString(sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(f.Canonical))).Replace("-", "").ToLowerInvariant();
            return f;
        }

        private static void AppendSimpleProperties(List<string> lines, string prefix, object obj)
        {
            if (obj == null) return;
            var props = obj.GetType().GetProperties(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public)
                           .Where(p => p.CanRead && p.GetIndexParameters().Length == 0)
                           .OrderBy(p => p.Name, StringComparer.Ordinal);
            foreach (var p in props)
            {
                object value;
                try { value = p.GetValue(obj, null); } catch { continue; }
                if (value == null) { lines.Add(prefix + "." + p.Name + "=<null>"); continue; }
                Type t = value.GetType();
                if (t.IsEnum || t == typeof(string) || t == typeof(bool) || t == typeof(byte) || t == typeof(short) || t == typeof(int) || t == typeof(long) || t == typeof(float) || t == typeof(double) || t == typeof(decimal))
                {
                    string text = value is IFormattable fmt ? fmt.ToString(null, CultureInfo.InvariantCulture) : value.ToString();
                    lines.Add(prefix + "." + p.Name + "=" + Escape(text));
                }
            }
        }

        private static string Escape(string value)
        {
            if (value == null) return "<null>";
            return value.Replace("\\", "\\\\").Replace("\n", "\\n").Replace("\r", "\\r").Replace("|", "\\|");
        }

        public string AuditSummary()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0} | {1} nodes / {2} elements | {3} materials | {4} steps | {5} BC / {6} loads | SHA256 {7}",
                UnitSystem, NodeCount, ElementCount, MaterialCount, StepCount, BoundaryConditionCount, LoadCount, Sha256);
        }
    }

    public partial class FrmMain
'@
if(-not $s.Contains($anchor)){throw 'C9.76 FrmMain anchor missing.'}
$s=$s.Replace($anchor,$code)
}
Set-Content $workspace $s -Encoding UTF8
Write-Host 'C9.76 automatic FeModel fingerprint extractor injected.' -ForegroundColor Green
