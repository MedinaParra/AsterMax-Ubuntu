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
    /// Deterministic native Results Workspace activation for the pinned C8.x smoke benchmark.
    /// It consumes genuine Code_Aster outputs, admits them through CodeAsterResultBridge,
    /// assigns the resulting FeResults to the live Controller and invokes the native draw path.
    /// C8.34 additionally renders a compact, machine-gated verification overlay from the very
    /// same Field objects used to validate the contour semantics.
    /// </summary>
    public static class CodeAsterResultsDemo
    {
        private static Form CreateVerificationOverlay(Controller controller, float min, float max, float dispMax)
        {
            Form overlay = new Form();
            overlay.Name = "AsterMaxVerifiedResultOverlay";
            overlay.Text = "AsterMax | Verified Result";
            overlay.FormBorderStyle = FormBorderStyle.FixedToolWindow;
            overlay.ShowInTaskbar = false;
            overlay.StartPosition = FormStartPosition.Manual;
            overlay.Width = 390;
            overlay.Height = 205;
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

            Label provenance = new Label();
            provenance.Name = "VerifiedProvenanceLabel";
            provenance.AutoSize = true;
            provenance.Left = 14;
            provenance.Top = 135;
            provenance.Text = "Oracle: pure shear  |  mm-N-MPa  |  fail-closed";

            overlay.Controls.Add(title);
            overlay.Controls.Add(source);
            overlay.Controls.Add(range);
            overlay.Controls.Add(deformation);
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

                Dictionary<int, FeNode> nodes = new Dictionary<int, FeNode>
                {
                    { 1, new FeNode(1, 0.0, 0.0, 0.0) },
                    { 2, new FeNode(2, 100.0, 0.0, 0.0) },
                    { 3, new FeNode(3, 0.0, 100.0, 0.0) },
                    { 4, new FeNode(4, 0.0, 0.0, 100.0) }
                };
                Dictionary<int, FeElement> elements = new Dictionary<int, FeElement>
                {
                    { 1, new LinearTetraElement(1, new int[] { 1, 2, 3, 4 }) }
                };

                FeMesh mesh = new FeMesh(nodes, elements, MeshRepresentation.Mesh, ImportOptions.DetectEdges);
                FeResults results = CodeAsterResultBridge.Read(rmedFile, resuFile, mesh, UnitSystemType.MM_TON_S_C);
                if (results == null || results.Mesh == null)
                    throw new InvalidDataException("CodeAsterResultBridge did not produce renderable FeResults.");
                results.Preprocess();

                FieldData stressData = new FieldData(FOFieldNames.Stress, FOComponentNames.Mises, 1, 1);
                Field stressField = results.GetField(stressData);
                if (stressField == null) throw new InvalidDataException("STRESS/MISES field is unavailable.");
                float[] mises = stressField.GetComponentValues(FOComponentNames.Mises);
                if (mises == null || mises.Length != 4 || mises.Any(x => Single.IsNaN(x) || Single.IsInfinity(x)))
                    throw new InvalidDataException("STRESS/MISES does not contain four finite nodal values.");
                float min = stressField.GetComponentMin(FOComponentNames.Mises);
                float max = stressField.GetComponentMax(FOComponentNames.Mises);
                const double expectedMises = 1.0392304845413265;
                if (Math.Abs(max - expectedMises) > 1e-5)
                    throw new InvalidDataException("STRESS/MISES maximum failed the pinned pure-shear oracle. Observed=" + max);

                FieldData dispData = new FieldData(FOFieldNames.Disp, FOComponentNames.All, 1, 1);
                Field dispField = results.GetField(dispData);
                if (dispField == null) throw new InvalidDataException("DISP/ALL deformation field is unavailable.");
                float dispMax = dispField.GetComponentMax(FOComponentNames.All);
                const double expectedDisp = 0.0007428571428571429;
                if (Math.Abs(dispMax - expectedDisp) > 1e-9)
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
                controller.Form.Refresh();
                Application.DoEvents();

                if (controller.CurrentResult == null || controller.CurrentFieldData == null)
                    throw new InvalidOperationException("Live Controller did not retain the admitted result/field state.");
                if (!String.Equals(controller.CurrentFieldData.Name, FOFieldNames.Stress, StringComparison.OrdinalIgnoreCase) ||
                    !String.Equals(controller.CurrentFieldData.Component, FOComponentNames.Mises, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Live Controller is not displaying STRESS/MISES. CurrentField=" +
                                                        controller.CurrentFieldData.Name + "/" + controller.CurrentFieldData.Component);
                if (controller.CurrentView != ViewGeometryModelResults.Results ||
                    controller.ViewResultsType != ViewResultsTypeEnum.ColorContours)
                    throw new InvalidOperationException("Live Controller is not in Results/ColorContours mode. CurrentView=" +
                                                        controller.CurrentView + ", ViewResultsType=" + controller.ViewResultsType);

                verificationOverlay = CreateVerificationOverlay(controller, min, max, dispMax);
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
                    "  \"schema\": \"astermax.results-demo-ready.v2\",\n" +
                    "  \"scene_ready\": true,\n" +
                    "  \"result_admitted\": true,\n" +
                    "  \"native_draw_invoked\": true,\n" +
                    "  \"view\": \"Results\",\n" +
                    "  \"view_results_type\": \"ColorContours\",\n" +
                    "  \"field\": \"STRESS\",\n" +
                    "  \"component\": \"MISES\",\n" +
                    "  \"unit_system\": \"mm-N-MPa\",\n" +
                    "  \"mises_min_mpa\": " + min.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"mises_max_mpa\": " + max.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"disp_max_mm\": " + dispMax.ToString("R", CultureInfo.InvariantCulture) + ",\n" +
                    "  \"verification_overlay_visible\": true,\n" +
                    "  \"verification_overlay_bound_to_field\": true\n" +
                    "}\n";
                File.WriteAllText(readyFile, payload);
                Console.WriteLine("AsterMax deterministic verified Results demo: READY");
                Console.WriteLine("Native Results state: STRESS/MISES + DISP/ALL");
                Console.WriteLine("Rendered semantics overlay: VERIFIED");

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