using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
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
    /// </summary>
    public static class CodeAsterResultsDemo
    {
        public static int Run(Controller controller, string[] args)
        {
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

                // Admit and synchronize the result while the UI is still in its current tab. RegenerateTree and
                // SetFieldData may raise model-tree selection events, so Results is deliberately selected LAST.
                controller.AllResults.Add(results.FileName, results);
                controller.CurrentFieldData = stressData;
                controller.Form.RegenerateTree();
                controller.Form.SetFieldData(FOFieldNames.Stress, FOComponentNames.Mises, 1, 1);
                Application.DoEvents();

                // Enter the live Results workspace only after the tree/field synchronization is complete.
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

                Directory.CreateDirectory(Path.GetDirectoryName(readyFile));
                string payload = "{\n" +
                    "  \"schema\": \"astermax.results-demo-ready.v1\",\n" +
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
                    "  \"disp_max_mm\": " + dispMax.ToString("R", CultureInfo.InvariantCulture) + "\n" +
                    "}\n";
                File.WriteAllText(readyFile, payload);
                Console.WriteLine("AsterMax deterministic verified Results demo: READY");
                Console.WriteLine("Native Results state: STRESS/MISES + DISP/ALL");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("AsterMax deterministic verified Results demo: FAIL");
                Console.Error.WriteLine(ex.ToString());
                return 1;
            }
        }
    }
}
