using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using CaeGlobals;
using CaeMesh;
using CaeResults;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Headless diagnostic entry used by CI to exercise the same CodeAsterResultBridge.Read()
    /// path used by the GUI. It never creates or modifies solver results.
    /// </summary>
    public static class CodeAsterImportProbe
    {
        public static int Run(string[] args)
        {
            try
            {
                if (args == null || args.Length != 2)
                {
                    Console.Error.WriteLine("Usage: PrePoMax.exe --codeaster-import-probe <result.rmed> <result.resu>");
                    return 64;
                }

                string rmedFile = Path.GetFullPath(args[0]);
                string resuFile = Path.GetFullPath(args[1]);
                if (!File.Exists(rmedFile))
                    throw new FileNotFoundException("RMED result does not exist.", rmedFile);
                if (!File.Exists(resuFile))
                    throw new FileNotFoundException("RESU interoperability result does not exist.", resuFile);

                // C8.30: this mesh must match the verified mm-N-MPa smoke geometry.
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
                if (results == null) throw new InvalidDataException("CodeAsterResultBridge returned null FeResults.");
                if (results.Mesh == null) throw new InvalidDataException("Imported FeResults has no mesh.");
                if (results.Mesh.Nodes == null || results.Mesh.Nodes.Count != 4)
                    throw new InvalidDataException("Imported FeResults does not contain the expected four smoke-test nodes.");
                if (results.Mesh.Elements == null || results.Mesh.Elements.Count != 1)
                    throw new InvalidDataException("Imported FeResults does not contain the expected tetrahedral element.");
                if (results.UnitSystem == null || results.UnitSystem.UnitSystemType != UnitSystemType.MM_TON_S_C)
                    throw new InvalidDataException("Imported FeResults is not tagged with the required mm-ton-s unit system used for mm-N-MPa mechanics.");

                HashSet<string> fields = new HashSet<string>(results.GetAllFieldNames(), StringComparer.OrdinalIgnoreCase);
                string[] requiredFields = new string[]
                {
                    FOFieldNames.Disp,
                    FOFieldNames.Stress,
                    FOFieldNames.ToStrain
                };
                string[] missing = requiredFields.Where(x => !fields.Contains(x)).ToArray();
                if (missing.Length > 0)
                    throw new InvalidDataException("Imported FeResults is missing fields: " + String.Join(", ", missing));

                // Verify exactly the semantic inventory the Results Workspace needs for a professional contour/deformation view.
                Dictionary<string, string[]> visible = results.GetAllVisibleFiledNameComponentNames();
                RequireComponents(visible, FOFieldNames.Disp,
                    new string[] { FOComponentNames.U1, FOComponentNames.U2, FOComponentNames.U3, FOComponentNames.All });
                RequireComponents(visible, FOFieldNames.Stress,
                    new string[] { FOComponentNames.S11, FOComponentNames.S22, FOComponentNames.S33,
                                   FOComponentNames.S12, FOComponentNames.S23, FOComponentNames.S13,
                                   FOComponentNames.Mises });
                RequireComponents(visible, FOFieldNames.ToStrain,
                    new string[] { FOComponentNames.E11, FOComponentNames.E22, FOComponentNames.E33,
                                   FOComponentNames.E12, FOComponentNames.E23, FOComponentNames.E13 });

                // Force the same preprocessing path used before interactive result presentation.
                results.Preprocess();
                string deformationField = results.DeformationFieldOutputName;
                if (String.IsNullOrWhiteSpace(deformationField))
                    throw new InvalidDataException("Results Workspace has no admissible deformation field after preprocessing.");

                Console.WriteLine("Code_Aster CaeResults import probe: PASS");
                Console.WriteLine("Unit system: " + results.UnitSystem.UnitSystemType);
                Console.WriteLine("Nodes: " + results.Mesh.Nodes.Count);
                Console.WriteLine("Elements: " + results.Mesh.Elements.Count);
                Console.WriteLine("Fields: " + String.Join(", ", fields.OrderBy(x => x)));
                Console.WriteLine("Deformation field: " + deformationField);
                Console.WriteLine("Stress contour component: " + FOComponentNames.Mises);
                Console.WriteLine("RMED bytes: " + new FileInfo(rmedFile).Length);
                Console.WriteLine("RESU bytes: " + new FileInfo(resuFile).Length);
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("Code_Aster CaeResults import probe: FAIL");
                Console.Error.WriteLine(ex.ToString());
                return 1;
            }
        }

        private static void RequireComponents(Dictionary<string, string[]> visible, string fieldName, string[] required)
        {
            string[] components;
            if (!visible.TryGetValue(fieldName, out components))
                throw new InvalidDataException("Results Workspace field is not visible: " + fieldName + ".");
            HashSet<string> set = new HashSet<string>(components, StringComparer.OrdinalIgnoreCase);
            string[] missing = required.Where(x => !set.Contains(x)).ToArray();
            if (missing.Length > 0)
                throw new InvalidDataException("Results Workspace field " + fieldName + " is missing component(s): " + String.Join(", ", missing));
        }
    }
}
