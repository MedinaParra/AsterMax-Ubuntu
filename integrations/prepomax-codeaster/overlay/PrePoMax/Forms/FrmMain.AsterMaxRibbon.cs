using System;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private Panel _asterMaxRibbonHost;
        private TabControl _asterMaxRibbonTabs;
        private bool _asterMaxRibbonEnabled = true;
        private bool _asterMaxShowClassicToolbars = false;

        private void InitializeAsterMaxRibbon()
        {
            _asterMaxRibbonHost = new Panel();
            _asterMaxRibbonHost.Name = "asterMaxRibbonHost";
            _asterMaxRibbonHost.Dock = DockStyle.Top;
            _asterMaxRibbonHost.Height = 126;
            _asterMaxRibbonHost.BackColor = Color.FromArgb(245, 247, 250);
            _asterMaxRibbonHost.Padding = new Padding(0, 1, 0, 1);

            _asterMaxRibbonTabs = new TabControl();
            _asterMaxRibbonTabs.Name = "asterMaxRibbonTabs";
            _asterMaxRibbonTabs.Dock = DockStyle.Fill;
            _asterMaxRibbonTabs.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            _asterMaxRibbonTabs.Padding = new Point(16, 5);
            _asterMaxRibbonTabs.SizeMode = TabSizeMode.Normal;

            BuildHomeRibbonTab();
            BuildGeometryRibbonTab();
            BuildMeshRibbonTab();
            BuildModelRibbonTab();
            BuildAnalysisRibbonTab();
            BuildResultsRibbonTab();
            BuildAsterMaxRibbonTab();

            _asterMaxRibbonHost.Controls.Add(_asterMaxRibbonTabs);
            Controls.Add(_asterMaxRibbonHost);
            _asterMaxRibbonHost.BringToFront();
            if (menuStripMain != null) menuStripMain.BringToFront();

            ApplyAsterMaxRibbonVisibility();
        }

        private TabPage CreateRibbonTab(string title)
        {
            TabPage page = new TabPage(title);
            page.BackColor = Color.FromArgb(248, 249, 251);
            page.Padding = new Padding(6, 4, 6, 3);
            page.UseVisualStyleBackColor = false;
            return page;
        }

        private FlowLayoutPanel CreateRibbonRow(TabPage page)
        {
            FlowLayoutPanel row = new FlowLayoutPanel();
            row.Dock = DockStyle.Fill;
            row.FlowDirection = FlowDirection.LeftToRight;
            row.WrapContents = false;
            row.AutoScroll = true;
            row.Padding = new Padding(2, 2, 2, 0);
            row.BackColor = page.BackColor;
            page.Controls.Add(row);
            return row;
        }

        private Panel CreateRibbonGroup(string title, params Control[] controls)
        {
            int width = Math.Max(110, controls.Length * 82 + 12);
            Panel group = new Panel();
            group.Width = width;
            group.Height = 83;
            group.Margin = new Padding(2, 0, 5, 0);
            group.BackColor = Color.White;
            group.BorderStyle = BorderStyle.FixedSingle;

            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.Dock = DockStyle.Fill;
            buttons.FlowDirection = FlowDirection.LeftToRight;
            buttons.WrapContents = false;
            buttons.Padding = new Padding(4, 3, 4, 17);
            buttons.BackColor = Color.White;
            foreach (Control control in controls) buttons.Controls.Add(control);

            Label label = new Label();
            label.Text = title;
            label.Dock = DockStyle.Bottom;
            label.Height = 16;
            label.TextAlign = ContentAlignment.MiddleCenter;
            label.Font = new Font("Segoe UI", 7.5F, FontStyle.Regular);
            label.ForeColor = Color.FromArgb(90, 96, 105);
            label.BackColor = Color.FromArgb(243, 245, 248);

            group.Controls.Add(buttons);
            group.Controls.Add(label);
            return group;
        }

        private Button RibbonCommand(string text, ToolStripItem command)
        {
            Button button = new Button();
            button.Text = text;
            button.Width = 76;
            button.Height = 57;
            button.Margin = new Padding(2, 1, 2, 1);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = Color.White;
            button.ForeColor = Color.FromArgb(32, 38, 46);
            button.Font = new Font("Segoe UI", 8.25F, FontStyle.Regular);
            button.TextImageRelation = TextImageRelation.ImageAboveText;
            button.ImageAlign = ContentAlignment.MiddleCenter;
            button.TextAlign = ContentAlignment.BottomCenter;
            button.Image = command == null ? null : command.Image;
            button.Enabled = command == null || command.Enabled;
            if (command != null)
            {
                button.Click += delegate { command.PerformClick(); };
                command.EnabledChanged += delegate { button.Enabled = command.Enabled; };
            }
            button.MouseEnter += delegate { button.BackColor = Color.FromArgb(232, 240, 250); };
            button.MouseLeave += delegate { button.BackColor = Color.White; };
            return button;
        }

        private Button RibbonAction(string text, EventHandler click)
        {
            Button button = new Button();
            button.Text = text;
            button.Width = 88;
            button.Height = 57;
            button.Margin = new Padding(2, 1, 2, 1);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = Color.White;
            button.ForeColor = Color.FromArgb(32, 38, 46);
            button.Font = new Font("Segoe UI", 8.25F, FontStyle.Regular);
            button.Click += click;
            button.MouseEnter += delegate { button.BackColor = Color.FromArgb(232, 240, 250); };
            button.MouseLeave += delegate { button.BackColor = Color.White; };
            return button;
        }

        private void AddGroup(FlowLayoutPanel row, string title, params Control[] controls)
        {
            row.Controls.Add(CreateRibbonGroup(title, controls));
        }

        private void BuildHomeRibbonTab()
        {
            TabPage page = CreateRibbonTab("Home");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Project",
                RibbonCommand("New", tsmiNew), RibbonCommand("Open", tsmiOpen),
                RibbonCommand("Import", tsmiImportFile), RibbonCommand("Save", tsmiSave));
            AddGroup(row, "History", RibbonCommand("Undo", tsmiUndo), RibbonCommand("Redo", tsmiRedo));
            AddGroup(row, "View", RibbonCommand("Zoom Fit", tsmiZoomToFit), RibbonCommand("Isometric", tsmiIsometricView));
            AddGroup(row, "Interface",
                RibbonAction("Classic Toolbars", delegate
                {
                    _asterMaxShowClassicToolbars = !_asterMaxShowClassicToolbars;
                    ApplyAsterMaxRibbonVisibility();
                }));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildGeometryRibbonTab()
        {
            TabPage page = CreateRibbonTab("Geometry");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Import", RibbonCommand("Import CAD", tsmiImportFile));
            AddGroup(row, "Prepare",
                RibbonCommand("Analyze", tsmiGeometryAnalyze),
                RibbonCommand("Compound", tsmiCreateAndImportCompoundPart));
            AddGroup(row, "View",
                RibbonCommand("Section", tsmiSectionView),
                RibbonCommand("Exploded", tsmiExplodedView));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildMeshRibbonTab()
        {
            TabPage page = CreateRibbonTab("Mesh");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Controls",
                RibbonCommand("Parameters", tsmiCreateMeshingParameters),
                RibbonCommand("Refinement", tsmiCreateMeshRefinement));
            AddGroup(row, "Generate",
                RibbonCommand("Preview Edge", tsmiPreviewEdgeMesh),
                RibbonCommand("Create Mesh", tsmiCreateMesh));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildModelRibbonTab()
        {
            TabPage page = CreateRibbonTab("Model");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Materials",
                RibbonCommand("Library", tsmiMaterialLibrary),
                RibbonCommand("Material", tsmiCreateMaterial));
            AddGroup(row, "Definition",
                RibbonCommand("Section", tsmiCreateSection),
                RibbonCommand("Surface", tsmiCreateSurface));
            AddGroup(row, "Sets",
                RibbonCommand("Node Set", tsmiCreateNodeSet),
                RibbonCommand("Element Set", tsmiCreateElementSet));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildAnalysisRibbonTab()
        {
            TabPage page = CreateRibbonTab("Analysis");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Setup", RibbonCommand("Step", tsmiCreateStep));
            AddGroup(row, "Loads & BC",
                RibbonCommand("Boundary", tsmiCreateBC),
                RibbonCommand("Load", tsmiCreateLoad));
            AddGroup(row, "Job",
                RibbonCommand("Analysis", tsmiCreateAnalysis),
                RibbonCommand("Check", tsmiCheckModel),
                RibbonCommand("Run", tsmiRunAnalysis));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildResultsRibbonTab()
        {
            TabPage page = CreateRibbonTab("Results");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Display",
                RibbonCommand("Undeformed", tsmiResultsUndeformed),
                RibbonCommand("Deformed", tsmiResultsDeformed),
                RibbonCommand("Contours", tsmiResultsColorContours));
            AddGroup(row, "View",
                RibbonCommand("Section", tsmiSectionView),
                RibbonCommand("Exploded", tsmiExplodedView));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildAsterMaxRibbonTab()
        {
            TabPage page = CreateRibbonTab("AsterMax");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddGroup(row, "Solver",
                RibbonCommand("Settings", tsmiSettings),
                RibbonCommand("Check Model", tsmiCheckModel),
                RibbonCommand("Run Solver", tsmiRunAnalysis));
            AddGroup(row, "Workspace",
                RibbonCommand("Material Library", tsmiMaterialLibrary),
                RibbonCommand("Query", tsmiQuery));
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void ApplyAsterMaxRibbonVisibility()
        {
            if (!_asterMaxRibbonEnabled) return;
            bool showClassic = _asterMaxShowClassicToolbars;
            if (tsFile != null) tsFile.Visible = showClassic;
            if (tsViews != null) tsViews.Visible = showClassic;
            if (tsModel != null) tsModel.Visible = showClassic;
            if (tsDeformationFactor != null) tsDeformationFactor.Visible = showClassic;
            if (tsResults != null) tsResults.Visible = showClassic;
            if (_asterMaxRibbonHost != null) _asterMaxRibbonHost.Visible = true;
        }
    }
}
