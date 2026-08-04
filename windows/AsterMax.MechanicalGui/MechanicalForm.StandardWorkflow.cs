namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private int? _selectedCadSurfaceTag;
    private SimpleFace? _selectedSimpleFace;

    private void InitializeStandardWorkflowIntegration()
    {
        _viewport.FaceSelected += HandleSimpleFaceSelected;
        _outline.AfterSelect += (_, _) => HighlightScopeForSelectedTreeObject();
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

    private void HandleSimpleFaceSelected(SimpleFace face)
    {
        _selectedSimpleFace = face;
        _statusSelection.Text = $"Selected: {face}";
        Log($"PRISM FACE SELECTED: {face}.");
        if (_outline.SelectedNode?.Tag is ModelObject { Kind: ObjectKind.Support or ObjectKind.Load } model)
        {
            ScopeSimpleObject(_outline.SelectedNode, model, face);
            UpdateDetails(_outline.SelectedNode);
        }
    }

    private bool TryAddScopedSupport(string type)
    {
        if (CadGeometryActive)
        {
            if (_selectedCadSurfaceTag is not int tag)
            {
                RequestFaceSelection("Select a CAD face in the Graphics window, then press Fixed Support.");
                return true;
            }
            var node = InsertAnalysisObject(type, ObjectKind.Support, "Support");
            ScopeCadObject(node, (ModelObject)node.Tag, tag);
            return true;
        }

        if (_simpleSolid is not null)
        {
            if (_selectedSimpleFace is not SimpleFace face)
            {
                RequestFaceSelection("Select one prism face in the Graphics window, then press Fixed Support.");
                return true;
            }
            var node = InsertAnalysisObject(type, ObjectKind.Support, "Support");
            ScopeSimpleObject(node, (ModelObject)node.Tag, face);
            return true;
        }
        return false;
    }

    private bool TryAddScopedLoad(string type)
    {
        if (type == "Gravity") return false;
        if (CadGeometryActive)
        {
            if (_selectedCadSurfaceTag is not int tag)
            {
                RequestFaceSelection($"Select a CAD face in the Graphics window, then press {type}.");
                return true;
            }
            var node = InsertAnalysisObject(type, ObjectKind.Load, "Load");
            InitializeLoadProperties((ModelObject)node.Tag, type);
            ScopeCadObject(node, (ModelObject)node.Tag, tag);
            return true;
        }

        if (_simpleSolid is not null)
        {
            if (_selectedSimpleFace is not SimpleFace face)
            {
                RequestFaceSelection($"Select one prism face in the Graphics window, then press {type}.");
                return true;
            }
            var node = InsertAnalysisObject(type, ObjectKind.Load, "Load");
            InitializeLoadProperties((ModelObject)node.Tag, type);
            ScopeSimpleObject(node, (ModelObject)node.Tag, face);
            return true;
        }
        return false;
    }

    private TreeNode InsertAnalysisObject(string type, ObjectKind kind, string category)
    {
        var analysis = SelectedAnalysis() ?? FirstAnalysis()
            ?? throw new InvalidOperationException("No analysis system exists in the project tree.");
        var count = kind == ObjectKind.Support ? _supportCount++ : _loadCount++;
        var name = count == 0 ? type : $"{type} {count + 1}";
        var node = MakeNode(name, kind, ObjectState.Ready, category);
        analysis.Nodes.Insert(Math.Max(1, analysis.Nodes.Count - 1), node);
        analysis.Expand();
        _outline.SelectedNode = node;
        return node;
    }

    private static void InitializeLoadProperties(ModelObject model, string type)
    {
        model.Properties["Define By"] = "Components";
        model.Properties["Magnitude"] = DefaultMagnitude(type);
        model.Properties["Direction"] = "Global -Z";
        model.Properties["FX"] = "0 N";
        model.Properties["FY"] = "0 N";
        model.Properties["FZ"] = "-1000 N";
    }

    private void ScopeCadObject(TreeNode node, ModelObject model, int faceTag)
    {
        var mesh = _cadVolumeMesh ?? _cadSurfacePreview;
        if (mesh is null) return;
        var topology = CadTopologyRegistry.Get(mesh);
        if (!topology.Faces.TryGetValue(faceTag, out var face))
        {
            MessageBox.Show(this, $"Face {faceTag} no longer exists in the active mesh. Select it again.", "Invalid face scope", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        model.Properties["Scoping Method"] = "Geometry Selection";
        model.Properties["Geometry"] = $"Face {faceTag}";
        model.Properties["CadSurfaceTag"] = faceTag.ToString(CultureInfo.InvariantCulture);
        model.Properties["Scoped Nodes"] = face.NodeIndices.Count.ToString("N0");
        model.Properties["Scoped Triangles"] = face.TriangleIndices.Count.ToString("N0");
        model.Properties["Surface Area"] = $"{face.AreaMm2:0.###} mm²";
        SetState(node, ObjectState.Ready);
        MarkSolutionDirty();
        RefreshCadScopeMarkers();
        Log($"{model.Name} scoped to real CAD Face {faceTag} ({face.NodeIndices.Count:N0} nodes)." );
        RefreshWorkflowChecklist(true);
    }

    private void ScopeSimpleObject(TreeNode node, ModelObject model, SimpleFace face)
    {
        model.Properties["Scoping Method"] = "Geometry Selection";
        model.Properties["Geometry"] = face.ToString();
        model.Properties["SimpleFace"] = face.ToString();
        SetState(node, ObjectState.Ready);
        if (model.Kind == ObjectKind.Support)
        {
            _simpleSetup.FixedFace = face;
            _viewport.FixedFace = face;
            _viewport.SupportVisible = true;
        }
        else if (model.Kind == ObjectKind.Load)
        {
            _simpleSetup.LoadFace = face;
            _simpleSetup.ForceN = ReadForce(model);
            _viewport.LoadFace = face;
            _viewport.ForceVector = _simpleSetup.ForceN;
            _viewport.ForceVisible = true;
        }
        _simpleSetupDefined = WorkflowSupportReady() && WorkflowLoadReady();
        _viewport.Invalidate();
        MarkSolutionDirty();
        Log($"{model.Name} scoped to real prism face {face}." );
        RefreshWorkflowChecklist(true);
    }

    private void RequestFaceSelection(string message)
    {
        _statusSelection.Text = "Select a face";
        MessageBox.Show(this, message + "\n\nRotate with Ctrl + drag or the middle mouse button; a normal left click selects a face.", "Face selection required", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private void HighlightScopeForSelectedTreeObject()
    {
        if (_outline.SelectedNode?.Tag is not ModelObject model) return;
        if (model.Properties.TryGetValue("CadSurfaceTag", out var cadText) &&
            int.TryParse(cadText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var cadTag))
        {
            _selectedCadSurfaceTag = cadTag;
            _cadCanvas?.SelectSurface(cadTag);
        }
        else if (model.Properties.TryGetValue("SimpleFace", out var simpleText) &&
                 Enum.TryParse<SimpleFace>(simpleText, out var simpleFace))
        {
            _selectedSimpleFace = simpleFace;
            _viewport.SelectFace(simpleFace);
        }
    }

    private void RefreshCadScopeMarkers()
    {
        if (_cadCanvas is null) return;
        var supports = ScopedCadTags(ObjectKind.Support);
        var loads = ScopedCadTags(ObjectKind.Load);
        _cadCanvas.SetScopeMarkers(supports, loads);
    }

    private IEnumerable<int> ScopedCadTags(ObjectKind kind) => AllNodes()
        .Where(node => node.Tag is ModelObject model && model.Kind == kind && model.State != ObjectState.Suppressed)
        .Select(node => ((ModelObject)node.Tag).Properties.GetValueOrDefault("CadSurfaceTag"))
        .Where(value => int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out _))
        .Select(value => int.Parse(value!, CultureInfo.InvariantCulture));

    private bool CadGeometryActive => _cadStepPath is not null && (_cadSurfacePreview is not null || _cadVolumeMesh is not null);

    private bool WorkflowSupportReady()
    {
        var supports = AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed }).ToArray();
        if (supports.Length == 0) return false;
        if (CadGeometryActive) return supports.Any(node => ((ModelObject)node.Tag).Properties.ContainsKey("CadSurfaceTag"));
        if (_simpleSolid is not null) return supports.Any(node => ((ModelObject)node.Tag).Properties.ContainsKey("SimpleFace"));
        return true;
    }

    private bool WorkflowLoadReady()
    {
        var loads = AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed }).ToArray();
        if (loads.Length == 0) return false;
        if (CadGeometryActive) return loads.Any(node => ((ModelObject)node.Tag).Properties.ContainsKey("CadSurfaceTag"));
        if (_simpleSolid is not null) return loads.Any(node => ((ModelObject)node.Tag).Properties.ContainsKey("SimpleFace"));
        return true;
    }

    private IEnumerable<string> WorkflowScopeIssues()
    {
        if (!WorkflowSupportReady()) yield return "Insert a fixed support scoped to a selected face.";
        if (!WorkflowLoadReady()) yield return "Insert a load scoped to a selected face.";
        if (CadGeometryActive && _cadVolumeMesh is null) yield return "Generate the volume mesh after importing the STEP.";
        if (_simpleSolid is not null && WorkflowSupportReady() && WorkflowLoadReady())
        {
            TryBuildSimpleSetupFromTree(out var message);
            if (message is not null) yield return message;
        }
    }

    private bool TryBuildSimpleSetupFromTree(out string? issue)
    {
        issue = null;
        if (_simpleSolid is null) return false;
        var support = AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed } model && model.Properties.ContainsKey("SimpleFace"));
        var load = AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed } model && model.Properties.ContainsKey("SimpleFace"));
        if (support?.Tag is not ModelObject supportModel || load?.Tag is not ModelObject loadModel)
        {
            issue = "The prism requires one face-scoped support and one face-scoped load.";
            return false;
        }
        if (!Enum.TryParse<SimpleFace>(supportModel.Properties["SimpleFace"], out var fixedFace) ||
            !Enum.TryParse<SimpleFace>(loadModel.Properties["SimpleFace"], out var loadFace))
        {
            issue = "A scoped prism face is invalid.";
            return false;
        }
        var force = ReadForce(loadModel);
        if (fixedFace == loadFace)
        {
            issue = "Fixed support and force cannot use the same face.";
            return false;
        }
        if (force.Length <= 1e-12)
        {
            issue = "The force vector is zero. Edit FX, FY or FZ in Details.";
            return false;
        }
        _simpleSetup.FixedFace = fixedFace;
        _simpleSetup.LoadFace = loadFace;
        _simpleSetup.ForceN = force;
        _simpleSetupDefined = true;
        _viewport.FixedFace = fixedFace;
        _viewport.LoadFace = loadFace;
        _viewport.ForceVector = force;
        _viewport.SupportVisible = true;
        _viewport.ForceVisible = true;
        return true;
    }

    private void SynchronizeWorkflowObject(ModelObject model)
    {
        if (_simpleSolid is not null && model.Kind is ObjectKind.Support or ObjectKind.Load)
        {
            TryBuildSimpleSetupFromTree(out _);
            _viewport.Invalidate();
        }
        RefreshCadScopeMarkers();
        RefreshWorkflowChecklist(true);
    }

    private static Vec3 ReadForce(ModelObject model) => new(
        ParseEngineeringNumber(model.Properties.GetValueOrDefault("FX", "0")),
        ParseEngineeringNumber(model.Properties.GetValueOrDefault("FY", "0")),
        ParseEngineeringNumber(model.Properties.GetValueOrDefault("FZ", "-1000")));

    private static double ParseEngineeringNumber(string value)
    {
        var token = new string(value.Trim().TakeWhile(character => char.IsDigit(character) || character is '+' or '-' or '.' or ',' or 'e' or 'E').ToArray()).Replace(',', '.');
        return double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed) ? parsed : 0.0;
    }
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
