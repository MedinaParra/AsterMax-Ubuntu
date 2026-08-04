namespace AsterMax.MechanicalGui;

internal static class Program
{
    private static bool _smokeTest;
    private static string CrashDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AsterMax",
        "crashes");

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Any(arg => string.Equals(arg, "--solver-smoke", StringComparison.OrdinalIgnoreCase)))
            return RunSolverSmokeTest();

        var generalSolverSmokeIndex = Array.FindIndex(args,
            arg => string.Equals(arg, "--general-cad-solver-smoke", StringComparison.OrdinalIgnoreCase));
        if (generalSolverSmokeIndex >= 0)
            return GeneralCadSolverSmoke.Run(args.Skip(generalSolverSmokeIndex + 1).ToArray());

        var gmshSmokeIndex = Array.FindIndex(args, arg => string.Equals(arg, "--gmsh-smoke", StringComparison.OrdinalIgnoreCase));
        if (gmshSmokeIndex >= 0)
            return RunGmshSmokeTest(args.Skip(gmshSmokeIndex + 1).ToArray());

        var workflowSmokeIndex = Array.FindIndex(args, arg => string.Equals(arg, "--workflow-smoke", StringComparison.OrdinalIgnoreCase));
        if (workflowSmokeIndex >= 0)
        {
            var workflowArguments = args.Skip(workflowSmokeIndex + 1).ToArray();
            var generalSolverResult = GeneralCadSolverSmoke.Run(workflowArguments);
            if (generalSolverResult != 0) return generalSolverResult;
            return StandardWorkflowVerifier.Run(new[] { "--workflow-smoke" }.Concat(workflowArguments).ToArray());
        }

        _smokeTest = args.Any(arg => string.Equals(arg, "--startup-smoke", StringComparison.OrdinalIgnoreCase));
        Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
        Application.ThreadException += (_, eventArgs) => HandleFatal(eventArgs.Exception, "UI thread");
        AppDomain.CurrentDomain.UnhandledException += (_, eventArgs) =>
            HandleFatal(eventArgs.ExceptionObject as Exception ?? new Exception(eventArgs.ExceptionObject?.ToString()), "AppDomain");

        try
        {
            ApplicationConfiguration.Initialize();
            using var form = new MechanicalForm();

            if (_smokeTest)
            {
                var timer = new System.Windows.Forms.Timer { Interval = 2500 };
                timer.Tick += (_, _) =>
                {
                    timer.Stop();
                    form.Close();
                };
                form.Shown += (_, _) => timer.Start();
            }

            Application.Run(form);
            return 0;
        }
        catch (Exception ex)
        {
            HandleFatal(ex, "startup");
            return 1;
        }
    }

    private static int RunSolverSmokeTest()
    {
        try
        {
            var solid = new SimpleStepSolid
            {
                SourcePath = "internal-tutorial-smoke.step",
                Min = new Vec3(0, 0, 0),
                Max = new Vec3(200, 40, 20),
                CartesianPointCount = 8,
                IsSupportedPrism = true,
                FidelityMessage = "Internal rectangular-prism test"
            };
            var material = new StaticMaterial();
            var setup = new SimpleStaticSetup
            {
                ElementSizeMm = 25,
                FixedFace = SimpleFace.XMin,
                LoadFace = SimpleFace.XMax,
                ForceN = new Vec3(0, 0, -1000)
            };

            var mesh = StructuredTetMesher.Generate(solid, setup.ElementSizeMm);
            var result = Tet4LinearStaticSolver.Solve(solid, mesh, material, setup);
            Require(double.IsFinite(result.MaxDisplacementMm) && result.MaxDisplacementMm > 0, "Static displacement is invalid.");
            Require(double.IsFinite(result.MaxVonMisesMpa) && result.MaxVonMisesMpa > 0, "Static equivalent stress is invalid.");
            Require(double.IsFinite(result.EquilibriumError) && result.EquilibriumError <= 1e-7,
                $"Static equilibrium error is {result.EquilibriumError:E3}.");

            var convergence = MeshConvergenceStudy.Run(solid, material, setup, new[] { 100.0, 50.0, 25.0 });
            Require(convergence.Count == 3, "Convergence study did not return three meshes.");
            Require(convergence.All(point => point.EquilibriumError <= 1e-7), "A convergence solution failed equilibrium.");

            var modal = EulerBernoulliModalSolver.Solve(solid, material, new BeamModalSetup
            {
                DensityKgM3 = 7850,
                BeamElements = 16,
                RequestedModes = 4
            });
            Require(modal.Count == 4, "Modal solver did not return four modes.");
            Require(modal[0].FrequencyHz > 0 && modal[0].DifferencePercent <= 2.0,
                $"First modal frequency failed the analytical gate: {modal[0].FrequencyHz:G8} Hz, error {modal[0].DifferencePercent:G5}%.");

            var thermal = Tet4SteadyThermalSolver.Solve(solid, mesh, new ThermalSetup
            {
                ConductivityWmK = 45,
                HotFace = SimpleFace.XMin,
                ColdFace = SimpleFace.XMax,
                HotTemperatureC = 100,
                ColdTemperatureC = 20
            });
            Require(double.IsFinite(thermal.HeatFlowW) && thermal.HeatFlowW > 0, "Thermal heat flow is invalid.");
            Require(thermal.HeatFlowDifferencePercent <= 1e-6,
                $"Thermal analytical difference is {thermal.HeatFlowDifferencePercent:G5}%.");
            Require(thermal.EnergyBalanceError <= 1e-8,
                $"Thermal energy balance error is {thermal.EnergyBalanceError:E3}.");

            Console.WriteLine(
                $"AsterMax 0.8.0 tutorial capability smoke passed | static: {mesh.Nodes.Count} nodes, {mesh.Elements.Count} TET4, " +
                $"Umax={result.MaxDisplacementMm:G8} mm, VM={result.MaxVonMisesMpa:G8} MPa | " +
                $"modal f1={modal[0].FrequencyHz:G8} Hz ({modal[0].DifferencePercent:G4}% error) | " +
                $"thermal Q={thermal.HeatFlowW:G8} W, balance={thermal.EnergyBalanceError:E3}");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 2;
        }
    }

    private static int RunGmshSmokeTest(string[] args)
    {
        try
        {
            Require(args.Length >= 2, "Usage: --gmsh-smoke <gmsh.exe> <complex.step>");
            var gmsh = Path.GetFullPath(args[0]);
            var step = Path.GetFullPath(args[1]);
            Require(File.Exists(gmsh), "Gmsh executable was not found.");
            Require(File.Exists(step), "Complex STEP smoke geometry was not found.");

            var envelope = SimpleStepReader.ReadPrismaticSolid(step);
            Require(!envelope.IsSupportedPrism, "The Gmsh smoke geometry must exercise curved or holed topology.");
            var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
            var target = Math.Max(longest / 10.0, 0.1);
            var surface = SelectableGmshMesher.GenerateAsync(gmsh, step, target, 2, CancellationToken.None).GetAwaiter().GetResult();
            var volume = SelectableGmshMesher.GenerateAsync(gmsh, step, target, 3, CancellationToken.None).GetAwaiter().GetResult();
            Require(surface.Nodes.Count > 0 && surface.SurfaceTriangles.Count > 0, "Surface preview mesh is empty.");
            Require(volume.Nodes.Count > 0 && volume.SurfaceTriangles.Count > 0 && volume.Tetrahedra.Count > 0, "Volume tetrahedral mesh is empty.");
            var surfaceTopology = CadTopologyRegistry.Get(surface);
            var volumeTopology = CadTopologyRegistry.Get(volume);
            Require(surfaceTopology.Faces.Count >= 4, "Surface preview did not preserve selectable CAD faces.");
            Require(volumeTopology.Faces.Count >= 4, "Volume mesh did not preserve selectable CAD faces.");
            Require(volumeTopology.Faces.Values.All(face => face.NodeIndices.Count > 0 && face.TriangleIndices.Count > 0), "At least one selectable face has an empty mesh scope.");
            Console.WriteLine($"Gmsh STEP smoke passed | surface: {surface.Nodes.Count} nodes, {surface.SurfaceTriangles.Count} triangles, {surfaceTopology.Faces.Count} faces | volume: {volume.Nodes.Count} nodes, {volume.Tetrahedra.Count} TET4, {volumeTopology.Faces.Count} faces");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 3;
        }
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }

    private static void HandleFatal(Exception exception, string stage)
    {
        string? crashFile = null;
        try
        {
            Directory.CreateDirectory(CrashDirectory);
            crashFile = Path.Combine(CrashDirectory, $"astermax-crash-{DateTime.Now:yyyyMMdd-HHmmss}.log");
            File.WriteAllText(crashFile,
                $"AsterMax Mechanical 0.8.0 beta{Environment.NewLine}" +
                $"Stage: {stage}{Environment.NewLine}" +
                $"Windows: {Environment.OSVersion}{Environment.NewLine}" +
                $"64-bit process: {Environment.Is64BitProcess}{Environment.NewLine}" +
                $"Time: {DateTimeOffset.Now:O}{Environment.NewLine}{Environment.NewLine}" +
                exception);
        }
        catch
        {
            // Last-resort handler must never throw another exception.
        }

        if (!_smokeTest)
        {
            try
            {
                MessageBox.Show(
                    $"AsterMax no pudo iniciar.\n\n{exception.Message}\n\n" +
                    (crashFile is null ? "No fue posible crear el registro." : $"Registro: {crashFile}"),
                    "AsterMax — error de inicio",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            catch
            {
                // Nothing else can be shown safely.
            }
        }

        Environment.ExitCode = 1;
        if (Application.MessageLoop)
            Application.Exit();
    }
}
