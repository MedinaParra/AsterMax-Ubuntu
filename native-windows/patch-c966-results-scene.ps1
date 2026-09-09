param([string]$Root)
$ErrorActionPreference = 'Stop'

$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$rwPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $uiPath)){ throw 'AsterMaxNativeUi.cs missing.' }
if(!(Test-Path $rwPath)){ throw 'C9.65 Results Workspace must be applied before C9.66.' }

$ui = Get-Content $uiPath -Raw
$ui = $ui.Replace('CommandTile("Load Results", "CODE_ASTER", () => OpenAsterMaxResultsBundle(), true)', 'CommandTile("Results Explorer", "CODE_ASTER", () => OpenAsterMaxResultsExplorer(), true)')
Set-Content $uiPath $ui -Encoding UTF8

$code = @'
using System;
using System.Globalization;
using System.Linq;
using System.Windows.Forms;

namespace PrePoMax
{
    internal sealed class AsterMaxResultsScene
    {
        public string Field { get; private set; }
        public double[] Scalars { get; private set; }
        public double[][] DeformedCoordinates { get; private set; }
        public double Minimum { get; private set; }
        public double Maximum { get; private set; }
        public int MinimumNodeIndex { get; private set; }
        public int MaximumNodeIndex { get; private set; }
        public double DeformationScale { get; private set; }
        public string Unit { get; private set; }
        public bool FeaValuesInvented { get { return false; } }

        public static AsterMaxResultsScene Build(AsterMaxResultsBundle bundle, string field, double deformationScale)
        {
            if (bundle == null) throw new ArgumentNullException("bundle");
            if (deformationScale < 0 || Double.IsNaN(deformationScale) || Double.IsInfinity(deformationScale))
                throw new ArgumentOutOfRangeException("deformationScale");
            var scalars = bundle.GetScalarField(field);
            int minIndex = 0, maxIndex = 0;
            for (int i = 1; i < scalars.Length; i++)
            {
                if (scalars[i] < scalars[minIndex]) minIndex = i;
                if (scalars[i] > scalars[maxIndex]) maxIndex = i;
            }
            return new AsterMaxResultsScene {
                Field = field,
                Scalars = scalars,
                DeformedCoordinates = bundle.GetDeformedCoordinates(deformationScale),
                Minimum = scalars[minIndex],
                Maximum = scalars[maxIndex],
                MinimumNodeIndex = minIndex,
                MaximumNodeIndex = maxIndex,
                DeformationScale = deformationScale,
                Unit = field == "Equivalent Stress" ? bundle.StressUnit : bundle.LengthUnit
            };
        }

        public static double RecommendDeformationScale(AsterMaxResultsBundle bundle, double targetFraction)
        {
            if (bundle == null) throw new ArgumentNullException("bundle");
            if (targetFraction <= 0 || targetFraction > 1) throw new ArgumentOutOfRangeException("targetFraction");
            double xmin=bundle.Coordinates.Min(p=>p[0]), xmax=bundle.Coordinates.Max(p=>p[0]);
            double ymin=bundle.Coordinates.Min(p=>p[1]), ymax=bundle.Coordinates.Max(p=>p[1]);
            double zmin=bundle.Coordinates.Min(p=>p[2]), zmax=bundle.Coordinates.Max(p=>p[2]);
            double diag=Math.Sqrt((xmax-xmin)*(xmax-xmin)+(ymax-ymin)*(ymax-ymin)+(zmax-zmin)*(zmax-zmin));
            double umax=bundle.TotalDeformation.Max();
            if (umax <= 0 || diag <= 0) return 1.0;
            double scale=targetFraction*diag/umax;
            return Math.Max(0.01, Math.Min(100000.0, scale));
        }

        public string Describe()
        {
            return String.Format(CultureInfo.InvariantCulture,
                "{0}: min {1:G7} {5} @ node {2}; max {3:G7} {5} @ node {4}; deformation x{6:G5}",
                Field, Minimum, MinimumNodeIndex + 1, Maximum, MaximumNodeIndex + 1, Unit, DeformationScale);
        }
    }

    internal sealed class AsterMaxResultsExplorerForm : Form
    {
        private readonly AsterMaxResultsBundle _bundle;
        private readonly ComboBox _field = new ComboBox();
        private readonly NumericUpDown _scale = new NumericUpDown();
        private readonly Label _summary = new Label();
        private readonly Label _probe = new Label();
        private readonly NumericUpDown _node = new NumericUpDown();

        public AsterMaxResultsExplorerForm(AsterMaxResultsBundle bundle)
        {
            _bundle = bundle;
            Text = "AsterMax Results Explorer — Code_Aster";
            Width = 620; Height = 330; StartPosition = FormStartPosition.CenterParent;
            FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false;
            var layout = new TableLayoutPanel { Dock=DockStyle.Fill, Padding=new Padding(16), ColumnCount=2, RowCount=6 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,150));
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            _field.DropDownStyle=ComboBoxStyle.DropDownList; _field.Items.AddRange(bundle.AvailableFields()); _field.SelectedIndex=0;
            _scale.DecimalPlaces=3; _scale.Minimum=0; _scale.Maximum=100000; _scale.Value=(decimal)Math.Min(100000,AsterMaxResultsScene.RecommendDeformationScale(bundle,0.10));
            _node.Minimum=1; _node.Maximum=bundle.NodeCount; _node.Value=bundle.NodeCount;
            _summary.AutoSize=true; _summary.MaximumSize=new System.Drawing.Size(410,0);
            _probe.AutoSize=true;
            layout.Controls.Add(new Label {Text="Result field",AutoSize=true},0,0); layout.Controls.Add(_field,1,0);
            layout.Controls.Add(new Label {Text="Deformation scale",AutoSize=true},0,1); layout.Controls.Add(_scale,1,1);
            layout.Controls.Add(new Label {Text="Scene extrema",AutoSize=true},0,2); layout.Controls.Add(_summary,1,2);
            layout.Controls.Add(new Label {Text="Probe node",AutoSize=true},0,3); layout.Controls.Add(_node,1,3);
            layout.Controls.Add(new Label {Text="Probe value",AutoSize=true},0,4); layout.Controls.Add(_probe,1,4);
            layout.Controls.Add(new Label {Text="Integrity",AutoSize=true},0,5); layout.Controls.Add(new Label {Text="Real solver bundle only • synthetic FEA values rejected",AutoSize=true},1,5);
            Controls.Add(layout);
            _field.SelectedIndexChanged += delegate { RefreshScene(); };
            _scale.ValueChanged += delegate { RefreshScene(); };
            _node.ValueChanged += delegate { RefreshScene(); };
            RefreshScene();
        }

        private void RefreshScene()
        {
            if (_field.SelectedItem == null) return;
            string f=(string)_field.SelectedItem;
            var scene=AsterMaxResultsScene.Build(_bundle,f,(double)_scale.Value);
            _summary.Text=scene.Describe();
            double v=_bundle.ProbeNode((int)_node.Value-1,f);
            _probe.Text=v.ToString("G9",CultureInfo.InvariantCulture)+" "+scene.Unit;
        }
    }

    public partial class FrmMain
    {
        private void OpenAsterMaxResultsExplorer()
        {
            try
            {
                using(var dlg=new OpenFileDialog())
                {
                    dlg.Title="Load real Code_Aster results bundle";
                    dlg.Filter="AsterMax Results Bundle (*.json)|*.json|All files (*.*)|*.*";
                    if(dlg.ShowDialog(this)!=DialogResult.OK) return;
                    _asterMaxLoadedResults=AsterMaxResultsBundle.Load(dlg.FileName);
                    using(var explorer=new AsterMaxResultsExplorerForm(_asterMaxLoadedResults)) explorer.ShowDialog(this);
                }
            }
            catch(Exception ex)
            {
                CaeGlobals.MessageBoxes.ShowError("AsterMax results bundle rejected: "+ex.Message);
            }
        }
    }
}
'@
$codePath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsScene.cs'
Set-Content $codePath $code -Encoding UTF8

$projPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$proj=Get-Content $projPath -Raw
if(-not $proj.Contains('Forms\AsterMaxResultsScene.cs')){
  $anchor='<Compile Include="Forms\AsterMaxResultsWorkspace.cs" />'
  if(-not $proj.Contains($anchor)){ throw 'C9.66 csproj anchor missing.' }
  $proj=$proj.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxResultsScene.cs" />')
  Set-Content $projPath $proj -Encoding UTF8
}
Write-Host 'C9.66 Results Scene + Explorer injected.' -ForegroundColor Green
