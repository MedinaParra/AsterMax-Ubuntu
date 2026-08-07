namespace AsterMax.MechanicalGui;

internal static class ProgressReportExtension
{
    public static void Report<T>(this Progress<T> progress, T value) => ((IProgress<T>)progress).Report(value);
}

internal sealed partial class MechanicalForm
{
    private GeneralCadSolveMessageFilter? _generalCadSolveFilter;

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        _generalCadSolveFilter ??= new GeneralCadSolveMessageFilter(this);
        Application.AddMessageFilter(_generalCadSolveFilter);
    }

    protected override void OnHandleDestroyed(EventArgs e)
    {
        if (_generalCadSolveFilter is not null)
            Application.RemoveMessageFilter(_generalCadSolveFilter);
        base.OnHandleDestroyed(e);
    }

    private bool CanRouteGeneralCadSolve() =>
        !_busy && _cadVolumeMesh is { Tetrahedra.Count: > 0 };

    private void RouteGeneralCadSolve()
    {
        if (!CanRouteGeneralCadSolve()) return;
        BeginInvoke(() => _ = SolveGeneralCadAsync());
    }

    private sealed class GeneralCadSolveMessageFilter(MechanicalForm owner) : IMessageFilter
    {
        private const int WmLeftButtonUp = 0x0202;
        private const int WmKeyUp = 0x0101;

        public bool PreFilterMessage(ref Message message)
        {
            if (!owner.CanRouteGeneralCadSolve()) return false;
            var control = Control.FromHandle(message.HWnd);
            var button = FindButton(control);
            if (button is null || !IsSolveButton(button)) return false;

            if (message.Msg == WmLeftButtonUp)
            {
                owner.RouteGeneralCadSolve();
                return true;
            }
            if (message.Msg == WmKeyUp)
            {
                var key = (Keys)(int)message.WParam;
                if (key is Keys.Space or Keys.Enter)
                {
                    owner.RouteGeneralCadSolve();
                    return true;
                }
            }
            return false;
        }

        private static Button? FindButton(Control? control)
        {
            while (control is not null)
            {
                if (control is Button button) return button;
                control = control.Parent;
            }
            return null;
        }

        private static bool IsSolveButton(Button button)
        {
            var text = button.Text.Replace("&", string.Empty).Trim();
            return text.Contains("Solve", StringComparison.OrdinalIgnoreCase);
        }
    }
}

internal static class GeneralCadSolverSmoke
{
    public static int Run(string[] args)
    {
        try
        {
            if (args.Length < 2)
                throw new InvalidOperationException("Usage: --general-cad-solver-smoke <gmsh.exe> <complex.step>");

            var gmsh = Path.GetFullPath(args[0]);
            var step = Path.GetFullPath(args[1]);
            if (!File.Exists(gmsh)) throw new FileNotFoundException("Gmsh executable was not found.", gmsh);
            if (!File.Exists(step)) throw new FileNotFoundException("Complex STEP smoke model was not found.", step);

            Console.WriteLine("General CAD solver smoke: generating bounded volume mesh...");
            var envelope = SimpleStepReader.ReadPrismaticSolid(step);
            var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
            var target = Math.Max(longest / 3.0, 0.1);
            var mesh = SelectableGmshMesher.GenerateAsync(gmsh, step, target, 3, CancellationToken.None)
                .GetAwaiter().GetResult();
            var topology = CadTopologyRegistry.Get(mesh);
            Console.WriteLine($"General CAD solver smoke: {mesh.Nodes.Count} nodes, {mesh.Tetrahedra.Count} TET4, {topology.Faces.Count} faces.");
            if (mesh.Tetrahedra.Count == 0 || topology.Faces.Count < 4)
                throw new InvalidOperationException("The smoke model did not produce a valid volume mesh and selectable faces.");

            var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
            var fixedFace = ordered.First();
            var loadedFace = ordered.Last();
            if (fixedFace.Tag == loadedFace.Tag)
                throw new InvalidOperationException("The same face was selected for support and load.");

            Console.WriteLine($"General CAD solver smoke: support Face {fixedFace.Tag}, load Face {loadedFace.Tag}.");
            using var solveTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            var solution = GeneralCadTet4Solver.Solve(
                mesh,
                new StaticMaterial(),
                fixedFace.NodeIndices.ToArray(),
                new[] { new CadSurfaceForce(loadedFace.TriangleIndices, new Vec3(1000, 0, 0), "Automated Axial Surface Force") },
                message => Console.WriteLine(message),
                solveTimeout.Token);

            if (!double.IsFinite(solution.MaxDisplacementMm) || solution.MaxDisplacementMm <= 0)
                throw new InvalidOperationException("The solver returned an invalid maximum displacement.");
            if (!double.IsFinite(solution.MaxVonMisesMpa) || solution.MaxVonMisesMpa <= 0)
                throw new InvalidOperationException("The solver returned an invalid equivalent stress.");
            if (solution.RelativeResidual > 2e-6)
                throw new InvalidOperationException($"PCG residual failed: {solution.RelativeResidual:E3}.");
            if (solution.EquilibriumError > 2e-5)
                throw new InvalidOperationException($"Force equilibrium failed: {solution.EquilibriumError:E3}.");

            Console.WriteLine(
                $"General CAD sparse solver passed | {mesh.Nodes.Count} nodes, {mesh.Tetrahedra.Count} TET4, " +
                $"{topology.Faces.Count} faces, Umax={solution.MaxDisplacementMm:G8} mm, " +
                $"VM={solution.MaxVonMisesMpa:G8} MPa, PCG={solution.Iterations}, " +
                $"residual={solution.RelativeResidual:E3}, equilibrium={solution.EquilibriumError:E3}");
            return 0;
        }
        catch (OperationCanceledException)
        {
            Console.Error.WriteLine("GENERAL CAD SOLVER SMOKE FAILED: 90-second numerical timeout.");
            return 23;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine("GENERAL CAD SOLVER SMOKE FAILED");
            Console.Error.WriteLine(exception);
            return 23;
        }
    }
}
