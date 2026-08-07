using System.Text.RegularExpressions;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private GeneralCadStaticSolution? _cadStaticSolution;
    private CadResultCanvas? _cadResultCanvas;
    private CancellationTokenSource? _cadSolveCancellation;
    private bool _cadResultSelectionHooked;

    private async Task SolveGeneralCadAsync()
    {
        if (_busy || _cadVolumeMesh is null) return;

        IReadOnlyCollection<int> fixedNodes;
        IReadOnlyList<CadSurfaceForce> surfaceForces;
        StaticMaterial material;
        try
        {
            (fixedNodes, surfaceForces, material) = BuildGeneralCadSolverInput();
        }
        catch (Exception exception)
        {
            Log("GENERAL CAD VALIDATION ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "General CAD model is not ready", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        _cadSolveCancellation?.Cancel();
        _cadSolveCancellation?.Dispose();
        _cadSolveCancellation = new CancellationTokenSource();
        var cancellationToken = _cadSolveCancellation.Token;
        var progress = new Progress<string>(message =>
        {
            _statusMain.Text = message;
            Log(message);
        });

        var solutionNode = FindFirst(ObjectKind.Solution);
        try
        {
            _busy = true;
            ToggleUi(false);
            SetState(solutionNode, ObjectState.Updating);
            _statusMain.Text = "Preparing sparse TET4 solution...";
            Log("--- GENERAL CAD SOLUTION START ---");
            Log($"Backend: AsterMax sparse linear-elastic TET4 / PCG.");
            Log($"Mesh: {_cadVolumeMesh.Nodes.Count:N0} nodes, {_cadVolumeMesh.Tetrahedra.Count:N0} TET4.");
            Log($"Material: {material.Name}; E={material.YoungModulusMpa:0.###} MPa; nu={material.PoissonRatio:0.####}.");
            Log($"Boundary conditions: {fixedNodes.Count:N0} fixed nodes; {surfaceForces.Count:N0} surface load(s).");

            var activeMesh = _cadVolumeMesh;
            var solved = await Task.Run(() => GeneralCadTet4Solver.Solve(
                activeMesh,
                material,
                fixedNodes,
                surfaceForces,
                message => progress.Report(message),
                cancellationToken), cancellationToken);

            _cadStaticSolution = solved;
            _solved = true;
            SetState(solutionNode, ObjectState.Solved);
            foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }))
                SetState(node, ObjectState.Solved);
            ApplyGeneralSolutionToTree(solved);
            EnsureGeneralResultSelectionHook();
            ShowGeneralCadResults("Equivalent Stress");
            RefreshWorkflow();
            RefreshWorkflowChecklist(true);
            _statusSolver.Text = "Solver: AsterMax sparse TET4";
            _statusMain.Text = "General CAD solution complete";
            Log($"Maximum displacement: {solved.MaxDisplacementMm:G8} mm at node {solved.MaxDisplacementNode + 1:N0}.");
            Log($"Maximum equivalent stress: {solved.MaxVonMisesMpa:G8} MPa at element {solved.MaxVonMisesElement + 1:N0}.");
            Log($"Reaction: ({solved.ReactionN.X:G8}, {solved.ReactionN.Y:G8}, {solved.ReactionN.Z:G8}) N.");
            Log($"Applied force: ({solved.AppliedForceN.X:G8}, {solved.AppliedForceN.Y:G8}, {solved.AppliedForceN.Z:G8}) N.");
            Log($"PCG: {solved.Iterations:N0} iterations; relative residual {solved.RelativeResidual:E3}.");
            Log($"Force equilibrium error: {solved.EquilibriumError:E3}.");
            Log("--- GENERAL CAD SOLUTION COMPLETE ---");
        }
        catch (OperationCanceledException)
        {
            SetState(solutionNode, ObjectState.NeedsAttention);
            _statusMain.Text = "General CAD solution cancelled";
            Log("General CAD solution cancelled.");
        }
        catch (Exception exception)
        {
            _cadStaticSolution = null;
            _solved = false;
            SetState(solutionNode, ObjectState.NeedsAttention);
            _statusMain.Text = "General CAD solution failed";
            Log("GENERAL CAD SOLVER ERROR: " + exception);
            MessageBox.Show(this,
                exception.Message + "\n\nNo result field was generated.",
                "General CAD solver failed",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }

    private (IReadOnlyCollection<int> FixedNodes, IReadOnlyList<CadSurfaceForce> Forces, StaticMaterial Material)
        BuildGeneralCadSolverInput()
    {
        if (_cadVolumeMesh is null || _cadVolumeMesh.Tetrahedra.Count == 0)
            throw new InvalidOperationException("Generate the tetrahedral volume mesh before solving.");

        var topology = CadTopologyRegistry.Get(_cadVolumeMesh);
        var fixedNodes = new HashSet<int>();
        var supportFaces = new HashSet<int>();
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed }))
        {
            var model = (ModelObject)node.Tag;
            if (!TryGetCadFaceTag(model, out var tag)) continue;
            if (!topology.Faces.TryGetValue(tag, out var face))
                throw new InvalidOperationException($"{model.Name} references Face {tag}, which is not present in the current volume mesh.");
            supportFaces.Add(tag);
            fixedNodes.UnionWith(face.NodeIndices);
        }
        if (fixedNodes.Count == 0)
            throw new InvalidOperationException("Insert a Fixed Support and scope it to a real CAD face before solving.");

        var forces = new List<CadSurfaceForce>();
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed }))
        {
            var model = (ModelObject)node.Tag;
            if (model.Name.Contains("Gravity", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Gravity is not yet supported by the general TET4 solver. Use a scoped Force object.");
            if (!TryGetCadFaceTag(model, out var tag)) continue;
            if (!topology.Faces.TryGetValue(tag, out var face))
                throw new InvalidOperationException($"{model.Name} references Face {tag}, which is not present in the current volume mesh.");
            if (supportFaces.Contains(tag))
                throw new InvalidOperationException($"{model.Name} and a Fixed Support use the same Face {tag}. Select a different load face.");
            var vector = ParseForceVector(model);
            forces.Add(new CadSurfaceForce(face.TriangleIndices, vector, model.Name));
        }
        if (forces.Count == 0)
            throw new InvalidOperationException("Insert a Force and scope it to a real CAD face before solving.");

        return (fixedNodes, forces, ResolveGeneralCadMaterial());
    }

    private StaticMaterial ResolveGeneralCadMaterial()
    {
        var material = new StaticMaterial
        {
            Name = _simpleMaterial.Name,
            YoungModulusMpa = _simpleMaterial.YoungModulusMpa,
            PoissonRatio = _simpleMaterial.PoissonRatio,
            YieldStrengthMpa = _simpleMaterial.YieldStrengthMpa
        };

        var source = AllNodes()
            .Where(node => node.Tag is ModelObject { Kind: ObjectKind.Material })
            .Select(node => (ModelObject)node.Tag)
            .LastOrDefault();
        if (source is null) return material;

        material.Name = source.Name;
        if (TryProperty(source, out var youngText, "Young's Modulus", "Young Modulus", "Elastic Modulus"))
            material.YoungModulusMpa = ParseEngineeringValue(youngText, "Young's modulus");
        if (TryProperty(source, out var poissonText, "Poisson's Ratio", "Poisson Ratio"))
            material.PoissonRatio = ParseEngineeringValue(poissonText, "Poisson's ratio");
        if (TryProperty(source, out var yieldText, "Yield Strength", "Yield Stress"))
            material.YieldStrengthMpa = ParseEngineeringValue(yieldText, "Yield strength");
        return material;
    }

    private static Vec3 ParseForceVector(ModelObject model)
    {
        var hasComponents = model.Properties.ContainsKey("FX") || model.Properties.ContainsKey("FY") || model.Properties.ContainsKey("FZ");
        if (hasComponents)
        {
            var fx = ParseEngineeringValue(model.Properties.GetValueOrDefault("FX", "0"), $"{model.Name} FX");
            var fy = ParseEngineeringValue(model.Properties.GetValueOrDefault("FY", "0"), $"{model.Name} FY");
            var fz = ParseEngineeringValue(model.Properties.GetValueOrDefault("FZ", "0"), $"{model.Name} FZ");
            var components = new Vec3(fx, fy, fz);
            if (components.Length > 1e-12) return components;
        }

        var magnitude = ParseEngineeringValue(model.Properties.GetValueOrDefault("Magnitude", "1000 N"), $"{model.Name} magnitude");
        var direction = model.Properties.GetValueOrDefault("Direction", "Global -Z").Replace(" ", string.Empty).ToUpperInvariant();
        var unit = direction.Contains("-X") ? new Vec3(-1, 0, 0) :
            direction.Contains("+X") || direction.EndsWith("X", StringComparison.Ordinal) ? new Vec3(1, 0, 0) :
            direction.Contains("-Y") ? new Vec3(0, -1, 0) :
            direction.Contains("+Y") || direction.EndsWith("Y", StringComparison.Ordinal) ? new Vec3(0, 1, 0) :
            direction.Contains("+Z") ? new Vec3(0, 0, 1) : new Vec3(0, 0, -1);
        return unit * Math.Abs(magnitude);
    }

    private static bool TryGetCadFaceTag(ModelObject model, out int tag) =>
        int.TryParse(model.Properties.GetValueOrDefault("CadSurfaceTag"), NumberStyles.Integer, CultureInfo.InvariantCulture, out tag);

    private static bool TryProperty(ModelObject model, out string value, params string[] names)
    {
        foreach (var name in names)
            if (model.Properties.TryGetValue(name, out value!)) return true;
        value = string.Empty;
        return false;
    }

    private static double ParseEngineeringValue(string? text, string label)
    {
        var match = Regex.Match(text ?? string.Empty, @"[-+]?\d+(?:[\.,]\d+)?(?:[eE][-+]?\d+)?");
        if (!match.Success || !double.TryParse(match.Value.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out var value) || !double.IsFinite(value))
            throw new InvalidOperationException($"{label} is not a valid number: '{text}'.");
        return value;
    }

    private void ApplyGeneralSolutionToTree(GeneralCadStaticSolution solution)
    {
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }))
        {
            var model = (ModelObject)node.Tag;
            if (model.Name.Contains("Deformation", StringComparison.OrdinalIgnoreCase))
            {
                model.Properties["Minimum"] = "0 mm";
                model.Properties["Maximum"] = $"{solution.MaxDisplacementMm:G8} mm";
                model.Properties["Maximum Node"] = (solution.MaxDisplacementNode + 1).ToString("N0");
            }
            else if (model.Name.Contains("Stress", StringComparison.OrdinalIgnoreCase))
            {
                model.Properties["Minimum"] = "0 MPa";
                model.Properties["Maximum"] = $"{solution.MaxVonMisesMpa:G8} MPa";
                model.Properties["Maximum Element"] = (solution.MaxVonMisesElement + 1).ToString("N0");
            }
        }

        if (FindFirst(ObjectKind.SolutionInformation)?.Tag is ModelObject information)
        {
            information.Properties["Solver"] = "Sparse PCG with diagonal preconditioner";
            information.Properties["Iterations"] = solution.Iterations.ToString("N0");
            information.Properties["Relative Residual"] = solution.RelativeResidual.ToString("E3", CultureInfo.InvariantCulture);
            information.Properties["Force Equilibrium Error"] = solution.EquilibriumError.ToString("E3", CultureInfo.InvariantCulture);
            information.Properties["Free DOF"] = solution.FreeDofCount.ToString("N0");
            information.Properties["Elapsed"] = solution.Elapsed.ToString("g");
        }
    }

    private void EnsureGeneralResultSelectionHook()
    {
        if (_cadResultSelectionHooked) return;
        _cadResultSelectionHooked = true;
        _outline.AfterSelect += (_, _) =>
        {
            if (_cadStaticSolution is null || _outline.SelectedNode?.Tag is not ModelObject { Kind: ObjectKind.Result } result) return;
            ShowGeneralCadResults(result.Name);
        };
    }

    private void ShowGeneralCadResults(string resultName)
    {
        if (_cadVolumeMesh is null || _cadStaticSolution is null) return;
        var field = resultName.Contains("Deformation", StringComparison.OrdinalIgnoreCase)
            ? CadResultField.TotalDeformation
            : CadResultField.EquivalentStress;
        _cadCanvas?.Hide();
        _cadResultCanvas ??= new CadResultCanvas();
        if (_cadResultCanvas.Parent != _viewport)
        {
            _cadResultCanvas.Dock = DockStyle.Fill;
            _viewport.Controls.Add(_cadResultCanvas);
        }
        _cadResultCanvas.SetSolution(_cadVolumeMesh, _cadStaticSolution, field);
        _cadResultCanvas.Visible = true;
        _cadResultCanvas.BringToFront();
        PopulateGeneralCadResultTable(field);
        SelectLowerTab("Tabular Data");
        _statusMain.Text = field == CadResultField.TotalDeformation
            ? "Displaying total deformation"
            : "Displaying equivalent stress";
    }

    private void PopulateGeneralCadResultTable(CadResultField field)
    {
        if (_cadStaticSolution is null) return;
        _tabular.Columns.Clear();
        _tabular.Rows.Clear();
        foreach (var column in new[] { "Result", "Minimum", "Maximum", "Location", "Unit" })
            _tabular.Columns.Add(column, column);
        if (field == CadResultField.TotalDeformation)
            _tabular.Rows.Add("Total Deformation", "0", _cadStaticSolution.MaxDisplacementMm.ToString("G8"), $"Node {_cadStaticSolution.MaxDisplacementNode + 1:N0}", "mm");
        else
            _tabular.Rows.Add("Equivalent Stress", "0", _cadStaticSolution.MaxVonMisesMpa.ToString("G8"), $"Element {_cadStaticSolution.MaxVonMisesElement + 1:N0}", "MPa");
        _tabular.Rows.Add("PCG Relative Residual", "-", _cadStaticSolution.RelativeResidual.ToString("E3"), $"{_cadStaticSolution.Iterations:N0} iterations", "-");
        _tabular.Rows.Add("Force Equilibrium Error", "-", _cadStaticSolution.EquilibriumError.ToString("E3"), "Reaction + applied force", "-");
        _tabular.Rows.Add("Reaction X", "-", _cadStaticSolution.ReactionN.X.ToString("G8"), "Fixed support", "N");
        _tabular.Rows.Add("Reaction Y", "-", _cadStaticSolution.ReactionN.Y.ToString("G8"), "Fixed support", "N");
        _tabular.Rows.Add("Reaction Z", "-", _cadStaticSolution.ReactionN.Z.ToString("G8"), "Fixed support", "N");
    }

    private void ClearGeneralCadResults()
    {
        _cadSolveCancellation?.Cancel();
        _cadStaticSolution = null;
        if (_cadResultCanvas is not null) _cadResultCanvas.Visible = false;
        if (_cadVolumeMesh is not null) EnsureCadCanvas().Show();
    }

    private void InvalidateGeneralCadSolution()
    {
        if (_cadStaticSolution is null && _cadResultCanvas is null) return;
        _cadStaticSolution = null;
        if (_cadResultCanvas is not null) _cadResultCanvas.Visible = false;
        if (_cadVolumeMesh is not null && _cadCanvas is not null) _cadCanvas.Visible = true;
    }
}

internal enum CadResultField
{
    EquivalentStress,
    TotalDeformation
}

internal sealed class CadResultCanvas : Control
{
    private CadMesh? _mesh;
    private GeneralCadStaticSolution? _solution;
    private CadResultField _field;
    private float _zoom = 1f;
    private float _yaw = -.55f;
    private Point _last;
    private bool _dragging;

    public CadResultCanvas()
    {
        DoubleBuffered = true;
        BackColor = Color.FromArgb(236, 242, 248);
        MouseWheel += (_, eventArgs) =>
        {
            _zoom = Math.Clamp(_zoom + (eventArgs.Delta > 0 ? .1f : -.1f), .25f, 4f);
            Invalidate();
        };
        MouseDown += (_, eventArgs) =>
        {
            if (eventArgs.Button is MouseButtons.Middle or MouseButtons.Left)
            {
                _dragging = true;
                _last = eventArgs.Location;
            }
        };
        MouseMove += (_, eventArgs) =>
        {
            if (!_dragging) return;
            _yaw += (eventArgs.X - _last.X) * .01f;
            _last = eventArgs.Location;
            Invalidate();
        };
        MouseUp += (_, _) => _dragging = false;
    }

    public void SetSolution(CadMesh mesh, GeneralCadStaticSolution solution, CadResultField field)
    {
        var resetView = !ReferenceEquals(_mesh, mesh);
        _mesh = mesh;
        _solution = solution;
        _field = field;
        if (resetView)
        {
            _zoom = 1f;
            _yaw = -.55f;
        }
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var graphics = e.Graphics;
        using var background = new LinearGradientBrush(ClientRectangle, Color.White, Color.FromArgb(216, 229, 241), 90f);
        graphics.FillRectangle(background, ClientRectangle);
        DrawFloor(graphics);
        if (_mesh is null || _solution is null) return;

        var center = (_mesh.Min + _mesh.Max) / 2.0;
        var dimensions = _mesh.Max - _mesh.Min;
        var maximumDimension = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
        var scale = Math.Min(ClientSize.Width, ClientSize.Height) * .56f * _zoom / Math.Max(maximumDimension, 1e-9);
        var cosine = MathF.Cos(_yaw);
        var sine = MathF.Sin(_yaw);
        var deformationScale = _solution.MaxDisplacementMm <= 1e-18
            ? 0.0
            : Math.Min(maximumDimension * .16 / _solution.MaxDisplacementMm, 1e7);

        Vec3 DeformedNode(int node)
        {
            var displacement = new Vec3(
                _solution.Displacements[node * 3],
                _solution.Displacements[node * 3 + 1],
                _solution.Displacements[node * 3 + 2]);
            return _mesh.Nodes[node] + displacement * deformationScale;
        }

        (PointF Point, float Depth) Project(Vec3 original)
        {
            var point = original - center;
            var x = (float)point.X;
            var y = (float)point.Y;
            var z = (float)point.Z;
            var rotatedX = x * cosine - y * sine;
            var depth = x * sine + y * cosine;
            return (new PointF(
                ClientSize.Width * .50f + rotatedX * (float)scale,
                ClientSize.Height * .50f - z * (float)scale + depth * (float)scale * .34f), depth);
        }

        var values = new double[_mesh.Nodes.Count];
        for (var node = 0; node < values.Length; node++)
        {
            values[node] = _field == CadResultField.EquivalentStress
                ? _solution.NodalVonMisesMpa[node]
                : new Vec3(
                    _solution.Displacements[node * 3],
                    _solution.Displacements[node * 3 + 1],
                    _solution.Displacements[node * 3 + 2]).Length;
        }
        var surfaceNodes = _mesh.SurfaceTriangles.SelectMany(triangle => triangle).Distinct().ToArray();
        var minimum = surfaceNodes.Length == 0 ? 0 : surfaceNodes.Min(node => values[node]);
        var maximum = surfaceNodes.Length == 0 ? 1 : surfaceNodes.Max(node => values[node]);
        if (maximum - minimum <= 1e-18) maximum = minimum + 1;

        var projectedNodes = Enumerable.Range(0, _mesh.Nodes.Count).Select(node => Project(DeformedNode(node))).ToArray();
        var triangles = _mesh.SurfaceTriangles
            .Select(triangle => new ResultTriangle(
                new[] { projectedNodes[triangle[0]].Point, projectedNodes[triangle[1]].Point, projectedNodes[triangle[2]].Point },
                (projectedNodes[triangle[0]].Depth + projectedNodes[triangle[1]].Depth + projectedNodes[triangle[2]].Depth) / 3f,
                (values[triangle[0]] + values[triangle[1]] + values[triangle[2]]) / 3.0))
            .OrderBy(triangle => triangle.Depth)
            .ToArray();

        graphics.SmoothingMode = triangles.Length <= 18000 ? SmoothingMode.AntiAlias : SmoothingMode.HighSpeed;
        var edgeStride = Math.Max(1, (int)Math.Ceiling(triangles.Length / 26000.0));
        using var edge = new Pen(Color.FromArgb(52, 20, 35, 50), .45f);
        for (var index = 0; index < triangles.Length; index++)
        {
            var triangle = triangles[index];
            var normalized = Math.Clamp((triangle.Value - minimum) / (maximum - minimum), 0, 1);
            using var brush = new SolidBrush(ResultColor(normalized));
            graphics.FillPolygon(brush, triangle.Points);
            if (index % edgeStride == 0) graphics.DrawPolygon(edge, triangle.Points);
        }

        DrawHeader(graphics, minimum, maximum, deformationScale);
        DrawLegend(graphics, minimum, maximum);
        DrawTriad(graphics);
    }

    private void DrawHeader(Graphics graphics, double minimum, double maximum, double deformationScale)
    {
        if (_mesh is null || _solution is null) return;
        using var panel = new SolidBrush(Color.FromArgb(235, 255, 255, 255));
        graphics.FillRectangle(panel, 14, 13, Math.Min(780, ClientSize.Width - 28), 92);
        using var titleFont = new Font("Segoe UI Semibold", 11f);
        using var textFont = new Font("Segoe UI", 8.7f);
        var title = _field == CadResultField.EquivalentStress ? "Equivalent Stress" : "Total Deformation";
        var unit = _field == CadResultField.EquivalentStress ? "MPa" : "mm";
        graphics.DrawString(title, titleFont, Brushes.DarkSlateGray, 26, 22);
        graphics.DrawString($"Range {minimum:G6} to {maximum:G6} {unit} · {_mesh.Nodes.Count:N0} nodes · {_mesh.Tetrahedra.Count:N0} TET4", textFont, Brushes.SlateGray, 26, 48);
        graphics.DrawString($"Deformed shape scale: {deformationScale:G5}× · PCG residual {_solution.RelativeResidual:E3} · equilibrium {_solution.EquilibriumError:E3}", textFont, Brushes.SlateGray, 26, 66);
        graphics.DrawString("Drag: rotate · Wheel: zoom", textFont, Brushes.SlateGray, 26, 84);
    }

    private void DrawLegend(Graphics graphics, double minimum, double maximum)
    {
        var x = ClientSize.Width - 92;
        var y = 28;
        var height = Math.Max(180, Math.Min(320, ClientSize.Height - 150));
        for (var row = 0; row < height; row++)
        {
            var normalized = 1.0 - row / (double)Math.Max(height - 1, 1);
            using var pen = new Pen(ResultColor(normalized), 12f);
            graphics.DrawLine(pen, x, y + row, x + 1, y + row);
        }
        using var font = new Font("Segoe UI", 8f);
        var unit = _field == CadResultField.EquivalentStress ? "MPa" : "mm";
        graphics.DrawString(maximum.ToString("G5"), font, Brushes.DarkSlateGray, x - 58, y - 7);
        graphics.DrawString(((minimum + maximum) * .5).ToString("G5"), font, Brushes.DarkSlateGray, x - 58, y + height / 2 - 7);
        graphics.DrawString(minimum.ToString("G5"), font, Brushes.DarkSlateGray, x - 58, y + height - 7);
        graphics.DrawString(unit, font, Brushes.DarkSlateGray, x - 4, y + height + 8);
    }

    private void DrawFloor(Graphics graphics)
    {
        using var pen = new Pen(Color.FromArgb(35, 105, 130, 155), .7f);
        var horizon = ClientSize.Height * .77f;
        for (var index = -12; index <= 12; index++)
        {
            var x = ClientSize.Width / 2f + index * 48f;
            graphics.DrawLine(pen, x, horizon - 58, x + index * 10, ClientSize.Height);
        }
        for (var row = 0; row < 8; row++)
        {
            var y = horizon + row * row * 4.5f;
            graphics.DrawLine(pen, 0, y, ClientSize.Width, y);
        }
    }

    private void DrawTriad(Graphics graphics)
    {
        var origin = new PointF(ClientSize.Width - 68, ClientSize.Height - 55);
        using var red = new Pen(Color.FromArgb(210, 54, 54), 2f);
        using var green = new Pen(Color.FromArgb(38, 145, 74), 2f);
        using var blue = new Pen(Color.FromArgb(45, 93, 205), 2f);
        graphics.DrawLine(red, origin, new PointF(origin.X + 34, origin.Y));
        graphics.DrawLine(green, origin, new PointF(origin.X - 23, origin.Y + 20));
        graphics.DrawLine(blue, origin, new PointF(origin.X, origin.Y - 35));
        using var font = new Font("Segoe UI", 8f);
        graphics.DrawString("X", font, Brushes.Firebrick, origin.X + 36, origin.Y - 7);
        graphics.DrawString("Y", font, Brushes.ForestGreen, origin.X - 35, origin.Y + 16);
        graphics.DrawString("Z", font, Brushes.RoyalBlue, origin.X - 4, origin.Y - 49);
    }

    private static Color ResultColor(double value)
    {
        value = Math.Clamp(value, 0, 1);
        if (value < .25) return Blend(Color.FromArgb(28, 62, 190), Color.FromArgb(20, 190, 230), value / .25);
        if (value < .5) return Blend(Color.FromArgb(20, 190, 230), Color.FromArgb(45, 190, 80), (value - .25) / .25);
        if (value < .75) return Blend(Color.FromArgb(45, 190, 80), Color.FromArgb(245, 220, 35), (value - .5) / .25);
        return Blend(Color.FromArgb(245, 220, 35), Color.FromArgb(210, 42, 38), (value - .75) / .25);
    }

    private static Color Blend(Color first, Color second, double amount)
    {
        amount = Math.Clamp(amount, 0, 1);
        return Color.FromArgb(
            (int)(first.R + (second.R - first.R) * amount),
            (int)(first.G + (second.G - first.G) * amount),
            (int)(first.B + (second.B - first.B) * amount));
    }

    private sealed record ResultTriangle(PointF[] Points, float Depth, double Value);
}
