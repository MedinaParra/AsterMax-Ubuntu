using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;

namespace AsterMax.MechanicalGui;

internal static class GeneralCadConvergenceRecoveryBootstrap
{
    [ModuleInitializer]
    internal static void Install() => Application.AddMessageFilter(new RecoverySolveMessageFilter());

    private sealed class RecoverySolveMessageFilter : IMessageFilter
    {
        private const int WmLeftButtonUp = 0x0202;
        private const int WmKeyUp = 0x0101;

        public bool PreFilterMessage(ref Message message)
        {
            if (message.Msg is not (WmLeftButtonUp or WmKeyUp)) return false;
            var control = Control.FromHandle(message.HWnd);
            var button = FindButton(control);
            if (button is null || !button.Text.Replace("&", string.Empty).Contains("Solve", StringComparison.OrdinalIgnoreCase))
                return false;
            if (message.Msg == WmKeyUp)
            {
                var key = (Keys)(int)message.WParam;
                if (key is not (Keys.Space or Keys.Enter)) return false;
            }
            if (button.FindForm() is not MechanicalForm form || !form.CanRunAutomaticCadRecovery()) return false;
            form.BeginInvoke(() => _ = form.SolveGeneralCadWithAutomaticRecoveryAsync());
            return true;
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
    }
}

internal sealed partial class MechanicalForm
{
    internal bool CanRunAutomaticCadRecovery() => !_busy && _cadVolumeMesh is { Tetrahedra.Count: > 0 };

    internal async Task SolveGeneralCadWithAutomaticRecoveryAsync()
    {
        if (!CanRunAutomaticCadRecovery()) return;

        _cadSolveCancellation?.Cancel();
        _cadSolveCancellation?.Dispose();
        _cadSolveCancellation = new CancellationTokenSource();
        var cancellationToken = _cadSolveCancellation.Token;
        var solutionNode = FindFirst(ObjectKind.Solution);
        var originalMesh = _cadVolumeMesh!;
        var originalScopes = CaptureCadScopes(originalMesh);
        var baseTargetSize = ResolveCurrentTargetSize(originalMesh);
        Exception? lastFailure = null;

        try
        {
            _busy = true;
            ToggleUi(false);
            SetState(solutionNode, ObjectState.Updating);
            _statusMain.Text = "Solving with automatic convergence control...";
            Log("--- AUTOMATIC CONVERGENCE SOLUTION START ---");

            var attempts = new[]
            {
                new RecoveryAttempt("Current mesh", 1.00, false),
                new RecoveryAttempt("Balanced recovery mesh", 1.45, true),
                new RecoveryAttempt("Robust recovery mesh", 2.05, true)
            };

            for (var attemptIndex = 0; attemptIndex < attempts.Length; attemptIndex++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var attempt = attempts[attemptIndex];
                try
                {
                    if (attempt.Remesh)
                    {
                        var recovered = await GenerateRecoveryMeshAsync(baseTargetSize * attempt.SizeFactor, originalScopes, cancellationToken);
                        _cadVolumeMesh = recovered;
                        _meshGenerated = true;
                        _solved = false;
                        _automaticallyStabilizedMesh = null;
                        PrepareAutomaticCadStabilization();
                        EnsureCadCanvas().SetMesh(_cadEnvelope!, recovered, true);
                        RefreshCadScopeMarkers();
                        PopulateCadMeshTable(recovered, baseTargetSize * attempt.SizeFactor);
                    }
                    else
                    {
                        PrepareAutomaticCadStabilization();
                    }

                    var mesh = _cadVolumeMesh!;
                    var (fixedNodes, surfaceForces, material) = BuildGeneralCadSolverInput();
                    Log($"Automatic convergence attempt {attemptIndex + 1}/{attempts.Length}: {attempt.Name}; " +
                        $"{mesh.Nodes.Count:N0} nodes, {mesh.Tetrahedra.Count:N0} TET4, {fixedNodes.Count:N0} constrained nodes.");
                    _statusMain.Text = $"{attempt.Name}: solving {mesh.Tetrahedra.Count:N0} TET4...";

                    var progress = new Progress<string>(message =>
                    {
                        _statusMain.Text = message;
                        Log(message);
                    });
                    var activeMesh = mesh;
                    var solved = await Task.Run(() => GeneralCadTet4Solver.Solve(
                        activeMesh,
                        material,
                        fixedNodes,
                        surfaceForces,
                        message => progress.Report(message),
                        cancellationToken), cancellationToken);

                    AcceptRecoveredSolution(solved, solutionNode, attempt.Name, attemptIndex + 1);
                    return;
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception exception) when (IsRecoverableConvergenceFailure(exception))
                {
                    lastFailure = exception;
                    Log($"Attempt {attemptIndex + 1} did not converge: {exception.Message}");
                    if (attemptIndex < attempts.Length - 1)
                    {
                        _statusMain.Text = "Convergence problem detected — generating an automatic recovery mesh...";
                        continue;
                    }
                }
            }

            throw new InvalidOperationException(
                "Automatic convergence recovery exhausted all solver strategies. " +
                "The geometry may contain severe sliver tetrahedra or the load/support arrangement may create a local mechanism.\n\n" +
                (lastFailure?.Message ?? "No numerical result was generated."), lastFailure);
        }
        catch (OperationCanceledException)
        {
            SetState(solutionNode, ObjectState.NeedsAttention);
            _statusMain.Text = "Automatic solution cancelled";
            Log("Automatic convergence solution cancelled.");
        }
        catch (Exception exception)
        {
            _cadStaticSolution = null;
            _solved = false;
            SetState(solutionNode, ObjectState.NeedsAttention);
            _statusMain.Text = "Automatic convergence recovery failed";
            Log("AUTOMATIC CONVERGENCE RECOVERY ERROR: " + exception);
            MessageBox.Show(this,
                exception.Message + "\n\nNo result field was generated.",
                "AsterMax automatic solver recovery",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }

    private async Task<CadMesh> GenerateRecoveryMeshAsync(
        double targetSize,
        IReadOnlyList<CapturedCadScope> scopes,
        CancellationToken cancellationToken)
    {
        if (_cadStepPath is null || _cadEnvelope is null)
            throw new InvalidOperationException("The STEP source is unavailable for automatic remeshing.");
        var gmsh = GmshCliMesher.FindExecutable();
        if (gmsh is null)
            throw new InvalidOperationException("Gmsh is required for automatic convergence recovery.");

        targetSize = Math.Max(targetSize, 0.05);
        Log($"Generating automatic recovery mesh with target size {targetSize:0.###} mm...");
        var mesh = await SelectableGmshMesher.GenerateAsync(gmsh, _cadStepPath, targetSize, 3, cancellationToken);
        if (mesh.Tetrahedra.Count == 0)
            throw new InvalidDataException("Automatic remeshing produced no tetrahedral elements.");
        RestoreCadScopes(mesh, scopes);
        return mesh;
    }

    private IReadOnlyList<CapturedCadScope> CaptureCadScopes(CadMesh mesh)
    {
        var topology = CadTopologyRegistry.Get(mesh);
        var captured = new List<CapturedCadScope>();
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Support or ObjectKind.Load }))
        {
            var model = (ModelObject)node.Tag;
            if (!int.TryParse(model.Properties.GetValueOrDefault("CadSurfaceTag"), NumberStyles.Integer,
                    CultureInfo.InvariantCulture, out var tag) || !topology.Faces.TryGetValue(tag, out var face)) continue;
            captured.Add(new CapturedCadScope(node, model.Kind, face.Centroid, face.Normal, face.AreaMm2));
        }
        return captured;
    }

    private void RestoreCadScopes(CadMesh mesh, IReadOnlyList<CapturedCadScope> scopes)
    {
        var topology = CadTopologyRegistry.Get(mesh);
        var diagonal = Math.Max((mesh.Max - mesh.Min).Length, 1e-9);
        foreach (var scope in scopes)
        {
            var candidate = topology.Faces.Values
                .Select(face => new
                {
                    Face = face,
                    Score = (face.Centroid - scope.Centroid).Length / diagonal +
                            (1.0 - Math.Abs(DirectionDot(face.Normal, scope.Normal))) * 0.65 +
                            Math.Abs(Math.Log(Math.Max(face.AreaMm2, 1e-12) / Math.Max(scope.AreaMm2, 1e-12))) * 0.08
                })
                .OrderBy(item => item.Score)
                .FirstOrDefault()?.Face;
            if (candidate is null) continue;
            var model = (ModelObject)scope.Node.Tag;
            model.Properties["CadSurfaceTag"] = candidate.Tag.ToString(CultureInfo.InvariantCulture);
            model.Properties["Geometry"] = $"Face {candidate.Tag}";
            model.Properties["Scoped Nodes"] = candidate.NodeIndices.Count.ToString("N0");
            model.Properties["Scoped Triangles"] = candidate.TriangleIndices.Count.ToString("N0");
            model.Properties["Surface Area"] = $"{candidate.AreaMm2:0.###} mm²";
            model.Properties["Automatic Scope Recovery"] = "Remapped after convergence remesh";
        }
    }

    private double ResolveCurrentTargetSize(CadMesh mesh)
    {
        if (_nodes["Mesh"].Tag is ModelObject meshObject &&
            meshObject.Properties.TryGetValue("Target Size", out var text))
        {
            var match = Regex.Match(text, @"[-+]?\d+(?:[\.,]\d+)?");
            if (match.Success && double.TryParse(match.Value.Replace(',', '.'), NumberStyles.Float,
                    CultureInfo.InvariantCulture, out var parsed) && parsed > 0)
                return parsed;
        }
        var bounds = mesh.Max - mesh.Min;
        var volumeScale = Math.Max(bounds.X * bounds.Y * bounds.Z, 1e-9);
        return Math.Max(Math.Pow(volumeScale / Math.Max(mesh.Tetrahedra.Count, 1), 1.0 / 3.0) * 1.8, 0.1);
    }

    private void AcceptRecoveredSolution(
        GeneralCadStaticSolution solved,
        TreeNode? solutionNode,
        string strategy,
        int attempt)
    {
        _cadStaticSolution = solved;
        _solved = true;
        SetState(solutionNode, ObjectState.Solved);
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }))
            SetState(node, ObjectState.Solved);
        ApplyGeneralSolutionToTree(solved);
        if (FindFirst(ObjectKind.SolutionInformation)?.Tag is ModelObject information)
        {
            information.Properties["Convergence Strategy"] = strategy;
            information.Properties["Automatic Attempts"] = attempt.ToString(CultureInfo.InvariantCulture);
            information.Properties["Final Mesh Nodes"] = _cadVolumeMesh!.Nodes.Count.ToString("N0");
            information.Properties["Final TET4"] = _cadVolumeMesh.Tetrahedra.Count.ToString("N0");
        }
        EnsureGeneralResultSelectionHook();
        ShowGeneralCadResults("Equivalent Stress");
        RefreshWorkflow();
        RefreshWorkflowChecklist(true);
        _statusSolver.Text = "Solver: AsterMax adaptive sparse TET4";
        _statusMain.Text = $"Solution complete using {strategy}";
        Log($"AUTOMATIC CONVERGENCE SUCCESS: {strategy}; attempt {attempt}; residual {solved.RelativeResidual:E3}; equilibrium {solved.EquilibriumError:E3}.");
        Log("--- AUTOMATIC CONVERGENCE SOLUTION COMPLETE ---");
    }

    private static bool IsRecoverableConvergenceFailure(Exception exception)
    {
        var text = exception.ToString();
        return text.Contains("did not converge", StringComparison.OrdinalIgnoreCase) ||
               text.Contains("positive definite", StringComparison.OrdinalIgnoreCase) ||
               text.Contains("preconditioned residual", StringComparison.OrdinalIgnoreCase) ||
               text.Contains("stiffness diagonal", StringComparison.OrdinalIgnoreCase) ||
               text.Contains("singular", StringComparison.OrdinalIgnoreCase);
    }

    private static double DirectionDot(Vec3 first, Vec3 second)
    {
        var denominator = Math.Max(first.Length * second.Length, 1e-30);
        return (first.X * second.X + first.Y * second.Y + first.Z * second.Z) / denominator;
    }

    private sealed record RecoveryAttempt(string Name, double SizeFactor, bool Remesh);
    private sealed record CapturedCadScope(TreeNode Node, ObjectKind Kind, Vec3 Centroid, Vec3 Normal, double AreaMm2);
}
