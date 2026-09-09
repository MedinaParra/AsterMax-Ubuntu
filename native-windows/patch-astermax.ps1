param([string]$Root)
$ErrorActionPreference = 'Stop'

function Replace-InFile([string]$Path,[string]$Old,[string]$New){
  $p = Join-Path $Root $Path
  $t = Get-Content $p -Raw
  if(-not $t.Contains($Old)){ throw "Anchor not found: $Path :: $Old" }
  $t = $t.Replace($Old,$New)
  Set-Content $p $t -Encoding UTF8
}

# Native product identity. Keep internal namespaces intact for compatibility.
Replace-InFile 'PrePoMax/Globals.cs' 'public static string ProgramName = "PrePoMax v1.4.0";' 'public static string ProgramName = "AsterMax Mechanical — Native PMV";'
Replace-InFile 'PrePoMax/PrePoMax.csproj' '<AssemblyName>PrePoMax</AssemblyName>' '<AssemblyName>AsterMax Mechanical</AssemblyName>'
Replace-InFile 'PrePoMax/Forms/FrmMain.cs' 'MessageBoxes.ShowError("PrePoMax has no write access for the folder: " + Application.StartupPath +' 'MessageBoxes.ShowError("AsterMax Mechanical has no write access for the folder: " + Application.StartupPath +'
Replace-InFile 'PrePoMax/Forms/FrmMain.cs' '"To run PrePoMax, move the base PrePoMax folder to another, non-protected folder.");' '"To run AsterMax Mechanical, move the application folder to another, non-protected folder.");'

# IMPORTANT: never mutate the native control tree while FrmMain_Load is still building Controller/VTK/forms.
# Register our Shown handler AFTER InitializeComponent's native FrmMain_Shown subscription. BeginInvoke guarantees
# that the original Shown handler has fully returned before the AsterMax presentation layer is applied.
$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$mainText = Get-Content $main -Raw
$ctorAnchor = '            _args = args;'
$shownHook = @'
            _args = args;
            this.Shown += (asterMaxSender, asterMaxArgs) =>
                BeginInvoke(new Action(ApplyAsterMaxNativeUi));
'@
if(-not $mainText.Contains('BeginInvoke(new Action(ApplyAsterMaxNativeUi))')){
  if(-not $mainText.Contains($ctorAnchor)){ throw 'FrmMain constructor args anchor not found' }
  $mainText = $mainText.Replace($ctorAnchor,$shownHook)
  Set-Content $main $mainText -Encoding UTF8
}

# Add partial FrmMain presentation layer. Existing Controller, ModelTree, VTK and command handlers remain source-of-truth.
$ui = @'
using System;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private static readonly Color AxWindow = Color.FromArgb(244, 246, 249);
        private static readonly Color AxSurface = Color.FromArgb(255, 255, 255);
        private static readonly Color AxRibbon = Color.FromArgb(247, 248, 250);
        private static readonly Color AxBorder = Color.FromArgb(211, 216, 223);
        private static readonly Color AxText = Color.FromArgb(34, 42, 53);
        private static readonly Color AxMuted = Color.FromArgb(100, 110, 124);
        private static readonly Color AxNavy = Color.FromArgb(30, 43, 59);
        private static readonly Color AxAccent = Color.FromArgb(39, 116, 174);
        private static readonly Color AxHover = Color.FromArgb(233, 242, 249);
        private static readonly Color AxViewportFrame = Color.FromArgb(225, 229, 234);
        private bool _asterMaxUiApplied;

        private void ApplyAsterMaxNativeUi()
        {
            if (_asterMaxUiApplied || IsDisposed || _controller == null || _modelTree == null || _vtk == null) return;
            _asterMaxUiApplied = true;

            SuspendLayout();
            try
            {
                Text = "AsterMax Mechanical";
                BackColor = AxWindow;
                Font = new Font("Segoe UI", 9.0f, FontStyle.Regular, GraphicsUnit.Point);
                MinimumSize = new Size(1040, 680);

                // The legacy toolbars remain alive because their real handlers are reused by AsterMax commands,
                // but they are no longer user-facing.
                menuStripMain.Visible = false;
                tsFile.Visible = false;
                tsViews.Visible = false;
                tsModel.Visible = false;
                tsDeformationFactor.Visible = false;
                tsResults.Visible = false;

                BuildAsterMaxTopChrome();
                PolishNativeWorkspace();
                ThemeRecursive(this);
                StartAsterMaxRuntimeSmoke();
            }
            finally
            {
                ResumeLayout(true);
                PerformLayout();
            }
        }

        private void BuildAsterMaxTopChrome()
        {
            var titleBar = new Panel
            {
                Name = "asterMaxTitleBar",
                Dock = DockStyle.Top,
                Height = 40,
                BackColor = AxNavy,
                Padding = new Padding(14, 0, 12, 0)
            };

            var brand = new Label
            {
                Text = "ASTERMAX  MECHANICAL",
                Dock = DockStyle.Left,
                Width = 245,
                ForeColor = Color.White,
                TextAlign = ContentAlignment.MiddleLeft,
                Font = new Font("Segoe UI Semibold", 10.5f, FontStyle.Bold)
            };

            var discipline = new Label
            {
                Text = "Mechanical Analysis",
                Dock = DockStyle.Left,
                Width = 165,
                ForeColor = Color.FromArgb(185, 198, 211),
                TextAlign = ContentAlignment.MiddleLeft,
                Font = new Font("Segoe UI", 9.0f)
            };

            var units = new Label
            {
                Text = "mm   |   N   |   MPa",
                Dock = DockStyle.Right,
                Width = 155,
                ForeColor = Color.FromArgb(208, 219, 230),
                TextAlign = ContentAlignment.MiddleRight,
                Font = new Font("Segoe UI Semibold", 8.5f)
            };

            var solver = new Label
            {
                Text = "Code_Aster ready path",
                Dock = DockStyle.Right,
                Width = 150,
                ForeColor = Color.FromArgb(158, 192, 218),
                TextAlign = ContentAlignment.MiddleRight,
                Font = new Font("Segoe UI", 8.5f)
            };

            titleBar.Controls.Add(discipline);
            titleBar.Controls.Add(brand);
            titleBar.Controls.Add(units);
            titleBar.Controls.Add(solver);

            var ribbon = new TabControl
            {
                Name = "asterMaxRibbon",
                Dock = DockStyle.Top,
                Height = 118,
                Font = new Font("Segoe UI Semibold", 9.0f),
                Padding = new Point(16, 5),
                Appearance = TabAppearance.Normal
            };

            ribbon.TabPages.Add(BuildRibbonPage("Home", new Control[] {
                CommandTile("New", "PROJECT", () => tsbNew.PerformClick()),
                CommandTile("Open", "PROJECT", () => tsbOpen.PerformClick()),
                CommandTile("Import Geometry", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Save", "PROJECT", () => tsbSave.PerformClick()),
                RibbonSeparator(),
                CommandTile("Fit", "VIEW", () => tsbZoomToFit.PerformClick()),
                CommandTile("Isometric", "VIEW", () => tsbIsometric.PerformClick())
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Geometry", new Control[] {
                CommandTile("Import STEP", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Analyze Geometry", "CHECK", () => tsmiGeometryAnalyze.PerformClick()),
                RibbonSeparator(),
                CommandTile("Fit", "VIEW", () => tsbZoomToFit.PerformClick()),
                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Model", new Control[] {
                CommandTile("Model Properties", "MODEL", () => tsmiEditModel.PerformClick()),
                CommandTile("Materials", "MODEL", () => tsmiCreateMaterial_Click(null, EventArgs.Empty)),
                CommandTile("Solid Section", "MODEL", () => tsmiCreateSection_Click(null, EventArgs.Empty)),
                CommandTile("Analysis Step", "MODEL", () => tsmiCreateStep_Click(null, EventArgs.Empty)),
                InfoCard("Coordinate systems and named selections live in Outline")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] {
                InfoCard("Connections and constraints are scoped from the real model tree"),
                StateCard("Scope", "Geometry / Named Selection")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Mesh", new Control[] {
                CommandTile("Mesh Controls", "MESH", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Generate Mesh", "MESH", () => tsmiCreateMesh.PerformClick(), true),
                InfoCard("TET4 baseline • TET10 next gate")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Environment", new Control[] {
                CommandTile("Supports", "MODEL", () => tsmiCreateBC_Click(null, EventArgs.Empty)),
                CommandTile("Loads", "MODEL", () => tsmiCreateLoad_Click(null, EventArgs.Empty)),
                StateCard("Analysis", "Static Structural")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] {
                StateCard("Solver", "Code_Aster integration path"),
                InfoCard("Solution requests stay in the analysis tree; no synthetic results")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Results", new Control[] {
                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick(), true),
                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),
                InfoCard("Deformation • Equivalent Stress • Reactions")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("View", new Control[] {
                CommandTile("Fit", "CAMERA", () => tsbZoomToFit.PerformClick()),
                CommandTile("Front", "CAMERA", () => tsbFrontView.PerformClick()),
                CommandTile("Top", "CAMERA", () => tsbTopView.PerformClick()),
                CommandTile("Right", "CAMERA", () => tsbRightView.PerformClick()),
                CommandTile("Isometric", "CAMERA", () => tsbIsometric.PerformClick()),
                RibbonSeparator(),
                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())
            }));

            Controls.Add(ribbon);
            Controls.Add(titleBar);
            ribbon.BringToFront();
            titleBar.BringToFront();
        }

        private void PolishNativeWorkspace()
        {
            splitContainer1.BackColor = AxBorder;
            splitContainer1.SplitterWidth = 1;
            splitContainer1.Panel1.BackColor = AxSurface;
            splitContainer1.Panel2.BackColor = AxWindow;

            // Give the native ModelTree an ANSYS-like Outline identity without replacing its data model.
            splitContainer1.Panel1.Padding = new Padding(0, 30, 0, 0);
            var outlineHeader = new Panel
            {
                Name = "asterMaxOutlineHeader",
                Dock = DockStyle.Top,
                Height = 30,
                BackColor = Color.FromArgb(238, 241, 245),
                Padding = new Padding(10, 0, 8, 0)
            };
            var outlineText = new Label
            {
                Text = "Outline",
                Dock = DockStyle.Left,
                Width = 100,
                ForeColor = AxText,
                TextAlign = ContentAlignment.MiddleLeft,
                Font = new Font("Segoe UI Semibold", 9.0f)
            };
            var stateText = new Label
            {
                Text = "Model",
                Dock = DockStyle.Right,
                Width = 70,
                ForeColor = AxMuted,
                TextAlign = ContentAlignment.MiddleRight,
                Font = new Font("Segoe UI", 8.0f)
            };
            outlineHeader.Controls.Add(stateText);
            outlineHeader.Controls.Add(outlineText);
            splitContainer1.Panel1.Controls.Add(outlineHeader);
            outlineHeader.BringToFront();

            // Make the native VTK workspace read as a dedicated Graphics area.
            var graphicsBadge = new Label
            {
                Name = "asterMaxGraphicsBadge",
                Text = "  Graphics  ",
                AutoSize = true,
                BackColor = Color.FromArgb(238, 241, 245),
                ForeColor = AxMuted,
                Font = new Font("Segoe UI Semibold", 8.0f),
                Padding = new Padding(3, 3, 3, 3),
                Location = new Point(8, 8)
            };
            splitContainer1.Panel2.Controls.Add(graphicsBadge);
            graphicsBadge.BringToFront();

            if (_vtk != null)
            {
                _vtk.BackColor = Color.FromArgb(250, 250, 250);
            }
        }

        private TabPage BuildRibbonPage(string name, Control[] controls)
        {
            var page = new TabPage(name)
            {
                BackColor = AxRibbon,
                Padding = new Padding(9, 8, 9, 7),
                ForeColor = AxText
            };
            var flow = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.LeftToRight,
                WrapContents = false,
                BackColor = AxRibbon,
                Margin = new Padding(0),
                Padding = new Padding(0)
            };
            flow.Controls.AddRange(controls);
            page.Controls.Add(flow);
            return page;
        }

        private Button CommandTile(string text, string group, Action action, bool primary = false)
        {
            var b = new Button
            {
                Text = group + Environment.NewLine + text,
                Width = text.Length > 14 ? 132 : 112,
                Height = 62,
                Margin = new Padding(3, 1, 3, 1),
                Padding = new Padding(4),
                FlatStyle = FlatStyle.Flat,
                BackColor = primary ? Color.FromArgb(238, 246, 252) : AxSurface,
                ForeColor = AxText,
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Segoe UI", 8.5f)
            };
            b.FlatAppearance.BorderColor = primary ? Color.FromArgb(136, 180, 214) : AxBorder;
            b.FlatAppearance.BorderSize = 1;
            b.FlatAppearance.MouseOverBackColor = AxHover;
            b.FlatAppearance.MouseDownBackColor = Color.FromArgb(219, 235, 247);
            b.Click += (s, e) => action();
            return b;
        }

        private Label InfoCard(string text)
        {
            return new Label
            {
                Text = text,
                AutoSize = false,
                Width = 285,
                Height = 62,
                Margin = new Padding(3, 1, 3, 1),
                Padding = new Padding(9, 5, 9, 5),
                BackColor = AxSurface,
                ForeColor = AxMuted,
                TextAlign = ContentAlignment.MiddleLeft,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 8.5f)
            };
        }

        private Label StateCard(string caption, string value)
        {
            return new Label
            {
                Text = caption.ToUpperInvariant() + Environment.NewLine + value,
                AutoSize = false,
                Width = 190,
                Height = 62,
                Margin = new Padding(3, 1, 3, 1),
                Padding = new Padding(9, 5, 9, 5),
                BackColor = Color.FromArgb(240, 246, 250),
                ForeColor = AxText,
                TextAlign = ContentAlignment.MiddleLeft,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 8.5f)
            };
        }

        private Control RibbonSeparator()
        {
            return new Panel
            {
                Width = 1,
                Height = 54,
                BackColor = AxBorder,
                Margin = new Padding(8, 5, 8, 3)
            };
        }

        private void ThemeRecursive(Control root)
        {
            foreach (Control c in root.Controls)
            {
                if (c.Name != null && c.Name.StartsWith("asterMax", StringComparison.OrdinalIgnoreCase))
                {
                    ThemeRecursive(c);
                    continue;
                }

                if (c is TreeView)
                {
                    c.BackColor = AxSurface;
                    c.ForeColor = AxText;
                    c.Font = new Font("Segoe UI", 9.0f);
                }
                else if (c is PropertyGrid)
                {
                    c.BackColor = AxSurface;
                    c.ForeColor = AxText;
                    c.Font = new Font("Segoe UI", 8.5f);
                }
                else if (c is SplitContainer)
                {
                    c.BackColor = AxBorder;
                }
                else if (c is StatusStrip)
                {
                    c.BackColor = Color.FromArgb(237, 240, 244);
                    c.ForeColor = AxMuted;
                }
                else if (c is TextBox)
                {
                    c.Font = new Font("Consolas", 8.5f);
                }

                ThemeRecursive(c);
            }
        }
    }
}
'@
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
Set-Content $uiPath $ui -Encoding UTF8

# Register new source file in project.
$proj = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$projText = Get-Content $proj -Raw
if(-not $projText.Contains('Forms\AsterMaxNativeUi.cs')){
  $marker = '<Compile Include="Forms\FrmMain.cs">'
  if(-not $projText.Contains($marker)){ throw 'PrePoMax.csproj FrmMain compile anchor not found' }
  $projText = $projText.Replace($marker, '<Compile Include="Forms\AsterMaxNativeUi.cs" />' + [Environment]::NewLine + '    ' + $marker)
  Set-Content $proj $projText -Encoding UTF8
}


# Keep designer node identifiers stable: ModelTree locates them with Nodes.Find(name)[0].
# Captions are presentation only and must never replace these lookup keys.
Write-Host 'AsterMax native UI applied; ModelTree lookup keys preserved.' -ForegroundColor Green
