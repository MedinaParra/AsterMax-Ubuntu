using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    // Native VTK anchor layer. Production anchors come from the observed Controller model.
    // C8.57 adds an opt-in deterministic in-memory structural fixture used only by CI to
    // exercise the same reflection -> region resolver -> FE XYZ -> native VTK widget path.
    // The fixture is NOT solver/model evidence and never runs unless the CI env flag is set.
    public sealed class AsterMaxNativeVtkAnchorLayer : IDisposable
    {
        private readonly Controller _controller;
        private readonly vtkControl.vtkControl _vtk;
        private readonly Timer _timer;
        private readonly List<string> _widgetNames;
        private string _lastSignature;
        private int _sequence;

        public AsterMaxNativeVtkAnchorLayer(Controller controller, vtkControl.vtkControl vtk)
        {
            _controller = controller;
            _vtk = vtk;
            _widgetNames = new List<string>();
            _timer = new Timer();
            _timer.Interval = 900;
            _timer.Tick += (s, e) => RefreshNativeAnchors();
            _timer.Start();
            RefreshNativeAnchors();
        }

        public void RefreshNativeAnchors()
        {
            List<NativeAnchor> anchors = CollectAnchors();
            bool fixtureMode = String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_STRUCTURAL_ANCHOR_FIXTURE"), "1", StringComparison.Ordinal);
            if (fixtureMode)
            {
                object fixture = BuildDeterministicFixtureModel();
                CollectAnchorsFromModel(fixture, anchors);
            }

            string signature = BuildSignature(anchors);
            if (String.Equals(signature, _lastSignature, StringComparison.Ordinal)) return;
            _lastSignature = signature;
            RemoveCurrentWidgets();

            foreach (NativeAnchor anchor in anchors)
            {
                string widgetName = "AsterMax_C857_" + (++_sequence).ToString(CultureInfo.InvariantCulture);
                string text = GlyphPrefix(anchor.Kind) + " " + anchor.Name + " · FE POSITION";
                try
                {
                    _vtk.AddArrowWidget(widgetName, text, "G4", anchor.Xyz, true, true, true);
                    _widgetNames.Add(widgetName);
                }
                catch { }
            }
            WriteHarnessRuntimeEvidence(anchors, fixtureMode);
        }

        private List<NativeAnchor> CollectAnchors()
        {
            List<NativeAnchor> result = new List<NativeAnchor>();
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            if (model != null) CollectAnchorsFromModel(model, result);
            return result;
        }

        private static void CollectAnchorsFromModel(object model, List<NativeAnchor> result)
        {
            if (model == null) return;
            object stepCollection = ReadMember(model, "StepCollection");
            IEnumerable steps = ReadMember(stepCollection, "StepsList") as IEnumerable;
            if (steps == null) return;
            foreach (object step in steps)
            {
                if (step == null) continue;
                CollectFromCollection(step, model, "BoundaryConditions", result);
                CollectFromCollection(step, model, "Loads", result);
            }
        }

        private static void CollectFromCollection(object step, object model, string propertyName, List<NativeAnchor> output)
        {
            IEnumerable items = ReadMember(step, propertyName) as IEnumerable;
            if (items == null) return;
            foreach (object raw in items)
            {
                object target = UnwrapDictionaryEntry(raw);
                if (target == null) continue;
                AnchorKind kind = Classify(target);
                if (kind == AnchorKind.Unsupported) continue;
                double[] xyz; string source;
                if (!TryResolveFeAnchor(model, target, out xyz, out source)) continue;
                output.Add(new NativeAnchor(kind, Safe(ReadMember(target, "Name")), xyz, source));
            }
        }

        private static bool TryResolveFeAnchor(object model, object target, out double[] xyz, out string source)
        {
            xyz = null; source = "UNQUALIFIED";
            try
            {
                MethodInfo resolver = typeof(AsterMaxRegionBindingInspector).GetMethod("ResolveAnchor", BindingFlags.NonPublic | BindingFlags.Static);
                if (resolver == null) return false;
                object resolution = resolver.Invoke(null, new object[] { model, target });
                if (resolution == null) return false;
                Type rt = resolution.GetType();
                FieldInfo resolvedField = rt.GetField("_resolved", BindingFlags.NonPublic | BindingFlags.Instance);
                FieldInfo xyzField = rt.GetField("_xyz", BindingFlags.NonPublic | BindingFlags.Instance);
                FieldInfo sourceField = rt.GetField("_source", BindingFlags.NonPublic | BindingFlags.Instance);
                if (resolvedField == null || xyzField == null) return false;
                object resolvedValue = resolvedField.GetValue(resolution);
                if (!(resolvedValue is bool) || !(bool)resolvedValue) return false;
                xyz = xyzField.GetValue(resolution) as double[];
                if (sourceField != null && sourceField.GetValue(resolution) != null) source = sourceField.GetValue(resolution).ToString();
                return xyz != null && xyz.Length >= 3;
            }
            catch { return false; }
        }

        private void WriteHarnessRuntimeEvidence(List<NativeAnchor> anchors, bool fixtureMode)
        {
            string path = Environment.GetEnvironmentVariable("ASTERMAX_VTK_ANCHOR_EVIDENCE_PATH");
            if (String.IsNullOrWhiteSpace(path)) return;
            try
            {
                int nativeCount = ReadNativeWidgetCount();
                NativeAnchor fixedAnchor = FindAnchor(anchors, AnchorKind.Fixed, "FIXTURE_FIXED");
                NativeAnchor forceAnchor = FindAnchor(anchors, AnchorKind.Force, "FIXTURE_FORCE_1000N_X");
                bool fixedExpected = HasXyz(fixedAnchor, 0, 0, 0);
                bool forceExpected = HasXyz(forceAnchor, 100, 0, 0);
                bool verified = fixtureMode && fixedExpected && forceExpected && nativeCount >= 2 && _widgetNames.Count >= 2;

                string dir = Path.GetDirectoryName(path);
                if (!String.IsNullOrWhiteSpace(dir)) Directory.CreateDirectory(dir);
                string json = "{\n" +
                    "  \"schema\": \"astermax.structural-anchor-fixture-runtime.v1\",\n" +
                    "  \"harness_only\": true,\n" +
                    "  \"fixture_in_memory\": true,\n" +
                    "  \"fixture_is_loaded_pmx_file\": false,\n" +
                    "  \"model_or_solver_evidence\": false,\n" +
                    "  \"fixed_expected_xyz_verified\": " + (fixedExpected ? "true" : "false") + ",\n" +
                    "  \"force_expected_xyz_verified\": " + (forceExpected ? "true" : "false") + ",\n" +
                    "  \"requested_widget_names\": " + _widgetNames.Count.ToString(CultureInfo.InvariantCulture) + ",\n" +
                    "  \"native_arrow_widget_count\": " + nativeCount.ToString(CultureInfo.InvariantCulture) + ",\n" +
                    "  \"fixture_runtime_verified\": " + (verified ? "true" : "false") + ",\n" +
                    "  \"solver_verified\": false\n" +
                    "}";
                File.WriteAllText(path, json, Encoding.UTF8);
            }
            catch { }
        }

        private int ReadNativeWidgetCount()
        {
            try
            {
                FieldInfo f = _vtk.GetType().GetField("_arrowWidgets", BindingFlags.NonPublic | BindingFlags.Instance);
                object nativeCollection = f == null ? null : f.GetValue(_vtk);
                IDictionary dict = nativeCollection as IDictionary;
                if (dict != null) return dict.Count;
                if (nativeCollection != null)
                {
                    PropertyInfo count = nativeCollection.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    object raw = count == null ? null : count.GetValue(nativeCollection, null);
                    int parsed; if (raw != null && Int32.TryParse(raw.ToString(), out parsed)) return parsed;
                }
            }
            catch { }
            return -1;
        }

        private static NativeAnchor FindAnchor(List<NativeAnchor> anchors, AnchorKind kind, string name)
        {
            foreach (NativeAnchor a in anchors)
                if (a.Kind == kind && String.Equals(a.Name, name, StringComparison.Ordinal)) return a;
            return null;
        }

        private static bool HasXyz(NativeAnchor a, double x, double y, double z)
        {
            if (a == null || a.Xyz == null || a.Xyz.Length < 3) return false;
            const double eps = 1e-9;
            return Math.Abs(a.Xyz[0]-x) < eps && Math.Abs(a.Xyz[1]-y) < eps && Math.Abs(a.Xyz[2]-z) < eps;
        }

        // Deterministic fixture geometry uses millimetres: node 1 at origin and node 2 at X=100 mm.
        // It validates structural region binding/anchoring only; force magnitude is a label, not solved physics.
        private static object BuildDeterministicFixtureModel()
        {
            FixtureMesh mesh = new FixtureMesh();
            mesh.Nodes[1] = new FixtureNode(0, 0, 0);
            mesh.Nodes[2] = new FixtureNode(100, 0, 0);
            mesh.NodeSets["FIXED_SET"] = new FixtureSet(new int[] { 1 });
            mesh.NodeSets["FORCE_SET"] = new FixtureSet(new int[] { 2 });

            FixtureStep step = new FixtureStep();
            step.Name = "STATIC_STRUCTURAL_FIXTURE";
            step.BoundaryConditions["FIXTURE_FIXED"] = new FixtureFixedSupport("FIXTURE_FIXED", "FIXED_SET");
            step.Loads["FIXTURE_FORCE_1000N_X"] = new FixtureForce("FIXTURE_FORCE_1000N_X", "FORCE_SET");

            FixtureModel model = new FixtureModel();
            model.Mesh = mesh;
            model.StepCollection.StepsList.Add(step);
            return model;
        }

        private static AnchorKind Classify(object target)
        {
            string haystack = (target.GetType().Name + " " + Safe(ReadMember(target, "Name"))).ToLowerInvariant();
            if (haystack.Contains("pressure")) return AnchorKind.Pressure;
            if (haystack.Contains("force") || haystack.Contains("concentrated")) return AnchorKind.Force;
            if (haystack.Contains("fixed") || haystack.Contains("constraint") || haystack.Contains("displacement") || haystack.Contains("support")) return AnchorKind.Fixed;
            return AnchorKind.Unsupported;
        }

        private static string GlyphPrefix(AnchorKind kind)
        {
            if (kind == AnchorKind.Fixed) return "⟂ FIXED";
            if (kind == AnchorKind.Pressure) return "⇊ PRESSURE";
            if (kind == AnchorKind.Force) return "↓ FORCE";
            return "ANCHOR";
        }

        private static string BuildSignature(List<NativeAnchor> anchors)
        {
            StringBuilder sb = new StringBuilder();
            foreach (NativeAnchor a in anchors)
            {
                sb.Append((int)a.Kind).Append('|').Append(a.Name).Append('|')
                  .Append(a.Xyz[0].ToString("R", CultureInfo.InvariantCulture)).Append(',')
                  .Append(a.Xyz[1].ToString("R", CultureInfo.InvariantCulture)).Append(',')
                  .Append(a.Xyz[2].ToString("R", CultureInfo.InvariantCulture)).Append('|').Append(a.Source).Append(';');
            }
            return sb.ToString();
        }

        private void RemoveCurrentWidgets()
        {
            if (_widgetNames.Count == 0) return;
            try { _vtk.RemoveArrowWidgets(_widgetNames.ToArray()); } catch { }
            _widgetNames.Clear();
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
            if (item == null) return null;
            object value = ReadMember(item, "Value");
            return value ?? item;
        }

        private static string Safe(object value)
        {
            if (value == null) return "?";
            string s = value.ToString();
            return String.IsNullOrWhiteSpace(s) ? "?" : s;
        }

        public void Dispose()
        {
            _timer.Stop(); _timer.Dispose(); RemoveCurrentWidgets();
        }

        private sealed class NativeAnchor
        {
            public readonly AnchorKind Kind; public readonly string Name; public readonly double[] Xyz; public readonly string Source;
            public NativeAnchor(AnchorKind kind, string name, double[] xyz, string source) { Kind=kind; Name=name; Xyz=xyz; Source=source; }
        }
        private enum AnchorKind { Unsupported=0, Fixed=1, Force=2, Pressure=3 }

        private sealed class FixtureModel { public FixtureMesh Mesh { get; set; } public FixtureStepCollection StepCollection { get; set; } public FixtureModel(){ StepCollection=new FixtureStepCollection(); } }
        private sealed class FixtureStepCollection { public List<object> StepsList { get; set; } public FixtureStepCollection(){ StepsList=new List<object>(); } }
        private sealed class FixtureStep { public string Name { get; set; } public Dictionary<string, object> BoundaryConditions { get; set; } public Dictionary<string, object> Loads { get; set; } public FixtureStep(){ BoundaryConditions=new Dictionary<string, object>(); Loads=new Dictionary<string, object>(); } }
        private sealed class FixtureMesh { public Dictionary<int, FixtureNode> Nodes { get; set; } public Dictionary<string, FixtureSet> NodeSets { get; set; } public FixtureMesh(){ Nodes=new Dictionary<int, FixtureNode>(); NodeSets=new Dictionary<string, FixtureSet>(); } }
        private sealed class FixtureNode { public double X { get; set; } public double Y { get; set; } public double Z { get; set; } public FixtureNode(double x,double y,double z){X=x;Y=y;Z=z;} }
        private sealed class FixtureSet { public int[] Labels { get; set; } public FixtureSet(int[] labels){Labels=labels;} }
        private sealed class FixtureFixedSupport { public string Name { get; set; } public string RegionName { get; set; } public string RegionType { get; set; } public FixtureFixedSupport(string n,string r){Name=n;RegionName=r;RegionType="NodeSetName";} }
        private sealed class FixtureForce { public string Name { get; set; } public string RegionName { get; set; } public string RegionType { get; set; } public FixtureForce(string n,string r){Name=n;RegionName=r;RegionType="NodeSetName";} }
    }
}
