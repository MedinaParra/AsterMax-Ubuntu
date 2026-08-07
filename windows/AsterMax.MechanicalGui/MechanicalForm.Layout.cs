namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private void BuildLayout()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 5,
            BackColor = Bg,
            Margin = Padding.Empty,
            Padding = Padding.Empty
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 27));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 126));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
        Controls.Add(root);

        _menu.Dock = DockStyle.Fill;
        _menu.BackColor = Color.FromArgb(20, 22, 26);
        _menu.ForeColor = TextMain;
        _menu.Renderer = new DarkRenderer();
        root.Controls.Add(_menu, 0, 0);

        _ribbon.Dock = DockStyle.Fill;
        _ribbon.Padding = new Point(14, 5);
        root.Controls.Add(_ribbon, 0, 1);

        BuildWorkflowBar();
        root.Controls.Add(_workflow, 0, 2);

        var content = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Vertical,
            SplitterDistance = 285,
            SplitterWidth = 5,
            Panel1MinSize = 220,
            Panel2MinSize = 680,
            BackColor = Border
        };
        root.Controls.Add(content, 0, 3);
        content.Panel1.Controls.Add(BuildOutlinePanel());

        var right = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Vertical,
            SplitterDistance = 900,
            SplitterWidth = 5,
            Panel1MinSize = 540,
            Panel2MinSize = 285,
            BackColor = Border
        };
        content.Panel2.Controls.Add(right);

        var center = new SplitContainer
        {
            Dock = DockStyle.Fill,
            Orientation = Orientation.Horizontal,
            SplitterDistance = 545,
            SplitterWidth = 5,
            Panel1MinSize = 320,
            Panel2MinSize = 150,
            BackColor = Border
        };
        right.Panel1.Controls.Add(center);
        center.Panel1.Controls.Add(BuildGraphicsPanel());
        center.Panel2.Controls.Add(BuildLowerTabs());
        right.Panel2.Controls.Add(BuildDetailsPanel());

        _status.Dock = DockStyle.Fill;
        _status.BackColor = Color.FromArgb(20, 22, 25);
        _status.ForeColor = TextMuted;
        _status.SizingGrip = false;
        _statusMain.Spring = true;
        _statusMain.TextAlign = ContentAlignment.MiddleLeft;
        _statusSelection.BorderSides = ToolStripStatusLabelBorderSides.Left;
        _statusSolver.BorderSides = ToolStripStatusLabelBorderSides.Left;
        _status.Items.AddRange(new ToolStripItem[] { _statusMain, _statusSelection, _statusSolver });
        root.Controls.Add(_status, 0, 4);
    }

    private void BuildWorkflowBar()
    {
        _workflow.Dock = DockStyle.Fill;
        _workflow.FlowDirection = FlowDirection.LeftToRight;
        _workflow.WrapContents = false;
        _workflow.Padding = new Padding(14, 5, 10, 4);
        _workflow.BackColor = Color.FromArgb(22, 25, 29);
        _workflow.Controls.Add(new Label
        {
            Text = "WORKFLOW",
            Width = 90,
            Height = 30,
            TextAlign = ContentAlignment.MiddleLeft,
            ForeColor = TextMuted,
            Font = new Font("Segoe UI Semibold", 9f)
        });
        AddWorkflowStep("1  Preliminary Decisions", "Project");
        AddWorkflowArrow();
        AddWorkflowStep("2  Preprocessing", "Model");
        AddWorkflowArrow();
        AddWorkflowStep("3  Solution", "Analysis Settings");
        AddWorkflowArrow();
        AddWorkflowStep("4  Postprocessing", "Solution");
    }

    private Control BuildOutlinePanel()
    {
        var panel = new Panel { Dock = DockStyle.Fill, BackColor = Panel };
        var header = SectionHeader("Outline");
        var search = new TextBox
        {
            Dock = DockStyle.Top,
            Height = 29,
            PlaceholderText = "Filter tree...",
            BackColor = Field,
            ForeColor = TextMain,
            BorderStyle = BorderStyle.FixedSingle
        };
        search.TextChanged += (_, _) => FilterTree(search.Text);
        _outline.Dock = DockStyle.Fill;
        _outline.BackColor = Panel;
        _outline.ForeColor = TextMain;
        _outline.BorderStyle = BorderStyle.None;
        _outline.HideSelection = false;
        _outline.FullRowSelect = true;
        _outline.DrawMode = TreeViewDrawMode.OwnerDrawText;
        _outline.ItemHeight = 23;
        _outline.Indent = 18;
        panel.Controls.Add(_outline);
        panel.Controls.Add(search);
        panel.Controls.Add(header);
        return panel;
    }

    private Control BuildGraphicsPanel()
    {
        var panel = new Panel { Dock = DockStyle.Fill, BackColor = Bg };
        _graphicsTools.Dock = DockStyle.Top;
        _graphicsTools.GripStyle = ToolStripGripStyle.Hidden;
        _graphicsTools.BackColor = Panel2;
        _graphicsTools.ForeColor = TextMain;
        _graphicsTools.Renderer = new DarkRenderer();
        _graphicsTools.Items.Add(new ToolStripLabel("Selection:"));
        foreach (var filter in new[] { "Vertex", "Edge", "Face", "Body", "Node", "Element" })
        {
            var item = new ToolStripButton(filter) { CheckOnClick = true, DisplayStyle = ToolStripItemDisplayStyle.Text };
            item.Click += (_, _) => _statusSelection.Text = $"Selection filter: {filter}";
            _graphicsTools.Items.Add(item);
        }
        _graphicsTools.Items.Add(new ToolStripSeparator());
        _graphicsTools.Items.Add(ToolButton("Fit (F7)", (_, _) => _viewport.Fit()));
        _graphicsTools.Items.Add(ToolButton("Geometry", (_, _) => ShowView("Geometry")));
        _graphicsTools.Items.Add(ToolButton("Mesh", (_, _) => ShowView("Mesh")));
        _graphicsTools.Items.Add(ToolButton("Results", (_, _) => ShowView("Results")));
        _graphicsTools.Items.Add(new ToolStripSeparator());
        _graphicsTools.Items.Add(new ToolStripLabel("Units:"));
        var units = new ToolStripComboBox { Width = 185, DropDownStyle = ComboBoxStyle.DropDownList };
        units.Items.AddRange(new object[] { "Metric (mm, kg, N, s)", "Metric (m, kg, N, s)", "SI (m, kg, Pa)", "US Customary (in, lbm, lbf)" });
        units.SelectedItem = _units;
        units.SelectedIndexChanged += (_, _) => { if (units.SelectedItem is string value) { _units = value; _statusMain.Text = $"Units: {_units}"; UpdateDetails(_outline.SelectedNode); } };
        _graphicsTools.Items.Add(units);
        panel.Controls.Add(_viewport);
        panel.Controls.Add(_graphicsTools);
        return panel;
    }

    private Control BuildDetailsPanel()
    {
        var panel = new Panel { Dock = DockStyle.Fill, BackColor = Panel };
        _details.Dock = DockStyle.Fill;
        ConfigureGrid(_details, headers: false);
        _details.SelectionMode = DataGridViewSelectionMode.CellSelect;
        _details.Columns.Add(new DataGridViewTextBoxColumn { Name = "Property", FillWeight = 43, ReadOnly = true });
        _details.Columns.Add(new DataGridViewTextBoxColumn { Name = "Value", FillWeight = 57 });
        panel.Controls.Add(_details);
        panel.Controls.Add(SectionHeader("Details"));
        return panel;
    }

    private Control BuildLowerTabs()
    {
        _lowerTabs.Dock = DockStyle.Fill;
        _lowerTabs.Padding = new Point(12, 4);

        var graphics = Tab("Graphics");
        graphics.Controls.Add(new Label
        {
            Dock = DockStyle.Fill,
            Text = "Select an Outline object to change the Graphics context.",
            TextAlign = ContentAlignment.MiddleCenter,
            ForeColor = TextMuted
        });
        _lowerTabs.TabPages.Add(graphics);

        var worksheet = Tab("Worksheet");
        ConfigureGrid(_worksheet, headers: true);
        worksheet.Controls.Add(_worksheet);
        _lowerTabs.TabPages.Add(worksheet);

        var graph = Tab("Graph");
        _graph.Dock = DockStyle.Fill;
        _graph.BackColor = Field;
        _graph.Paint += DrawGraph;
        graph.Controls.Add(_graph);
        _lowerTabs.TabPages.Add(graph);

        var tabular = Tab("Tabular Data");
        ConfigureGrid(_tabular, headers: true);
        tabular.Controls.Add(_tabular);
        _lowerTabs.TabPages.Add(tabular);

        var messages = Tab("Messages");
        _messages.Dock = DockStyle.Fill;
        _messages.ReadOnly = true;
        _messages.BackColor = Field;
        _messages.ForeColor = Color.FromArgb(205, 215, 226);
        _messages.BorderStyle = BorderStyle.None;
        _messages.Font = new Font("Cascadia Mono", 9f);
        messages.Controls.Add(_messages);
        _lowerTabs.TabPages.Add(messages);
        return _lowerTabs;
    }

    private void BuildMenus()
    {
        var file = Menu("File",
            Item("New Project", (_, _) => NewProject(), Keys.Control | Keys.N),
            Item("Open Project...", (_, _) => OpenProject(), Keys.Control | Keys.O),
            Item("Save", (_, _) => SaveProject(false), Keys.Control | Keys.S),
            Item("Save As...", (_, _) => SaveProject(true)),
            new ToolStripSeparator(),
            Item("Import Geometry...", (_, _) => ImportGeometry()),
            Item("Import Mesh...", (_, _) => ImportMesh()),
            new ToolStripSeparator(),
            Item("Exit", (_, _) => Close()));

        var edit = Menu("Edit",
            Item("Rename", (_, _) => RenameSelected(), Keys.F2),
            Item("Duplicate", (_, _) => DuplicateSelected()),
            Item("Suppress / Unsuppress", (_, _) => ToggleSuppression()),
            Item("Delete", (_, _) => DeleteSelected(), Keys.Delete));

        var view = Menu("View",
            Item("Fit", (_, _) => _viewport.Fit(), Keys.F7),
            Item("Geometry", (_, _) => ShowView("Geometry")),
            Item("Mesh", (_, _) => ShowView("Mesh")),
            Item("Results", (_, _) => ShowView("Results")),
            new ToolStripSeparator(),
            Item("Worksheet", (_, _) => _lowerTabs.SelectedIndex = 1),
            Item("Graph", (_, _) => _lowerTabs.SelectedIndex = 2),
            Item("Messages", (_, _) => _lowerTabs.SelectedIndex = 4));

        var solver = Menu("Solver",
            Item("Configure Code_Aster...", (_, _) => ConfigureSolver()),
            Item("Validate Backend", async (_, _) => await ValidateBackendAsync()),
            Item("Run .export...", async (_, _) => await RunExportAsync()),
            new ToolStripSeparator(),
            Item("Export .comm...", (_, _) => ExportComm()));

        var help = Menu("Help",
            Item("Workflow Guide", (_, _) => ShowWorkflowGuide()),
            Item("About", (_, _) => MessageBox.Show(this,
                "AsterMax Mechanical 0.3 beta\n\nOriginal AsterMax interface implementing the Mechanical finite-element workflow without redistributing proprietary code, icons or screenshots.\n\nGNU GPL v3.",
                "About AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Information)));

        _menu.Items.AddRange(new ToolStripItem[] { file, edit, view, solver, help });
    }

    private void BuildRibbon()
    {
        _ribbon.TabPages.Add(RibbonPage("Home",
            Group("Project", RButton("New", NewProject), RButton("Open", OpenProject), RButton("Save", () => SaveProject(false))),
            Group("Model", RButton("Import Geometry", ImportGeometry), RButton("Materials", () => SelectNode("Materials")), RButton("Named Selection", AddNamedSelection)),
            Group("Analysis", RButton("Static Structural", () => AddAnalysis("Static Structural")), RButton("Modal", () => AddAnalysis("Modal")), RButton("Thermal", () => AddAnalysis("Steady-State Thermal"))),
            Group("Solve", RButton("Generate Mesh", GenerateMesh), RButton("Solve", () => _ = SolveAsync(), true), RButton("Evaluate All", EvaluateResults))));

        _ribbon.TabPages.Add(RibbonPage("Geometry",
            Group("Import", RButton("STEP / IGES / BREP", ImportGeometry), RButton("MED / MSH", ImportMesh)),
            Group("Body", RButton("Assign Material", AssignMaterial), RButton("Suppress", ToggleSuppression), RButton("Point Mass", () => AddSimpleObject("Geometry", "Point Mass", ObjectKind.Body, "Geometry"))),
            Group("Coordinate Systems", RButton("Coordinate System", AddCoordinateSystem), RButton("Display All", () => Log("All coordinate systems displayed."))),
            Group("Selections", RButton("Named Selection", AddNamedSelection), RButton("Worksheet", OpenWorksheet))));

        _ribbon.TabPages.Add(RibbonPage("Connections",
            Group("Contact", RButton("Automatic Contacts", CreateContacts), RButton("Contact Region", AddContact), RButton("Contact Tool", AddContactTool)),
            Group("Connections", RButton("Joint", () => AddSimpleObject("Connections", "Joint", ObjectKind.Contact, "Joint")), RButton("Spring", () => AddSimpleObject("Connections", "Spring", ObjectKind.Contact, "Spring")), RButton("Beam", () => AddSimpleObject("Connections", "Beam Connection", ObjectKind.Contact, "Beam"))),
            Group("Remote", RButton("Remote Point", () => AddSimpleObject("Connections", "Remote Point", ObjectKind.Contact, "Remote")), RButton("Constraint Equation", () => AddSimpleObject("Connections", "Constraint Equation", ObjectKind.Contact, "Constraint Equation"))),
            Group("Review", RButton("Worksheet", ShowConnectionsWorksheet), RButton("Matrix", ShowConnectionMatrix))));

        _ribbon.TabPages.Add(RibbonPage("Mesh",
            Group("Mesh", RButton("Generate", GenerateMesh, true), RButton("Clear", ClearMesh), RButton("Statistics", ShowMeshStatistics)),
            Group("Controls", RButton("Sizing", () => AddMeshControl("Sizing")), RButton("Method", () => AddMeshControl("Method")), RButton("Inflation", () => AddMeshControl("Inflation")), RButton("Face Meshing", () => AddMeshControl("Face Meshing"))),
            Group("Quality", RButton("Element Quality", () => ShowMeshMetric("Element Quality")), RButton("Skewness", () => ShowMeshMetric("Skewness")), RButton("Jacobian", () => ShowMeshMetric("Jacobian Ratio")))));

        _ribbon.TabPages.Add(RibbonPage("Environment",
            Group("Supports", RButton("Fixed Support", () => AddSupport("Fixed Support")), RButton("Displacement", () => AddSupport("Displacement")), RButton("Frictionless", () => AddSupport("Frictionless Support")), RButton("Cylindrical", () => AddSupport("Cylindrical Support"))),
            Group("Loads", RButton("Force", () => AddLoad("Force")), RButton("Pressure", () => AddLoad("Pressure")), RButton("Moment", () => AddLoad("Moment")), RButton("Gravity", () => AddLoad("Gravity"))),
            Group("Remote Loads", RButton("Remote Force", () => AddLoad("Remote Force")), RButton("Bearing Load", () => AddLoad("Bearing Load")), RButton("Thermal", () => AddLoad("Thermal Condition"))),
            Group("Analysis", RButton("Analysis Settings", () => SelectNode("Analysis Settings")), RButton("Step Controls", ShowStepWorksheet))));

        _ribbon.TabPages.Add(RibbonPage("Results",
            Group("Deformation", RButton("Total", () => AddResult("Total Deformation")), RButton("Directional", () => AddResult("Directional Deformation"))),
            Group("Stress", RButton("Equivalent", () => AddResult("Equivalent Stress")), RButton("Maximum Principal", () => AddResult("Maximum Principal Stress")), RButton("Stress Intensity", () => AddResult("Stress Intensity"))),
            Group("Strain", RButton("Equivalent Elastic", () => AddResult("Equivalent Elastic Strain")), RButton("Thermal", () => AddResult("Thermal Strain"))),
            Group("Tools", RButton("Reaction Probe", () => AddResult("Force Reaction", ObjectKind.Probe)), RButton("Contact Tool", AddContactTool), RButton("Chart", AddChart)),
            Group("Evaluate", RButton("Evaluate All", EvaluateResults, true), RButton("Clear Data", ClearResults))));

        _ribbon.TabPages.Add(RibbonPage("Advanced",
            Group("Analysis Types", RButton("Modal", () => AddAnalysis("Modal")), RButton("Thermal", () => AddAnalysis("Steady-State Thermal")), RButton("Buckling", () => AddAnalysis("Eigenvalue Buckling")), RButton("Submodel", () => AddAnalysis("Submodel"))),
            Group("Nonlinear", RButton("Large Deflection", ToggleLargeDeflection), RButton("Multistep", ShowStepWorksheet), RButton("Restart Controls", () => Log("Restart controls selected."))),
            Group("Automation", RButton("Object Generator", OpenObjectGenerator), RButton("Parameters", ShowParameters), RButton("Export Code_Aster", ExportComm))));

        var contextPage = RibbonPage("Context");
        _contextTitle.Width = 205;
        _contextTitle.Height = 76;
        _contextTitle.TextAlign = ContentAlignment.MiddleCenter;
        _contextTitle.ForeColor = TextMain;
        _contextTitle.Font = new Font("Segoe UI Semibold", 10.5f);
        _contextButtons.AutoSize = true;
        _contextButtons.WrapContents = false;
        _contextButtons.BackColor = Panel;
        ((FlowLayoutPanel)contextPage.Controls[0]).Controls.Add(_contextTitle);
        ((FlowLayoutPanel)contextPage.Controls[0]).Controls.Add(_contextButtons);
        _ribbon.TabPages.Add(contextPage);
    }

    private TabPage RibbonPage(string title, params Control[] groups)
    {
        var tab = new TabPage(title) { BackColor = Panel, ForeColor = TextMain, Padding = new Padding(4) };
        var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight, WrapContents = false, AutoScroll = true, BackColor = Panel };
        foreach (var group in groups) flow.Controls.Add(group);
        tab.Controls.Add(flow);
        return tab;
    }

    private Control Group(string title, params Control[] buttons)
    {
        var panel = new Panel { Width = Math.Max(152, buttons.Length * 91 + 12), Height = 88, BackColor = Panel, Margin = new Padding(2) };
        var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(4, 4, 4, 18), WrapContents = false, FlowDirection = FlowDirection.LeftToRight, BackColor = Panel };
        foreach (var button in buttons) flow.Controls.Add(button);
        panel.Controls.Add(flow);
        panel.Controls.Add(new Label { Dock = DockStyle.Bottom, Height = 17, Text = title, TextAlign = ContentAlignment.MiddleCenter, ForeColor = TextMuted, Font = new Font("Segoe UI", 8f) });
        return panel;
    }

    private Button RButton(string text, Action action, bool primary = false)
    {
        var button = new Button
        {
            Text = text,
            Width = 87,
            Height = 58,
            FlatStyle = FlatStyle.Flat,
            BackColor = primary ? Accent : Panel2,
            ForeColor = Color.White,
            Margin = new Padding(2),
            Cursor = Cursors.Hand,
            Font = new Font("Segoe UI", 8.4f)
        };
        button.FlatAppearance.BorderColor = primary ? Color.FromArgb(75, 177, 255) : Border;
        button.Click += (_, _) => action();
        return button;
    }

    private void AddWorkflowStep(string text, string key)
    {
        var button = new Button
        {
            Text = text,
            Width = 198,
            Height = 30,
            Tag = key,
            FlatStyle = FlatStyle.Flat,
            BackColor = Panel2,
            ForeColor = TextMain,
            Cursor = Cursors.Hand,
            Margin = new Padding(2, 0, 2, 0)
        };
        button.FlatAppearance.BorderColor = Border;
        button.Click += (_, _) => SelectNode(key);
        _workflow.Controls.Add(button);
    }

    private void AddWorkflowArrow() => _workflow.Controls.Add(new Label { Text = ">", Width = 24, Height = 30, TextAlign = ContentAlignment.MiddleCenter, ForeColor = TextMuted });

    private static Panel SectionHeader(string title)
    {
        var panel = new Panel { Dock = DockStyle.Top, Height = 29, BackColor = Color.FromArgb(31, 35, 41) };
        panel.Controls.Add(new Label { Dock = DockStyle.Fill, Text = "  " + title, TextAlign = ContentAlignment.MiddleLeft, ForeColor = TextMain, Font = new Font("Segoe UI Semibold", 9.5f) });
        return panel;
    }

    private static TabPage Tab(string title) => new(title) { BackColor = Field, ForeColor = TextMain, Padding = new Padding(2) };

    private static void ConfigureGrid(DataGridView grid, bool headers)
    {
        grid.Dock = DockStyle.Fill;
        grid.BackgroundColor = Field;
        grid.BorderStyle = BorderStyle.None;
        grid.AllowUserToAddRows = false;
        grid.AllowUserToDeleteRows = false;
        grid.RowHeadersVisible = false;
        grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill;
        grid.EnableHeadersVisualStyles = false;
        grid.ColumnHeadersVisible = headers;
        grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(50, 55, 64);
        grid.ColumnHeadersDefaultCellStyle.ForeColor = TextMain;
        grid.DefaultCellStyle.BackColor = Field;
        grid.DefaultCellStyle.ForeColor = TextMain;
        grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(58, 90, 130);
        grid.DefaultCellStyle.SelectionForeColor = Color.White;
        grid.GridColor = Border;
    }

    private static ToolStripMenuItem Menu(string text, params ToolStripItem[] items)
    {
        var menu = new ToolStripMenuItem(text);
        menu.DropDownItems.AddRange(items);
        return menu;
    }

    private static ToolStripMenuItem Item(string text, EventHandler click, Keys shortcut = Keys.None)
    {
        var item = new ToolStripMenuItem(text) { ShortcutKeys = shortcut };
        item.Click += click;
        return item;
    }

    private static ToolStripButton ToolButton(string text, EventHandler click)
    {
        var button = new ToolStripButton(text) { DisplayStyle = ToolStripItemDisplayStyle.Text };
        button.Click += click;
        return button;
    }

    private sealed class DarkRenderer : ToolStripProfessionalRenderer
    {
        public DarkRenderer() : base(new DarkColorTable()) { }
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = e.Item.Enabled ? TextMain : TextMuted;
            base.OnRenderItemText(e);
        }
    }

    private sealed class DarkColorTable : ProfessionalColorTable
    {
        public override Color MenuStripGradientBegin => Color.FromArgb(20, 22, 26);
        public override Color MenuStripGradientEnd => Color.FromArgb(20, 22, 26);
        public override Color ToolStripDropDownBackground => Panel2;
        public override Color ImageMarginGradientBegin => Panel2;
        public override Color ImageMarginGradientMiddle => Panel2;
        public override Color ImageMarginGradientEnd => Panel2;
        public override Color MenuItemSelected => Color.FromArgb(57, 91, 132);
        public override Color MenuItemBorder => Accent;
        public override Color MenuBorder => Border;
        public override Color ButtonSelectedHighlight => Color.FromArgb(57, 91, 132);
        public override Color ButtonSelectedBorder => Accent;
    }
}
