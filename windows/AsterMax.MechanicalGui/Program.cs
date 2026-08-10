using System.Diagnostics;

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

        var stepSmokeIndex = Array.FindIndex(args,
            arg => string.Equals(arg, "--step-import-smoke", StringComparison.OrdinalIgnoreCase));
        if (stepSmokeIndex >= 0)
            return RunStepImportSmoke(args.Skip(stepSmokeIndex + 1).ToArray());

        var controlSmokeIndex = Array.FindIndex(args,
            arg => string.Equals(arg, "--step-import-control-smoke", StringComparison.OrdinalIgnoreCase));
        if (controlSmokeIndex >= 0)
            return RunStepImportControlSmoke(args.Skip(controlSmokeIndex + 1).ToArray());

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
            CadViewerQualityBootstrap.Start();
            MechanicalInterfaceRoadmapIteration.Start();

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
                SourcePath = "internal-core-prism-smoke.step",
                Min = new Vec3(0, 0, 0),
                Max = new Vec3(200, 40, 20),
                CartesianPointCount = 8,
                IsSupportedPrism = true,
                FidelityMessage = "Internal rectangular-prism core test"
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
                $"Core prism solver smoke passed | static: {mesh.Nodes.Count} nodes, {mesh.Elements.Count} TET4, " +
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

    private static int RunStepImportSmoke(string[] args)
    {
        try
        {
            Require(args.Length >= 1,
                "Usage: --step-import-smoke <step> [--expect-solids N] [--expect-faces N]");
            var step = Path.GetFullPath(args[0]);
            Require(File.Exists(step), "STEP smoke geometry was not found.");
            var gmsh = GmshCliMesher.FindExecutable();
            Require(gmsh is not null, "Bundled Gmsh executable was not found.");
            var expectedSolids = ReadIntOption(args, "--expect-solids");
            var expectedFaces = ReadIntOption(args, "--expect-faces");

            using var operation = new OperationController();
            var result = StepImportService.ImportSurfaceAsync(
                    gmsh!, step, operation, TimeSpan.FromSeconds(60))
                .GetAwaiter().GetResult();
            var metadata = result.Metadata;
            if (expectedSolids is int solids)
                Require(metadata.SolidCount == solids,
                    $"Expected {solids} solid(s), got {metadata.SolidCount}.");
            if (expectedFaces is int faces)
                Require(metadata.FaceCount == faces,
                    $"Expected {faces} selectable face(s), got {metadata.FaceCount}.");
            Require(metadata.IsClosed, "STEP surface skin is not closed.");
            Require(metadata.VolumeMm3 > 0, "STEP volume is not positive.");
            Require(result.Surface.Mesh.Nodes.Count > 0 && result.Surface.Mesh.SurfaceTriangles.Count > 0,
                "CylinderStep_GeneratesNonEmptySurfaceMesh failed.");

            if (Path.GetFileName(step).Contains("CILINDRO-SIMPLE", StringComparison.OrdinalIgnoreCase))
            {
                Require(metadata.SourceUnit == "metre" && Math.Abs(metadata.SourceToMillimetres - 1000.0) <= 1e-12,
                    "CylinderStep_ConvertsMetresToMillimetres failed.");
                Require(metadata.SolidCount == 1 && metadata.FaceCount == 3,
                    "CylinderStep_ImportsAsOneClosedSolidWithThreeFaces failed.");
                var dimensions = new[] { metadata.Dimensions.X, metadata.Dimensions.Y, metadata.Dimensions.Z }
                    .OrderBy(value => value).ToArray();
                const double expectedDiameter = 34.0587727318528;
                const double expectedLength = 106.6;
                const double bboxToleranceMm = 0.05;
                Require(Math.Abs(dimensions[0] - expectedDiameter) <= bboxToleranceMm &&
                        Math.Abs(dimensions[1] - expectedDiameter) <= bboxToleranceMm &&
                        Math.Abs(dimensions[2] - expectedLength) <= bboxToleranceMm,
                    $"Cylinder OCC bbox mismatch: {dimensions[0]:G10}, {dimensions[1]:G10}, {dimensions[2]:G10} mm.");
                Console.WriteLine("PASS CylinderStep_DoesNotUseCartesianPointEnvelopeAsValidityGate");
                Console.WriteLine("PASS CylinderStep_ImportsAsOneClosedSolidWithThreeFaces");
                Console.WriteLine("PASS CylinderStep_ConvertsMetresToMillimetres");
                Console.WriteLine("PASS CylinderStep_GeneratesNonEmptySurfaceMesh");
            }

            var longest = Math.Max(metadata.Dimensions.X, Math.Max(metadata.Dimensions.Y, metadata.Dimensions.Z));
            var target = Math.Max(longest / 10.0, 0.1);
            var volumeRun = ManagedGmshMesher.GenerateAsync(
                    gmsh!, step, target, 3, TimeSpan.FromSeconds(60), CancellationToken.None)
                .GetAwaiter().GetResult();
            Require(volumeRun.Mesh.Nodes.Count > 0 && volumeRun.Mesh.Tetrahedra.Count > 0,
                "CylinderStep_GeneratesNonEmptyTet4VolumeMesh failed.");
            if (Path.GetFileName(step).Contains("CILINDRO-SIMPLE", StringComparison.OrdinalIgnoreCase))
                Console.WriteLine("PASS CylinderStep_GeneratesNonEmptyTet4VolumeMesh");

            Console.WriteLine(
                $"STEP import smoke passed | file={Path.GetFileName(step)} | sha256={metadata.Sha256} | " +
                $"sourceUnit={metadata.SourceUnit} | solids={metadata.SolidCount} | faces={metadata.FaceCount} | " +
                $"bbox={metadata.Dimensions.X:G8}x{metadata.Dimensions.Y:G8}x{metadata.Dimensions.Z:G8} mm | " +
                $"volume={metadata.VolumeMm3:G10} mm3 | surface={result.Surface.Mesh.Nodes.Count} nodes/{result.Surface.Mesh.SurfaceTriangles.Count} triangles | " +
                $"volumeMesh={volumeRun.Mesh.Nodes.Count} nodes/{volumeRun.Mesh.Tetrahedra.Count} TET4 | " +
                $"preview={operation.Elapsed.TotalMilliseconds:0} ms | gmsh={metadata.GmshVersion}");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 4;
        }
    }

    private static int RunStepImportControlSmoke(string[] args)
    {
        try
        {
            Require(args.Length >= 1, "Usage: --step-import-control-smoke <step>");
            var step = Path.GetFullPath(args[0]);
            Require(File.Exists(step), "STEP smoke geometry was not found.");
            var gmsh = GmshCliMesher.FindExecutable();
            Require(gmsh is not null, "Bundled Gmsh executable was not found.");

            var processName = Path.GetFileNameWithoutExtension(gmsh!);
            var baselineProcesses = Process.GetProcessesByName(processName).Select(process => process.Id).ToHashSet();
            var tempRoot = Path.Combine(Path.GetTempPath(), "AsterMax", "gmsh");
            var baselineDirectories = Directory.Exists(tempRoot)
                ? Directory.GetDirectories(tempRoot).Select(Path.GetFileName).ToHashSet(StringComparer.OrdinalIgnoreCase)
                : new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            var timeoutObserved = false;
            try
            {
                ManagedGmshMesher.GenerateAsync(
                        gmsh!, step, 0.5, 3, TimeSpan.FromMilliseconds(1), CancellationToken.None)
                    .GetAwaiter().GetResult();
            }
            catch (TimeoutException)
            {
                timeoutObserved = true;
            }
            Require(timeoutObserved, "ImportTimeout_ClosesOverlayAndRestoresUi prerequisite failed: forced timeout was not observed.");

            var cancelWatch = Stopwatch.StartNew();
            using (var cancellation = new CancellationTokenSource())
            {
                cancellation.CancelAfter(TimeSpan.FromMilliseconds(1));
                var cancelled = false;
                try
                {
                    ManagedGmshMesher.GenerateAsync(
                            gmsh!, step, 0.5, 3, TimeSpan.FromSeconds(60), cancellation.Token)
                        .GetAwaiter().GetResult();
                }
                catch (OperationCanceledException)
                {
                    cancelled = true;
                }
                Require(cancelled, "ImportCancel_KillsEntireGmshProcessTree prerequisite failed: cancellation was not observed.");
            }
            cancelWatch.Stop();
            Require(cancelWatch.Elapsed <= TimeSpan.FromSeconds(2),
                $"ImportCancel_KillsEntireGmshProcessTree exceeded 2 s: {cancelWatch.Elapsed.TotalMilliseconds:0} ms.");

            Thread.Sleep(150);
            var unexpectedProcesses = Process.GetProcessesByName(processName)
                .Where(process => !baselineProcesses.Contains(process.Id))
                .Select(process => process.Id)
                .ToArray();
            Require(unexpectedProcesses.Length == 0,
                "Unexpected orphan Gmsh process IDs: " + string.Join(", ", unexpectedProcesses));

            var unexpectedDirectories = Directory.Exists(tempRoot)
                ? Directory.GetDirectories(tempRoot)
                    .Select(Path.GetFileName)
                    .Where(name => name is not null && !baselineDirectories.Contains(name))
                    .ToArray()
                : Array.Empty<string?>();
            Require(unexpectedDirectories.Length == 0,
                "TemporaryWorkspace_IsRemovedAfterSuccessFailureAndCancel failed: " + string.Join(", ", unexpectedDirectories));

            Console.WriteLine("PASS ImportCancel_KillsEntireGmshProcessTree");
            Console.WriteLine("PASS ImportTimeout_ClosesOverlayAndRestoresUi process-layer prerequisite");
            Console.WriteLine("PASS TemporaryWorkspace_IsRemovedAfterSuccessFailureAndCancel process-layer prerequisite");
            Console.WriteLine($"STEP process-control smoke passed | cancel={cancelWatch.Elapsed.TotalMilliseconds:0} ms | new-orphans=0 | new-temp-workspaces=0");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 5;
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

            using var operation = new OperationController();
            var imported = StepImportService.ImportSurfaceAsync(
                    gmsh, step, operation, TimeSpan.FromSeconds(60))
                .GetAwaiter().GetResult();
            var metadata = imported.Metadata;
            Require(metadata.SolidCount >= 1 && metadata.IsClosed && metadata.VolumeMm3 > 0,
                "OpenCASCADE did not return a closed positive-volume solid.");
            Require(metadata.FaceCount >= 1,
                "Surface preview did not preserve selectable CAD faces.");

            var longest = Math.Max(metadata.Dimensions.X, Math.Max(metadata.Dimensions.Y, metadata.Dimensions.Z));
            var target = Math.Max(longest / 10.0, 0.1);
            var volume = ManagedGmshMesher.GenerateAsync(
                    gmsh, step, target, 3, TimeSpan.FromSeconds(90), CancellationToken.None)
                .GetAwaiter().GetResult().Mesh;
            Require(volume.Nodes.Count > 0 && volume.SurfaceTriangles.Count > 0 && volume.Tetrahedra.Count > 0,
                "Volume tetrahedral mesh is empty.");
            var volumeTopology = CadTopologyRegistry.Get(volume);
            Require(volumeTopology.Faces.Count >= 1, "Volume mesh did not preserve selectable CAD faces.");
            Require(volumeTopology.Faces.Values.All(face => face.NodeIndices.Count > 0 && face.TriangleIndices.Count > 0),
                "At least one selectable face has an empty mesh scope.");
            Console.WriteLine($"Gmsh STEP smoke passed | surface: {imported.Surface.Mesh.Nodes.Count} nodes, {imported.Surface.Mesh.SurfaceTriangles.Count} triangles, {metadata.FaceCount} faces | volume: {volume.Nodes.Count} nodes, {volume.Tetrahedra.Count} TET4, {volumeTopology.Faces.Count} faces");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 3;
        }
    }

    private static int? ReadIntOption(string[] args, string name)
    {
        var index = Array.FindIndex(args, arg => string.Equals(arg, name, StringComparison.OrdinalIgnoreCase));
        if (index < 0) return null;
        Require(index + 1 < args.Length && int.TryParse(args[index + 1], out var value) && value >= 0,
            $"Invalid integer value for {name}.");
        return int.Parse(args[index + 1], System.Globalization.CultureInfo.InvariantCulture);
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
                $"AsterMax Windows 2.0 beta — Mechanical 0.8.1 beta{Environment.NewLine}" +
                $"Stage: {stage}{Environment.NewLine}" +
                $"Windows: {Environment.OSVersion}{Environment.NewLine}" +
                $"64-bit process: {Environment.Is64BitProcess}{Environment.NewLine}" +
                $"Time: {DateTimeOffset.Now:O}{Environment.NewLine}{Environment.NewLine}" +
                exception);
        }
        catch
        {
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
            }
        }

        Environment.ExitCode = 1;
        if (Application.MessageLoop)
            Application.Exit();
    }
}
