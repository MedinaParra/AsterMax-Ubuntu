param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $p)){throw 'C9.68 Results HUD must be applied before C9.69.'}
$s=Get-Content $p -Raw

$nsAnchor='namespace PrePoMax'+[Environment]::NewLine+'{'
if(-not $s.Contains($nsAnchor)){throw 'C9.69 namespace anchor missing.'}
$contract=@'
namespace PrePoMax
{
    internal sealed class AsterMaxResultsColorContract
    {
        public string Field { get; private set; }
        public string Unit { get; private set; }
        public double Minimum { get; private set; }
        public double Maximum { get; private set; }
        public double SpectrumMinimum { get; private set; }
        public double SpectrumMaximum { get; private set; }
        public bool FeaValuesInvented { get; private set; }

        private AsterMaxResultsColorContract() { }

        public static AsterMaxResultsColorContract FromScene(AsterMaxResultsScene scene)
        {
            if (scene == null) throw new ArgumentNullException("scene");
            if (scene.FeaValuesInvented) throw new InvalidOperationException("Synthetic FEA scene rejected by renderer contract.");
            if (Double.IsNaN(scene.Minimum) || Double.IsInfinity(scene.Minimum) ||
                Double.IsNaN(scene.Maximum) || Double.IsInfinity(scene.Maximum))
                throw new InvalidOperationException("Non-finite result range rejected.");
            double lo=scene.Minimum, hi=scene.Maximum;
            if (hi < lo) throw new InvalidOperationException("Invalid result range.");
            double span=Math.Abs(hi-lo);
            double eps=Math.Max(1e-12,Math.Max(Math.Abs(lo),Math.Abs(hi))*1e-12);
            double slo=lo, shi=hi;
            if (span <= eps) { slo=lo-eps; shi=hi+eps; }
            return new AsterMaxResultsColorContract {
                Field=scene.Field, Unit=scene.Unit, Minimum=lo, Maximum=hi,
                SpectrumMinimum=slo, SpectrumMaximum=shi, FeaValuesInvented=false
            };
        }

        public vtkControl.vtkMaxColorSpectrum CreateVtkSpectrum()
        {
            var spectrum=new vtkControl.vtkMaxColorSpectrum();
            spectrum.Type=vtkControl.vtkColorSpectrumType.Rainbow;
            spectrum.MinMaxType=vtkControl.vtkColorSpectrumMinMaxType.Manual;
            spectrum.NumberOfColors=12;
            // vtkMaxColorSpectrum setters enforce min<max. Sequence is selected so arbitrary
            // positive, negative and mixed result ranges remain valid.
            if (SpectrumMaximum <= 0)
            {
                spectrum.MinUserValue=SpectrumMinimum;
                spectrum.MaxUserValue=SpectrumMaximum;
            }
            else
            {
                spectrum.MaxUserValue=SpectrumMaximum;
                spectrum.MinUserValue=SpectrumMinimum;
            }
            return spectrum;
        }

        public string Describe()
        {
            return String.Format(System.Globalization.CultureInfo.InvariantCulture,
                "{0}|{1}|min={2:R}|max={3:R}|vtkMin={4:R}|vtkMax={5:R}|invented=false",
                Field,Unit,Minimum,Maximum,SpectrumMinimum,SpectrumMaximum);
        }
    }
'@
$s=$s.Replace($nsAnchor,$contract)

$old='            _legend.SetRange(_scene.Minimum,_scene.Maximum,_scene.Unit,_scene.Field);'
$new='            _legend.SetContract(AsterMaxResultsColorContract.FromScene(_scene));'
if(-not $s.Contains($old)){throw 'C9.69 legend range anchor missing.'}
$s=$s.Replace($old,$new)

$oldRender=@'
            _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
            _host.Controls.Add(_view);
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
'@
$newRender=@'
            _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
            _host.Controls.Add(_view);
            // One contract is the source of truth for the VTK mapper/scalar bar and the HUD.
            // Configure vtkControl before AddCells so actor lookup-table construction sees the
            // exact manual range derived from the real results scene.
            var colorContract=AsterMaxResultsColorContract.FromScene(_scene);
            _view.SetScalarBarColorSpectrum(colorContract.CreateVtkSpectrum());
            _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
'@
if(-not $s.Contains($oldRender)){throw 'C9.69 RenderScene anchor missing.'}
$s=$s.Replace($oldRender,$newRender)

$oldLegend=@'
            private double _min,_max; private string _unit="",_field="";
            public AsterMaxLegendPanel(){DoubleBuffered=true;BackColor=Color.White;}
            public void SetRange(double min,double max,string unit,string field){_min=min;_max=max;_unit=unit??"";_field=field??"";Invalidate();}
'@
$newLegend=@'
            private double _min,_max; private string _unit="",_field="";
            public AsterMaxLegendPanel(){DoubleBuffered=true;BackColor=Color.White;}
            public void SetContract(AsterMaxResultsColorContract c)
            {
                if(c==null || c.FeaValuesInvented) throw new InvalidOperationException("Invalid renderer color contract.");
                _min=c.Minimum; _max=c.Maximum; _unit=c.Unit??""; _field=c.Field??""; Invalidate();
            }
'@
if(-not $s.Contains($oldLegend)){throw 'C9.69 legend contract anchor missing.'}
$s=$s.Replace($oldLegend,$newLegend)

# Remove the independent pseudo-color gradient from the side rail. The authoritative color map
# is now vtkControl's native scalar bar; the HUD retains numeric tick/range traceability only.
$oldPaint='                Color[] c={Color.FromArgb(170,0,0),Color.Orange,Color.Yellow,Color.LimeGreen,Color.Cyan,Color.RoyalBlue};'+[Environment]::NewLine+'                for(int i=0;i<h;i++){double t=(double)i/Math.Max(1,h-1);int seg=Math.Min(c.Length-2,(int)(t*(c.Length-1)));double u=t*(c.Length-1)-seg;Color a=c[seg],b=c[seg+1];Color q=Color.FromArgb((int)(a.R+(b.R-a.R)*u),(int)(a.G+(b.G-a.G)*u),(int)(a.B+(b.B-a.B)*u));using(var pen=new Pen(q))g.DrawLine(pen,x,y+i,x+w,y+i);}'
$newPaint='                using(var fill=new SolidBrush(Color.FromArgb(244,246,249))) g.FillRectangle(fill,x,y,w,h);'+[Environment]::NewLine+'                using(var f=new Font("Segoe UI",7.5F)) g.DrawString("VTK scalar bar",f,Brushes.DimGray,x+2,y+h/2-6);'
if(-not $s.Contains($oldPaint)){throw 'C9.69 legacy HUD gradient anchor missing.'}
$s=$s.Replace($oldPaint,$newPaint)

$summaryAnchor='        public string EvidenceSummary()'+[Environment]::NewLine+'        {'
$rendererSummary=@'
        public string RendererContractSummary()
        {
            RefreshMetadata();
            return AsterMaxResultsColorContract.FromScene(_scene).Describe();
        }

        public string EvidenceSummary()
        {
'@
if(-not $s.Contains($summaryAnchor)){throw 'C9.69 summary anchor missing.'}
$s=$s.Replace($summaryAnchor,$rendererSummary)

Set-Content $p $s -Encoding UTF8
Write-Host 'C9.69 renderer-synchronized results contract injected.' -ForegroundColor Green
