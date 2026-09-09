param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $p)){throw 'C9.67 VTK binding must be applied before C9.68.'}
$s=Get-Content $p -Raw
$start=$s.IndexOf('    internal sealed class AsterMaxResultsViewportForm : Form')
$end=$s.IndexOf('    public partial class FrmMain',$start)
if($start -lt 0 -or $end -lt 0){throw 'C9.68 viewport anchors missing.'}
$new=@'
    internal sealed class AsterMaxResultsViewportForm : Form
    {
        private readonly AsterMaxResultsBundle _bundle;
        private readonly Panel _host;
        private vtkControl.vtkControl _view;
        private readonly ComboBox _field;
        private readonly NumericUpDown _scale;
        private readonly NumericUpDown _probeNode;
        private readonly Label _status;
        private readonly Label _minLabel;
        private readonly Label _maxLabel;
        private readonly Label _probeLabel;
        private readonly Label _integrityLabel;
        private readonly AsterMaxLegendPanel _legend;
        private AsterMaxResultsScene _scene;

        public AsterMaxResultsViewportForm(AsterMaxResultsBundle bundle)
        {
            _bundle=bundle ?? throw new ArgumentNullException("bundle");
            Text="AsterMax Mechanical — Results Workspace";
            Width=1280; Height=800; StartPosition=FormStartPosition.CenterParent;
            BackColor=Color.FromArgb(245,247,250);

            var top=new FlowLayoutPanel { Dock=DockStyle.Top, Height=48, Padding=new Padding(10,8,10,6), BackColor=Color.White };
            _field=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=210 };
            _field.Items.AddRange(bundle.AvailableFields()); _field.SelectedIndex=Math.Min(1,_field.Items.Count-1);
            _scale=new NumericUpDown { DecimalPlaces=3, Minimum=0, Maximum=100000, Width=105 };
            _scale.Value=(decimal)Math.Min(100000,AsterMaxResultsScene.RecommendDeformationScale(bundle,0.10));
            var render=new Button { Text="Update result", AutoSize=true };
            var capture=new Button { Text="Capture evidence PNG", AutoSize=true };
            _status=new Label { AutoSize=true, Padding=new Padding(10,7,0,0), ForeColor=Color.FromArgb(45,55,72) };
            top.Controls.Add(new Label {Text="Result",AutoSize=true,Padding=new Padding(0,7,0,0)}); top.Controls.Add(_field);
            top.Controls.Add(new Label {Text="Deformation x",AutoSize=true,Padding=new Padding(12,7,0,0)}); top.Controls.Add(_scale);
            top.Controls.Add(render); top.Controls.Add(capture); top.Controls.Add(_status);

            var right=new Panel { Dock=DockStyle.Right, Width=270, Padding=new Padding(14), BackColor=Color.White };
            var title=new Label { Text="RESULT DETAILS", Dock=DockStyle.Top, Height=30, Font=new Font("Segoe UI Semibold",10F), ForeColor=Color.FromArgb(22,42,70) };
            var fieldTitle=new Label { Text="Code_Aster field", Dock=DockStyle.Top, Height=28, Font=new Font("Segoe UI",9F,FontStyle.Bold) };
            _legend=new AsterMaxLegendPanel { Dock=DockStyle.Top, Height=260, Margin=new Padding(0,6,0,10) };
            _maxLabel=new Label { Dock=DockStyle.Top, Height=42, Font=new Font("Consolas",9F), AutoEllipsis=true };
            _minLabel=new Label { Dock=DockStyle.Top, Height=42, Font=new Font("Consolas",9F), AutoEllipsis=true };
            var probeTitle=new Label { Text="Nodal probe", Dock=DockStyle.Top, Height=26, Font=new Font("Segoe UI",9F,FontStyle.Bold) };
            _probeNode=new NumericUpDown { Dock=DockStyle.Top, Minimum=1, Maximum=Math.Max(1,bundle.NodeCount), Value=Math.Max(1,bundle.NodeCount) };
            _probeLabel=new Label { Dock=DockStyle.Top, Height=52, Font=new Font("Consolas",9F), Padding=new Padding(0,8,0,0) };
            _integrityLabel=new Label { Dock=DockStyle.Bottom, Height=58, Text="SOURCE: real Code_Aster results bundle\r\nSynthetic FEA values: rejected", ForeColor=Color.FromArgb(34,105,65), Font=new Font("Segoe UI",8.5F,FontStyle.Bold) };
            right.Controls.Add(_integrityLabel); right.Controls.Add(_probeLabel); right.Controls.Add(_probeNode); right.Controls.Add(probeTitle); right.Controls.Add(_minLabel); right.Controls.Add(_maxLabel); right.Controls.Add(_legend); right.Controls.Add(fieldTitle); right.Controls.Add(title);

            _host=new Panel { Dock=DockStyle.Fill, BackColor=Color.FromArgb(232,236,241) };
            Controls.Add(_host); Controls.Add(right); Controls.Add(top);
            render.Click+=delegate { RenderScene(); };
            capture.Click+=delegate { using(var dlg=new SaveFileDialog { Filter="PNG image (*.png)|*.png", FileName="AsterMax-C9.68-results-evidence.png" }) if(dlg.ShowDialog(this)==DialogResult.OK) CaptureEvidencePng(dlg.FileName); };
            _field.SelectedIndexChanged+=delegate { RefreshMetadata(); };
            _scale.ValueChanged+=delegate { RefreshMetadata(); };
            _probeNode.ValueChanged+=delegate { RefreshMetadata(); };
            Shown+=delegate { RenderScene(); };
            RefreshMetadata();
        }

        private void RefreshMetadata()
        {
            if(_field.SelectedItem==null) return;
            _scene=AsterMaxResultsScene.Build(_bundle,(string)_field.SelectedItem,(double)_scale.Value);
            _legend.SetRange(_scene.Minimum,_scene.Maximum,_scene.Unit,_scene.Field);
            _maxLabel.Text=String.Format(System.Globalization.CultureInfo.InvariantCulture,"MAX  {0:G9} {1}\r\nNode {2}",_scene.Maximum,_scene.Unit,_scene.MaximumNodeIndex+1);
            _minLabel.Text=String.Format(System.Globalization.CultureInfo.InvariantCulture,"MIN  {0:G9} {1}\r\nNode {2}",_scene.Minimum,_scene.Unit,_scene.MinimumNodeIndex+1);
            int node=(int)_probeNode.Value-1;
            double value=_bundle.ProbeNode(node,_scene.Field);
            var xyz=_bundle.Coordinates[node];
            _probeLabel.Text=String.Format(System.Globalization.CultureInfo.InvariantCulture,"N{0}: {1:G9} {2}\r\n({3:G6}, {4:G6}, {5:G6}) mm",node+1,value,_scene.Unit,xyz[0],xyz[1],xyz[2]);
            _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" HEXA8";
        }

        private void RenderScene()
        {
            RefreshMetadata();
            var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);
            if(_view!=null){_host.Controls.Remove(_view);_view.Dispose();}
            _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
            _host.Controls.Add(_view);
            _view.AddCells(data);
            _view.AdjustCameraDistanceAndClipping();
        }

        public string EvidenceSummary()
        {
            RefreshMetadata();
            return String.Format(System.Globalization.CultureInfo.InvariantCulture,
                "{0}|{1}|min={2:R}|minNode={3}|max={4:R}|maxNode={5}|probeNode={6}|probe={7:R}|invented=false",
                _scene.Field,_scene.Unit,_scene.Minimum,_scene.MinimumNodeIndex+1,_scene.Maximum,_scene.MaximumNodeIndex+1,(int)_probeNode.Value,
                _bundle.ProbeNode((int)_probeNode.Value-1,_scene.Field));
        }

        public void CaptureEvidencePng(string path)
        {
            if(String.IsNullOrWhiteSpace(path)) throw new ArgumentException("Evidence path is required.","path");
            RefreshMetadata();
            using(var bmp=new Bitmap(Math.Max(1,Width),Math.Max(1,Height)))
            {
                DrawToBitmap(bmp,new Rectangle(0,0,bmp.Width,bmp.Height));
                bmp.Save(path,System.Drawing.Imaging.ImageFormat.Png);
            }
        }

        private sealed class AsterMaxLegendPanel : Control
        {
            private double _min,_max; private string _unit="",_field="";
            public AsterMaxLegendPanel(){DoubleBuffered=true;BackColor=Color.White;}
            public void SetRange(double min,double max,string unit,string field){_min=min;_max=max;_unit=unit??"";_field=field??"";Invalidate();}
            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e); var g=e.Graphics; g.Clear(Color.White);
                using(var f=new Font("Segoe UI Semibold",9F)) g.DrawString(_field+" ["+_unit+"]",f,Brushes.Black,2,2);
                int x=18,y=30,w=42,h=Math.Max(80,Height-52);
                Color[] c={Color.FromArgb(170,0,0),Color.Orange,Color.Yellow,Color.LimeGreen,Color.Cyan,Color.RoyalBlue};
                for(int i=0;i<h;i++){double t=(double)i/Math.Max(1,h-1);int seg=Math.Min(c.Length-2,(int)(t*(c.Length-1)));double u=t*(c.Length-1)-seg;Color a=c[seg],b=c[seg+1];Color q=Color.FromArgb((int)(a.R+(b.R-a.R)*u),(int)(a.G+(b.G-a.G)*u),(int)(a.B+(b.B-a.B)*u));using(var pen=new Pen(q))g.DrawLine(pen,x,y+i,x+w,y+i);}
                using(var p=new Pen(Color.DimGray))g.DrawRectangle(p,x,y,w,h);
                using(var f=new Font("Consolas",8.5F))
                {
                    for(int k=0;k<=5;k++){double t=(double)k/5;double v=_max-( _max-_min)*t;int yy=y+(int)(h*t);g.DrawString(v.ToString("G6",System.Globalization.CultureInfo.InvariantCulture),f,Brushes.Black,x+w+8,yy-7);}
                }
            }
        }
    }

'@
$s=$s.Substring(0,$start)+$new+$s.Substring($end)
Set-Content $p $s -Encoding UTF8
Write-Host 'C9.68 professional real-results HUD injected.' -ForegroundColor Green
