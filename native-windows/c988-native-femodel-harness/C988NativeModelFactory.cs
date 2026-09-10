using CaeGlobals;
using CaeMesh;
using CaeModel;

namespace AsterMax.Harness
{
    /// <summary>
    /// Strongly typed test-model factory for the C9.88 production serializer gate.
    /// This intentionally avoids PowerShell reflection/binder coercion so the
    /// harness validates AsterMax/PrePoMax APIs rather than PSObject conversion.
    /// </summary>
    public static class C988NativeModelFactory
    {
        public static FeModel Build()
        {
            var model = new FeModel("C988-native-production");
            model.UnitSystem = new UnitSystem(UnitSystemType.MM_TON_S_C);

            double[][] xyz =
            {
                new double[] { 0, 0, 0 },
                new double[] { 10, 0, 0 },
                new double[] { 10, 10, 0 },
                new double[] { 0, 10, 0 },
                new double[] { 0, 0, 10 },
                new double[] { 10, 0, 10 },
                new double[] { 10, 10, 10 },
                new double[] { 0, 10, 10 }
            };

            for (int i = 0; i < xyz.Length; i++)
            {
                int id = i + 1;
                model.Mesh.Nodes.Add(id, new FeNode(id, xyz[i][0], xyz[i][1], xyz[i][2]));
            }

            model.Mesh.Elements.Add(1, new LinearHexaElement(1, new[] { 1, 2, 3, 4, 5, 6, 7, 8 }));
            model.Mesh.NodeSets.Add("FIXED", new FeNodeSet("FIXED", new[] { 1, 4, 5, 8 }));
            model.Mesh.NodeSets.Add("LOAD", new FeNodeSet("LOAD", new[] { 2, 3, 6, 7 }));

            var material = new Material("Steel-C988");
            material.AddProperty(new Elastic(new[]
            {
                new[] { 210000.0, 0.3, 20.0 }
            }));
            model.Materials.Add("Steel-C988", material);

            var step = new StaticStep("Step-1");
            step.AddBoundaryCondition(new FixedBC("Fixed-1", "FIXED", RegionTypeEnum.NodeSetName, false));
            step.AddLoad(new CLoad("Force-1", "LOAD", RegionTypeEnum.NodeSetName,
                                   0.0, -100.0, 0.0, false, false, 0.0));
            model.StepCollection.AddStep(step, false);

            return model;
        }
    }
}
