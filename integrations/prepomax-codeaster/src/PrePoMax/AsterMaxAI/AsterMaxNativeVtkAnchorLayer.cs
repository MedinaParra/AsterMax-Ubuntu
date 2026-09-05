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
    // Native VTK anchor layer. It uses vtkControl's own 3D arrow widgets so annotations
    // stay attached to FE world coordinates while the user rotates, pans or zooms.
    // Position is observed from the FE model; exact CAD centroid, physical load direction
    // and solver verification are deliberately not inferred.
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
            _lastSignature = null;
            _sequence = 0;

            _timer = new Timer();
            _timer.Interval = 900;
            _timer.Tick += (s, e) => RefreshNativeAnchors();
            _timer.Start();
            RefreshNativeAnchors();
        }

        public void RefreshNativeAnchors()
        {
            List<NativeAnchor> anchors = CollectAnchors();

            // Harness-only proof point. This is never simulation/model evidence and is
            // activated only by the CI environment variable used by C8.56.
            if (String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_VTK_ANCHOR_POC"), "1", StringComparison.Ordinal))
                anchors.Add(new NativeAnchor(AnchorKind.Proof, "POC WORLD ORIGIN · NOT MODEL DATA", new double[] { 0, 0, 0 }, "HARNESS_ONLY"));

            string signature = BuildSignature(anchors);
            if (String.Equals(signature, _lastSignature, StringComparison.Ordinal)) return;
            _lastSignature = signature;

            RemoveCurrentWidgets();
            foreach (NativeAnchor anchor in anchors)
            {
                string widgetName = "AsterMax_C856_" + (++_sequence).ToString(CultureInfo.InvariantCulture);
                string text = GlyphPrefix(anchor.Kind) + " " + anchor.Name + " · FE POSITION";
                try
                {
                    _vtk.AddArrowWidget(widgetName, text, "G4", anchor.Xyz,
                                        true, true, true);
                    _widgetNames.Add(widgetName);
                }
                catch
                {
                    // Fail closed: a widget that cannot be created is not counted or replaced by fake screen data.
                }
            }
            WriteHarnessRuntimeEvidence();
        }

        private void WriteHarnessRuntimeEvidence()
        {
            string path = Environment.GetEnvironmentVariable("ASTERMAX_VTK_ANCHOR_EVIDENCE_PATH");
            if (String.IsNullOrWhiteSpace(path)) return;
            try
            {
                int nativeCount = -1;
                FieldInfo f = _vtk.GetType().GetField("_arrowWidgets", BindingFlags.NonPublic | BindingFlags.Instance);
                object nativeCollection = f == null ? null : f.GetValue(_vtk);
                IDictionary dict = nativeCollection as IDictionary;
                if (dict != null) nativeCount = dict.Count;
                else if (nativeCollection != null)
                {
                    PropertyInfo count = nativeCollection.GetType().GetProperty("Count", BindingFlags.Public | BindingFlags.Instance);
                    object raw = count == null ? null : count.GetValue(nativeCollection, null);
                    int parsed;
                    if (raw != null && Int32.TryParse(raw.ToString(), out parsed)) nativeCount = parsed;
                }

                string dir = Path.GetDirectoryName(path);
                if (!String.IsNullOrWhiteSpace(dir)) Directory.CreateDirectory(dir);
                bool verified = nativeCount >= 1 && _widgetNames.Count >= 1;
                string json = "{\n" +
                    "  \"schema\": \"astermax.native-vtk-anchor-runtime.v1\",\n" +
                    "  \"harness_only\": true,\n" +
                    "  \"model_or_solver_evidence\": false,\n" +
                    "  \"requested_widget_names\": " + _widgetNames.Count.ToString(CultureInfo.InvariantCulture) + ",\n" +
                    "  \"native_arrow_widget_count\": " + nativeCount.ToString(CultureInfo.InvariantCulture) + ",\n" +
                    "  \"native_widget_runtime_verified\": " + (verified ? "true" : "false") + "\n" +
                    "}";
                File.WriteAllText(path, json, Encoding.UTF8);
            }
            catch
            {
                // Evidence instrumentation must never turn into product/model evidence.
            }
        }

        private List<NativeAnchor> CollectAnchors()
        {
            List<NativeAnchor> result = new List<NativeAnchor>();
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            if (model == null) return result;

            object stepCollection = ReadMember(model, "StepCollection");
            IEnumerable steps = ReadMember(stepCollection, "StepsList") as IEnumerable;
            if (steps == null) return result;

            foreach (object step in steps)
            {
                if (step == null) continue;
                CollectFromCollection(step, model, "BoundaryConditions", result);
                CollectFromCollection(step, model, "Loads", result);
            }
            return result;
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

                double[] xyz;
                string source;
                if (!TryResolveFeAnchor(model, target, out xyz, out source)) continue;
                string name = Safe(ReadMember(target, "Name"));
                output.Add(new NativeAnchor(kind, name, xyz, source));
            }
        }

        private static bool TryResolveFeAnchor(object model, object target, out double[] xyz, out string source)
        {
            xyz = null;
            source = "UNQUALIFIED";
            try
            {
                MethodInfo resolver = typeof(AsterMaxRegionBindingInspector).GetMethod("ResolveAnchor",
                    BindingFlags.NonPublic | BindingFlags.Static);
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
                if (sourceField != null && sourceField.GetValue(resolution) != null)
                    source = sourceField.GetValue(resolution).ToString();
                return xyz != null && xyz.Length >= 3;
            }
            catch { return false; }
        }

        private static AnchorKind Classify(object target)
        {
            string haystack = (target.GetType().Name + " " + Safe(ReadMember(target, "Name"))).ToLowerInvariant();
            if (haystack.Contains("pressure")) return AnchorKind.Pressure;
            if (haystack.Contains("force") || haystack.Contains("concentrated")) return AnchorKind.Force;
            if (haystack.Contains("fixed") || haystack.Contains("constraint") ||
                haystack.Contains("displacement") || haystack.Contains("support")) return AnchorKind.Fixed;
            return AnchorKind.Unsupported;
        }

        private static string GlyphPrefix(AnchorKind kind)
        {
            if (kind == AnchorKind.Fixed) return "⟂ FIXED";
            if (kind == AnchorKind.Pressure) return "⇊ PRESSURE";
            if (kind == AnchorKind.Force) return "↓ FORCE";
            if (kind == AnchorKind.Proof) return "⊕ VTK PROJECTION POC";
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
                  .Append(a.Xyz[2].ToString("R", CultureInfo.InvariantCulture)).Append('|')
                  .Append(a.Source).Append(';');
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
            _timer.Stop();
            _timer.Dispose();
            RemoveCurrentWidgets();
        }

        private sealed class NativeAnchor
        {
            public readonly AnchorKind Kind;
            public readonly string Name;
            public readonly double[] Xyz;
            public readonly string Source;
            public NativeAnchor(AnchorKind kind, string name, double[] xyz, string source)
            {
                Kind = kind; Name = name; Xyz = xyz; Source = source;
            }
        }

        private enum AnchorKind { Unsupported = 0, Fixed = 1, Force = 2, Pressure = 3, Proof = 9 }
    }
}
