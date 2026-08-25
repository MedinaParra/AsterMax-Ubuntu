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

            var fixedNodes = fixedFace.NodeIndices.ToArray();
            var material = new StaticMaterial();
            var surfaceForces = new[]
            {
                new CadSurfaceForce(loadedFace.TriangleIndices, new Vec3(1000, 0, 0), "Automated Axial Surface Force")
            };

            Console.WriteLine($"General CAD solver smoke: support Face {fixedFace.Tag}, load Face {loadedFace.Tag}.");
            using var solveTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            var solution = GeneralCadTet4Solver.Solve(
                mesh,
                material,
                fixedNodes,
                surfaceForces,
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

            var benchmark = SelectMpcBenchmark(mesh, loadedFace, fixedNodes, solution);
            Console.WriteLine(
                $"General CAD MPC smoke: tying node {benchmark.NodeA + 1} and node {benchmark.NodeB + 1} " +
                $"on {benchmark.DegreeOfFreedom}; unconstrained gap={benchmark.BaselineGap:E6} mm.");

            var constraint = new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "Automated TET4 MPC tie",
                Terms = new[]
                {
                    new ConstraintEquationTerm(
                        new ConstraintTermTarget(ConstraintTargetKind.MeshNode, benchmark.NodeA + 1, null),
                        benchmark.DegreeOfFreedom,
                        1.0),
                    new ConstraintEquationTerm(
                        new ConstraintTermTarget(ConstraintTargetKind.MeshNode, benchmark.NodeB + 1, null),
                        benchmark.DegreeOfFreedom,
                        -1.0)
                },
                RightHandSide = 0.0
            };

            using var constrainedTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
            var constrainedSolution = GeneralCadTet4Solver.Solve(
                mesh,
                material,
                fixedNodes,
                surfaceForces,
                message => Console.WriteLine(message),
                constrainedTimeout.Token,
                new[] { constraint });

            var component = ComponentIndex(benchmark.DegreeOfFreedom);
            var constrainedGap = Math.Abs(
                constrainedSolution.Displacements[benchmark.NodeA * 3 + component] -
                constrainedSolution.Displacements[benchmark.NodeB * 3 + component]);

            if (constrainedSolution.ActiveConstraintCount != 1)
                throw new InvalidOperationException($"Expected one active MPC equation, observed {constrainedSolution.ActiveConstraintCount}.");
            if (!double.IsFinite(constrainedSolution.MaximumConstraintResidual) || constrainedSolution.MaximumConstraintResidual > 1e-8)
                throw new InvalidOperationException($"TET4 MPC residual failed: {constrainedSolution.MaximumConstraintResidual:E3}.");
            if (!double.IsFinite(constrainedGap) || constrainedGap > 1e-8)
                throw new InvalidOperationException($"TET4 MPC displacement compatibility failed: {constrainedGap:E3} mm.");
            if (constrainedGap > benchmark.BaselineGap * 1e-3)
                throw new InvalidOperationException(
                    $"The MPC equation did not materially change the selected compatibility gap: " +
                    $"baseline={benchmark.BaselineGap:E3}, constrained={constrainedGap:E3}.");
            if (!double.IsFinite(constrainedSolution.EquilibriumError) || constrainedSolution.EquilibriumError > 5e-5)
                throw new InvalidOperationException($"TET4 MPC force equilibrium failed: {constrainedSolution.EquilibriumError:E3}.");
            if (!double.IsFinite(constrainedSolution.MaximumConstraintMultiplier))
                throw new InvalidOperationException("TET4 MPC multiplier recovery returned a non-finite value.");

            Console.WriteLine(
                $"General CAD sparse solver passed | {mesh.Nodes.Count} nodes, {mesh.Tetrahedra.Count} TET4, " +
                $"{topology.Faces.Count} faces, Umax={solution.MaxDisplacementMm:G8} mm, " +
                $"VM={solution.MaxVonMisesMpa:G8} MPa, PCG={solution.Iterations}, " +
                $"residual={solution.RelativeResidual:E3}, equilibrium={solution.EquilibriumError:E3}");
            Console.WriteLine(
                $"General CAD TET4 MPC passed | DOF={benchmark.DegreeOfFreedom}, " +
                $"baseline-gap={benchmark.BaselineGap:E6} mm, constrained-gap={constrainedGap:E6} mm, " +
                $"constraint-residual={constrainedSolution.MaximumConstraintResidual:E3}, " +
                $"equilibrium={constrainedSolution.EquilibriumError:E3}, " +
                $"|lambda|max={constrainedSolution.MaximumConstraintMultiplier:E3}");
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

    private static MpcBenchmarkSelection SelectMpcBenchmark(
        CadMesh mesh,
        CadSurfaceFace loadedFace,
        IReadOnlyCollection<int> fixedNodes,
        GeneralCadStaticSolution baseline)
    {
        var fixedSet = fixedNodes.ToHashSet();
        var candidates = loadedFace.NodeIndices
            .Distinct()
            .Where(node => !fixedSet.Contains(node))
            .ToArray();
        if (candidates.Length < 2)
            candidates = Enumerable.Range(0, mesh.Nodes.Count).Where(node => !fixedSet.Contains(node)).ToArray();
        if (candidates.Length < 2)
            throw new InvalidOperationException("The TET4 MPC benchmark requires at least two free mesh nodes.");

        MpcBenchmarkSelection? best = null;
        for (var component = 0; component < 3; component++)
        {
            var minNode = candidates.MinBy(node => baseline.Displacements[node * 3 + component]);
            var maxNode = candidates.MaxBy(node => baseline.Displacements[node * 3 + component]);
            if (minNode == maxNode) continue;
            var gap = Math.Abs(
                baseline.Displacements[maxNode * 3 + component] -
                baseline.Displacements[minNode * 3 + component]);
            var dof = component switch
            {
                0 => ConstraintDegreeOfFreedom.TranslationX,
                1 => ConstraintDegreeOfFreedom.TranslationY,
                _ => ConstraintDegreeOfFreedom.TranslationZ
            };
            if (best is null || gap > best.BaselineGap)
                best = new MpcBenchmarkSelection(minNode, maxNode, dof, gap);
        }

        if (best is null || !double.IsFinite(best.BaselineGap) || best.BaselineGap <= 1e-10)
            throw new InvalidOperationException(
                "The real TET4 baseline did not produce two sufficiently different free DOF values for a meaningful MPC compatibility benchmark.");
        return best;
    }

    private static int ComponentIndex(ConstraintDegreeOfFreedom degreeOfFreedom) => degreeOfFreedom switch
    {
        ConstraintDegreeOfFreedom.TranslationX => 0,
        ConstraintDegreeOfFreedom.TranslationY => 1,
        ConstraintDegreeOfFreedom.TranslationZ => 2,
        _ => throw new InvalidOperationException($"Unsupported TET4 benchmark DOF {degreeOfFreedom}.")
    };

    private sealed record MpcBenchmarkSelection(
        int NodeA,
        int NodeB,
        ConstraintDegreeOfFreedom DegreeOfFreedom,
        double BaselineGap);
}
