using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxRegionBindingInspector : UserControl
    {
        private readonly Controller _controller;
        private readonly TextBox _report;
        private readonly Timer _timer;

        public AsterMaxRegionBindingInspector(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxRegionBindingInspector";
            Dock = DockStyle.Bottom;
            Height = 132;
            BackColor = AsterMaxUiTheme.SurfaceRaised;
            Padding = new Padding(8, 5, 8, 5);

            Label title = new Label();
            title.Dock = DockStyle.Top;
            title.Height = 22;
            title.Text = "ENTITY COORDINATE RESOLVER · STEP → BC/LOAD → REGION → FE CENTROID";
            title.ForeColor = AsterMaxUiTheme.AccentGlow;
            title.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Bold);

            _report = new TextBox();
            _report.Dock = DockStyle.Fill;
            _report.Multiline = true;
            _report.ReadOnly = true;
            _report.ScrollBars = ScrollBars.Vertical;
            _report.BackColor = AsterMaxUiTheme.Background;
            _report.ForeColor = AsterMaxUiTheme.TextSecondary;
            _report.BorderStyle = BorderStyle.FixedSingle;
            _report.Font = new Font(FontFamily.GenericMonospace, 7.7f, FontStyle.Regular);

            Controls.Add(_report);
            Controls.Add(title);

            _timer = new Timer();
            _timer.Interval = 1500;
            _timer.Tick += (s, e) => RefreshReport();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();
            RefreshReport();
        }

        public void RefreshReport()
        {
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("Observed FE coordinates only. Selection/surface geometry remains UNQUALIFIED; no viewport anchoring or solver verification inferred.");
            if (model == null) { sb.Append("MODEL: MISSING"); _report.Text = sb.ToString(); return; }

            object stepCollection = ReadMember(model, "StepCollection");
            object steps = ReadMember(stepCollection, "StepsList");
            IEnumerable enumerable = steps as IEnumerable;
            if (enumerable == null)
            {
                sb.Append("STEPS: API UNKNOWN");
                _report.Text = sb.ToString();
                return;
            }

            int stepIndex = 0;
            foreach (object step in enumerable)
            {
                if (step == null) continue;
                stepIndex++;
                string stepName = Safe(ReadMember(step, "Name"));
                sb.AppendLine("STEP[" + stepIndex + "] " + stepName);
                InspectCollection(step, model, "BoundaryConditions", "  BC", sb);
                InspectCollection(step, model, "Loads", "  LOAD", sb);
            }
            if (stepIndex == 0) sb.Append("STEPS: NONE");
            _report.Text = sb.ToString();
        }

        private static void InspectCollection(object step, object model, string propertyName, string kind, StringBuilder sb)
        {
            object collection = ReadMember(step, propertyName);
            IEnumerable enumerable = collection as IEnumerable;
            if (enumerable == null) { sb.AppendLine(kind + ": NONE/UNREADABLE"); return; }
            int count = 0;
            foreach (object item in enumerable)
            {
                if (item == null) continue;
                object target = UnwrapDictionaryEntry(item);
                if (target == null) continue;
                count++;
                string name = Safe(ReadMember(target, "Name"));
                string region = Safe(ReadMember(target, "RegionName"));
                string regionType = Safe(ReadMember(target, "RegionType"));
                string refs = Safe(ReadMember(target, "CreationIds"));
                AnchorResolution anchor = ResolveAnchor(model, target);
                sb.AppendLine(kind + "[" + count + "] type=" + target.GetType().Name +
                              " name=" + name + " region=" + region + " regionType=" + regionType +
                              " refs=" + refs + " anchor=" + anchor.ToText());
            }
            if (count == 0) sb.AppendLine(kind + ": NONE");
        }

        private static AnchorResolution ResolveAnchor(object model, object target)
        {
            object mesh = ReadMember(model, "Mesh");
            if (mesh == null) return AnchorResolution.Unknown("MESH_API_UNKNOWN");
            string regionType = Safe(ReadMember(target, "RegionType"));
            string regionName = Safe(ReadMember(target, "RegionName"));

            if (regionType.Equals("NodeId", StringComparison.OrdinalIgnoreCase))
            {
                int nodeId;
                if (!Int32.TryParse(regionName, NumberStyles.Integer, CultureInfo.InvariantCulture, out nodeId))
                    return AnchorResolution.Unknown("NODE_ID_PARSE_FAILED");
                return ResolveNodes(mesh, new int[] { nodeId }, "NODE_ID");
            }
            if (regionType.Equals("NodeSetName", StringComparison.OrdinalIgnoreCase))
            {
                object set = FindNamedValue(ReadMember(mesh, "NodeSets"), regionName);
                if (set == null) return AnchorResolution.Unknown("NODE_SET_NOT_FOUND");
                double[] storedCg = ReadDouble3(ReadMember(set, "CenterOfGravity"));
                if (storedCg != null) return AnchorResolution.Resolved(storedCg, "NODE_SET_CG");
                int[] labels = ReadIntArray(ReadMember(set, "Labels"));
                return labels == null ? AnchorResolution.Unknown("NODE_SET_LABELS_UNKNOWN") : ResolveNodes(mesh, labels, "NODE_SET_NODES");
            }
            if (regionType.Equals("ElementId", StringComparison.OrdinalIgnoreCase))
            {
                int elementId;
                if (!Int32.TryParse(regionName, NumberStyles.Integer, CultureInfo.InvariantCulture, out elementId))
                    return AnchorResolution.Unknown("ELEMENT_ID_PARSE_FAILED");
                return ResolveElements(mesh, new int[] { elementId }, "ELEMENT_ID");
            }
            if (regionType.Equals("ElementSetName", StringComparison.OrdinalIgnoreCase))
            {
                object set = FindNamedValue(ReadMember(mesh, "ElementSets"), regionName);
                if (set == null) return AnchorResolution.Unknown("ELEMENT_SET_NOT_FOUND");
                int[] labels = ReadIntArray(ReadMember(set, "Labels"));
                return labels == null ? AnchorResolution.Unknown("ELEMENT_SET_LABELS_UNKNOWN") : ResolveElements(mesh, labels, "ELEMENT_SET_CG");
            }
            if (regionType.Equals("ReferencePointName", StringComparison.OrdinalIgnoreCase))
            {
                object rp = FindNamedValue(ReadMember(mesh, "ReferencePoints"), regionName);
                if (rp == null) return AnchorResolution.Unknown("REFERENCE_POINT_NOT_FOUND");
                double[] xyz = ReadXYZ(rp);
                return xyz == null ? AnchorResolution.Unknown("REFERENCE_POINT_COORD_UNKNOWN") : AnchorResolution.Resolved(xyz, "REFERENCE_POINT");
            }
            if (regionType.Equals("SurfaceName", StringComparison.OrdinalIgnoreCase))
                return AnchorResolution.Unknown("SURFACE_TO_FACE_CENTROID_NOT_QUALIFIED");
            if (regionType.Equals("Selection", StringComparison.OrdinalIgnoreCase))
                return AnchorResolution.Unknown("SELECTION_IDS_ARE_GEOMETRY_ENCODED");
            if (regionType.Equals("PartName", StringComparison.OrdinalIgnoreCase))
                return AnchorResolution.Unknown("PART_CENTROID_NOT_QUALIFIED");
            return AnchorResolution.Unknown("REGION_TYPE_UNSUPPORTED");
        }

        private static AnchorResolution ResolveNodes(object mesh, int[] nodeIds, string source)
        {
            object nodes = ReadMember(mesh, "Nodes");
            if (nodes == null) return AnchorResolution.Unknown("NODES_API_UNKNOWN");
            double x = 0, y = 0, z = 0; int n = 0;
            HashSet<int> unique = new HashSet<int>();
            foreach (int id in nodeIds)
            {
                if (!unique.Add(id)) continue;
                object node = FindNumericValue(nodes, id);
                double[] xyz = ReadXYZ(node);
                if (xyz == null) continue;
                x += xyz[0]; y += xyz[1]; z += xyz[2]; n++;
            }
            if (n == 0) return AnchorResolution.Unknown(source + "_COORD_NOT_FOUND");
            return AnchorResolution.Resolved(new double[] { x / n, y / n, z / n }, source + " n=" + n);
        }

        private static AnchorResolution ResolveElements(object mesh, int[] elementIds, string source)
        {
            object elements = ReadMember(mesh, "Elements");
            if (elements == null) return AnchorResolution.Unknown("ELEMENTS_API_UNKNOWN");
            List<int> nodeIds = new List<int>();
            int resolvedElements = 0;
            foreach (int id in elementIds)
            {
                object element = FindNumericValue(elements, id);
                if (element == null) continue;
                int[] ids = ReadIntArray(ReadMember(element, "NodeIds"));
                if (ids == null || ids.Length == 0) continue;
                resolvedElements++;
                nodeIds.AddRange(ids);
            }
            if (resolvedElements == 0) return AnchorResolution.Unknown(source + "_ELEMENTS_NOT_FOUND");
            AnchorResolution result = ResolveNodes(mesh, nodeIds.ToArray(), source + " e=" + resolvedElements);
            return result;
        }

        private static object ReadMember(object target, string name)
        {
            if (target == null) return null;
            try
            {
                Type t = target.GetType();
                PropertyInfo p = t.GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (p != null) return p.GetValue(target, null);
                FieldInfo f = t.GetField(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (f != null) return f.GetValue(target);
            }
            catch { }
            return null;
        }

        private static object UnwrapDictionaryEntry(object item)
        {
            object value = ReadMember(item, "Value");
            return value ?? item;
        }

        private static object FindNamedValue(object collection, string key)
        {
            if (collection == null || String.IsNullOrWhiteSpace(key) || key == "?") return null;
            IDictionary dict = collection as IDictionary;
            if (dict != null)
            {
                foreach (DictionaryEntry entry in dict)
                    if (entry.Key != null && String.Equals(entry.Key.ToString(), key, StringComparison.OrdinalIgnoreCase)) return entry.Value;
            }
            IEnumerable enumerable = collection as IEnumerable;
            if (enumerable != null)
            {
                foreach (object item in enumerable)
                {
                    object k = ReadMember(item, "Key");
                    if (k != null && String.Equals(k.ToString(), key, StringComparison.OrdinalIgnoreCase)) return ReadMember(item, "Value");
                }
            }
            return null;
        }

        private static object FindNumericValue(object collection, int key)
        {
            if (collection == null) return null;
            IDictionary dict = collection as IDictionary;
            if (dict != null)
            {
                try { if (dict.Contains(key)) return dict[key]; } catch { }
                foreach (DictionaryEntry entry in dict)
                {
                    int k;
                    if (entry.Key != null && Int32.TryParse(entry.Key.ToString(), out k) && k == key) return entry.Value;
                }
            }
            IEnumerable enumerable = collection as IEnumerable;
            if (enumerable != null)
            {
                foreach (object item in enumerable)
                {
                    object k = ReadMember(item, "Key");
                    int parsed;
                    if (k != null && Int32.TryParse(k.ToString(), out parsed) && parsed == key) return ReadMember(item, "Value");
                }
            }
            return null;
        }

        private static int[] ReadIntArray(object value)
        {
            if (value == null) return null;
            int[] direct = value as int[];
            if (direct != null) return direct;
            IEnumerable e = value as IEnumerable;
            if (e == null || value is string) return null;
            List<int> ids = new List<int>();
            foreach (object item in e)
            {
                int id;
                if (item != null && Int32.TryParse(item.ToString(), out id)) ids.Add(id);
            }
            return ids.Count == 0 ? null : ids.ToArray();
        }

        private static double[] ReadDouble3(object value)
        {
            if (value == null) return null;
            double[] direct = value as double[];
            if (direct != null && direct.Length >= 3) return new double[] { direct[0], direct[1], direct[2] };
            return null;
        }

        private static double[] ReadXYZ(object value)
        {
            if (value == null) return null;
            double x, y, z;
            if (!TryDouble(ReadMember(value, "X"), out x)) return null;
            if (!TryDouble(ReadMember(value, "Y"), out y)) return null;
            if (!TryDouble(ReadMember(value, "Z"), out z)) return null;
            return new double[] { x, y, z };
        }

        private static bool TryDouble(object value, out double result)
        {
            result = 0;
            if (value == null) return false;
            return Double.TryParse(value.ToString(), NumberStyles.Float | NumberStyles.AllowThousands, CultureInfo.InvariantCulture, out result) ||
                   Double.TryParse(value.ToString(), out result);
        }

        private static string Safe(object value)
        {
            if (value == null) return "?";
            if (value is string) return String.IsNullOrWhiteSpace((string)value) ? "?" : (string)value;
            IEnumerable e = value as IEnumerable;
            if (e != null)
            {
                StringBuilder b = new StringBuilder(); int n = 0;
                foreach (object x in e) { if (n++ > 0) b.Append(','); b.Append(x); if (n >= 8) { b.Append("…"); break; } }
                return b.Length == 0 ? "?" : b.ToString();
            }
            string s = value.ToString();
            return String.IsNullOrWhiteSpace(s) ? "?" : s;
        }

        private sealed class AnchorResolution
        {
            private readonly bool _resolved;
            private readonly double[] _xyz;
            private readonly string _source;
            private AnchorResolution(bool resolved, double[] xyz, string source) { _resolved = resolved; _xyz = xyz; _source = source; }
            public static AnchorResolution Resolved(double[] xyz, string source) { return new AnchorResolution(true, xyz, source); }
            public static AnchorResolution Unknown(string reason) { return new AnchorResolution(false, null, reason); }
            public string ToText()
            {
                if (!_resolved || _xyz == null) return "UNQUALIFIED[" + _source + "]";
                return String.Format(CultureInfo.InvariantCulture, "FE_CENTROID({0:0.###},{1:0.###},{2:0.###})[{3}]", _xyz[0], _xyz[1], _xyz[2], _source);
            }
        }
    }
}
