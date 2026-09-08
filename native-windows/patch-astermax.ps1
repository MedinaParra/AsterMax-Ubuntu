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

# Apply the visual layer after the real ModelTree and VTK controls are created.
$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$mainText = Get-Content $main -Raw
$anchor = '_modelTree.Dock = DockStyle.Fill;'
$inject = @'
_modelTree.Dock = DockStyle.Fill;
                ApplyAsterMaxNativeUi();
'@
if(-not $mainText.Contains('ApplyAsterMaxNativeUi();')){
  if(-not $mainText.Contains($anchor)){ throw 'FrmMain ModelTree anchor not found' }
  $mainText = $mainText.Replace($anchor,$inject)
  Set-Content $main $mainText -Encoding UTF8
}

# Add partial FrmMain visual/interaction layer. Existing handlers remain the source of truth.
$ui = @'
using System;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private static readonly Color AxBackground = Color.FromArgb(245,247,250);
        private static readonly Color AxPanel = Color.FromArgb(255,255,255);
        private static readonly Color AxRibbon = Color.FromArgb(241,244,248);
        private static readonly Color AxBorder = Color.FromArgb(207,214,223);
        private static readonly Color AxText = Color.FromArgb(32,42,55);
        private static readonly Color AxAccent = Color.FromArgb(0,102,204);

        private void ApplyAsterMaxNativeUi()
        {
            Text = "AsterMax Mechanical";
            BackColor = AxBackground;
            Font = new Font("Segoe UI", 9.0f, FontStyle.Regular, GraphicsUnit.Point);

            // Reuse the real PrePoMax command handlers; only reorganize their presentation.
            menuStripMain.Visible = false;
            tsFile.Visible = false;
            tsViews.Visible = false;
            tsModel.Visible = false;
            tsDeformationFactor.Visible = false;
            tsResults.Visible = false;

            splitContainer1.BackColor = AxBorder;
            splitContainer1.Panel1.BackColor = AxPanel;
            splitContainer1.Panel2.BackColor = AxBackground;

            var header = new Panel { Dock = DockStyle.Top, Height = 34, BackColor = Color.FromArgb(27,38,52), Padding = new Padding(12,0,12,0) };
            var brand = new Label { Text = "ASTERMAX  MECHANICAL", Dock = DockStyle.Left, Width = 255, ForeColor = Color.White, TextAlign = ContentAlignment.MiddleLeft, Font = new Font("Segoe UI Semibold", 10.5f) };
            var units = new Label { Text = "mm · N · MPa", Dock = DockStyle.Right, Width = 130, ForeColor = Color.FromArgb(203,214,226), TextAlign = ContentAlignment.MiddleRight };
            header.Controls.Add(units); header.Controls.Add(brand);

            var ribbon = new TabControl { Dock = DockStyle.Top, Height = 108, Font = new Font("Segoe UI Semibold", 9.0f), Padding = new Point(14,4) };
            ribbon.TabPages.Add(BuildRibbonPage("Home", new [] {
                CommandButton("New", () => tsbNew.PerformClick()),
                CommandButton("Open", () => tsbOpen.PerformClick()),
                CommandButton("Import Geometry", () => tsbImport.PerformClick()),
                CommandButton("Save", () => tsbSave.PerformClick()),
                CommandButton("Fit", () => tsbZoomToFit.PerformClick()),
                CommandButton("Isometric", () => tsbIsometric.PerformClick())
            }));
            ribbon.TabPages.Add(BuildRibbonPage("Geometry", new [] {
                CommandButton("Import STEP", () => tsbImport.PerformClick()),
                CommandButton("Analyze", () => tsmiGeometryAnalyze.PerformClick()),
                CommandButton("Fit", () => tsbZoomToFit.PerformClick())
            }));
            ribbon.TabPages.Add(BuildRibbonPage("Model", new [] {
                CommandButton("Materials", () => tsmiModel.PerformClick()),
                CommandButton("Model", () => tsmiEditModel.PerformClick())
            }));
            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] { InfoChip("Connections / constraints are managed from Outline") }));
            ribbon.TabPages.Add(BuildRibbonPage("Mesh", new [] {
                CommandButton("Mesh Parameters", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandButton("Generate Mesh", () => tsmiCreateMesh.PerformClick())
            }));
            ribbon.TabPages.Add(BuildRibbonPage("Environment", new Control[] { InfoChip("Supports and loads are scoped from the model tree") }));
            ribbon.TabPages.Add(BuildRibbonPage("Solution", new Control[] { InfoChip("Code_Aster adapter: next integration gate") }));
            ribbon.TabPages.Add(BuildRibbonPage("Results", new [] {
                CommandButton("Contours", () => tsbResultsColorContours.PerformClick()),
                CommandButton("Deformed", () => tsbResultsDeformed.PerformClick())
            }));
            ribbon.TabPages.Add(BuildRibbonPage("View", new [] {
                CommandButton("Fit", () => tsbZoomToFit.PerformClick()),
                CommandButton("Front", () => tsbFrontView.PerformClick()),
                CommandButton("Top", () => tsbTopView.PerformClick()),
                CommandButton("Right", () => tsbRightView.PerformClick()),
                CommandButton("Isometric", () => tsbIsometric.PerformClick()),
                CommandButton("Edges", () => tsbShowModelEdges.PerformClick())
            }));

            Controls.Add(ribbon);
            Controls.Add(header);
            ribbon.BringToFront();
            header.BringToFront();

            ThemeRecursive(this);
            header.BackColor = Color.FromArgb(27,38,52);
            brand.ForeColor = Color.White;
            units.ForeColor = Color.FromArgb(203,214,226);
        }

        private TabPage BuildRibbonPage(string name, Control[] controls)
        {
            var page = new TabPage(name) { BackColor = AxRibbon, Padding = new Padding(10,8,10,8) };
            var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight, WrapContents = false, BackColor = AxRibbon };
            flow.Controls.AddRange(controls); page.Controls.Add(flow); return page;
        }

        private Button CommandButton(string text, Action action)
        {
            var b = new Button { Text = text, Width = 116, Height = 54, Margin = new Padding(3), FlatStyle = FlatStyle.Flat, BackColor = Color.White, ForeColor = AxText };
            b.FlatAppearance.BorderColor = AxBorder;
            b.FlatAppearance.MouseOverBackColor = Color.FromArgb(230,240,252);
            b.Click += (s,e) => action(); return b;
        }

        private Label InfoChip(string text)
        {
            return new Label { Text = text, AutoSize = false, Width = 310, Height = 54, Margin = new Padding(3), BackColor = Color.White, ForeColor = Color.FromArgb(85,96,110), TextAlign = ContentAlignment.MiddleCenter, BorderStyle = BorderStyle.FixedSingle };
        }

        private void ThemeRecursive(Control root)
        {
            foreach(Control c in root.Controls)
            {
                if(c is TreeView) { c.BackColor = Color.White; c.ForeColor = AxText; c.Font = new Font("Segoe UI",9.0f); }
                else if(c is PropertyGrid) { c.BackColor = Color.White; c.ForeColor = AxText; }
                else if(c is SplitContainer) { c.BackColor = AxBorder; }
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

# Mechanical-style terminology without changing model semantics.
$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
$mt = Get-Content $modelTree -Raw
$mt = $mt.Replace('private string _geomPartsName = "Parts";','private string _geomPartsName = "Geometry";')
$mt = $mt.Replace('private string _boundaryConditionsName = "BCs";','private string _boundaryConditionsName = "Supports / BCs";')
$mt = $mt.Replace('private string _analysesName = "Analyses";','private string _analysesName = "Solution";')
Set-Content $modelTree $mt -Encoding UTF8

Write-Host 'AsterMax native fork patches applied.' -ForegroundColor Green
