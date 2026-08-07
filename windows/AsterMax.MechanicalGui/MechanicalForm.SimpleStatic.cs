using System.Diagnostics;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private readonly StaticMaterial _simpleMaterial = new();
    private readonly SimpleStaticSetup _simpleSetup = new();
    private SimpleStepSolid? _simpleSolid;
    private TetMesh? _simpleMesh;
    private StaticSolution? _simpleSolution;
    private bool _simpleSetupDefined;
    private TabPage? _simpleTutorialPage;

    private void InitializeSimpleStaticWorkflow()
    {
        BuildSimpleTutorialRibbon();
        BuildSimpleTutorialMenu();
        _details.CellFormatting += FormatDefinitionRows;
        Shown += (_, _) => BeginInvoke(() =>
        {
            CorrectMechanicalVisualLayout();
            _viewport.ClearModel();
            _statusMain.Text = "Ready — Tutorial 01 static workflow available";
        });
    }

    private void BuildSimpleTutorialRibbon()
    {
        _simpleTutorialPage = new TabPage("Static Tutorial")
        {
            BackColor = Panel,
            ForeColor = TextMain,
            Padding = new Padding(4)
        };
        var flow = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            AutoScroll = true,
            BackColor = Panel,
            Padding = new Padding(4, 3, 4, 2)
        };
        flow.Controls.Add(TutorialGroup("Geometry",
            TutorialButton("Import STEP", "import", ImportSimpleStep),
            TutorialButton("Example STEP", "geometry", CreateAndImportExampleStep)));
        flow.Controls.Add(TutorialGroup("Definition",
            TutorialButton("Material + BC", "settings", ConfigureSimpleStatic),
            TutorialButton("Generate Mesh", "mesh", GenerateSimpleMesh)));
        flow.Controls.Add(TutorialGroup("Solution",
            TutorialButton("Solve TET4", "solve", () => _ = SolveSimpleStaticAsync(), true),
            TutorialButton("Show Results", "result", ShowSimpleResults)));
        flow.Controls.Add(TutorialGroup("Documentation",
            TutorialButton("Calculation Report", "export", ExportSimpleCalculationReport),
            TutorialButton("Clear Tutorial", "new", ResetSimpleStatic)));
        _simpleTutorialPage.Controls.Add(flow);
        _ribbon.TabPages.Insert(Math.Min(1, _ribbon.TabPages.Count), _simpleTutorialPage);
    }

    private void BuildSimpleTutorialMenu()
    {
        var menu = new ToolStripMenuItem("Tutorial 01");
        menu.DropDownItems.Add(MenuCommand("Import simple STEP...", "import", ImportSimpleStep));
        menu.DropDownItems.Add(MenuCommand("Create cantilever example...", "geometry", CreateAndImportExampleStep));
        menu.DropDownItems.Add(new ToolStripSeparator());
        menu.DropDownItems.Add(MenuCommand("Material and boundary conditions...", "settings", ConfigureSimpleStatic));
        menu.DropDownItems.Add(MenuCommand("Generate real TET4 mesh", "mesh", GenerateSimpleMesh));
        menu.DropDownItems.Add(MenuCommand("Solve linear static model", "solve", () => _ = SolveSimpleStaticAsync()));
        menu.DropDownItems.Add(MenuCommand("Export preliminary calculation report...", "export", ExportSimpleCalculationReport));
        _menu.Items.Insert(Math.Max(0, _menu.Items.Count - 1), menu);
    }

    private ToolStripMenuItem MenuCommand(string text, string icon, Action action)
    {
        var item = new ToolStripMenuItem(text)
        {
            Image = SvgIconRenderer.Render(icon, 18, TextMain, Accent)
        };
        item.Click += (_, _) => action();
        return item;
    }

    private Control TutorialGroup(string title, params Control[] buttons)
    {
        var panel = new System.Windows.Forms.Panel
        {
            Width = Math.Max(222, buttons.Length * 106 + 12),
            Height = 108,
            BackColor = Panel,
            Margin = new Padding(2)
        };
        var flow = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            BackColor = Panel,
            Padding = new Padding(4, 2, 4, 20)
        };
        foreach (var button in buttons) flow.Controls.Add(button);
        panel.Controls.Add(flow);
        panel.Controls.Add(new Label
        {
            Dock = DockStyle.Bottom,
            Height = 18,
            Text = title,
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = TextMuted,
            Font = new Font("Segoe UI", 8f)
        });
        return panel;
    }

    private Button TutorialButton(string text, string icon, Action action, bool primary = false)
    {
        var button = new Button
        {
            Text = text,
            Width = 102,
            Height = 76,
            FlatStyle = FlatStyle.Flat,
            BackColor = primary ? Accent : Panel2,
            ForeColor = primary ? Color.White : TextMain,
            Image = SvgIconRenderer.Render(icon, 28, primary ? Color.White : TextMain, primary ? Color.White : Accent),
            TextImageRelation = TextImageRelation.ImageAboveText,
            ImageAlign = ContentAlignment.TopCenter,
            TextAlign = ContentAlignment.BottomCenter,
            Padding = new Padding(2, 5, 2, 4),
            Margin = new Padding(2),
            Cursor = Cursors.Hand,
            Font = new Font("Segoe UI", 8.2f)
        };
        button.FlatAppearance.BorderColor = primary ? Color.FromArgb(0, 88, 154) : Border;
        button.Click += (_, _) => action();
        return button;
    }

    private void CorrectMechanicalVisualLayout()
    {
        if (_ribbon.Parent is TableLayoutPanel root && root.RowStyles.Count > 1)
            root.RowStyles[1].Height = 154;
        _ribbon.Padding = new Point(7, 4);
        foreach (var button in Descendants(_ribbon).OfType<Button>())
        {
            button.TextImageRelation = TextImageRelation.ImageAboveText;
            button.ImageAlign = ContentAlignment.TopCenter;
            button.TextAlign = ContentAlignment.BottomCenter;
            button.Padding = new Padding(2, 4, 2, 4);
            button.Font = new Font("Segoe UI", 8.0f);
            button.AutoEllipsis = true;
            if (button.Height < 70) button.Height = 72;
            if (button.Width < 88) button.Width = 92;
        }
        _graphicsTools.ImageScalingSize = new Size(16, 16);
        foreach (ToolStripItem item in _graphicsTools.Items)
            if (item is ToolStripComboBox combo)
            {
                combo.Width = 210;
                combo.DropDownWidth = 285;
            }
        _details.ColumnHeadersHeight = 24;
        _details.RowTemplate.Height = 23;
        _outline.ItemHeight = 23;
        _lowerTabs.ItemSize = new Size(110, 25);
        _lowerTabs.SizeMode = TabSizeMode.Normal;
    }

    private static IEnumerable<Control> Descendants(Control parent)
    {
        foreach (Control child in parent.Controls)
        {
            yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }

    private void FormatDefinitionRows(object? sender, DataGridViewCellFormattingEventArgs e)
    {
        if (e.RowIndex < 0 || _details.Rows[e.RowIndex].Cells.Count < 2) return;
        var first = _details.Rows[e.RowIndex].Cells[0].Value?.ToString() ?? string.Empty;
        if (!first.StartsWith('[') || !first.EndsWith(']')) return;
        _details.Rows[e.RowIndex].DefaultCellStyle.BackColor = Color.FromArgb(215, 232, 246);
        _details.Rows[e.RowIndex].DefaultCellStyle.ForeColor = Color.FromArgb(25, 49, 71);
        _details.Rows[e.RowIndex].DefaultCellStyle.Font = new Font("Segoe UI Semibold", 8.8f);
    }

    private void ImportSimpleStep()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Tutorial 01 — Import a single prismatic STEP solid",
            Filter = "STEP geometry (*.step;*.stp)|*.step;*.stp|All files (*.*)|*.*"
        };
        if (dialog.ShowDialog(this) == DialogResult.OK) ImportSimpleStep(dialog.FileName);
    }

    private void ImportSimpleStep(string path)
    {
        try
        {
            var solid = SimpleStepReader.ReadPrismaticSolid(path);
            if (!solid.IsSupportedPrism)
            {
                MessageBox.Show(this,
                    solid.FidelityMessage + "\n\nUse a simple rectangular cantilever STEP for Tutorial 01.",
                    "STEP geometry not supported",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
                return;
            }

            _simpleSolid = solid;
            _simpleMesh = null;
            _simpleSolution = null;
            _simpleSetupDefined = false;
            _geometryPath = path;
            _meshGenerated = false;
            _solved = false;
            _viewport.SetSolid(solid);
            _viewport.MeshVisible = false;
            _viewport.ResultVisible = false;
            _viewport.SupportVisible = false;
            _viewport.ForceVisible = false;

            var geometry = _nodes["Geometry"];
            geometry.Nodes.Clear();
            var body = MakeNode(Path.GetFileNameWithoutExtension(path), ObjectKind.Body, ObjectState.UpToDate, "Prismatic Solid");
            var bodyObject = (ModelObject)body.Tag;
            bodyObject.Properties["Geometry Fidelity"] = "Rectangular STEP envelope";
            bodyObject.Properties["Length X"] = $"{solid.LengthX:0.###} mm";
            bodyObject.Properties["Length Y"] = $"{solid.LengthY:0.###} mm";
            bodyObject.Properties["Length Z"] = $"{solid.LengthZ:0.###} mm";
            bodyObject.Properties["Volume"] = $"{solid.Volume:0.###} mm³";
            bodyObject.Properties["Material"] = _simpleMaterial.Name;
            bodyObject.Properties["Source"] = path;
            geometry.Nodes.Add(body);
            geometry.Expand();
            SetState(geometry, ObjectState.UpToDate);
            SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
            MarkSolutionDirty();
            Log($"REAL STEP IMPORT: {path}");
            Log($"Prismatic envelope: {solid.LengthX:0.###} x {solid.LengthY:0.###} x {solid.LengthZ:0.###} mm; {solid.CartesianPointCount} STEP points read.");
            Log("Restriction: holes, rounds, curved surfaces and assemblies are rejected in Tutorial 01.");
            _outline.SelectedNode = body;
            _simpleTutorialPage?.Select();
            _statusMain.Text = "STEP prism imported — define material and boundary conditions";
        }
        catch (Exception exception)
        {
            Log("STEP IMPORT ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "STEP import failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void CreateAndImportExampleStep()
    {
        using var dialog = new SaveFileDialog
        {
            Title = "Save Tutorial 01 cantilever STEP",
            Filter = "STEP file (*.step)|*.step",
            FileName = "AsterMax_Tutorial01_Cantilever_200x40x20.step"
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        File.WriteAllText(dialog.FileName, TutorialStepText(200, 40, 20), new System.Text.UTF8Encoding(false));
        ImportSimpleStep(dialog.FileName);
    }

    private static string TutorialStepText(double lx, double ly, double lz)
    {
        var points = new[]
        {
            new Vec3(0,0,0), new Vec3(lx,0,0), new Vec3(lx,ly,0), new Vec3(0,ly,0),
            new Vec3(0,0,lz), new Vec3(lx,0,lz), new Vec3(lx,ly,lz), new Vec3(0,ly,lz)
        };
        var lines = points.Select((p, i) => $"#{i + 1}=CARTESIAN_POINT('',({p.X.ToString(CultureInfo.InvariantCulture)},{p.Y.ToString(CultureInfo.InvariantCulture)},{p.Z.ToString(CultureInfo.InvariantCulture)}));");
        return "ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('AsterMax Tutorial 01 rectangular prism'),'2;1');\nFILE_NAME('cantilever.step','2026-08-03T00:00:00',('AsterMax'),('AsterMax'),'','','');\nFILE_SCHEMA(('CONFIG_CONTROL_DESIGN'));\nENDSEC;\nDATA;\n" + string.Join("\n", lines) + "\n#20=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));\nENDSEC;\nEND-ISO-10303-21;\n";
    }

    private void ConfigureSimpleStatic()
    {
        if (_simpleSolid is null)
        {
            MessageBox.Show(this, "Import a supported prismatic STEP first.", "Tutorial 01", MessageBoxButtons.OK, MessageBoxIcon.Information);
            ImportSimpleStep();
            return;
        }
        using var dialog = new SimpleStaticSetupDialog(_simpleMaterial, _simpleSetup);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        dialog.Apply(_simpleMaterial, _simpleSetup);
        if (_simpleSetup.FixedFace == _simpleSetup.LoadFace)
        {
            MessageBox.Show(this, "Fixed and loaded faces must be different.", "Invalid setup", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        _simpleSetupDefined = true;
        _simpleMesh = null;
        _simpleSolution = null;
        _meshGenerated = false;
        _solved = false;
        UpdateSimpleTreeObjects();
        _viewport.SupportVisible = true;
        _viewport.ForceVisible = true;
        _viewport.FixedFace = _simpleSetup.FixedFace;
        _viewport.LoadFace = _simpleSetup.LoadFace;
        _viewport.ForceVector = _simpleSetup.ForceN;
        _viewport.Invalidate();
        SetState(_nodes["Mesh"], ObjectState.NeedsAttention);
        MarkSolutionDirty();
        Log($"Tutorial setup: E={_simpleMaterial.YoungModulusMpa:0.###} MPa, nu={_simpleMaterial.PoissonRatio:0.###}, fixed={_simpleSetup.FixedFace}, load={_simpleSetup.LoadFace}, F={_simpleSetup.ForceN} N.");
        _statusMain.Text = "Material and boundary conditions defined — generate mesh";
    }

    private void UpdateSimpleTreeObjects()
    {
        if (_simpleSolid is null) return;
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject obj && obj.Properties.TryGetValue("Tutorial", out var value) && value == "SimpleStatic").ToList())
            node.Remove();

        var materials = _nodes["Materials"];
        var materialNode = MakeNode(_simpleMaterial.Name, ObjectKind.Material, ObjectState.UpToDate, "Linear Elastic Material");
        var materialObject = (ModelObject)materialNode.Tag;
        materialObject.Properties["Tutorial"] = "SimpleStatic";
        materialObject.Properties["Young's Modulus"] = $"{_simpleMaterial.YoungModulusMpa:0.###} MPa";
        materialObject.Properties["Poisson's Ratio"] = $"{_simpleMaterial.PoissonRatio:0.####}";
        materialObject.Properties["Yield Strength"] = $"{_simpleMaterial.YieldStrengthMpa:0.###} MPa";
        materials.Nodes.Add(materialNode);
        materials.Expand();
        SetState(materials, ObjectState.UpToDate);

        var analysis = AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Analysis });
        if (analysis is null) return;
        var solution = analysis.Nodes.Cast<TreeNode>().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Solution });
        var insertIndex = solution?.Index ?? analysis.Nodes.Count;
        var support = MakeNode($"Fixed Support ({_simpleSetup.FixedFace})", ObjectKind.Support, ObjectState.Ready, "Fixed Support");
        var supportObject = (ModelObject)support.Tag;
        supportObject.Properties["Tutorial"] = "SimpleStatic";
        supportObject.Properties["Geometry"] = _simpleSetup.FixedFace.ToString();
        supportObject.Properties["UX"] = supportObject.Properties["UY"] = supportObject.Properties["UZ"] = "0 mm";
        analysis.Nodes.Insert(insertIndex++, support);
        var force = MakeNode($"Force ({_simpleSetup.LoadFace})", ObjectKind.Load, ObjectState.Ready, "Force");
        var forceObject = (ModelObject)force.Tag;
        forceObject.Properties["Tutorial"] = "SimpleStatic";
        forceObject.Properties["Geometry"] = _simpleSetup.LoadFace.ToString();
        forceObject.Properties["FX"] = $"{_simpleSetup.ForceN.X:0.###} N";
        forceObject.Properties["FY"] = $"{_simpleSetup.ForceN.Y:0.###} N";
        forceObject.Properties["FZ"] = $"{_simpleSetup.ForceN.Z:0.###} N";
        analysis.Nodes.Insert(insertIndex, force);
        analysis.Expand();
    }

    private void GenerateSimpleMesh()
    {
        if (_simpleSolid is null)
        {
            MessageBox.Show(this, "Import the Tutorial 01 STEP first.", "Tutorial 01", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        if (!_simpleSetupDefined) ConfigureSimpleStatic();
        if (!_simpleSetupDefined) return;
        try
        {
            UseWaitCursor = true;
            _simpleMesh = StructuredTetMesher.Generate(_simpleSolid, _simpleSetup.ElementSizeMm);
            _simpleSolution = null;
            _meshGenerated = true;
            _solved = false;
            _viewport.SetMesh(_simpleMesh);
            _viewport.MeshVisible = true;
            _viewport.ResultVisible = false;
            SetState(_nodes["Mesh"], ObjectState.UpToDate);
            if (_nodes["Mesh"].Tag is ModelObject meshObject)
            {
                meshObject.Properties["Mesher"] = "AsterMax structured prism TET4";
                meshObject.Properties["Nodes"] = _simpleMesh.Nodes.Count.ToString("N0");
                meshObject.Properties["Elements"] = _simpleMesh.Elements.Count.ToString("N0");
                meshObject.Properties["Divisions"] = $"{_simpleMesh.DivisionsX} x {_simpleMesh.DivisionsY} x {_simpleMesh.DivisionsZ}";
                meshObject.Properties["Target Size"] = $"{_simpleSetup.ElementSizeMm:0.###} mm";
            }
            MarkSolutionDirty();
            PopulateSimpleMeshTable();
            Log($"REAL TET4 MESH: {_simpleMesh.Nodes.Count} nodes, {_simpleMesh.Elements.Count} elements, divisions {_simpleMesh.DivisionsX} x {_simpleMesh.DivisionsY} x {_simpleMesh.DivisionsZ}.");
            SelectLowerTab("Worksheet");
            SelectNode("Mesh");
            _statusMain.Text = "Real TET4 mesh generated — solve model";
        }
        catch (Exception exception)
        {
            Log("MESH ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Meshing failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private async Task SolveSimpleStaticAsync()
    {
        if (_simpleSolid is null) { ImportSimpleStep(); return; }
        if (!_simpleSetupDefined) ConfigureSimpleStatic();
        if (!_simpleSetupDefined) return;
        if (_simpleMesh is null) GenerateSimpleMesh();
        if (_simpleMesh is null) return;
        try
        {
            UseWaitCursor = true;
            _statusMain.Text = "Assembling and solving the real TET4 model...";
            Log("--- TUTORIAL 01 REAL SOLUTION START ---");
            Log("Model: one rectangular STEP envelope; isotropic linear elasticity; small displacement; 3-D TET4.");
            var solid = _simpleSolid;
            var mesh = _simpleMesh;
            _simpleSolution = await Task.Run(() => Tet4LinearStaticSolver.Solve(solid, mesh, _simpleMaterial, _simpleSetup));
            _solved = true;
            _viewport.SetSolution(_simpleSolution);
            _viewport.ResultVisible = true;
            EnsureSimpleResultNodes();
            PopulateSimpleResultTable();
            Log($"Max displacement: {_simpleSolution.MaxDisplacementMm:0.######} mm");
            Log($"Max von Mises: {_simpleSolution.MaxVonMisesMpa:0.######} MPa");
            Log($"Reaction: {_simpleSolution.ReactionN} N");
            Log($"Relative equilibrium error: {_simpleSolution.EquilibriumError:E3}");
            Log("--- TUTORIAL 01 REAL SOLUTION COMPLETE ---");
            SelectLowerTab("Tabular Data");
            _statusMain.Text = "Tutorial 01 solved — review results and export report";
            MessageBox.Show(this,
                $"Real internal TET4 solution completed.\n\nMax displacement: {_simpleSolution.MaxDisplacementMm:0.######} mm\nMax von Mises: {_simpleSolution.MaxVonMisesMpa:0.######} MPa\nEquilibrium error: {_simpleSolution.EquilibriumError:E3}\n\nThis beta is restricted to a rectangular/prismatic solid.",
                "Tutorial 01 solved",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
        catch (Exception exception)
        {
            _solved = false;
            Log("SOLVER ERROR: " + exception);
            SelectLowerTab("Messages");
            MessageBox.Show(this, exception.Message, "Solver failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private void EnsureSimpleResultNodes()
    {
        var solution = AllNodes().FirstOrDefault(node => node.Tag is ModelObject { Kind: ObjectKind.Solution });
        if (solution is null) return;
        foreach (var name in new[] { "Total Deformation", "Equivalent Stress", "Force Reaction" })
        {
            var node = solution.Nodes.Cast<TreeNode>().FirstOrDefault(child => child.Text == name);
            if (node is null)
            {
                var kind = name == "Force Reaction" ? ObjectKind.Probe : ObjectKind.Result;
                node = MakeNode(name, kind, ObjectState.Solved, kind == ObjectKind.Probe ? "Probe" : "Result");
                ((ModelObject)node.Tag).Properties["Tutorial"] = "SimpleStatic";
                solution.Nodes.Add(node);
            }
            SetState(node, ObjectState.Solved);
        }
        solution.Expand();
        SetState(solution, ObjectState.Solved);
    }

    private void ShowSimpleResults()
    {
        if (_simpleSolution is null)
        {
            _ = SolveSimpleStaticAsync();
            return;
        }
        _viewport.SetSolution(_simpleSolution);
        _viewport.ResultVisible = true;
        PopulateSimpleResultTable();
        SelectLowerTab("Tabular Data");
    }

    private void PopulateSimpleMeshTable()
    {
        if (_simpleMesh is null) return;
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        _worksheet.Columns.Add("Property", "Mesh Property");
        _worksheet.Columns.Add("Value", "Value");
        _worksheet.Rows.Add("Mesher", "Structured rectangular TET4");
        _worksheet.Rows.Add("Nodes", _simpleMesh.Nodes.Count.ToString("N0"));
        _worksheet.Rows.Add("Elements", _simpleMesh.Elements.Count.ToString("N0"));
        _worksheet.Rows.Add("Divisions", $"{_simpleMesh.DivisionsX} x {_simpleMesh.DivisionsY} x {_simpleMesh.DivisionsZ}");
        _worksheet.Rows.Add("Target size", $"{_simpleSetup.ElementSizeMm:0.###} mm");
        _worksheet.Rows.Add("Element order", "Linear / first-order");
    }

    private void PopulateSimpleResultTable()
    {
        if (_simpleSolution is null) return;
        _tabular.Columns.Clear();
        _tabular.Rows.Clear();
        _tabular.Columns.Add("Result", "Result");
        _tabular.Columns.Add("Value", "Value");
        _tabular.Columns.Add("Unit", "Unit");
        _tabular.Rows.Add("Maximum displacement", _simpleSolution.MaxDisplacementMm.ToString("0.######"), "mm");
        _tabular.Rows.Add("Loaded-face UX", _simpleSolution.LoadedFaceAverageDisplacementMm.X.ToString("0.######"), "mm");
        _tabular.Rows.Add("Loaded-face UY", _simpleSolution.LoadedFaceAverageDisplacementMm.Y.ToString("0.######"), "mm");
        _tabular.Rows.Add("Loaded-face UZ", _simpleSolution.LoadedFaceAverageDisplacementMm.Z.ToString("0.######"), "mm");
        _tabular.Rows.Add("Maximum equivalent stress", _simpleSolution.MaxVonMisesMpa.ToString("0.######"), "MPa");
        _tabular.Rows.Add("Reaction X", _simpleSolution.ReactionN.X.ToString("0.######"), "N");
        _tabular.Rows.Add("Reaction Y", _simpleSolution.ReactionN.Y.ToString("0.######"), "N");
        _tabular.Rows.Add("Reaction Z", _simpleSolution.ReactionN.Z.ToString("0.######"), "N");
        _tabular.Rows.Add("Equilibrium error", _simpleSolution.EquilibriumError.ToString("E3"), "relative");
        if (_simpleSolution.BeamTheoryDisplacementMm is double beamDeflection)
            _tabular.Rows.Add("Beam-theory tip displacement", beamDeflection.ToString("0.######"), "mm");
        if (_simpleSolution.BeamTheoryStressMpa is double beamStress)
            _tabular.Rows.Add("Beam-theory fixed-end stress", beamStress.ToString("0.######"), "MPa");
    }

    private void ExportSimpleCalculationReport()
    {
        if (_simpleSolid is null || _simpleMesh is null || _simpleSolution is null)
        {
            MessageBox.Show(this, "Complete and solve Tutorial 01 before exporting the calculation report.", "Report unavailable", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        using var dialog = new SaveFileDialog
        {
            Title = "Export preliminary calculation report",
            Filter = "HTML report (*.html)|*.html",
            FileName = Path.GetFileNameWithoutExtension(_simpleSolid.SourcePath) + "_AsterMax_Preliminary_Calculation.html"
        };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        try
        {
            SimpleCalculationReport.Write(dialog.FileName, _simpleSolid, _simpleMesh, _simpleMaterial, _simpleSetup, _simpleSolution);
            Log("Calculation report exported: " + dialog.FileName);
            Process.Start(new ProcessStartInfo(dialog.FileName) { UseShellExecute = true });
        }
        catch (Exception exception)
        {
            MessageBox.Show(this, exception.Message, "Report export failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ResetSimpleStatic()
    {
        _simpleSolid = null;
        _simpleMesh = null;
        _simpleSolution = null;
        _simpleSetupDefined = false;
        _meshGenerated = false;
        _solved = false;
        _viewport.ClearModel();
        if (_nodes.TryGetValue("Geometry", out var geometry)) { geometry.Nodes.Clear(); SetState(geometry, ObjectState.NeedsAttention); }
        if (_nodes.TryGetValue("Mesh", out var mesh)) SetState(mesh, ObjectState.NeedsAttention);
        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject obj && obj.Properties.TryGetValue("Tutorial", out var value) && value == "SimpleStatic").ToList()) node.Remove();
        Log("Tutorial 01 model cleared.");
        _statusMain.Text = "Tutorial 01 cleared — import a simple STEP";
    }

    private void SelectLowerTab(string title)
    {
        var page = _lowerTabs.TabPages.Cast<TabPage>().FirstOrDefault(tab => tab.Text.Equals(title, StringComparison.OrdinalIgnoreCase));
        if (page is not null) _lowerTabs.SelectedTab = page;
    }
}
