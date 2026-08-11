namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private void BuildProjectTree()
    {
        _outline.BeginUpdate();
        _outline.Nodes.Clear();
        _nodes.Clear();

        var project = MakeNode("Project", ObjectKind.Project, ObjectState.Ready, "Project");
        var model = MakeNode("Model", ObjectKind.Model, ObjectState.NeedsAttention, "Model");
        var geometry = MakeNode("Geometry", ObjectKind.Geometry, ObjectState.NeedsAttention, "Geometry");
        var materials = MakeNode("Materials", ObjectKind.Materials, ObjectState.UpToDate, "Materials");
        materials.Nodes.Add(MakeNode("Structural Steel", ObjectKind.Material, ObjectState.UpToDate, "Material"));
        var coordinates = MakeNode("Coordinate Systems", ObjectKind.CoordinateSystems, ObjectState.UpToDate, "Coordinate Systems");
        coordinates.Nodes.Add(MakeNode("Global Coordinate System", ObjectKind.CoordinateSystem, ObjectState.UpToDate, "Coordinate System"));
        var connections = MakeNode("Connections", ObjectKind.Connections, ObjectState.Ready, "Connections");
        var namedSelections = MakeNode("Named Selections", ObjectKind.NamedSelections, ObjectState.Ready, "Named Selections");
        var mesh = MakeNode("Mesh", ObjectKind.Mesh, ObjectState.NeedsAttention, "Mesh");
        model.Nodes.AddRange(new[] { geometry, materials, coordinates, connections, namedSelections, mesh });

        var analysis = CreateAnalysisNode("Static Structural");
        project.Nodes.Add(model);
        project.Nodes.Add(analysis);
        _outline.Nodes.Add(project);
        project.Expand();
        model.Expand();
        analysis.Expand();
        _outline.EndUpdate();
        RefreshWorkflow();
    }

    private TreeNode CreateAnalysisNode(string name)
    {
        var analysis = MakeNode(name, ObjectKind.Analysis, ObjectState.NeedsAttention, name);
        var settings = MakeNode("Analysis Settings", ObjectKind.AnalysisSettings, ObjectState.Ready, "Analysis Settings");
        var solution = MakeNode("Solution", ObjectKind.Solution, ObjectState.NeedsAttention, "Solution");
        solution.Nodes.Add(MakeNode("Solution Information", ObjectKind.SolutionInformation, ObjectState.Ready, "Solution Information"));
        solution.Nodes.Add(MakeNode("Total Deformation", ObjectKind.Result, ObjectState.NeedsAttention, "Result"));
        solution.Nodes.Add(MakeNode("Equivalent Stress", ObjectKind.Result, ObjectState.NeedsAttention, "Result"));
        analysis.Nodes.Add(settings);
        analysis.Nodes.Add(solution);
        return analysis;
    }

    private void WireEvents()
    {
        _outline.DrawNode += DrawTreeNode;
        // Selection rendering is owned exclusively by InstallStableSelectionController().
        _outline.NodeMouseClick += (_, e) =>
        {
            if (e.Button != MouseButtons.Right) return;
            _outline.SelectedNode = e.Node;
            BuildContextMenu(e.Node).Show(_outline, e.Location);
        };
        _outline.AfterLabelEdit += (_, e) =>
        {
            if (e.Label is not null && e.Node?.Tag is ModelObject obj) obj.Name = e.Label;
        };
        _details.CellEndEdit += (_, e) => SavePropertyEdit(e.RowIndex);
        KeyDown += (_, e) =>
        {
            if (e.KeyCode == Keys.F7) { _viewport.Fit(); e.Handled = true; }
            if (e.KeyCode == Keys.F5) { _ = SolveAsync(); e.Handled = true; }
            if (e.KeyCode == Keys.Delete) { DeleteSelected(); e.Handled = true; }
        };
        DragEnter += (_, e) =>
        {
            if (e.Data?.GetDataPresent(DataFormats.FileDrop) == true) e.Effect = DragDropEffects.Copy;
        };
        DragDrop += (_, e) =>
        {
            if (e.Data?.GetData(DataFormats.FileDrop) is not string[] files || files.Length == 0) return;
            var file = files[0];
            var ext = Path.GetExtension(file).ToLowerInvariant();
            if (ext is ".step" or ".stp" or ".iges" or ".igs" or ".brep") ImportGeometry(file);
            else if (ext is ".med" or ".msh") ImportMesh(file);
            else if (ext == ".json") OpenProject(file);
            else if (ext == ".export") _ = RunExportAsync(file);
        };
        FormClosing += (_, e) =>
        {
            if (!_busy) return;
            e.Cancel = true;
            MessageBox.Show(this, "Wait for the current operation to finish.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        };
    }

    private void OnObjectSelected(TreeNode? node)
    {
        if (node?.Tag is not ModelObject obj) return;
        _statusSelection.Text = $"Selected: {obj.Name}";
        _contextTitle.Text = $"{obj.Category}\n{obj.Name}";
        UpdateContextCommands(node);
        UpdateDetails(node);
        PopulateWorksheet(node);
        UpdateViewport(node);
        HighlightWorkflow(node);
    }

    private void UpdateViewport(TreeNode node)
    {
        if (node.Tag is not ModelObject obj) return;
        _viewport.Caption = obj.Category;
        _viewport.SubCaption = obj.Name;
        _viewport.MeshVisible = _meshGenerated || obj.Kind is ObjectKind.Mesh or ObjectKind.MeshControl;
        _viewport.SupportVisible = obj.Kind == ObjectKind.Support || AllNodes().Any(n => n.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed });
        _viewport.ForceVisible = obj.Kind == ObjectKind.Load || AllNodes().Any(n => n.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed });
        _viewport.ResultVisible = obj.Kind is ObjectKind.Result or ObjectKind.Probe || obj.Kind == ObjectKind.Solution && _solved;
        _viewport.Invalidate();
        if (_viewport.ResultVisible)
        {
            PopulateResultTable(obj.Name);
            _lowerTabs.SelectedIndex = 3;
        }
    }

    private void UpdateContextCommands(TreeNode node)
    {
        _contextButtons.Controls.Clear();
        if (node.Tag is not ModelObject obj) return;
        void Add(string text, Action action, bool primary = false) => _contextButtons.Controls.Add(RButton(text, action, primary));

        switch (obj.Kind)
        {
            case ObjectKind.Project:
                Add("Import Geometry", ImportGeometry, true);
                Add("Add Analysis", () => AddAnalysis("Static Structural"));
                Add("Save", () => SaveProject(false));
                break;
            case ObjectKind.Geometry:
                Add("Import", ImportGeometry, true);
                Add("Assign Material", AssignMaterial);
                Add("Named Selection", AddNamedSelection);
                break;
            case ObjectKind.Connections:
                Add("Automatic Contacts", CreateContacts, true);
                Add("Contact Region", AddContact);
                Add("Worksheet", ShowConnectionsWorksheet);
                break;
            case ObjectKind.Mesh:
                Add("Generate", GenerateMesh, true);
                Add("Sizing", () => AddMeshControl("Sizing"));
                Add("Method", () => AddMeshControl("Method"));
                Add("Quality", () => ShowMeshMetric("Element Quality"));
                break;
            case ObjectKind.Analysis:
                Add("Fixed Support", () => AddSupport("Fixed Support"));
                Add("Force", () => AddLoad("Force"));
                Add("Solve", () => _ = SolveAsync(), true);
                break;
            case ObjectKind.Solution:
                Add("Solve", () => _ = SolveAsync(), true);
                Add("Deformation", () => AddResult("Total Deformation"));
                Add("Stress", () => AddResult("Equivalent Stress"));
                Add("Evaluate All", EvaluateResults);
                break;
            case ObjectKind.Result:
            case ObjectKind.Probe:
                Add("Evaluate", EvaluateResults, true);
                Add("Chart", AddChart);
                Add("Export CSV", ExportResultCsv);
                break;
            default:
                Add("Duplicate", DuplicateSelected);
                Add("Suppress", ToggleSuppression);
                Add("Delete", DeleteSelected);
                break;
        }
    }

    private ContextMenuStrip BuildContextMenu(TreeNode node)
    {
        var menu = new ContextMenuStrip { Renderer = new DarkRenderer(), BackColor = Panel2, ForeColor = TextMain };
        if (node.Tag is not ModelObject obj) return menu;
        menu.Items.Add(Item("Rename", (_, _) => RenameSelected(), Keys.F2));
        menu.Items.Add(Item("Duplicate", (_, _) => DuplicateSelected()));
        menu.Items.Add(Item(obj.State == ObjectState.Suppressed ? "Unsuppress" : "Suppress", (_, _) => ToggleSuppression()));
        menu.Items.Add(new ToolStripSeparator());
        if (obj.Kind == ObjectKind.Geometry)
        {
            menu.Items.Add(Item("Import Geometry...", (_, _) => ImportGeometry()));
            menu.Items.Add(Item("Insert Named Selection", (_, _) => AddNamedSelection()));
        }
        else if (obj.Kind == ObjectKind.Mesh)
        {
            menu.Items.Add(Item("Generate Mesh", (_, _) => GenerateMesh()));
            menu.Items.Add(Item("Insert Sizing", (_, _) => AddMeshControl("Sizing")));
            menu.Items.Add(Item("Insert Method", (_, _) => AddMeshControl("Method")));
        }
        else if (obj.Kind == ObjectKind.Analysis)
        {
            menu.Items.Add(Item("Insert Fixed Support", (_, _) => AddSupport("Fixed Support")));
            menu.Items.Add(Item("Insert Force", (_, _) => AddLoad("Force")));
            menu.Items.Add(Item("Solve", async (_, _) => await SolveAsync()));
        }
        else if (obj.Kind == ObjectKind.Solution)
        {
            menu.Items.Add(Item("Insert Total Deformation", (_, _) => AddResult("Total Deformation")));
            menu.Items.Add(Item("Insert Equivalent Stress", (_, _) => AddResult("Equivalent Stress")));
            menu.Items.Add(Item("Evaluate All", (_, _) => EvaluateResults()));
        }
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(Item("Delete", (_, _) => DeleteSelected(), Keys.Delete));
        return menu;
    }

    private void DrawTreeNode(object? sender, DrawTreeNodeEventArgs e)
    {
        if (e.Node.Tag is not ModelObject obj) return;
        var selected = (e.State & TreeNodeStates.Selected) != 0;
        using var bg = new SolidBrush(selected ? Color.FromArgb(57, 91, 132) : _outline.BackColor);
        e.Graphics.FillRectangle(bg, e.Bounds.X, e.Bounds.Y, Math.Max(e.Bounds.Width + 220, _outline.ClientSize.Width - e.Bounds.X), e.Bounds.Height);
        using var dot = new SolidBrush(StateColor(obj.State));
        var y = e.Bounds.Top + e.Bounds.Height / 2 - 4;
        e.Graphics.FillEllipse(dot, e.Bounds.Left, y, 8, 8);
        var bold = obj.Kind is ObjectKind.Project or ObjectKind.Model or ObjectKind.Analysis or ObjectKind.Solution;
        using var font = new Font(Font, bold ? FontStyle.Bold : FontStyle.Regular);
        using var brush = new SolidBrush(obj.State == ObjectState.Suppressed ? TextMuted : TextMain);
        e.Graphics.DrawString(e.Node.Text, font, brush, e.Bounds.Left + 14, e.Bounds.Top + 2);
    }

    private void FilterTree(string filter)
    {
        foreach (var node in AllNodes())
            node.BackColor = !string.IsNullOrWhiteSpace(filter) && node.Text.Contains(filter, StringComparison.OrdinalIgnoreCase)
                ? Color.FromArgb(95, 82, 40)
                : Color.Empty;
    }

    private void RefreshWorkflow()
    {
        foreach (Control control in _workflow.Controls)
        {
            if (control.Tag is not string key) continue;
            var complete = key switch
            {
                "Project" => true,
                "Model" => _nodes.TryGetValue("Geometry", out var geometry) && geometry.Nodes.Count > 0 && _meshGenerated,
                "Analysis Settings" => ValidateModel().Count == 0,
                "Solution" => _solved,
                _ => false
            };
            control.BackColor = complete ? Color.FromArgb(45, 106, 78) : Panel2;
            control.ForeColor = complete ? Color.FromArgb(210, 255, 227) : TextMain;
        }
        _outline.Invalidate();
    }

    private void HighlightWorkflow(TreeNode node)
    {
        var stage = node.Tag is ModelObject obj ? obj.Kind switch
        {
            ObjectKind.Project => "Project",
            ObjectKind.Model or ObjectKind.Geometry or ObjectKind.Body or ObjectKind.Materials or ObjectKind.Material or ObjectKind.CoordinateSystems or ObjectKind.CoordinateSystem or ObjectKind.Connections or ObjectKind.Contact or ObjectKind.NamedSelections or ObjectKind.NamedSelection or ObjectKind.Mesh or ObjectKind.MeshControl => "Model",
            ObjectKind.Analysis or ObjectKind.AnalysisSettings or ObjectKind.Support or ObjectKind.Load => "Analysis Settings",
            _ => "Solution"
        } : string.Empty;
        foreach (Control control in _workflow.Controls)
        {
            if (control is not Button button || control.Tag is not string key) continue;
            button.FlatAppearance.BorderColor = key == stage ? Accent : Border;
            button.FlatAppearance.BorderSize = key == stage ? 2 : 1;
        }
    }

    private TreeNode MakeNode(string name, ObjectKind kind, ObjectState state, string category)
    {
        var obj = new ModelObject { Name = name, Kind = kind, State = state, Category = category };
        var node = new TreeNode(name) { Tag = obj, ForeColor = TextMain };
        if (!_nodes.ContainsKey(name)) _nodes[name] = node;
        return node;
    }

    private void AddSimpleObject(string parentName, string name, ObjectKind kind, string category)
    {
        if (!_nodes.TryGetValue(parentName, out var parent)) return;
        var unique = name;
        var index = 2;
        while (parent.Nodes.Cast<TreeNode>().Any(n => n.Text == unique)) unique = $"{name} {index++}";
        var node = MakeNode(unique, kind, ObjectState.Ready, category);
        parent.Nodes.Add(node);
        parent.Expand();
        _outline.SelectedNode = node;
        MarkSolutionDirty();
    }

    private TreeNode? SelectedAnalysis()
    {
        var node = _outline.SelectedNode;
        while (node is not null)
        {
            if (node.Tag is ModelObject { Kind: ObjectKind.Analysis }) return node;
            node = node.Parent;
        }
        return null;
    }

    private TreeNode? SelectedSolution()
    {
        var node = _outline.SelectedNode;
        while (node is not null)
        {
            if (node.Tag is ModelObject { Kind: ObjectKind.Solution }) return node;
            node = node.Parent;
        }
        return null;
    }

    private TreeNode? FirstAnalysis() => AllNodes().FirstOrDefault(n => n.Tag is ModelObject { Kind: ObjectKind.Analysis });
    private TreeNode? FindFirst(ObjectKind kind) => AllNodes().FirstOrDefault(n => n.Tag is ModelObject obj && obj.Kind == kind);

    private IEnumerable<TreeNode> AllNodes()
    {
        foreach (TreeNode root in _outline.Nodes)
            foreach (var node in Enumerate(root)) yield return node;
    }

    private static IEnumerable<TreeNode> Enumerate(TreeNode node)
    {
        yield return node;
        foreach (TreeNode child in node.Nodes)
            foreach (var nested in Enumerate(child)) yield return nested;
    }

    private void SelectNode(string key)
    {
        if (!_nodes.TryGetValue(key, out var node))
            node = AllNodes().FirstOrDefault(n => n.Text.Equals(key, StringComparison.OrdinalIgnoreCase));
        if (node is null) return;

        var changed = !ReferenceEquals(_outline.SelectedNode, node);
        _outline.SelectedNode = node;
        node.EnsureVisible();

        // AfterSelect is not emitted when the same selected node is assigned again. STEP
        // import commonly updates Geometry while Geometry is already selected, so force the
        // one stable synchronous render in that exact case.
        if (!changed)
            ActivateStableTreeNode(node, "same-node-refresh");
    }

    private static void SetState(TreeNode? node, ObjectState state)
    {
        if (node?.Tag is ModelObject obj) obj.State = state;
        node?.TreeView?.Invalidate();
    }

    private static Color StateColor(ObjectState state) => state switch
    {
        ObjectState.NeedsAttention => Yellow,
        ObjectState.Ready => Color.FromArgb(85, 160, 230),
        ObjectState.Updating => Accent,
        ObjectState.UpToDate => Green,
        ObjectState.Solved => Color.FromArgb(100, 225, 145),
        ObjectState.Suppressed => Color.FromArgb(120, 125, 135),
        ObjectState.Error => Red,
        _ => Color.Gray
    };

    private static string StateText(ObjectState state) => state switch
    {
        ObjectState.NeedsAttention => "Needs attention",
        ObjectState.Ready => "Ready for input",
        ObjectState.Updating => "Updating",
        ObjectState.UpToDate => "Up-to-date",
        ObjectState.Solved => "Solved",
        ObjectState.Suppressed => "Suppressed",
        ObjectState.Error => "Error",
        _ => "Undefined"
    };
}
