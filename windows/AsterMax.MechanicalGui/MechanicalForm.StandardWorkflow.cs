namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private int? _selectedCadSurfaceTag;
    private bool _standardWorkflowInitialized;

    protected override void OnShown(EventArgs e)
    {
        base.OnShown(e);
        if (_standardWorkflowInitialized) return;
        _standardWorkflowInitialized = true;
        _outline.AfterSelect += (_, _) => HighlightScopeForSelectedTreeObject();
        _ribbon.SelectedTab = _ribbon.TabPages.Cast<TabPage>()
            .FirstOrDefault(page => page.Text == "Workflow") ?? _ribbon.SelectedTab;
        Log("Standard workflow verification active: import -> material -> mesh -> face selection -> support/load -> solve.");
    }

    private void HandleCadFaceSelected(CadSurfaceSelection selection)
    {
        _selectedCadSurfaceTag = selection.Tag;
        _statusSelection.Text = $"Selected: Face {selection.Tag} · {selection.AreaMm2:0.###} mm²";
        Log($"CAD FACE SELECTED: Face {selection.Tag}; {selection.TriangleCount:N0} triangles; {selection.NodeCount:N0} nodes; area {selection.AreaMm2:0.###} mm².");

        if (_outline.SelectedNode?.Tag is ModelObject { Kind: ObjectKind.Support or ObjectKind.Load } model)
        {
            ScopeCadObject(_outline.SelectedNode, model, selection.Tag);
            UpdateDetails(_outline.SelectedNode);
        }
    }

    private void HighlightScopeForSelectedTreeObject()
    {
        if (_outline.SelectedNode?.Tag is not ModelObject model ||
            model.Kind is not (ObjectKind.Support or ObjectKind.Load)) return;

        if (model.Properties.TryGetValue("CadSurfaceTag", out var stored) &&
            int.TryParse(stored, NumberStyles.Integer, CultureInfo.InvariantCulture, out var existingTag))
        {
            _selectedCadSurfaceTag = existingTag;
            _cadCanvas?.SelectSurface(existingTag);
            return;
        }

        if (_selectedCadSurfaceTag is int selectedTag && (_cadVolumeMesh is not null || _cadSurfacePreview is not null))
        {
            ScopeCadObject(_outline.SelectedNode, model, selectedTag);
            UpdateDetails(_outline.SelectedNode);
        }
        else if (_cadVolumeMesh is not null || _cadSurfacePreview is not null)
        {
            _statusSelection.Text = "Select a face for " + model.Name;
            Log($"{model.Name}: select a real CAD face with a normal left click.");
        }
    }

    private void ScopeCadObject(TreeNode node, ModelObject model, int faceTag)
    {
        var mesh = _cadVolumeMesh ?? _cadSurfacePreview;
        if (mesh is null) return;
        var topology = CadTopologyRegistry.Get(mesh);
        if (!topology.Faces.TryGetValue(faceTag, out var face))
        {
            MessageBox.Show(this, $"Face {faceTag} no longer exists in the active geometry. Select the face again.", "Invalid face scope", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        model.Properties["Scoping Method"] = "Geometry Selection";
        model.Properties["Geometry"] = $"Face {faceTag}";
        model.Properties["CadSurfaceTag"] = faceTag.ToString(CultureInfo.InvariantCulture);
        model.Properties["Scoped Nodes"] = face.NodeIndices.Count.ToString("N0");
        model.Properties["Scoped Triangles"] = face.TriangleIndices.Count.ToString("N0");
        model.Properties["Surface Area"] = $"{face.AreaMm2:0.###} mm²";
        if (model.Kind == ObjectKind.Load)
        {
            model.Properties.TryAdd("Define By", "Components");
            model.Properties.TryAdd("Magnitude", "1000 N");
            model.Properties.TryAdd("Direction", "Global -Z");
            model.Properties.TryAdd("FX", "0 N");
            model.Properties.TryAdd("FY", "0 N");
            model.Properties.TryAdd("FZ", "-1000 N");
        }
        SetState(node, ObjectState.Ready);
        MarkSolutionDirty();
        RefreshCadScopeMarkers();
        RefreshWorkflowChecklist(true);
        Log($"{model.Name} scoped to real CAD Face {faceTag} ({face.NodeIndices.Count:N0} nodes, {face.AreaMm2:0.###} mm²)." );
    }

    private void RefreshCadScopeMarkers()
    {
        if (_cadCanvas is null) return;
        _cadCanvas.SetScopeMarkers(ScopedCadTags(ObjectKind.Support), ScopedCadTags(ObjectKind.Load));
    }

    private IEnumerable<int> ScopedCadTags(ObjectKind kind) => AllNodes()
        .Where(node => node.Tag is ModelObject model && model.Kind == kind && model.State != ObjectState.Suppressed)
        .Select(node => ((ModelObject)node.Tag).Properties.GetValueOrDefault("CadSurfaceTag"))
        .Where(value => int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out _))
        .Select(value => int.Parse(value!, CultureInfo.InvariantCulture));
}

internal static class StandardWorkflowVerifier
{
    public static int Run(string[] args)
    {
        try
        {
            var solid = new SimpleStepSolid
            {
                SourcePath = "standard-workflow.step",
                Min = new Vec3(0, 0, 0),
                Max = new Vec3(200, 40, 20),
                CartesianPointCount = 8,
                IsSupportedPrism = true,
                FidelityMessage = "Standard workflow prism"
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
            var solution = Tet4LinearStaticSolver.Solve(solid, mesh, material, setup);
            Require(solution.EquilibriumError <= 1e-7, "Standard prism workflow failed equilibrium.");

            if (args.Length >= 3)
            {
                var gmsh = args[1];
                var step = args[2];
                var envelope = SimpleStepReader.ReadPrismaticSolid(step);
                var target = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ)) / 8.0;
                var cadMesh = SelectableGmshMesher.GenerateAsync(gmsh, step, target, 3, CancellationToken.None).GetAwaiter().GetResult();
                var topology = CadTopologyRegistry.Get(cadMesh);
                Require(cadMesh.Tetrahedra.Count > 0, "CAD workflow produced no TET4 elements.");
                Require(topology.Faces.Count >= 4, "CAD workflow did not preserve selectable boundary faces.");
                var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
                var support = ordered.First();
                var load = ordered.Last();
                Require(support.Tag != load.Tag, "CAD workflow selected the same surface for support and load.");
                Require(support.NodeIndices.Count > 0 && load.NodeIndices.Count > 0, "CAD workflow produced empty face scopes.");
                Console.WriteLine($"Standard CAD workflow passed | {cadMesh.Nodes.Count} nodes, {cadMesh.Tetrahedra.Count} TET4, {topology.Faces.Count} selectable faces, support Face {support.Tag}, load Face {load.Tag}");
            }

            Console.WriteLine($"Standard prism workflow passed | {mesh.Nodes.Count} nodes, {mesh.Elements.Count} TET4, Umax={solution.MaxDisplacementMm:G8} mm, VM={solution.MaxVonMisesMpa:G8} MPa");
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
}
