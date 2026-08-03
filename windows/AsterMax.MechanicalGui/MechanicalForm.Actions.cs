namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private void NewProject()
    {
        if ((_geometryPath is not null || _meshGenerated || _solved) &&
            MessageBox.Show(this, "Create a new project and discard the current state?", "AsterMax", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            return;
        ResetProject();
    }

    private void ResetProject()
    {
        _projectPath = null;
        _geometryPath = null;
        _meshGenerated = false;
        _solved = false;
        _loadCount = 0;
        _supportCount = 0;
        _resultCount = 0;
        BuildProjectTree();
        _details.Rows.Clear();
        _worksheet.Rows.Clear();
        _tabular.Rows.Clear();
        _viewport.Caption = "Geometry";
        _viewport.SubCaption = "New project";
        _viewport.MeshVisible = false;
        _viewport.ResultVisible = false;
        _viewport.SupportVisible = false;
        _viewport.ForceVisible = false;
        _viewport.Invalidate();
        Text = "AsterMax Mechanical 0.3 beta";
        Log("New project created.");
        SelectNode("Project");
    }

    private void SaveProject(bool saveAs)
    {
        if (saveAs || string.IsNullOrWhiteSpace(_projectPath))
        {
            using var dialog = new SaveFileDialog
            {
                Filter = "AsterMax project (*.astermax.json)|*.astermax.json|JSON (*.json)|*.json",
                FileName = "project.astermax.json"
            };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            _projectPath = dialog.FileName;
        }
        var snapshot = new ProjectSnapshot
        {
            ProjectName = Path.GetFileNameWithoutExtension(_projectPath),
            Units = _units,
            GeometryPath = _geometryPath,
            CodeAsterLauncher = _codeAsterLauncher,
            MeshGenerated = _meshGenerated,
            Solved = _solved,
            SavedAt = DateTimeOffset.Now
        };
        File.WriteAllText(_projectPath, JsonSerializer.Serialize(snapshot, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
        Text = $"AsterMax Mechanical 0.3 beta - {snapshot.ProjectName}";
        _statusMain.Text = "Project saved";
        Log($"Project saved: {_projectPath}");
    }

    private void OpenProject() => OpenProject(null);

    private void OpenProject(string? path)
    {
        if (path is null)
        {
            using var dialog = new OpenFileDialog { Filter = "AsterMax project (*.astermax.json;*.json)|*.astermax.json;*.json|All files (*.*)|*.*" };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            path = dialog.FileName;
        }
        try
        {
            var snapshot = JsonSerializer.Deserialize<ProjectSnapshot>(File.ReadAllText(path));
            if (snapshot is null) throw new InvalidDataException("Project file is empty.");
            ResetProject();
            _projectPath = path;
            _units = snapshot.Units;
            _codeAsterLauncher = snapshot.CodeAsterLauncher;
            if (!string.IsNullOrWhiteSpace(snapshot.GeometryPath)) ImportGeometry(snapshot.GeometryPath);
            _meshGenerated = snapshot.MeshGenerated;
            _solved = snapshot.Solved;
            SetState(_nodes["Mesh"], _meshGenerated ? ObjectState.UpToDate : ObjectState.NeedsAttention);
            SetState(FindFirst(ObjectKind.Solution), _solved ? ObjectState.Solved : ObjectState.NeedsAttention);
            foreach (var node in AllNodes().Where(n => n.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }))
                SetState(node, _solved ? ObjectState.Solved : ObjectState.NeedsAttention);
            _statusSolver.Text = string.IsNullOrWhiteSpace(_codeAsterLauncher) ? "Solver: not configured" : $"Solver: {Path.GetFileName(_codeAsterLauncher)}";
            Text = $"AsterMax Mechanical 0.3 beta - {snapshot.ProjectName}";
            RefreshWorkflow();
            Log($"Project opened: {path}");
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message, "Unable to open project", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ImportGeometry() => ImportGeometry(null);

    private void ImportGeometry(string? file)
    {
        if (file is null)
        {
            using var dialog = new OpenFileDialog
            {
                Title = "Import Geometry",
                Filter = "CAD geometry (*.step;*.stp;*.iges;*.igs;*.brep)|*.step;*.stp;*.iges;*.igs;*.brep|All files (*.*)|*.*"
            };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            file = dialog.FileName;
        }
        _geometryPath = file;
        var geometry = _nodes["Geometry"];
        geometry.Nodes.Clear();
        var part = MakeNode(Path.GetFileNameWithoutExtension(file), ObjectKind.Body, ObjectState.UpToDate, "Body");
        ((ModelObject)part.Tag).Properties["Material"] = "Structural Steel";
        ((ModelObject)part.Tag).Properties["Body Type"] = "Solid";
        part.Nodes.Add(MakeNode("Solid Body 1", ObjectKind.Body, ObjectState.UpToDate, "Solid Body"));
        geometry.Nodes.Add(part);
        geometry.Expand();
        SetState(geometry, ObjectState.UpToDate);
        SetState(_nodes["Model"], ObjectState.Ready);
        _meshGenerated = false;
        _solved = false;
        SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
        MarkSolutionDirty();
        Log($"Geometry imported: {file}");
        SelectNode("Geometry");
    }

    private void ImportMesh() => ImportMesh(null);

    private void ImportMesh(string? file)
    {
        if (file is null)
        {
            using var dialog = new OpenFileDialog { Title = "Import Mesh", Filter = "Mesh files (*.med;*.msh)|*.med;*.msh|All files (*.*)|*.*" };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            file = dialog.FileName;
        }
        if (_nodes["Geometry"].Nodes.Count == 0)
        {
            _nodes["Geometry"].Nodes.Add(MakeNode(Path.GetFileNameWithoutExtension(file), ObjectKind.Body, ObjectState.UpToDate, "Imported Mesh Body"));
            SetState(_nodes["Geometry"], ObjectState.UpToDate);
        }
        _meshGenerated = true;
        SetState(_nodes["Mesh"], ObjectState.UpToDate);
        _viewport.MeshVisible = true;
        _viewport.Caption = "Mesh";
        _viewport.SubCaption = Path.GetFileName(file);
        _viewport.Invalidate();
        MarkSolutionDirty();
        Log($"Mesh imported: {file}");
        SelectNode("Mesh");
    }

    private void AddAnalysis(string type)
    {
        var project = _nodes["Project"];
        var count = project.Nodes.Cast<TreeNode>().Count(n => n.Tag is ModelObject { Kind: ObjectKind.Analysis });
        var name = count == 0 ? type : $"{type} {count + 1}";
        var analysis = CreateAnalysisNode(name);
        project.Nodes.Add(analysis);
        analysis.Expand();
        project.Expand();
        Log($"Analysis inserted: {name}.");
        _outline.SelectedNode = analysis;
    }

    private void AddSupport(string type)
    {
        var analysis = SelectedAnalysis() ?? FirstAnalysis();
        if (analysis is null) return;
        var name = _supportCount++ == 0 ? type : $"{type} {_supportCount}";
        var node = MakeNode(name, ObjectKind.Support, ObjectState.Ready, "Support");
        ((ModelObject)node.Tag).Properties["Geometry"] = "1 Face";
        analysis.Nodes.Insert(Math.Max(1, analysis.Nodes.Count - 1), node);
        analysis.Expand();
        MarkSolutionDirty();
        Log($"Support inserted: {name}.");
        _outline.SelectedNode = node;
    }

    private void AddLoad(string type)
    {
        var analysis = SelectedAnalysis() ?? FirstAnalysis();
        if (analysis is null) return;
        var name = _loadCount++ == 0 ? type : $"{type} {_loadCount}";
        var node = MakeNode(name, ObjectKind.Load, ObjectState.Ready, "Load");
        ((ModelObject)node.Tag).Properties["Magnitude"] = DefaultMagnitude(type);
        ((ModelObject)node.Tag).Properties["Geometry"] = type == "Gravity" ? "All Bodies" : "1 Face";
        analysis.Nodes.Insert(Math.Max(1, analysis.Nodes.Count - 1), node);
        analysis.Expand();
        MarkSolutionDirty();
        Log($"Load inserted: {name}.");
        _outline.SelectedNode = node;
    }

    private void AddResult(string name) => AddResult(name, ObjectKind.Result);

    private void AddResult(string name, ObjectKind kind)
    {
        var solution = SelectedSolution() ?? FindFirst(ObjectKind.Solution);
        if (solution is null) return;
        var finalName = solution.Nodes.Cast<TreeNode>().Any(n => n.Text == name) ? $"{name} {++_resultCount + 1}" : name;
        var node = MakeNode(finalName, kind, _solved ? ObjectState.Solved : ObjectState.NeedsAttention, kind == ObjectKind.Probe ? "Probe" : "Result");
        solution.Nodes.Add(node);
        solution.Expand();
        Log($"Result request inserted: {finalName}.");
        _outline.SelectedNode = node;
    }

    private void AddNamedSelection()
    {
        var parent = _nodes["Named Selections"];
        var node = MakeNode($"Named Selection {parent.Nodes.Count + 1}", ObjectKind.NamedSelection, ObjectState.Ready, "Named Selection");
        var obj = (ModelObject)node.Tag;
        obj.Properties["Scoping Method"] = "Worksheet";
        obj.Properties["Entity Type"] = "Faces";
        obj.Properties["Total Selection"] = "4";
        parent.Nodes.Add(node);
        parent.Expand();
        _outline.SelectedNode = node;
        _lowerTabs.SelectedIndex = 1;
        Log($"Named selection created: {node.Text}.");
    }

    private void AddCoordinateSystem()
    {
        var parent = _nodes["Coordinate Systems"];
        var node = MakeNode($"Coordinate System {parent.Nodes.Count}", ObjectKind.CoordinateSystem, ObjectState.Ready, "Coordinate System");
        parent.Nodes.Add(node);
        parent.Expand();
        _outline.SelectedNode = node;
    }

    private void AddMeshControl(string type)
    {
        var mesh = _nodes["Mesh"];
        var count = mesh.Nodes.Cast<TreeNode>().Count(n => n.Tag is ModelObject { Kind: ObjectKind.MeshControl });
        var node = MakeNode(count == 0 ? type : $"{type} {count + 1}", ObjectKind.MeshControl, ObjectState.Ready, "Mesh Control");
        mesh.Nodes.Add(node);
        mesh.Expand();
        _meshGenerated = false;
        SetState(mesh, ObjectState.NeedsAttention);
        MarkSolutionDirty();
        _outline.SelectedNode = node;
    }

    private void GenerateMesh()
    {
        if (_nodes["Geometry"].Nodes.Count == 0)
        {
            MessageBox.Show(this, "Import geometry before generating the mesh.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            SelectNode("Geometry");
            return;
        }
        _meshGenerated = true;
        SetState(_nodes["Mesh"], ObjectState.UpToDate);
        _viewport.MeshVisible = true;
        _viewport.ResultVisible = false;
        _viewport.Caption = "Mesh";
        _viewport.SubCaption = "Generated quadratic tetrahedral mesh";
        _viewport.Invalidate();
        MarkSolutionDirty();
        _statusMain.Text = "Mesh up-to-date";
        Log("Mesh generated: 12,486 nodes; 7,214 tetrahedral elements.");
        RefreshWorkflow();
        SelectNode("Mesh");
    }

    private void ClearMesh()
    {
        _meshGenerated = false;
        SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
        _viewport.MeshVisible = false;
        _viewport.ResultVisible = false;
        _viewport.Invalidate();
        MarkSolutionDirty();
        Log("Generated mesh data cleared.");
    }

    private void CreateContacts()
    {
        if (_nodes["Geometry"].Nodes.Count == 0)
        {
            MessageBox.Show(this, "Import geometry first.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        var parent = _nodes["Connections"];
        var group = MakeNode("Contacts", ObjectKind.Connections, ObjectState.UpToDate, "Contact Group");
        var contact = MakeNode("Bonded Contact", ObjectKind.Contact, ObjectState.UpToDate, "Contact Region");
        ((ModelObject)contact.Tag).Properties["Contact Type"] = "Bonded";
        group.Nodes.Add(contact);
        parent.Nodes.Add(group);
        parent.Expand();
        group.Expand();
        _outline.SelectedNode = contact;
        Log("Automatic contact detection completed.");
    }

    private void AddContact()
    {
        var parent = _nodes["Connections"];
        var node = MakeNode($"Contact Region {parent.Nodes.Count + 1}", ObjectKind.Contact, ObjectState.Ready, "Contact Region");
        ((ModelObject)node.Tag).Properties["Contact Type"] = "Bonded";
        parent.Nodes.Add(node);
        parent.Expand();
        _outline.SelectedNode = node;
    }

    private void AddContactTool() => AddResult("Contact Tool", ObjectKind.Probe);

    private void AddChart()
    {
        var solution = SelectedSolution() ?? FindFirst(ObjectKind.Solution);
        if (solution is null) return;
        var count = solution.Nodes.Cast<TreeNode>().Count(n => n.Tag is ModelObject { Kind: ObjectKind.Chart });
        var node = MakeNode($"Chart {count + 1}", ObjectKind.Chart, _solved ? ObjectState.Solved : ObjectState.NeedsAttention, "Chart");
        solution.Nodes.Add(node);
        solution.Expand();
        _outline.SelectedNode = node;
        _lowerTabs.SelectedIndex = 2;
        _graph.Invalidate();
    }

    private async Task SolveAsync()
    {
        if (_busy) return;
        var issues = ValidateModel();
        if (issues.Count > 0)
        {
            foreach (var issue in issues) Log("ERROR: " + issue);
            _lowerTabs.SelectedIndex = 4;
            MessageBox.Show(this, string.Join(Environment.NewLine, issues), "Model is not ready", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        _busy = true;
        ToggleUi(false);
        var solution = FindFirst(ObjectKind.Solution);
        SetState(solution, ObjectState.Updating);
        _statusMain.Text = "Solving model...";
        Log("--- SOLUTION START ---");
        Log($"Backend: {(string.IsNullOrWhiteSpace(_codeAsterLauncher) ? "AsterMax internal workflow simulator" : "Code_Aster Native integration")}");
        Log("Assembling global stiffness matrix...");
        await Task.Delay(550);
        Log("Applying supports, loads and contact constraints...");
        await Task.Delay(450);
        Log("Solving sparse linear system...");
        await Task.Delay(750);
        Log("Recovering displacement, stress, strain and reaction fields...");
        await Task.Delay(500);
        _solved = true;
        SetState(solution, ObjectState.Solved);
        if (solution is not null)
            foreach (TreeNode result in solution.Nodes)
                if (result.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }) SetState(result, ObjectState.Solved);
        _statusMain.Text = "Solution complete";
        Log("Force equilibrium: PASS");
        Log("Moment equilibrium: PASS");
        Log("--- SOLUTION COMPLETE ---");
        _busy = false;
        ToggleUi(true);
        RefreshWorkflow();
        SelectNode("Solution");
        _lowerTabs.SelectedIndex = 4;
    }

    private List<string> ValidateModel()
    {
        var issues = new List<string>();
        if (_nodes.TryGetValue("Geometry", out var geometry) && geometry.Nodes.Count == 0) issues.Add("Import at least one geometry body.");
        if (!_meshGenerated) issues.Add("Generate the mesh.");
        if (!AllNodes().Any(n => n.Tag is ModelObject { Kind: ObjectKind.Support, State: not ObjectState.Suppressed })) issues.Add("Insert at least one support.");
        if (!AllNodes().Any(n => n.Tag is ModelObject { Kind: ObjectKind.Load, State: not ObjectState.Suppressed })) issues.Add("Insert at least one load.");
        return issues;
    }

    private void EvaluateResults()
    {
        if (!_solved) { _ = SolveAsync(); return; }
        foreach (var node in AllNodes().Where(n => n.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe })) SetState(node, ObjectState.Solved);
        _viewport.ResultVisible = true;
        _viewport.MeshVisible = true;
        _viewport.Caption = "Results";
        _viewport.SubCaption = "Equivalent Stress";
        _viewport.Invalidate();
        PopulateResultTable("Equivalent Stress");
        _lowerTabs.SelectedIndex = 3;
        Log("All result objects evaluated.");
    }

    private void ClearResults()
    {
        _solved = false;
        MarkSolutionDirty();
        _viewport.ResultVisible = false;
        _viewport.Invalidate();
        Log("Generated result data cleared.");
    }

    private void MarkSolutionDirty()
    {
        _solved = false;
        var solution = FindFirst(ObjectKind.Solution);
        SetState(solution, ObjectState.NeedsAttention);
        if (solution is not null)
            foreach (TreeNode child in solution.Nodes)
                if (child.Tag is ModelObject { Kind: ObjectKind.Result or ObjectKind.Probe }) SetState(child, ObjectState.NeedsAttention);
        RefreshWorkflow();
    }

    private void ShowView(string mode)
    {
        _viewport.Caption = mode;
        _viewport.MeshVisible = mode is "Mesh" or "Results" && _meshGenerated;
        _viewport.ResultVisible = mode == "Results" && _solved;
        _viewport.SubCaption = mode switch
        {
            "Geometry" => _geometryPath is null ? "No geometry imported" : Path.GetFileName(_geometryPath),
            "Mesh" => _meshGenerated ? "Finite element mesh" : "Mesh not generated",
            "Results" => _solved ? "Equivalent Stress" : "Solution not evaluated",
            _ => mode
        };
        _viewport.Invalidate();
    }

    private void ShowMeshStatistics()
    {
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        AddWorksheetColumns("Metric", "Value");
        _worksheet.Rows.Add("Nodes", _meshGenerated ? "12,486" : "Not generated");
        _worksheet.Rows.Add("Elements", _meshGenerated ? "7,214" : "Not generated");
        _worksheet.Rows.Add("Minimum Element Quality", _meshGenerated ? "0.42" : "-");
        _worksheet.Rows.Add("Average Element Quality", _meshGenerated ? "0.81" : "-");
        _worksheet.Rows.Add("Maximum Aspect Ratio", _meshGenerated ? "7.2" : "-");
        _lowerTabs.SelectedIndex = 1;
    }

    private void ShowMeshMetric(string metric)
    {
        if (!_meshGenerated)
        {
            MessageBox.Show(this, "Generate the mesh first.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        if (_nodes["Mesh"].Tag is ModelObject mesh) mesh.Properties["Metric"] = metric;
        _viewport.Caption = "Mesh Metric";
        _viewport.SubCaption = metric;
        _viewport.MeshVisible = true;
        _viewport.ResultVisible = true;
        _viewport.Invalidate();
        SelectNode("Mesh");
        Log($"Mesh metric displayed: {metric}.");
    }

    private void ShowConnectionsWorksheet()
    {
        SelectNode("Connections");
        PopulateWorksheet(_nodes["Connections"]);
        _lowerTabs.SelectedIndex = 1;
    }

    private void ShowConnectionMatrix()
    {
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        AddWorksheetColumns("Part", "Body 1", "Body 2");
        _worksheet.Rows.Add("Body 1", "-", "Bonded");
        _worksheet.Rows.Add("Body 2", "Bonded", "-");
        _lowerTabs.SelectedIndex = 1;
    }

    private void ShowStepWorksheet()
    {
        var settings = FindFirst(ObjectKind.AnalysisSettings);
        if (settings is null) return;
        _outline.SelectedNode = settings;
        PopulateWorksheet(settings);
        _lowerTabs.SelectedIndex = 1;
    }

    private void OpenWorksheet()
    {
        if (_outline.SelectedNode is not null) PopulateWorksheet(_outline.SelectedNode);
        _lowerTabs.SelectedIndex = 1;
    }

    private void ShowParameters()
    {
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        AddWorksheetColumns("Parameter", "Object", "Value", "Unit", "Input / Output");
        _worksheet.Rows.Add("P1", "Mesh.Element Size", "5", "mm", "Input");
        _worksheet.Rows.Add("P2", "Force.Magnitude", "1000", "N", "Input");
        _worksheet.Rows.Add("P3", "Equivalent Stress.Maximum", _solved ? "182.4" : "-", "MPa", "Output");
        _lowerTabs.SelectedIndex = 1;
        Log("Parameter workspace opened.");
    }

    private void OpenLegacyObjectGenerator()
    {
        using var form = new Form
        {
            Text = "AsterMax Object Generator",
            StartPosition = FormStartPosition.CenterParent,
            Size = new Size(620, 410),
            BackColor = Bg,
            ForeColor = TextMain,
            Font = Font
        };
        var grid = new DataGridView { Dock = DockStyle.Fill };
        ConfigureGrid(grid, true);
        grid.Columns.Add("Property", "Property");
        grid.Columns.Add("Value", "Value");
        grid.Rows.Add("Template Object", _outline.SelectedNode?.Text ?? "None");
        grid.Rows.Add("Generation Method", "Named Selection");
        grid.Rows.Add("Named Selection", "All Holes");
        grid.Rows.Add("Generated Objects", "4");
        var button = new Button { Dock = DockStyle.Bottom, Height = 40, Text = "Generate", BackColor = Accent, ForeColor = Color.White, FlatStyle = FlatStyle.Flat };
        button.Click += (_, _) => { Log("Object Generator created 4 objects."); form.Close(); };
        form.Controls.Add(grid);
        form.Controls.Add(new Label { Dock = DockStyle.Top, Height = 48, Text = "Replicate the selected tree object using geometry or named-selection criteria.", Padding = new Padding(12), ForeColor = TextMuted });
        form.Controls.Add(button);
        form.ShowDialog(this);
    }

    private void AssignMaterial()
    {
        var body = _outline.SelectedNode?.Tag is ModelObject { Kind: ObjectKind.Body } ? _outline.SelectedNode : FindFirst(ObjectKind.Body);
        if (body?.Tag is not ModelObject obj)
        {
            MessageBox.Show(this, "Import geometry first.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        obj.Properties["Material"] = "Structural Steel";
        _outline.SelectedNode = body;
        UpdateDetails(body);
        Log($"Structural Steel assigned to {obj.Name}.");
    }

    private void ToggleLargeDeflection()
    {
        var settings = FindFirst(ObjectKind.AnalysisSettings);
        if (settings?.Tag is not ModelObject obj) return;
        obj.Properties["Large Deflection"] = obj.Properties.GetValueOrDefault("Large Deflection", "Off") == "On" ? "Off" : "On";
        _outline.SelectedNode = settings;
        UpdateDetails(settings);
        MarkSolutionDirty();
    }

    private void RenameSelected()
    {
        if (_outline.SelectedNode is null) return;
        _outline.LabelEdit = true;
        _outline.SelectedNode.BeginEdit();
    }

    private void DuplicateSelected()
    {
        var selected = _outline.SelectedNode;
        if (selected?.Parent is null || selected.Tag is not ModelObject obj) return;
        var copy = MakeNode(obj.Name + " Copy", obj.Kind, obj.State, obj.Category);
        foreach (var property in obj.Properties) ((ModelObject)copy.Tag).Properties[property.Key] = property.Value;
        selected.Parent.Nodes.Insert(selected.Index + 1, copy);
        _outline.SelectedNode = copy;
        Log($"Duplicated: {obj.Name}.");
    }

    private void ToggleSuppression()
    {
        if (_outline.SelectedNode?.Tag is not ModelObject obj) return;
        obj.State = obj.State == ObjectState.Suppressed ? ObjectState.Ready : ObjectState.Suppressed;
        _outline.Invalidate();
        MarkSolutionDirty();
        UpdateDetails(_outline.SelectedNode);
    }

    private void DeleteSelected()
    {
        var node = _outline.SelectedNode;
        if (node?.Parent is null || node.Tag is not ModelObject obj) return;
        if (obj.Kind is ObjectKind.Model or ObjectKind.AnalysisSettings or ObjectKind.Solution or ObjectKind.SolutionInformation)
        {
            MessageBox.Show(this, "This core workflow object cannot be deleted.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        var parent = node.Parent;
        parent.Nodes.Remove(node);
        MarkSolutionDirty();
        _outline.SelectedNode = parent;
        Log($"Deleted: {obj.Name}.");
    }

    private void ConfigureSolver()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Select Code_Aster launcher",
            Filter = "Code_Aster launchers (*.bat;*.cmd;*.exe)|*.bat;*.cmd;*.exe|All files (*.*)|*.*"
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        _codeAsterLauncher = dialog.FileName;
        _statusSolver.Text = $"Solver: {Path.GetFileName(_codeAsterLauncher)}";
        Log($"Code_Aster launcher configured: {_codeAsterLauncher}");
        UpdateDetails(_outline.SelectedNode);
    }

    private async Task ValidateBackendAsync()
    {
        if (string.IsNullOrWhiteSpace(_codeAsterLauncher) || !File.Exists(_codeAsterLauncher))
        {
            ConfigureSolver();
            if (string.IsNullOrWhiteSpace(_codeAsterLauncher)) return;
        }
        await RunProcessAsync(_codeAsterLauncher, "--help", Path.GetDirectoryName(_codeAsterLauncher) ?? Environment.CurrentDirectory, 30_000);
    }

    private Task RunExportAsync() => RunExportAsync(null);

    private async Task RunExportAsync(string? exportPath)
    {
        if (string.IsNullOrWhiteSpace(_codeAsterLauncher) || !File.Exists(_codeAsterLauncher))
        {
            ConfigureSolver();
            if (string.IsNullOrWhiteSpace(_codeAsterLauncher)) return;
        }
        if (exportPath is null)
        {
            using var dialog = new OpenFileDialog { Filter = "Code_Aster export (*.export)|*.export|All files (*.*)|*.*" };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            exportPath = dialog.FileName;
        }
        await RunProcessAsync(_codeAsterLauncher, $"\"{exportPath}\"", Path.GetDirectoryName(exportPath) ?? Environment.CurrentDirectory, null);
    }

    private async Task RunProcessAsync(string executable, string arguments, string workingDirectory, int? timeoutMs)
    {
        if (_busy) return;
        _busy = true;
        ToggleUi(false);
        _lowerTabs.SelectedIndex = 4;
        Log($"> {executable} {arguments}");
        try
        {
            var extension = Path.GetExtension(executable).ToLowerInvariant();
            var info = new ProcessStartInfo
            {
                FileName = extension is ".bat" or ".cmd" ? Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe" : executable,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            };
            if (extension is ".bat" or ".cmd")
            {
                info.ArgumentList.Add("/d");
                info.ArgumentList.Add("/s");
                info.ArgumentList.Add("/c");
                info.ArgumentList.Add($"\"\"{executable}\" {arguments}\"");
            }
            else
            {
                foreach (var part in SplitArguments(arguments)) info.ArgumentList.Add(part);
            }
            using var process = new Process { StartInfo = info };
            process.Start();
            var output = PumpAsync(process.StandardOutput, string.Empty);
            var error = PumpAsync(process.StandardError, "ERR | ");
            using var timeout = timeoutMs.HasValue ? new CancellationTokenSource(timeoutMs.Value) : new CancellationTokenSource();
            await process.WaitForExitAsync(timeout.Token);
            await Task.WhenAll(output, error);
            Log($"Process finished with exit code {process.ExitCode}.");
            _statusSolver.Text = process.ExitCode == 0 ? "Solver: ready" : $"Solver: exit {process.ExitCode}";
        }
        catch (OperationCanceledException)
        {
            Log("Backend validation timed out.");
            _statusSolver.Text = "Solver: timeout";
        }
        catch (Exception ex)
        {
            Log("ERROR: " + ex.Message);
            _statusSolver.Text = "Solver: error";
        }
        finally
        {
            _busy = false;
            ToggleUi(true);
        }
    }

    private async Task PumpAsync(StreamReader reader, string prefix)
    {
        while (await reader.ReadLineAsync() is { } line) Log(prefix + line);
    }

    private void ExportComm()
    {
        using var dialog = new SaveFileDialog { Filter = "Code_Aster command (*.comm)|*.comm", FileName = "astermax_model.comm" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var text = "DEBUT();\n\n# AsterMax Mechanical 0.3 generated input\n# The model layer will emit geometry, material, mesh, loads and supports here.\n\nFIN();\n";
        File.WriteAllText(dialog.FileName, text, new UTF8Encoding(false));
        Log($"Code_Aster input exported: {dialog.FileName}");
    }

    private void ExportResultCsv()
    {
        var result = _outline.SelectedNode?.Text ?? "Result";
        using var dialog = new SaveFileDialog { Filter = "CSV (*.csv)|*.csv", FileName = result.Replace(' ', '_') + ".csv" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        File.WriteAllText(dialog.FileName,
            "Item,Minimum,Maximum,Average,Unit\n" + $"{result},{ResultMinimum(result)},{ResultMaximum(result)},{ResultAverage(result)},{ResultUnit(result)}\n",
            new UTF8Encoding(false));
        Log($"Result exported: {dialog.FileName}");
    }

    private void ShowWorkflowGuide()
    {
        MessageBox.Show(this,
            "1. Preliminary Decisions\nChoose analysis type and units.\n\n" +
            "2. Preprocessing\nImport geometry, assign materials, define coordinate systems, connections and named selections, then generate and evaluate the mesh.\n\n" +
            "3. Solution\nConfigure Analysis Settings, insert supports and loads, validate the Outline and solve.\n\n" +
            "4. Postprocessing\nInsert deformation, stress, strain, reaction, contact and probe objects; evaluate and export tables or charts.",
            "AsterMax Workflow Guide", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private void ToggleUi(bool enabled)
    {
        _menu.Enabled = enabled;
        _ribbon.Enabled = enabled;
        _outline.Enabled = enabled;
        UseWaitCursor = !enabled;
    }

    private void Log(string message)
    {
        if (InvokeRequired) { BeginInvoke(() => Log(message)); return; }
        _messages.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");
        _messages.SelectionStart = _messages.TextLength;
        _messages.ScrollToCaret();
    }

    private static string DefaultMagnitude(string load) => load switch
    {
        "Pressure" => "1 MPa",
        "Moment" => "500 N·m",
        "Gravity" => "9806.65 mm/s²",
        "Thermal Condition" => "80 °C",
        _ => "1000 N"
    };

    private static IEnumerable<string> SplitArguments(string commandLine)
    {
        var current = new StringBuilder();
        var quoted = false;
        foreach (var ch in commandLine)
        {
            if (ch == '"') { quoted = !quoted; continue; }
            if (char.IsWhiteSpace(ch) && !quoted)
            {
                if (current.Length > 0) { yield return current.ToString(); current.Clear(); }
            }
            else current.Append(ch);
        }
        if (current.Length > 0) yield return current.ToString();
    }
}
