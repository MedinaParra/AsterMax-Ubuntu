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
                string[] requiredFields = new string[] { FOFieldNames.Disp, FOFieldNames.Stress, FOFieldNames.ToStrain };
                string[] missing = requiredFields.Where(x => !fields.Contains(x)).ToArray();
                if (missing.Length > 0)
                    throw new InvalidDataException("Imported FeResults is missing fields: " + String.Join(", ", missing));

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

                results.Preprocess();
                string deformationField = results.DeformationFieldOutputName;
                if (String.IsNullOrWhiteSpace(deformationField))
                    throw new InvalidDataException("Results Workspace has no admissible deformation field after preprocessing.");

                // C8.31: exercise the exact FieldData objects that the native Results Workspace consumes.
                FieldData stressData = new FieldData(FOFieldNames.Stress, FOComponentNames.Mises, 1, 1);
                Field stressField = results.GetField(stressData);
                if (stressField == null) throw new InvalidDataException("Native Results Workspace could not resolve STRESS/MISES FieldData.");
                float[] mises = stressField.GetComponentValues(FOComponentNames.Mises);
                RequireFiniteValues("STRESS/MISES", mises, 4);
                float misesMin = stressField.GetComponentMin(FOComponentNames.Mises);
                float misesMax = stressField.GetComponentMax(FOComponentNames.Mises);
                if (Single.IsNaN(misesMin) || Single.IsInfinity(misesMin) || Single.IsNaN(misesMax) || Single.IsInfinity(misesMax))
                    throw new InvalidDataException("Native Results Workspace STRESS/MISES min/max is non-finite.");
                if (misesMax < misesMin)
                    throw new InvalidDataException("Native Results Workspace STRESS/MISES min/max ordering is invalid.");

                FieldData dispData = new FieldData(FOFieldNames.Disp, FOComponentNames.All, 1, 1);
                Field dispField = results.GetField(dispData);
                if (dispField == null) throw new InvalidDataException("Native Results Workspace could not resolve DISP/ALL FieldData.");
                float[] displacementMagnitude = dispField.GetComponentValues(FOComponentNames.All);
                RequireFiniteValues("DISP/ALL", displacementMagnitude, 4);
                float dispMin = dispField.GetComponentMin(FOComponentNames.All);
                float dispMax = dispField.GetComponentMax(FOComponentNames.All);
                if (Single.IsNaN(dispMin) || Single.IsInfinity(dispMin) || Single.IsNaN(dispMax) || Single.IsInfinity(dispMax))
                    throw new InvalidDataException("Native Results Workspace DISP/ALL min/max is non-finite.");
                if (dispMax < dispMin)
                    throw new InvalidDataException("Native Results Workspace DISP/ALL min/max ordering is invalid.");

                // The pinned benchmark oracle independently establishes SIXZ=0.6 MPa and DX(N4)=0.000742857... mm.
                // Here we verify the native invariant pipeline produces the corresponding renderable scalar fields.
                const double expectedMises = 1.0392304845413265; // sqrt(3) * 0.6 MPa pure shear
                if (Math.Abs(misesMax - expectedMises) > 1e-5)
                    throw new InvalidDataException("Native STRESS/MISES maximum does not match the pinned pure-shear invariant. Observed=" + misesMax);
                const double expectedDisp = 0.0007428571428571429;
                if (Math.Abs(dispMax - expectedDisp) > 1e-9)
                    throw new InvalidDataException("Native DISP/ALL maximum does not match the pinned displacement oracle. Observed=" + dispMax);

                Console.WriteLine("Code_Aster CaeResults import probe: PASS");
                Console.WriteLine("Unit system: " + results.UnitSystem.UnitSystemType);
                Console.WriteLine("Nodes: " + results.Mesh.Nodes.Count);
                Console.WriteLine("Elements: " + results.Mesh.Elements.Count);
                Console.WriteLine("Fields: " + String.Join(", ", fields.OrderBy(x => x)));
                Console.WriteLine("Deformation field: " + deformationField);
                Console.WriteLine("Native contour field: " + stressData.Name + "/" + stressData.Component);
                Console.WriteLine("Native contour min/max [MPa]: " + misesMin + " / " + misesMax);
                Console.WriteLine("Native deformation field: " + dispData.Name + "/" + dispData.Component);
                Console.WriteLine("Native deformation min/max [mm]: " + dispMin + " / " + dispMax);
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

        private static void RequireFiniteValues(string label, float[] values, int expectedCount)
        {
            if (values == null || values.Length != expectedCount)
                throw new InvalidDataException(label + " does not contain the expected " + expectedCount + " nodal values.");
            if (values.Any(x => Single.IsNaN(x) || Single.IsInfinity(x)))
                throw new InvalidDataException(label + " contains non-finite nodal values.");
        }
    }
}
