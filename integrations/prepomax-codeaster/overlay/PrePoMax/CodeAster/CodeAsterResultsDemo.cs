using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows.Forms;
using CaeGlobals;
using CaeMesh;
using CaeResults;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Deterministic native Results Workspace activation for verified Code_Aster benchmarks.
    /// The original one-tetra benchmark remains the analytical oracle case. C8.38 adds the
    /// genuine five-node/two-tetra benchmark so native contour/scalar-bar semantics can be
    /// exercised on a nondegenerate field without fabricating result values.
    /// </summary>
    public static class CodeAsterResultsDemo
    {
        private sealed class DemoCase
        {
            public string Name;
            public FeMesh Mesh;
            public int ExpectedNodeCount;
            public bool RequireNondegenerateMises;
            public double? ExpectedMisesMax;
            public double? ExpectedDispMax;
        }

        private static DemoCase CreateCase(string resuFile)
        {
            bool visual = String.Equals(Path.GetFileName(resuFile), "visual.resu", StringComparison.OrdinalIgnoreCase);
            if (visual)
            {
                Dictionary<int, FeNode> nodes = new Dictionary<int, FeNode>
                {
                    { 1, new FeNode(1, 0.0, 0.0, 0.0) },
                    { 2, new FeNode(2, 100.0, 0.0, 0.0) },
                    { 3, new FeNode(3, 0.0, 100.0, 0.0) },
                    { 4, new FeNode(4, 0.0, 0.0, 100.0) },
                    { 5, new FeNode(5, 100.0, 100.0, 100.0) }
                };
                Dictionary<int, FeElement> elements = new Dictionary<int, FeElement>
                {
                    { 1, new LinearTetraElement(1, new int[] { 1, 2, 3, 4 }) },
                    { 2, new LinearTetraElement(2, new int[] { 2, 3, 4, 5 }) }
                };
                return new DemoCase
                {
                    Name = "C8.37-two-tetra-visual",
                    Mesh = new FeMesh(nodes, elements, MeshRepresentation.Mesh, ImportOptions.DetectEdges),
                    ExpectedNodeCount = 5,
                    RequireNondegenerateMises = true,
                    ExpectedMisesMax = null,
                    ExpectedDispMax = null
                };
            }

            Dictionary<int, FeNode> smokeNodes = new Dictionary<int, FeNode>
            {
                { 1, new FeNode(1, 0.0, 0.0, 0.0) },
                { 2, new FeNode(2, 100.0, 0.0, 0.0) },
                { 3, new FeNode(3, 0.0, 100.0, 0.0) },
                { 4, new FeNode(4, 0.0, 0.0, 100.0) }
            };
            Dictionary<int, FeElement> smokeElements = new Dictionary<int, FeElement>
            {
                { 1, new LinearTetraElement(1, new int[] { 1, 2, 3, 4 }) }
            };
            return new DemoCase
            {
                Name = "C8.29-one-tetra-oracle",
                Mesh = new FeMesh(smokeNodes, smokeElements, MeshRepresentation.Mesh, ImportOptions.DetectEdges),
                ExpectedNodeCount = 4,
                RequireNondegenerateMises = false,
                ExpectedMisesMax = 1.0392304845413265,
                ExpectedDispMax = 0.0007428571428571429
            };
        }

        private static Form CreateVerificationOverlay(Controller controller, DemoCase demoCase, float min, float max, float dispMax)
        {
            Form overlay = new Form();
            overlay.Name = "AsterMaxVerifiedResultOverlay";
            overlay.Text = "AsterMax | Verified Result";
            overlay.FormBorderStyle = FormBorderStyle.FixedToolWindow;
            overlay.ShowInTaskbar = false;
            overlay.StartPosition = FormStartPosition.Manual;
            overlay.Width = 430;
            overlay.Height = 225;
            overlay.Left = Math.Max(controller.Form.Left + 24, 0);
            overlay.Top = Math.Max(controller.Form.Top + 72, 0);

            Label title = new Label();
            title.Name = "VerifiedFieldLabel";
            title.AutoSize = true;
            title.Font = new Font(SystemFonts.MessageBoxFont, FontStyle.Bold);
            title.Left = 14;
            title.Top = 14;
            title.Text = "VERIFIED FIELD  STRESS / MISES";

            Label source = new Label();
            source.Name = "VerifiedSourceLabel";
            source.AutoSize = true;
            source.Left = 14;
            source.Top = 45;
            source.Text = "Source: Code_Aster 17.4.0  |  Units: MPa";

            Label range = new Label();
            range.Name = "VerifiedRangeLabel";
            range.AutoSize = true;
            range.Left = 14;
            range.Top = 75;
            range.Text = "Range: " + min.ToString("G9", CultureInfo.InvariantCulture) +
                         " .. " + max.ToString("G9", CultureInfo.InvariantCulture) + " MPa";

            Label deformation = new Label();
            deformation.Name = "VerifiedDeformationLabel";
            deformation.AutoSize = true;
            deformation.Left = 14;
            deformation.Top = 105;
            deformation.Text = "DISP / ALL max: " + dispMax.ToString("G9", CultureInfo.InvariantCulture) + " mm";

            Label benchmark = new Label();
            benchmark.Name = "VerifiedBenchmarkLabel";
            benchmark.AutoSize = true;
            benchmark.Left = 14;
            benchmark.Top = 135;
            benchmark.Text = "Benchmark: " + demoCase.Name;

            Label provenance = new Label();
            provenance.Name = "VerifiedProvenanceLabel";
            provenance.AutoSize = true;
            provenance.Left = 14;
            provenance.Top = 165;
            provenance.Text = "Provenance: genuine solver field  |  mm-N-MPa  |  fail-closed";

            overlay.Controls.Add(title);
            overlay.Controls.Add(source);
            overlay.Controls.Add(range);
            overlay.Controls.Add(deformation);
            overlay.Controls.Add(benchmark);
            overlay.Controls.Add(provenance);
            overlay.Tag = new Dictionary<string, double>
            {
                { "mises_min_mpa", min },
                { "mises_max_mpa", max },
                { "disp_max_mm", dispMax }
            };
            overlay.Show(controller.Form);
            overlay.BringToFront();
            Application.DoEvents();
            return overlay;
        }

        public static int Run(Controller controller, string[] args)
        {
            Form verificationOverlay = null;
            try
            {
                if (controller == null) throw new ArgumentNullException("controller");
                if (args == null || args.Length != 3)
                    throw new ArgumentException("Usage: --astermax-results-demo <result.rmed> <result.resu> <ready.json>");

                string rmedFile = Path.GetFullPath(args[0]);
                string resuFile = Path.GetFullPath(args[1]);
                string readyFile = Path.GetFullPath(args[2]);
                if (!File.Exists(rmedFile)) throw new FileNotFoundException("RMED result does not exist.", rmedFile);
                if (!File.Exists(resuFile)) throw new FileNotFoundException("RESU result does not exist.", resuFile);

                DemoCase demoCase = CreateCase(resuFile);
                FeResults results = CodeAsterResultBridge.Read(rmedFile, resuFile, demoCase.Mesh, UnitSystemType.MM_TON_S_C);
                if (results == null || results.Mesh == null)
                    throw new InvalidDataException("CodeAsterResultBridge did not produce renderable FeResults.");
                results.Preprocess();

                FieldData stressData = new FieldData(FOFieldNames.Stress, FOComponentNames.Mises, 1, 1);
                Field stressField = results.GetField(stressData);
                if (stressField == null) throw new InvalidDataException("STRESS/MISES field is unavailable.");
                float[] mises = stressField.GetComponentValues(FOComponentNames.Mises);
                if (mises == null || mises.Length != demoCase.ExpectedNodeCount || mises.Any(x => Single.IsNaN(x) || Single.IsInfinity(x)))
                    throw new InvalidDataException("STRESS/MISES nodal coverage/finite-value gate failed. Expected=" + demoCase.ExpectedNodeCount);
                float min = stressField.GetComponentMin(FOComponentNames.Mises);
                float max = stressField.GetComponentMax(FOComponentNames.Mises);
                if (demoCase.RequireNondegenerateMises)
                {
                    double scale = Math.Max(1.0, Math.Max(Math.Abs(min), Math.Abs(max)));
                    if ((max - min) <= 1e-6 * scale)
                        throw new InvalidDataException("Visual benchmark STRESS/MISES is degenerate. min=" + min + " max=" + max);
                }
                if (demoCase.ExpectedMisesMax.HasValue && Math.Abs(max - demoCase.ExpectedMisesMax.Value) > 1e-5)
                    throw new InvalidDataException("STRESS/MISES maximum failed the pinned analytical oracle. Observed=" + max);

                FieldData dispData = new FieldData(FOFieldNames.Disp, FOComponentNames.All, 1, 1);
                Field dispField = results.GetField(dispData);
                if (dispField == null) throw new InvalidDataException("DISP/ALL deformation field is unavailable.");
                float dispMax = dispField.GetComponentMax(FOComponentNames.All);
                if (Single.IsNaN(dispMax) || Single.IsInfinity(dispMax))
                    throw new InvalidDataException("DISP/ALL maximum is non-finite.");
                if (demoCase.ExpectedDispMax.HasValue && Math.Abs(dispMax - demoCase.ExpectedDispMax.Value) > 1e-9)
                    throw new InvalidDataException("DISP/ALL maximum failed the pinned displacement oracle. Observed=" + dispMax);

                controller.AllResults.Add(results.FileName, results);
                controller.CurrentFieldData = stressData;
                controller.Form.RegenerateTree();
                controller.Form.SetFieldData(FOFieldNames.Stress, FOComponentNames.Mises, 1, 1);
                Application.DoEvents();

                controller.CurrentView = ViewGeometryModelResults.Results;
                Application.DoEvents();
                controller.ViewResultsType = ViewResultsTypeEnum.ColorContours;
                controller.DrawResults(false);
                Application.DoEvents();

                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);
                if (!scalarBarReport.ControlFound || !scalarBarReport.MethodFound ||
                    !scalarBarReport.MethodInvoked || !scalarBarReport.InternalSpectrumAutomatic ||
                    !scalarBarReport.ScalarBarWidgetFound || !scalarBarReport.LookupTableFound ||
                    !scalarBarReport.LookupTableRangeReadable || !scalarBarReport.RangeMatchesField)
                    throw new InvalidOperationException("Native scalar-bar numerical semantics gate failed: " + scalarBarReport.ToString());

                controller.Form.Refresh();
                Application.DoEvents();

                if (controller.CurrentResult == null || controller.CurrentFieldData == null)
                    throw new InvalidOperationException("Live Controller did not retain the admitted result/field state.");
                if (!String.Equals(controller.CurrentFieldData.Name, FOFieldNames.Stress, StringComparison.OrdinalIgnoreCase) ||
                    !String.Equals(controller.CurrentFieldData.Component, FOComponentNames.Mises, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Live Controller is not displaying STRESS/MISES.");
                if (controller.CurrentView != ViewGeometryModelResults.Results ||
                    controller.ViewResultsType != ViewResultsTypeEnum.ColorContours)
                    throw new InvalidOperationException("Live Controller is not in Results/ColorContours mode.");

                verificationOverlay = CreateVerificationOverlay(controller, demoCase, min, max, dispMax);
                if (verificationOverlay == null || verificationOverlay.IsDisposed || !verificationOverlay.Visible)
                    throw new InvalidOperationException("Verified-result semantics overlay is not visible.");
                Dictionary<string, double> renderedValues = verificationOverlay.Tag as Dictionary<string, double>;
                if (renderedValues == null ||
                    Math.Abs(renderedValues["mises_max_mpa"] - max) > 1e-8 ||
                    Math.Abs(renderedValues["mises_min_mpa"] - min) > 1e-8 ||
                    Math.Abs(renderedValues["disp_max_mm"] - dispMax) > 1e-12)
                    throw new InvalidOperationException("Rendered verification overlay is not bound to the admitted Field values.");

                Directory.CreateDirectory(Path.GetDirectoryName(readyFile));
                string payload = "{\n" +
                    "  \"schema\": \"astermax.results-demo-ready.v3\",\n" +
                    "  \"benchmark\": \"" + demoCase.Name + "\",\n" +
                    "  \"scene_ready\": true,\n" +
                    "  \"result_admitted\": true,\n" +
                    "  \"native_draw_invoked\": true,\n" +
                    "  \"view\": \"Results\",\n" +
                    "  \"view_results_type\": \"ColorContours\",\n" +
                    "  \"field\": \"STRESS\",\n" +
                    "  \"component\": \"MISES\",\n" +
                    "  \"unit_system\": \"mm-N-MPa\",\n" +
                    "  \"mesh_nodes\": " + demoCase.ExpectedNodeCount.ToString(CultureInfo.InvariantCulture) + ",\n" +
                    "  \"mises_min_mpa\": " + min.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"mises_max_mpa\": " + max.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"mises_nondegenerate\": " + demoCase.RequireNondegenerateMises.ToString().ToLowerInvariant() + ",\n" +
                    "  \"disp_max_mm\": " + dispMax.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"verification_overlay_visible\": true,\n" +
                    "  \"verification_overlay_bound_to_field\": true,\n" +
                    "  \"native_scalar_bar_control_found\": true,\n" +
                    "  \"native_scalar_bar_method_invoked\": true,\n" +
                    "  \"native_scalar_bar_automatic_range_contract\": true,\n" +
                    "  \"native_scalar_bar_lut_found\": true,\n" +
                    "  \"native_scalar_bar_range_source\": \"vtkMaxScalarBarWidget._lookupTable.GetTableRange()\",\n" +
                    "  \"native_scalar_bar_min_mpa\": " + scalarBarReport.NativeRangeMin.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"native_scalar_bar_max_mpa\": " + scalarBarReport.NativeRangeMax.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"native_scalar_bar_range_matches_field\": true,\n" +
                    "  \"native_scalar_bar_semantically_verified\": true\n" +
                    "}\n";
                File.WriteAllText(readyFile, payload);
                Console.WriteLine("AsterMax deterministic verified Results demo: READY");
                Console.WriteLine("Benchmark: " + demoCase.Name);
                Console.WriteLine("Native Results state: STRESS/MISES + DISP/ALL");
                Console.WriteLine("Native scalar-bar numerical semantics: VERIFIED " + scalarBarReport.ToString());

                DateTime leaseDeadline = DateTime.UtcNow.AddSeconds(60);
                while (DateTime.UtcNow < leaseDeadline)
                {
                    if (controller.Form == null || controller.Form.IsDisposed) break;
                    Application.DoEvents();
                    Thread.Sleep(100);
                }
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("AsterMax deterministic verified Results demo: FAIL");
                Console.Error.WriteLine(ex.ToString());
                return 1;
            }
            finally
            {
                if (verificationOverlay != null && !verificationOverlay.IsDisposed)
                    verificationOverlay.Close();
            }
        }
    }
}
