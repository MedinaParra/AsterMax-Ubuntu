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
            if (!double.IsFinite(result.MaxDisplacementMm) || result.MaxDisplacementMm <= 0)
                throw new InvalidOperationException("Solver smoke test returned an invalid displacement.");
            if (!double.IsFinite(result.MaxVonMisesMpa) || result.MaxVonMisesMpa <= 0)
                throw new InvalidOperationException("Solver smoke test returned an invalid equivalent stress.");
            if (!double.IsFinite(result.EquilibriumError) || result.EquilibriumError > 1e-7)
                throw new InvalidOperationException($"Solver smoke test equilibrium error is {result.EquilibriumError:E3}.");
            Console.WriteLine($"TET4 smoke passed: nodes={mesh.Nodes.Count}, elements={mesh.Elements.Count}, Umax={result.MaxDisplacementMm:G8} mm, VM={result.MaxVonMisesMpa:G8} MPa, equilibrium={result.EquilibriumError:E3}");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 2;
        }
    }

    private static void HandleFatal(Exception exception, string stage)
    {
        string? crashFile = null;
        try
        {
            Directory.CreateDirectory(CrashDirectory);
            crashFile = Path.Combine(CrashDirectory, $"astermax-crash-{DateTime.Now:yyyyMMdd-HHmmss}.log");
            File.WriteAllText(crashFile,
                $"AsterMax Mechanical 0.5 beta{Environment.NewLine}" +
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
