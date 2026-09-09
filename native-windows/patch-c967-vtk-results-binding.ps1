param([string]$Root)
$ErrorActionPreference = 'Stop'

$rwPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$scenePath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsScene.cs'
if(!(Test-Path $rwPath)){ throw 'C9.65 Results Workspace must be applied before C9.67.' }
if(!(Test-Path $scenePath)){ throw 'C9.66 Results Scene must be applied before C9.67.' }

# Extend the real-results bundle with the connectivity that C9.64 already stores.
$rw = Get-Content $rwPath -Raw
$rw = $rw.Replace('public double[][] Displacement { get; private set; }', 'public double[][] Displacement { get; private set; }'+[Environment]::NewLine+'        public int[][] Connectivity { get; private set; }')
$rw = $rw.Replace('b.Displacement = ReadJagged(root["arrays"]["displacement"], 3);', 'b.Displacement = ReadJagged(root["arrays"]["displacement"], 3);'+[Environment]::NewLine+'            b.Connectivity = ReadIntJagged(root["arrays"]["connectivity"], 8);')
$anchor = @'
        private static double[][] ReadJagged(JToken token, int width)
        {
            var rows = token.Select(row => row.Select(x => (double)x).ToArray()).ToArray();
            if (rows.Any(row => row.Length != width)) throw new InvalidDataException("Unexpected vector width.");
            return rows;
        }
'@
$insert = $anchor + @'

        private static int[][] ReadIntJagged(JToken token, int width)
        {
            var rows = token.Select(row => row.Select(x => (int)x).ToArray()).ToArray();
            if (rows.Any(row => row.Length != width)) throw new InvalidDataException("Unexpected connectivity width.");
            return rows;
        }
'@
if(-not $rw.Contains($anchor)){ throw 'C9.67 ReadJagged anchor missing.' }
$rw = $rw.Replace($anchor,$insert)
$oldValidate = 'if (Coordinates.Length != NodeCount || Displacement.Length != NodeCount ||'+[Environment]::NewLine+'                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount)'
$newValidate = 'if (Coordinates.Length != NodeCount || Displacement.Length != NodeCount ||'+[Environment]::NewLine+'                TotalDeformation.Length != NodeCount || EquivalentStress.Length != NodeCount || Connectivity.Length != ElementCount)'
if(-not $rw.Contains($oldValidate)){ throw 'C9.67 validation anchor missing.' }
$rw = $rw.Replace($oldValidate,$newValidate)
$finiteAnchor = 'throw new InvalidDataException("Non-finite FEA value detected.");'
$finiteInsert = $finiteAnchor + [Environment]::NewLine + '            if (Connectivity.Any(c => c.Length != 8 || c.Any(id => id < 1 || id > NodeCount)))'+[Environment]::NewLine+'                throw new InvalidDataException("Invalid HEXA8 connectivity detected.");'
$rw = $rw.Replace($finiteAnchor,$finiteInsert)
Set-Content $rwPath $rw -Encoding UTF8

$code = @'
using System;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using CaeGlobals;
using vtkControl;

namespace PrePoMax
{
    internal static class AsterMaxVtkResultsBinding
    {
        public const int VtkHexahedron = 12;

        public static vtkMaxActorData BuildActorData(AsterMaxResultsBundle bundle, AsterMaxResultsScene scene)
        {
            if (bundle == null) throw new ArgumentNullException("bundle");
            if (scene == null) throw new ArgumentNullException("scene");
            if (scene.FeaValuesInvented) throw new InvalidOperationException("Synthetic FEA scene rejected.");
            if (bundle.Connectivity == null || bundle.Connectivity.Length != bundle.ElementCount)
                throw new InvalidOperationException("Result mesh connectivity is unavailable.");
            if (scene.Scalars.Length != bundle.NodeCount || scene.DeformedCoordinates.Length != bundle.NodeCount)
                throw new InvalidOperationException("Scene array/node count mismatch.");

            var data = new vtkMaxActorData();
            data.Name = "AsterMax::" + scene.Field;
            data.Pickable = true;
            data.ColorContours = true;
            data.CanHaveElementEdges = true;
            data.ActorRepresentation = vtkMaxActorRepresentation.Solid;
            data.BackfaceCulling = false;
            data.Ambient = 0.25;
            data.Diffuse = 0.75;
            data.Color = Color.LightGray;

            data.Geometry.Nodes.Ids = Enumerable.Range(1, bundle.NodeCount).ToArray();
            data.Geometry.Nodes.Coor = scene.DeformedCoordinates.Select(p => new[] { p[0], p[1], p[2] }).ToArray();
            data.Geometry.Nodes.Values = scene.Scalars.Select(x => (float)x).ToArray();
            data.Geometry.Cells.Ids = Enumerable.Range(1, bundle.ElementCount).ToArray();
            // C9.64 connectivity is one-based Code_Aster/MED numbering. PartExchangeData expects
            // zero-based point indices when constructing VTK cells.
            data.Geometry.Cells.CellNodeIds = bundle.Connectivity.Select(c => c.Select(id => id - 1).ToArray()).ToArray();
            data.Geometry.Cells.Types = Enumerable.Repeat(VtkHexahedron, bundle.ElementCount).ToArray();
            data.Geometry.Cells.Values = null;
            return data;
        }

        public static vtkMaxActor BuildVtkActor(AsterMaxResultsBundle bundle, AsterMaxResultsScene scene)
        {
            return new vtkMaxActor(BuildActorData(bundle, scene));
        }
    }

    internal sealed class AsterMaxResultsViewportForm : Form
    {
        private readonly AsterMaxResultsBundle _bundle;
        private readonly vtkControl.vtkControl _view;
        private readonly ComboBox _field;
        private readonly NumericUpDown _scale;
        private readonly Label _status;

        public AsterMaxResultsViewportForm(AsterMaxResultsBundle bundle)
        {
            _bundle = bundle ?? throw new ArgumentNullException("bundle");
            Text = "AsterMax — Real FEA Results Viewport";
            Width = 1100; Height = 760; StartPosition = FormStartPosition.CenterParent;

            var top = new FlowLayoutPanel { Dock=DockStyle.Top, Height=42, Padding=new Padding(8), AutoSize=false };
            _field = new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=190 };
            _field.Items.AddRange(bundle.AvailableFields()); _field.SelectedIndex=1;
            _scale = new NumericUpDown { DecimalPlaces=3, Minimum=0, Maximum=100000, Width=110 };
            _scale.Value=(decimal)Math.Min(100000,AsterMaxResultsScene.RecommendDeformationScale(bundle,0.10));
            _status = new Label { AutoSize=true, Padding=new Padding(12,6,0,0) };
            var refresh = new Button { Text="Render real result", AutoSize=true };
            top.Controls.Add(new Label {Text="Field",AutoSize=true,Padding=new Padding(0,6,0,0)}); top.Controls.Add(_field);
            top.Controls.Add(new Label {Text="Deformation x",AutoSize=true,Padding=new Padding(10,6,0,0)}); top.Controls.Add(_scale);
            top.Controls.Add(refresh); top.Controls.Add(_status);

            _view = new vtkControl.vtkControl { Dock=DockStyle.Fill };
            Controls.Add(_view); Controls.Add(top);
            refresh.Click += delegate { RenderScene(); };
            Shown += delegate { RenderScene(); };
        }

        private void RenderScene()
        {
            string field=(string)_field.SelectedItem;
            var scene=AsterMaxResultsScene.Build(_bundle,field,(double)_scale.Value);
            var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,scene);
            // This is a real binding to PrePoMax's native vtkControl pipeline. AddCells constructs
            // a vtkMaxActor, mapper and VTK cells using the deformed coordinates and real scalars.
            _view.ClearAllActors();
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
            _view.Render();
            _status.Text=scene.Describe();
        }
    }

    public partial class FrmMain
    {
        private void OpenAsterMaxResultsViewport()
        {
            try
            {
                if (_asterMaxLoadedResults == null)
                {
                    using(var dlg=new OpenFileDialog())
                    {
                        dlg.Title="Load real Code_Aster results bundle";
                        dlg.Filter="AsterMax Results Bundle (*.json)|*.json|All files (*.*)|*.*";
                        if(dlg.ShowDialog(this)!=DialogResult.OK) return;
                        _asterMaxLoadedResults=AsterMaxResultsBundle.Load(dlg.FileName);
                    }
                }
                using(var viewport=new AsterMaxResultsViewportForm(_asterMaxLoadedResults)) viewport.ShowDialog(this);
            }
            catch(Exception ex)
            {
                CaeGlobals.MessageBoxes.ShowError("AsterMax VTK results binding rejected: "+ex.Message);
            }
        }
    }
}
'@
$codePath = Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
Set-Content $codePath $code -Encoding UTF8

# Add a dedicated results-viewport command beside Results Explorer.
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$ui = Get-Content $uiPath -Raw
$old='CommandTile("Results Explorer", "CODE_ASTER", () => OpenAsterMaxResultsExplorer(), true),'
$new=$old+[Environment]::NewLine+'                CommandTile("FEA Viewport", "VTK", () => OpenAsterMaxResultsViewport(), true),'
if(-not $ui.Contains($old)){ throw 'C9.67 Results Explorer UI anchor missing.' }
$ui=$ui.Replace($old,$new)
Set-Content $uiPath $ui -Encoding UTF8

$projPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$proj=Get-Content $projPath -Raw
if(-not $proj.Contains('Forms\AsterMaxVtkResultsBinding.cs')){
  $anchor='<Compile Include="Forms\AsterMaxResultsScene.cs" />'
  if(-not $proj.Contains($anchor)){ throw 'C9.67 csproj anchor missing.' }
  $proj=$proj.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxVtkResultsBinding.cs" />')
  Set-Content $projPath $proj -Encoding UTF8
}
Write-Host 'C9.67 native VTK results binding injected.' -ForegroundColor Green
