using System.Runtime.CompilerServices;

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

internal static class GeneralCadSolverModuleGate
{
    [ModuleInitializer]
    internal static void RunBeforeMain()
    {
        var args = Environment.GetCommandLineArgs().Skip(1).ToArray();
        var workflowIndex = Array.FindIndex(args, arg => string.Equals(arg, "--workflow-smoke", StringComparison.OrdinalIgnoreCase));
        if (workflowIndex < 0) return;
        if (args.Length < workflowIndex + 3) return;

        try
        {
            var gmsh = Path.GetFullPath(args[workflowIndex + 1]);
            var step = Path.GetFullPath(args[workflowIndex + 2]);
            if (!File.Exists(gmsh) || !File.Exists(step)) return;

            var envelope = SimpleStepReader.ReadPrismaticSolid(step);
            var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
            var target = Math.Max(longest / 8.0, 0.1);
            var mesh = SelectableGmshMesher.GenerateAsync(gmsh, step, target, 3, CancellationToken.None)
                .GetAwaiter().GetResult();
            var topology = CadTopologyRegistry.Get(mesh);
            if (mesh.Tetrahedra.Count == 0 || topology.Faces.Count < 4)
                throw new InvalidOperationException("General CAD solver gate did not obtain a valid volume mesh and selectable faces.");

            var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
            var fixedFace = ordered.First();
            var loadedFace = ordered.Last();
            if (fixedFace.Tag == loadedFace.Tag)
                throw new InvalidOperationException("General CAD solver gate selected the same face for support and load.");

            var solution = GeneralCadTet4Solver.Solve(
                mesh,
                new StaticMaterial(),
                fixedFace.NodeIndices.ToArray(),
                new[] { new CadSurfaceForce(loadedFace.TriangleIndices, new Vec3(0, 0, -1000), "Automated Surface Force") });

            if (!double.IsFinite(solution.MaxDisplacementMm) || solution.MaxDisplacementMm <= 0)
                throw new InvalidOperationException("General CAD solver returned an invalid maximum displacement.");
            if (!double.IsFinite(solution.MaxVonMisesMpa) || solution.MaxVonMisesMpa <= 0)
                throw new InvalidOperationException("General CAD solver returned an invalid equivalent stress.");
            if (solution.RelativeResidual > 1e-7)
                throw new InvalidOperationException($"General CAD PCG residual failed: {solution.RelativeResidual:E3}.");
            if (solution.EquilibriumError > 1e-6)
                throw new InvalidOperationException($"General CAD equilibrium failed: {solution.EquilibriumError:E3}.");

            Console.WriteLine(
                $"General CAD sparse solver gate passed | {mesh.Nodes.Count} nodes, {mesh.Tetrahedra.Count} TET4, " +
                $"{topology.Faces.Count} faces, Umax={solution.MaxDisplacementMm:G8} mm, " +
                $"VM={solution.MaxVonMisesMpa:G8} MPa, PCG={solution.Iterations}, " +
                $"residual={solution.RelativeResidual:E3}, equilibrium={solution.EquilibriumError:E3}");
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine("GENERAL CAD SOLVER GATE FAILED");
            Console.Error.WriteLine(exception);
            Environment.Exit(23);
        }
    }
}
