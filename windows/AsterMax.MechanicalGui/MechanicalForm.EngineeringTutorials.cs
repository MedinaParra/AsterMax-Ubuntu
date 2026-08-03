namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private readonly DataGridView _namedSelectionGrid = new();
    private readonly DataGridView _convergenceGrid = new();
    private readonly DataGridView _designPointGrid = new();
    private readonly DataGridView _modalGrid = new();
    private readonly DataGridView _thermalGrid = new();
    private readonly StudyPlotPanel _engineeringPlot = new();
    private readonly BeamModalSetup _modalSetup = new();
    private readonly ThermalSetup _thermalSetup = new();
    private List<FaceNamedSelection> _faceSelections = [];
    private IReadOnlyList<MeshConvergencePoint> _convergenceResults = [];
    private IReadOnlyList<DesignPointResult> _designPointResults = [];
    private IReadOnlyList<BeamModeResult> _modalResults = [];
    private ThermalSolution? _thermalSolution;
    private TabControl? _engineeringResultTabs;

    private void InitializeEngineeringTutorials()
    {
        BuildEngineeringTutorialRibbon();
        BuildEngineeringResultsTab();
        BuildEngineeringTutorialMenu();
        Log("AsterMax 0.6 curriculum block loaded: Named Selections, Object Generator, Mesh Evaluation, Design Points, Modal and Steady-State Thermal.");
    }

    private void BuildEngineeringTutorialRibbon()
    {
        var preprocessing = new TabPage("Pre/Post Tutorials") { BackColor = Panel, ForeColor = TextMain, Padding = new Padding(4) };
        var preprocessingFlow = NewTutorialFlow();
        preprocessingFlow.Controls.Add(TutorialGroup("WS02 — Scoping",
            TutorialButton("Named Selections", "selection", BuildFaceNamedSelections),
            TutorialButton("Object Generator", "settings", OpenObjectGenerator)));
        preprocessingFlow.Controls.Add(TutorialGroup("WS04 — Verification",
            TutorialButton("Mesh Convergence", "mesh-control", () => _ = RunMeshConvergenceAsync(), true),
            TutorialButton("Design Points", "chart", () => _ = RunDesignPointStudyAsync())));
        preprocessingFlow.Controls.Add(TutorialGroup("Reports",
            TutorialButton("Export Study", "export", ExportActiveEngineeringStudy),
            TutorialButton("Tutorial Results", "result", ShowEngineeringResults)));
        preprocessing.Controls.Add(preprocessingFlow);

        var modal = new TabPage("Modal Tutorial") { BackColor = Panel, ForeColor = TextMain, Padding = new Padding(4) };
        var modalFlow = NewTutorialFlow();
        modalFlow.Controls.Add(TutorialGroup("WS07.1 — Modal",
            TutorialButton("Modal Settings", "settings", ConfigureModalTutorial),
            TutorialButton("Solve Modes", "modal", () => _ = SolveModalTutorialAsync(), true)));
        modalFlow.Controls.Add(TutorialGroup("Results",
            TutorialButton("Mode Table", "result", ShowModalResults),
            TutorialButton("Export Modal", "export", ExportModalStudy)));
        modal.Controls.Add(modalFlow);

        var thermal = new TabPage("Thermal Tutorial") { BackColor = Panel, ForeColor = TextMain, Padding = new Padding(4) };
        var thermalFlow = NewTutorialFlow();
        thermalFlow.Controls.Add(TutorialGroup("WS07.2 — Thermal",
            TutorialButton("Thermal Settings", "thermal", ConfigureThermalTutorial),
            TutorialButton("Solve Thermal", "solve", () => _ = SolveThermalTutorialAsync(), true)));
        thermalFlow.Controls.Add(TutorialGroup("Results",
            TutorialButton("Temperature Table", "result", ShowThermalResults),
            TutorialButton("Export Thermal", "export", ExportThermalStudy)));
        thermal.Controls.Add(thermalFlow);

        _ribbon.TabPages.Insert(Math.Min(2, _ribbon.TabPages.Count), preprocessing);
        _ribbon.TabPages.Insert(Math.Min(3, _ribbon.TabPages.Count), modal);
        _ribbon.TabPages.Insert(Math.Min(4, _ribbon.TabPages.Count), thermal);
    }

    private FlowLayoutPanel NewTutorialFlow() => new()
    {
        Dock = DockStyle.Fill,
        FlowDirection = FlowDirection.LeftToRight,
        WrapContents = false,
        AutoScroll = true,
        BackColor = Panel,
        Padding = new Padding(4, 3, 4, 2)
    };

    private void BuildEngineeringResultsTab()
    {
        var page = new TabPage("Tutorial Results") { BackColor = Field, ForeColor = TextMain, Padding = new Padding(2) };
        _engineeringResultTabs = new TabControl { Dock = DockStyle.Fill, Padding = new Point(10, 4) };
        page.Controls.Add(_engineeringResultTabs);
        _lowerTabs.TabPages.Add(page);

        AddResultGridTab("Named Selections", _namedSelectionGrid,
            ("Name", 25), ("Face", 15), ("Area (mm²)", 18), ("Center", 27), ("Nodes", 15));
        AddResultGridTab("Mesh Convergence", _convergenceGrid,
            ("Element size (mm)", 14), ("Nodes", 10), ("TET4", 10), ("Umax (mm)", 15),
            ("von Mises (MPa)", 15), ("ΔU vs fine (%)", 14), ("Δσ vs fine (%)", 14), ("Equilibrium", 12));
        AddResultGridTab("Design Points", _designPointGrid,
            ("Point", 8), ("Force (N)", 14), ("E (MPa)", 14), ("Size (mm)", 12),
            ("Umax (mm)", 16), ("von Mises (MPa)", 16), ("Safety factor", 12), ("Equilibrium", 12));
        AddResultGridTab("Modal", _modalGrid,
            ("Mode", 10), ("FE frequency (Hz)", 25), ("Analytical (Hz)", 25), ("Difference (%)", 20), ("Status", 20));
        AddResultGridTab("Thermal", _thermalGrid,
            ("Result", 42), ("Value", 30), ("Unit", 13), ("Acceptance", 15));

        var plotTab = new TabPage("Study Plot") { BackColor = Color.White, Padding = new Padding(2) };
        _engineeringPlot.Dock = DockStyle.Fill;
        plotTab.Controls.Add(_engineeringPlot);
        _engineeringResultTabs.TabPages.Add(plotTab);
    }

    private void AddResultGridTab(string title, DataGridView grid, params (string Name, int Weight)[] columns)
    {
        ConfigureGrid(grid, true);
        grid.ReadOnly = true;
        grid.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
        grid.AllowUserToAddRows = false;
        grid.AllowUserToDeleteRows = false;
        grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        foreach (var column in columns)
            grid.Columns.Add(new DataGridViewTextBoxColumn { HeaderText = column.Name, FillWeight = column.Weight });
        var tab = new TabPage(title) { BackColor = Field, Padding = new Padding(2) };
        tab.Controls.Add(grid);
        _engineeringResultTabs!.TabPages.Add(tab);
    }

    private void BuildEngineeringTutorialMenu()
    {
        var menu = new ToolStripMenuItem("Tutorials 02–07");
        menu.DropDownItems.Add(MenuCommand("WS02 — Create face Named Selections", "selection", BuildFaceNamedSelections));
        menu.DropDownItems.Add(MenuCommand("WS02 — Object Generator", "settings", OpenObjectGenerator));
        menu.DropDownItems.Add(new ToolStripSeparator());
        menu.DropDownItems.Add(MenuCommand("WS04 — Mesh convergence", "mesh-control", () => _ = RunMeshConvergenceAsync()));
        menu.DropDownItems.Add(MenuCommand("WS04 — Design Points", "chart", () => _ = RunDesignPointStudyAsync()));
        menu.DropDownItems.Add(new ToolStripSeparator());
        menu.DropDownItems.Add(MenuCommand("WS07.1 — Modal", "modal", () => _ = SolveModalTutorialAsync()));
        menu.DropDownItems.Add(MenuCommand("WS07.2 — Steady thermal", "thermal", () => _ = SolveThermalTutorialAsync()));
        _menu.Items.Insert(Math.Max(0, _menu.Items.Count - 1), menu);
    }

    private bool RequireStaticGeometry(bool requireSetup = false)
    {
        if (_simpleSolid is null)
        {
            MessageBox.Show(this, "Import the Tutorial STEP or create the cantilever example first.", "AsterMax tutorials", MessageBoxButtons.OK, MessageBoxIcon.Information);
            CreateAndImportExampleStep();
            return false;
        }
        if (requireSetup && !_simpleSetupDefined)
        {
            ConfigureSimpleStatic();
            return _simpleSetupDefined;
        }
        return true;
    }

    private void BuildFaceNamedSelections()
    {
        if (!RequireStaticGeometry()) return;
        var solid = _simpleSolid!;
        var mesh = _simpleMesh ?? StructuredTetMesher.Generate(solid, _simpleSetup.ElementSizeMm);
        _faceSelections = Enum.GetValues<SimpleFace>().Select(face => new FaceNamedSelection(
            $"NS_{face}", face, FaceArea(solid, face), FaceCenterForSelection(solid, face),
            Tet4LinearStaticSolver.FaceNodes(solid, mesh, face).Count)).ToList();

        _namedSelectionGrid.Rows.Clear();
        foreach (var selection in _faceSelections)
            _namedSelectionGrid.Rows.Add(selection.Name, selection.Face, selection.AreaMm2.ToString("0.###"), selection.Center, selection.NodeCount);

        var root = _nodes["Named Selections"];
        foreach (var node in root.Nodes.Cast<TreeNode>().Where(node => node.Tag is ModelObject obj && obj.Properties.TryGetValue("Tutorial", out var value) && value == "WS02").ToArray())
            node.Remove();
        foreach (var selection in _faceSelections)
        {
            var node = MakeNode(selection.Name, ObjectKind.NamedSelection, ObjectState.UpToDate, "Face Named Selection");
            var model = (ModelObject)node.Tag;
            model.Properties["Tutorial"] = "WS02";
            model.Properties["Scoping Method"] = "Geometry Selection";
            model.Properties["Face"] = selection.Face.ToString();
            model.Properties["Area"] = $"{selection.AreaMm2:0.###} mm²";
            model.Properties["Mesh Nodes"] = selection.NodeCount.ToString(CultureInfo.InvariantCulture);
            root.Nodes.Add(node);
        }
        root.Expand();
        SetState(root, ObjectState.UpToDate);
        ShowEngineeringTab("Named Selections");
        Log("WS02.2: six persistent face Named Selections generated from the prism topology.");
        _statusMain.Text = "Named Selections generated — use Object Generator to scope supports or loads";
    }

    private void OpenObjectGenerator()
    {
        if (!RequireStaticGeometry()) return;
        if (_faceSelections.Count == 0) BuildFaceNamedSelections();
        using var dialog = new ObjectGeneratorDialog(_faceSelections);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        _simpleSetupDefined = true;
        if (dialog.ObjectType == "Fixed Support") _simpleSetup.FixedFace = dialog.SelectedFace;
        else _simpleSetup.LoadFace = dialog.SelectedFace;
        if (_simpleSetup.FixedFace == _simpleSetup.LoadFace)
        {
            MessageBox.Show(this, "The generated support and load cannot use the same face.", "Object Generator", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        _simpleMesh = null;
        _simpleSolution = null;
        _meshGenerated = false;
        _solved = false;
        UpdateSimpleTreeObjects();
        _viewport.FixedFace = _simpleSetup.FixedFace;
        _viewport.LoadFace = _simpleSetup.LoadFace;
        _viewport.SupportVisible = true;
        _viewport.ForceVisible = true;
        _viewport.Invalidate();
        Log($"WS02.3/02.4 Object Generator: {dialog.ObjectType} scoped to NS_{dialog.SelectedFace}.");
        _statusMain.Text = $"Generated {dialog.ObjectType} on NS_{dialog.SelectedFace}";
    }

    private async Task RunMeshConvergenceAsync()
    {
        if (!RequireStaticGeometry(true)) return;
        var solid = _simpleSolid!;
        var longest = Math.Max(solid.LengthX, Math.Max(solid.LengthY, solid.LengthZ));
        var sizes = new[] { longest / 2.0, longest / 3.0, longest / 4.0, longest / 6.0, longest / 8.0 };
        try
        {
            UseWaitCursor = true;
            _statusMain.Text = "Running real TET4 mesh convergence study…";
            _convergenceResults = await Task.Run(() => MeshConvergenceStudy.Run(solid, _simpleMaterial, _simpleSetup, sizes));
            _convergenceGrid.Rows.Clear();
            foreach (var point in _convergenceResults)
                _convergenceGrid.Rows.Add(
                    point.ElementSizeMm.ToString("0.###"), point.Nodes, point.Elements,
                    point.MaxDisplacementMm.ToString("0.######"), point.MaxVonMisesMpa.ToString("0.######"),
                    point.DisplacementDifferencePercent.ToString("0.###"), point.StressDifferencePercent.ToString("0.###"),
                    point.EquilibriumError.ToString("E3"));
            _engineeringPlot.SetSeries(
                "WS04.1 — Mesh convergence",
                "TET4 elements", "Maximum displacement (mm)",
                _convergenceResults.Select(point => new StudyPoint(point.Elements, point.MaxDisplacementMm, $"h={point.ElementSizeMm:0.#}")));
            ShowEngineeringTab("Mesh Convergence");
            var finest = _convergenceResults[^1];
            Log($"WS04.1 completed: finest={finest.Elements} TET4, Umax={finest.MaxDisplacementMm:0.######} mm, VM={finest.MaxVonMisesMpa:0.###} MPa.");
            _statusMain.Text = "Mesh convergence completed — review differences against the finest mesh";
        }
        catch (Exception exception)
        {
            Log("CONVERGENCE ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Mesh convergence failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private async Task RunDesignPointStudyAsync()
    {
        if (!RequireStaticGeometry(true)) return;
        using var dialog = new DesignPointDialog(Math.Max(_simpleSetup.ForceN.Length * 0.5, 1), _simpleSetup.ForceN.Length * 2.0, 5);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var values = Enumerable.Range(0, dialog.Count)
            .Select(index => dialog.Minimum + (dialog.Maximum - dialog.Minimum) * index / Math.Max(1, dialog.Count - 1))
            .ToArray();
        try
        {
            UseWaitCursor = true;
            _statusMain.Text = "Solving static Design Points…";
            _designPointResults = await Task.Run(() => StaticDesignPointStudy.Run(_simpleSolid!, _simpleMaterial, _simpleSetup, values));
            _designPointGrid.Rows.Clear();
            foreach (var point in _designPointResults)
                _designPointGrid.Rows.Add(
                    point.Index, point.ForceMagnitudeN.ToString("0.###"), point.YoungModulusMpa.ToString("0.###"), point.ElementSizeMm.ToString("0.###"),
                    point.MaxDisplacementMm.ToString("0.######"), point.MaxVonMisesMpa.ToString("0.######"),
                    point.SafetyFactor.ToString("0.###"), point.EquilibriumError.ToString("E3"));
            _engineeringPlot.SetSeries(
                "WS04.2 — Design Points",
                "Force magnitude (N)", "Maximum von Mises stress (MPa)",
                _designPointResults.Select(point => new StudyPoint(point.ForceMagnitudeN, point.MaxVonMisesMpa, $"DP{point.Index}")));
            ShowEngineeringTab("Design Points");
            Log($"WS04.2 completed: {_designPointResults.Count} static design points solved.");
            _statusMain.Text = "Design Point study completed";
        }
        catch (Exception exception)
        {
            Log("DESIGN POINT ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Design Point study failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private void ConfigureModalTutorial()
    {
        if (!RequireStaticGeometry()) return;
        using var dialog = new ModalSetupDialog(_modalSetup);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        dialog.Apply(_modalSetup);
        _modalResults = [];
        Log($"WS07.1 modal settings: density={_modalSetup.DensityKgM3:0.###} kg/m³, elements={_modalSetup.BeamElements}, modes={_modalSetup.RequestedModes}.");
        _statusMain.Text = "Modal settings defined — solve modes";
    }

    private async Task SolveModalTutorialAsync()
    {
        if (!RequireStaticGeometry()) return;
        try
        {
            UseWaitCursor = true;
            _statusMain.Text = "Solving Euler-Bernoulli modal eigenproblem…";
            _modalResults = await Task.Run(() => EulerBernoulliModalSolver.Solve(_simpleSolid!, _simpleMaterial, _modalSetup));
            _modalGrid.Rows.Clear();
            foreach (var mode in _modalResults)
                _modalGrid.Rows.Add(mode.Mode, mode.FrequencyHz.ToString("0.######"), mode.AnalyticalFrequencyHz.ToString("0.######"),
                    mode.DifferencePercent.ToString("0.###"), mode.DifferencePercent <= 2.0 ? "PASS" : "REVIEW");
            _engineeringPlot.SetSeries(
                "WS07.1 — Modal frequencies",
                "Mode", "Frequency (Hz)",
                _modalResults.Select(mode => new StudyPoint(mode.Mode, mode.FrequencyHz, $"Mode {mode.Mode}")));
            ShowEngineeringTab("Modal");
            _viewport.Caption = "Modal Analysis";
            _viewport.SubCaption = $"Mode 1 = {_modalResults[0].FrequencyHz:0.###} Hz · analytical difference {_modalResults[0].DifferencePercent:0.##}%";
            _viewport.Invalidate();
            Log($"WS07.1 completed: first frequency {_modalResults[0].FrequencyHz:0.######} Hz.");
            _statusMain.Text = "Modal solution completed";
        }
        catch (Exception exception)
        {
            Log("MODAL ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Modal tutorial failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private void ConfigureThermalTutorial()
    {
        if (!RequireStaticGeometry()) return;
        using var dialog = new ThermalSetupDialog(_thermalSetup);
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        dialog.Apply(_thermalSetup);
        _thermalSolution = null;
        Log($"WS07.2 thermal settings: k={_thermalSetup.ConductivityWmK:0.###} W/mK, {_thermalSetup.HotFace}={_thermalSetup.HotTemperatureC:0.###} °C, {_thermalSetup.ColdFace}={_thermalSetup.ColdTemperatureC:0.###} °C.");
        _statusMain.Text = "Thermal settings defined — solve thermal model";
    }

    private async Task SolveThermalTutorialAsync()
    {
        if (!RequireStaticGeometry()) return;
        try
        {
            UseWaitCursor = true;
            _statusMain.Text = "Solving steady-state TET4 heat conduction…";
            var mesh = _simpleMesh ?? StructuredTetMesher.Generate(_simpleSolid!, _simpleSetup.ElementSizeMm);
            _thermalSolution = await Task.Run(() => Tet4SteadyThermalSolver.Solve(_simpleSolid!, mesh, _thermalSetup));
            _simpleMesh = mesh;
            PopulateThermalGrid();
            ShowEngineeringTab("Thermal");
            _viewport.SetSolid(_simpleSolid!);
            _viewport.SetMesh(mesh);
            _viewport.SetThermalSolution(_thermalSolution, _thermalSetup.HotFace, _thermalSetup.ColdFace);
            Log($"WS07.2 completed: Q={_thermalSolution.HeatFlowW:0.######} W, analytical={_thermalSolution.AnalyticalHeatFlowW:0.######} W, balance={_thermalSolution.EnergyBalanceError:E3}.");
            _statusMain.Text = "Steady-state thermal solution completed";
        }
        catch (Exception exception)
        {
            Log("THERMAL ERROR: " + exception.Message);
            MessageBox.Show(this, exception.Message, "Thermal tutorial failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally { UseWaitCursor = false; }
    }

    private void PopulateThermalGrid()
    {
        if (_thermalSolution is null) return;
        _thermalGrid.Rows.Clear();
        AddThermalRow("Minimum temperature", _thermalSolution.MinimumTemperatureC, "°C", "Defined BC");
        AddThermalRow("Maximum temperature", _thermalSolution.MaximumTemperatureC, "°C", "Defined BC");
        AddThermalRow("Total heat flow", _thermalSolution.HeatFlowW, "W", _thermalSolution.HeatFlowDifferencePercent <= 1 ? "PASS" : "REVIEW");
        AddThermalRow("Analytical heat flow", _thermalSolution.AnalyticalHeatFlowW, "W", "Reference");
        AddThermalRow("Heat-flow difference", _thermalSolution.HeatFlowDifferencePercent, "%", _thermalSolution.HeatFlowDifferencePercent <= 1 ? "PASS" : "REVIEW");
        AddThermalRow("Maximum heat flux", _thermalSolution.MaximumHeatFluxWm2, "W/m²", "Result");
        AddThermalRow("Energy-balance error", _thermalSolution.EnergyBalanceError, "relative", _thermalSolution.EnergyBalanceError <= 1e-8 ? "PASS" : "FAIL");
        _engineeringPlot.SetSeries(
            "WS07.2 — Temperature along the prism",
            "Normalized distance", "Temperature (°C)",
            Enumerable.Range(0, 11).Select(index =>
            {
                var fraction = index / 10.0;
                return new StudyPoint(fraction,
                    _thermalSetup.HotTemperatureC + (_thermalSetup.ColdTemperatureC - _thermalSetup.HotTemperatureC) * fraction,
                    $"{fraction:0.0}");
            }));
    }

    private void AddThermalRow(string name, double value, string unit, string acceptance) =>
        _thermalGrid.Rows.Add(name, double.IsNaN(value) ? "N/A" : value.ToString("0.######"), unit, acceptance);

    private void ShowEngineeringResults()
    {
        var page = _lowerTabs.TabPages.Cast<TabPage>().FirstOrDefault(tab => tab.Text == "Tutorial Results");
        if (page is not null) _lowerTabs.SelectedTab = page;
    }

    private void ShowEngineeringTab(string title)
    {
        ShowEngineeringResults();
        if (_engineeringResultTabs is null) return;
        var tab = _engineeringResultTabs.TabPages.Cast<TabPage>().FirstOrDefault(page => page.Text == title);
        if (tab is not null) _engineeringResultTabs.SelectedTab = tab;
    }

    private void ShowModalResults()
    {
        if (_modalResults.Count == 0) { _ = SolveModalTutorialAsync(); return; }
        ShowEngineeringTab("Modal");
    }

    private void ShowThermalResults()
    {
        if (_thermalSolution is null) { _ = SolveThermalTutorialAsync(); return; }
        PopulateThermalGrid();
        ShowEngineeringTab("Thermal");
    }

    private void ExportActiveEngineeringStudy()
    {
        if (_convergenceResults.Count > 0) ExportConvergenceStudy();
        else if (_designPointResults.Count > 0) ExportDesignPointStudy();
        else MessageBox.Show(this, "Run a mesh convergence or Design Point study first.", "Export study", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private void ExportConvergenceStudy()
    {
        if (_convergenceResults.Count == 0) return;
        using var dialog = new SaveFileDialog { Filter = "HTML report (*.html)|*.html", FileName = "AsterMax_WS04_Mesh_Convergence.html" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var rows = _convergenceResults.Select(point => new[]
        {
            point.ElementSizeMm.ToString("0.###"), point.Nodes.ToString(), point.Elements.ToString(),
            point.MaxDisplacementMm.ToString("0.######"), point.MaxVonMisesMpa.ToString("0.######"),
            point.DisplacementDifferencePercent.ToString("0.###"), point.StressDifferencePercent.ToString("0.###"), point.EquilibriumError.ToString("E3")
        });
        WriteStudyReport(dialog.FileName, "WS04.1 — Mesh Convergence", new[] { "h (mm)", "Nodes", "TET4", "Umax (mm)", "von Mises (MPa)", "ΔU (%)", "Δσ (%)", "Equilibrium" }, rows,
            "Convergence is measured against the finest generated mesh. A formal memorandum should define an acceptance threshold before the study is run.");
    }

    private void ExportDesignPointStudy()
    {
        if (_designPointResults.Count == 0) return;
        using var dialog = new SaveFileDialog { Filter = "HTML report (*.html)|*.html", FileName = "AsterMax_WS04_Design_Points.html" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var rows = _designPointResults.Select(point => new[]
        {
            point.Index.ToString(), point.ForceMagnitudeN.ToString("0.###"), point.YoungModulusMpa.ToString("0.###"), point.ElementSizeMm.ToString("0.###"),
            point.MaxDisplacementMm.ToString("0.######"), point.MaxVonMisesMpa.ToString("0.######"), point.SafetyFactor.ToString("0.###"), point.EquilibriumError.ToString("E3")
        });
        WriteStudyReport(dialog.FileName, "WS04.2 — Design Points", new[] { "DP", "Force (N)", "E (MPa)", "h (mm)", "Umax (mm)", "VM (MPa)", "SF", "Equilibrium" }, rows,
            "This study varies the force magnitude while preserving its direction and all other model settings.");
    }

    private void ExportModalStudy()
    {
        if (_modalResults.Count == 0) { _ = SolveModalTutorialAsync(); return; }
        using var dialog = new SaveFileDialog { Filter = "HTML report (*.html)|*.html", FileName = "AsterMax_WS07_Modal.html" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var rows = _modalResults.Select(mode => new[]
        {
            mode.Mode.ToString(), mode.FrequencyHz.ToString("0.######"), mode.AnalyticalFrequencyHz.ToString("0.######"), mode.DifferencePercent.ToString("0.###")
        });
        WriteStudyReport(dialog.FileName, "WS07.1 — Modal Cantilever", new[] { "Mode", "FE frequency (Hz)", "Analytical (Hz)", "Difference (%)" }, rows,
            "The verified scope is a slender rectangular cantilever represented with Euler-Bernoulli beam elements and a consistent mass matrix.");
    }

    private void ExportThermalStudy()
    {
        if (_thermalSolution is null) { _ = SolveThermalTutorialAsync(); return; }
        using var dialog = new SaveFileDialog { Filter = "HTML report (*.html)|*.html", FileName = "AsterMax_WS07_Steady_Thermal.html" };
        if (dialog.ShowDialog(this) != DialogResult.OK) return;
        var rows = new[]
        {
            new[] { "Minimum temperature", _thermalSolution.MinimumTemperatureC.ToString("0.######"), "°C" },
            new[] { "Maximum temperature", _thermalSolution.MaximumTemperatureC.ToString("0.######"), "°C" },
            new[] { "Heat flow", _thermalSolution.HeatFlowW.ToString("0.######"), "W" },
            new[] { "Analytical heat flow", _thermalSolution.AnalyticalHeatFlowW.ToString("0.######"), "W" },
            new[] { "Difference", _thermalSolution.HeatFlowDifferencePercent.ToString("0.###"), "%" },
            new[] { "Maximum heat flux", _thermalSolution.MaximumHeatFluxWm2.ToString("0.######"), "W/m²" },
            new[] { "Energy balance", _thermalSolution.EnergyBalanceError.ToString("E3"), "relative" }
        };
        WriteStudyReport(dialog.FileName, "WS07.2 — Steady-State Thermal", new[] { "Result", "Value", "Unit" }, rows,
            "The model solves scalar heat conduction on the same structured TET4 mesh with prescribed temperatures on two faces.");
    }

    private static void WriteStudyReport(string path, string title, IReadOnlyList<string> headers, IEnumerable<string[]> rows, string note)
    {
        var builder = new StringBuilder();
        builder.Append("<!doctype html><html lang='en'><head><meta charset='utf-8'><title>").Append(WebUtility.HtmlEncode(title)).Append("</title>")
            .Append("<style>body{font-family:Segoe UI,Arial;margin:36px;color:#263746}h1{color:#0767a5}table{border-collapse:collapse;width:100%}th,td{border:1px solid #b9c7d4;padding:7px}th{background:#e7f0f7}.note{margin:18px 0;padding:12px;background:#fff5ce;border-left:5px solid #d49700}</style></head><body>")
            .Append("<h1>").Append(WebUtility.HtmlEncode(title)).Append("</h1><p>AsterMax Mechanical 0.6 beta · ").Append(DateTime.Now.ToString("yyyy-MM-dd HH:mm")).Append("</p>")
            .Append("<div class='note'>").Append(WebUtility.HtmlEncode(note)).Append(" Results remain subject to model assumptions, mesh verification and engineering review.</div><table><thead><tr>");
        foreach (var header in headers) builder.Append("<th>").Append(WebUtility.HtmlEncode(header)).Append("</th>");
        builder.Append("</tr></thead><tbody>");
        foreach (var row in rows)
        {
            builder.Append("<tr>");
            foreach (var value in row) builder.Append("<td>").Append(WebUtility.HtmlEncode(value)).Append("</td>");
            builder.Append("</tr>");
        }
        builder.Append("</tbody></table></body></html>");
        File.WriteAllText(path, builder.ToString(), new UTF8Encoding(false));
        var csv = Path.ChangeExtension(path, ".csv");
        var csvBuilder = new StringBuilder().AppendLine(string.Join(',', headers.Select(Csv)));
        foreach (var row in rows) csvBuilder.AppendLine(string.Join(',', row.Select(Csv)));
        File.WriteAllText(csv, csvBuilder.ToString(), new UTF8Encoding(false));
        Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });

        static string Csv(string value) => "\"" + value.Replace("\"", "\"\"") + "\"";
    }

    private static double FaceArea(SimpleStepSolid solid, SimpleFace face) => face switch
    {
        SimpleFace.XMin or SimpleFace.XMax => solid.LengthY * solid.LengthZ,
        SimpleFace.YMin or SimpleFace.YMax => solid.LengthX * solid.LengthZ,
        SimpleFace.ZMin or SimpleFace.ZMax => solid.LengthX * solid.LengthY,
        _ => 0
    };

    private static Vec3 FaceCenterForSelection(SimpleStepSolid solid, SimpleFace face) => face switch
    {
        SimpleFace.XMin => new(solid.Min.X, solid.Center.Y, solid.Center.Z),
        SimpleFace.XMax => new(solid.Max.X, solid.Center.Y, solid.Center.Z),
        SimpleFace.YMin => new(solid.Center.X, solid.Min.Y, solid.Center.Z),
        SimpleFace.YMax => new(solid.Center.X, solid.Max.Y, solid.Center.Z),
        SimpleFace.ZMin => new(solid.Center.X, solid.Center.Y, solid.Min.Z),
        SimpleFace.ZMax => new(solid.Center.X, solid.Center.Y, solid.Max.Z),
        _ => solid.Center
    };
}

internal sealed record FaceNamedSelection(string Name, SimpleFace Face, double AreaMm2, Vec3 Center, int NodeCount);
internal sealed record StudyPoint(double X, double Y, string Label);

internal sealed class StudyPlotPanel : Panel
{
    private string _title = "Run a tutorial study";
    private string _xLabel = string.Empty;
    private string _yLabel = string.Empty;
    private IReadOnlyList<StudyPoint> _points = [];

    public StudyPlotPanel()
    {
        DoubleBuffered = true;
        BackColor = Color.White;
    }

    public void SetSeries(string title, string xLabel, string yLabel, IEnumerable<StudyPoint> points)
    {
        _title = title;
        _xLabel = xLabel;
        _yLabel = yLabel;
        _points = points.ToArray();
        Invalidate();
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        using var titleFont = new Font("Segoe UI Semibold", 12f);
        using var axisFont = new Font("Segoe UI", 8.5f);
        using var pen = new Pen(Color.FromArgb(48, 91, 122), 1.2f);
        using var series = new Pen(Color.FromArgb(0, 114, 198), 2.2f);
        using var pointBrush = new SolidBrush(Color.FromArgb(0, 114, 198));
        g.DrawString(_title, titleFont, Brushes.DarkSlateGray, 18, 14);
        var chart = new RectangleF(72, 52, Math.Max(80, Width - 105), Math.Max(70, Height - 105));
        g.DrawLine(pen, chart.Left, chart.Bottom, chart.Right, chart.Bottom);
        g.DrawLine(pen, chart.Left, chart.Top, chart.Left, chart.Bottom);
        g.DrawString(_xLabel, axisFont, Brushes.SlateGray, chart.Left + chart.Width / 2 - 30, chart.Bottom + 28);
        g.DrawString(_yLabel, axisFont, Brushes.SlateGray, 8, chart.Top - 3);
        if (_points.Count == 0) return;
        var minX = _points.Min(point => point.X);
        var maxX = _points.Max(point => point.X);
        var minY = _points.Min(point => point.Y);
        var maxY = _points.Max(point => point.Y);
        if (Math.Abs(maxX - minX) < 1e-15) maxX = minX + 1;
        if (Math.Abs(maxY - minY) < 1e-15) maxY = minY + 1;
        PointF Map(StudyPoint point) => new(
            chart.Left + (float)((point.X - minX) / (maxX - minX) * chart.Width),
            chart.Bottom - (float)((point.Y - minY) / (maxY - minY) * chart.Height));
        var mapped = _points.Select(Map).ToArray();
        if (mapped.Length > 1) g.DrawLines(series, mapped);
        for (var index = 0; index < mapped.Length; index++)
        {
            g.FillEllipse(pointBrush, mapped[index].X - 4, mapped[index].Y - 4, 8, 8);
            g.DrawString(_points[index].Label, axisFont, Brushes.DimGray, mapped[index].X + 5, mapped[index].Y - 16);
        }
        g.DrawString(minX.ToString("0.###"), axisFont, Brushes.SlateGray, chart.Left - 10, chart.Bottom + 4);
        g.DrawString(maxX.ToString("0.###"), axisFont, Brushes.SlateGray, chart.Right - 28, chart.Bottom + 4);
        g.DrawString(minY.ToString("0.###"), axisFont, Brushes.SlateGray, 30, chart.Bottom - 8);
        g.DrawString(maxY.ToString("0.###"), axisFont, Brushes.SlateGray, 30, chart.Top - 6);
    }
}

internal sealed class ObjectGeneratorDialog : Form
{
    private readonly ComboBox _type = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
    private readonly ComboBox _selection = new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
    public string ObjectType => _type.SelectedItem?.ToString() ?? "Fixed Support";
    public SimpleFace SelectedFace => ((FaceNamedSelection)_selection.SelectedItem!).Face;

    public ObjectGeneratorDialog(IReadOnlyList<FaceNamedSelection> selections)
    {
        Text = "WS02 — Object Generator";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(430, 180);
        _type.Items.AddRange(new object[] { "Fixed Support", "Force" });
        _type.SelectedIndex = 0;
        foreach (var selection in selections) _selection.Items.Add(selection);
        _selection.DisplayMember = nameof(FaceNamedSelection.Name);
        _selection.SelectedIndex = Math.Min(1, _selection.Items.Count - 1);
        var table = DialogTable();
        table.Controls.Add(new Label { Text = "Template object", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 0);
        table.Controls.Add(_type, 1, 0);
        table.Controls.Add(new Label { Text = "Target Named Selection", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 1);
        table.Controls.Add(_selection, 1, 1);
        table.Controls.Add(DialogButtons(this), 0, 3);
        table.SetColumnSpan(table.GetControlFromPosition(0, 3), 2);
        Controls.Add(table);
    }

    private static TableLayoutPanel DialogTable() => new()
    {
        Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 2, RowCount = 4,
        ColumnStyles = { new ColumnStyle(SizeType.Absolute, 150), new ColumnStyle(SizeType.Percent, 100) },
        RowStyles = { new RowStyle(SizeType.Absolute, 38), new RowStyle(SizeType.Absolute, 38), new RowStyle(SizeType.Percent, 100), new RowStyle(SizeType.Absolute, 42) }
    };

    internal static FlowLayoutPanel DialogButtons(Form owner)
    {
        var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft };
        var ok = new Button { Text = "Apply", DialogResult = DialogResult.OK, Width = 90 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 90 };
        flow.Controls.Add(ok); flow.Controls.Add(cancel);
        owner.AcceptButton = ok; owner.CancelButton = cancel;
        return flow;
    }
}

internal sealed class DesignPointDialog : Form
{
    private readonly NumericUpDown _minimum = NumberBox(1, 100000000, 1);
    private readonly NumericUpDown _maximum = NumberBox(1, 100000000, 1);
    private readonly NumericUpDown _count = NumberBox(2, 12, 1);
    public double Minimum => (double)_minimum.Value;
    public double Maximum => (double)_maximum.Value;
    public int Count => (int)_count.Value;

    public DesignPointDialog(double minimum, double maximum, int count)
    {
        Text = "WS04.2 — Design Point force sweep";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(430, 220);
        _minimum.Value = ClampDecimal(minimum, _minimum.Minimum, _minimum.Maximum);
        _maximum.Value = ClampDecimal(maximum, _maximum.Minimum, _maximum.Maximum);
        _count.Value = count;
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 2, RowCount = 5 };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 170)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(table, 0, "Minimum force (N)", _minimum); AddRow(table, 1, "Maximum force (N)", _maximum); AddRow(table, 2, "Design points", _count);
        var buttons = ObjectGeneratorDialog.DialogButtons(this); table.Controls.Add(buttons, 0, 4); table.SetColumnSpan(buttons, 2);
        Controls.Add(table);
    }

    internal static NumericUpDown NumberBox(decimal minimum, decimal maximum, int decimals) => new()
    { Dock = DockStyle.Fill, Minimum = minimum, Maximum = maximum, DecimalPlaces = decimals, ThousandsSeparator = true };
    internal static decimal ClampDecimal(double value, decimal minimum, decimal maximum) => Math.Clamp((decimal)value, minimum, maximum);
    internal static void AddRow(TableLayoutPanel table, int row, string label, Control control)
    { table.RowStyles.Add(new RowStyle(SizeType.Absolute, 38)); table.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left }, 0, row); table.Controls.Add(control, 1, row); }
}

internal sealed class ModalSetupDialog : Form
{
    private readonly NumericUpDown _density = DesignPointDialog.NumberBox(1, 100000, 1);
    private readonly NumericUpDown _elements = DesignPointDialog.NumberBox(2, 40, 0);
    private readonly NumericUpDown _modes = DesignPointDialog.NumberBox(1, 6, 0);

    public ModalSetupDialog(BeamModalSetup setup)
    {
        Text = "WS07.1 — Modal settings";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(430, 220);
        _density.Value = DesignPointDialog.ClampDecimal(setup.DensityKgM3, _density.Minimum, _density.Maximum);
        _elements.Value = setup.BeamElements;
        _modes.Value = setup.RequestedModes;
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 2, RowCount = 5 };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 170)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        DesignPointDialog.AddRow(table, 0, "Density (kg/m³)", _density);
        DesignPointDialog.AddRow(table, 1, "Beam elements", _elements);
        DesignPointDialog.AddRow(table, 2, "Requested modes", _modes);
        var buttons = ObjectGeneratorDialog.DialogButtons(this); table.Controls.Add(buttons, 0, 4); table.SetColumnSpan(buttons, 2);
        Controls.Add(table);
    }

    public void Apply(BeamModalSetup setup)
    { setup.DensityKgM3 = (double)_density.Value; setup.BeamElements = (int)_elements.Value; setup.RequestedModes = (int)_modes.Value; }
}

internal sealed class ThermalSetupDialog : Form
{
    private readonly NumericUpDown _conductivity = DesignPointDialog.NumberBox(1, 10000, 3);
    private readonly NumericUpDown _hotTemperature = DesignPointDialog.NumberBox(-273, 5000, 2);
    private readonly NumericUpDown _coldTemperature = DesignPointDialog.NumberBox(-273, 5000, 2);
    private readonly ComboBox _hotFace = FaceBox();
    private readonly ComboBox _coldFace = FaceBox();

    public ThermalSetupDialog(ThermalSetup setup)
    {
        Text = "WS07.2 — Steady-state thermal settings";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(460, 300);
        _conductivity.Value = DesignPointDialog.ClampDecimal(setup.ConductivityWmK, _conductivity.Minimum, _conductivity.Maximum);
        _hotTemperature.Value = DesignPointDialog.ClampDecimal(setup.HotTemperatureC, _hotTemperature.Minimum, _hotTemperature.Maximum);
        _coldTemperature.Value = DesignPointDialog.ClampDecimal(setup.ColdTemperatureC, _coldTemperature.Minimum, _coldTemperature.Maximum);
        _hotFace.SelectedItem = setup.HotFace; _coldFace.SelectedItem = setup.ColdFace;
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(14), ColumnCount = 2, RowCount = 7 };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 190)); table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        DesignPointDialog.AddRow(table, 0, "Conductivity (W/m·K)", _conductivity);
        DesignPointDialog.AddRow(table, 1, "Hot face", _hotFace);
        DesignPointDialog.AddRow(table, 2, "Hot temperature (°C)", _hotTemperature);
        DesignPointDialog.AddRow(table, 3, "Cold face", _coldFace);
        DesignPointDialog.AddRow(table, 4, "Cold temperature (°C)", _coldTemperature);
        var buttons = ObjectGeneratorDialog.DialogButtons(this); table.Controls.Add(buttons, 0, 6); table.SetColumnSpan(buttons, 2);
        Controls.Add(table);
    }

    public void Apply(ThermalSetup setup)
    {
        setup.ConductivityWmK = (double)_conductivity.Value;
        setup.HotFace = (SimpleFace)_hotFace.SelectedItem!;
        setup.ColdFace = (SimpleFace)_coldFace.SelectedItem!;
        setup.HotTemperatureC = (double)_hotTemperature.Value;
        setup.ColdTemperatureC = (double)_coldTemperature.Value;
    }

    private static ComboBox FaceBox()
    {
        var box = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList };
        box.Items.AddRange(Enum.GetValues<SimpleFace>().Cast<object>().ToArray());
        return box;
    }
}
