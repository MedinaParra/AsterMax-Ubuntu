param([string]$Root)
$ErrorActionPreference='Stop'

$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $p)){throw 'C10.13 requires AsterMaxVtkResultsBinding.cs after C10.12.'}
$s=Get-Content $p -Raw

# C10.13: make the real Code_Aster scalar field visible on the actor and expose practical
# post-processing controls. The previous viewport configured the color spectrum BEFORE AddCells,
# but never called vtkControl.UpdateScalarFormatting after the actor existed. As a result the
# TETRA10 surface rendered with the actor's uniform base color even though real nodal scalars were present.

# ---- Controls / fields ---------------------------------------------------------------
$fieldAnchor='        private readonly NumericUpDown _scale;'
$fieldInsert=@'
        private readonly NumericUpDown _scale;
        private readonly CheckBox _showContours;
        private readonly CheckBox _showEdges;
        private readonly CheckBox _showDeformed;
        private readonly CheckBox _autoRange;
        private readonly NumericUpDown _rangeMin;
        private readonly NumericUpDown _rangeMax;
'@
if($s.Contains($fieldAnchor) -and -not $s.Contains('private readonly CheckBox _showContours;')){
    $s=$s.Replace($fieldAnchor,$fieldInsert.TrimEnd())
}
elseif(-not $s.Contains('private readonly CheckBox _showContours;')){throw 'C10.13 viewport field anchor missing.'}

$topAnchor='            var top=new FlowLayoutPanel { Dock=DockStyle.Top, Height=48, Padding=new Padding(10,8,10,6), BackColor=Color.White };'
$topNew='            var top=new FlowLayoutPanel { Dock=DockStyle.Top, Height=82, Padding=new Padding(10,8,10,6), BackColor=Color.White, AutoScroll=true, WrapContents=true };'
if($s.Contains($topAnchor)){$s=$s.Replace($topAnchor,$topNew)}

$initAnchor='            _scale.Value=(decimal)Math.Min(100000,AsterMaxResultsScene.RecommendDeformationScale(bundle,0.10));'
$initNew=@'
            _scale.Value=(decimal)Math.Min(100000,AsterMaxResultsScene.RecommendDeformationScale(bundle,0.10));
            _showDeformed=new CheckBox { Text="Deformed", Checked=true, AutoSize=true, Padding=new Padding(8,5,0,0) };
            _showContours=new CheckBox { Text="Contours", Checked=true, AutoSize=true, Padding=new Padding(8,5,0,0) };
            _showEdges=new CheckBox { Text="Mesh edges", Checked=true, AutoSize=true, Padding=new Padding(8,5,0,0) };
            _autoRange=new CheckBox { Text="Auto range", Checked=true, AutoSize=true, Padding=new Padding(8,5,0,0) };
            _rangeMin=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=92, Enabled=false };
            _rangeMax=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=92, Enabled=false };
'@
if($s.Contains($initAnchor) -and -not $s.Contains('_showContours=new CheckBox')){$s=$s.Replace($initAnchor,$initNew.TrimEnd())}
elseif(-not $s.Contains('_showContours=new CheckBox')){throw 'C10.13 control initialization anchor missing.'}

$topControlsAnchor='            top.Controls.Add(new Label {Text="Deformation x",AutoSize=true,Padding=new Padding(12,7,0,0)}); top.Controls.Add(_scale);'+[Environment]::NewLine+'            top.Controls.Add(render); top.Controls.Add(capture); top.Controls.Add(_status);'
$topControlsNew=@'
            top.Controls.Add(new Label {Text="Deformation x",AutoSize=true,Padding=new Padding(12,7,0,0)}); top.Controls.Add(_scale);
            top.Controls.Add(_showDeformed); top.Controls.Add(_showContours); top.Controls.Add(_showEdges); top.Controls.Add(_autoRange);
            top.Controls.Add(new Label {Text="Min",AutoSize=true,Padding=new Padding(8,7,0,0)}); top.Controls.Add(_rangeMin);
            top.Controls.Add(new Label {Text="Max",AutoSize=true,Padding=new Padding(4,7,0,0)}); top.Controls.Add(_rangeMax);
            top.Controls.Add(render); top.Controls.Add(capture); top.Controls.Add(_status);
'@
if($s.Contains($topControlsAnchor) -and -not $s.Contains('top.Controls.Add(_showContours)')){$s=$s.Replace($topControlsAnchor,$topControlsNew.TrimEnd())}
elseif(-not $s.Contains('top.Controls.Add(_showContours)')){throw 'C10.13 top controls anchor missing.'}

$eventAnchor='            _probeNode.ValueChanged+=delegate { RefreshMetadata(); };'
$eventNew=@'
            _probeNode.ValueChanged+=delegate { RefreshMetadata(); };
            _showDeformed.CheckedChanged+=delegate { _scale.Enabled=_showDeformed.Checked; RenderScene(); };
            _showContours.CheckedChanged+=delegate { RenderScene(); };
            _showEdges.CheckedChanged+=delegate { RenderScene(); };
            _autoRange.CheckedChanged+=delegate {
                _rangeMin.Enabled=!_autoRange.Checked; _rangeMax.Enabled=!_autoRange.Checked;
                RenderScene();
            };
'@
if($s.Contains($eventAnchor) -and -not $s.Contains('_showContours.CheckedChanged')){$s=$s.Replace($eventAnchor,$eventNew.TrimEnd())}
elseif(-not $s.Contains('_showContours.CheckedChanged')){throw 'C10.13 control event anchor missing.'}

# ---- Metadata, auto/manual range and deformation toggle ------------------------------
$refreshAnchor='        private void RefreshMetadata()'+[Environment]::NewLine+'        {'
if(-not $s.Contains('private static void SetNumericResultValue')){
    $helpers=@'
        private static void SetNumericResultValue(NumericUpDown control,double value)
        {
            if(control==null || Double.IsNaN(value) || Double.IsInfinity(value)) return;
            decimal v;
            try { v=(decimal)value; } catch { v=value<0 ? control.Minimum : control.Maximum; }
            if(v<control.Minimum) v=control.Minimum;
            if(v>control.Maximum) v=control.Maximum;
            control.Value=v;
        }

        private vtkControl.vtkMaxColorSpectrum CreateDisplaySpectrum(AsterMaxResultsColorContract contract)
        {
            if(contract==null) throw new ArgumentNullException("contract");
            if(_autoRange.Checked) return contract.CreateVtkSpectrum();
            double lo=(double)_rangeMin.Value, hi=(double)_rangeMax.Value;
            if(!(hi>lo)) throw new InvalidOperationException("Manual contour range requires Max > Min.");
            var spectrum=new vtkControl.vtkMaxColorSpectrum();
            spectrum.Type=vtkControl.vtkColorSpectrumType.Rainbow;
            spectrum.MinMaxType=vtkControl.vtkColorSpectrumMinMaxType.Manual;
            spectrum.NumberOfColors=12;
            if(hi<=0){spectrum.MinUserValue=lo;spectrum.MaxUserValue=hi;}
            else{spectrum.MaxUserValue=hi;spectrum.MinUserValue=lo;}
            return spectrum;
        }

'@
    if(-not $s.Contains($refreshAnchor)){throw 'C10.13 RefreshMetadata anchor missing.'}
    $s=$s.Replace($refreshAnchor,$helpers+$refreshAnchor)
}

$sceneLine='            _scene=AsterMaxResultsScene.Build(_bundle,(string)_field.SelectedItem,(double)_scale.Value);'
$sceneNew=@'
            double deformationScale=_showDeformed.Checked ? (double)_scale.Value : 0.0;
            _scene=AsterMaxResultsScene.Build(_bundle,(string)_field.SelectedItem,deformationScale);
            if(_autoRange.Checked)
            {
                SetNumericResultValue(_rangeMin,_scene.Minimum);
                SetNumericResultValue(_rangeMax,_scene.Maximum);
            }
'@
if($s.Contains($sceneLine)){$s=$s.Replace($sceneLine,$sceneNew.TrimEnd())}
elseif(-not $s.Contains('double deformationScale=_showDeformed.Checked')){throw 'C10.13 deformation scene anchor missing.'}

$legendLine='            _legend.SetContract(AsterMaxResultsColorContract.FromScene(_scene));'
$legendNew=@'
            var displayContract=AsterMaxResultsColorContract.FromScene(_scene);
            _legend.SetDisplayRange(_autoRange.Checked ? _scene.Minimum : (double)_rangeMin.Value,
                                    _autoRange.Checked ? _scene.Maximum : (double)_rangeMax.Value,
                                    _scene.Unit,_scene.Field);
'@
if($s.Contains($legendLine)){$s=$s.Replace($legendLine,$legendNew.TrimEnd())}
elseif(-not $s.Contains('_legend.SetDisplayRange(')){throw 'C10.13 legend metadata anchor missing.'}

# ---- Legend: actual color ramp instead of the old grey placeholder -------------------
$legendMethod=@'
            public void SetContract(AsterMaxResultsColorContract c)
            {
                if(c==null || c.FeaValuesInvented) throw new InvalidOperationException("Invalid renderer color contract.");
                _min=c.Minimum; _max=c.Maximum; _unit=c.Unit??""; _field=c.Field??""; Invalidate();
            }
'@
$legendMethodNew=@'
            public void SetContract(AsterMaxResultsColorContract c)
            {
                if(c==null || c.FeaValuesInvented) throw new InvalidOperationException("Invalid renderer color contract.");
                SetDisplayRange(c.Minimum,c.Maximum,c.Unit,c.Field);
            }
            public void SetDisplayRange(double min,double max,string unit,string field)
            {
                _min=min; _max=max; _unit=unit??""; _field=field??""; Invalidate();
            }
'@
if($s.Contains($legendMethod) -and -not $s.Contains('public void SetDisplayRange(')){$s=$s.Replace($legendMethod,$legendMethodNew)}
elseif(-not $s.Contains('public void SetDisplayRange(')){throw 'C10.13 legend method anchor missing.'}

$greyPaint='                using(var fill=new SolidBrush(Color.FromArgb(244,246,249))) g.FillRectangle(fill,x,y,w,h);'+[Environment]::NewLine+'                using(var f=new Font("Segoe UI",7.5F)) g.DrawString("VTK scalar bar",f,Brushes.DimGray,x+2,y+h/2-6);'
$gradientPaint=@'
                Color[] c={Color.FromArgb(180,0,0),Color.OrangeRed,Color.Gold,Color.LimeGreen,Color.Cyan,Color.RoyalBlue};
                for(int i=0;i<h;i++)
                {
                    double t=(double)i/Math.Max(1,h-1);
                    int seg=Math.Min(c.Length-2,(int)(t*(c.Length-1)));
                    double u=t*(c.Length-1)-seg; Color a=c[seg],b=c[seg+1];
                    Color q=Color.FromArgb((int)(a.R+(b.R-a.R)*u),(int)(a.G+(b.G-a.G)*u),(int)(a.B+(b.B-a.B)*u));
                    using(var pen=new Pen(q)) g.DrawLine(pen,x,y+i,x+w,y+i);
                }
'@
if($s.Contains($greyPaint)){$s=$s.Replace($greyPaint,$gradientPaint.TrimEnd())}
elseif(-not $s.Contains('Color[] c={Color.FromArgb(180,0,0)')){throw 'C10.13 grey legend placeholder anchor missing.'}

# ---- Renderer: apply nodal scalars AFTER the actor exists ----------------------------
$colorSpectrumLine='                _view.SetScalarBarColorSpectrum(colorContract.CreateVtkSpectrum());'
if($s.Contains($colorSpectrumLine)){$s=$s.Replace($colorSpectrumLine,'                _view.SetScalarBarColorSpectrum(CreateDisplaySpectrum(colorContract));')}

$dataAnchor='                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);'
$dataNew=@'
                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);
                data.ColorContours=_showContours.Checked;
'@
if($s.Contains($dataAnchor) -and -not $s.Contains('data.ColorContours=_showContours.Checked;')){$s=$s.Replace($dataAnchor,$dataNew.TrimEnd())}
elseif(-not $s.Contains('data.ColorContours=_showContours.Checked;')){throw 'C10.13 contour actor anchor missing.'}

$addCellsAnchor='                _view.AddCells(data);'+[Environment]::NewLine+'                _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);'
$addCellsNew=@'
                _view.AddCells(data);
                _view.EdgesVisibility=_showEdges.Checked ? vtkControl.vtkEdgesVisibility.ElementEdges : vtkControl.vtkEdgesVisibility.NoEdges;
                // Critical C10.13 fix: AddCells creates the actor after the spectrum was configured.
                // Re-run scalar formatting now so the actor mapper receives the real nodal scalar LUT/range.
                _view.UpdateScalarsAndCameraAndRedraw();
                _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);
'@
if($s.Contains($addCellsAnchor) -and -not $s.Contains('_view.UpdateScalarsAndCameraAndRedraw();')){$s=$s.Replace($addCellsAnchor,$addCellsNew.TrimEnd())}
elseif(-not $s.Contains('_view.UpdateScalarsAndCameraAndRedraw();')){throw 'C10.13 AddCells scalar-refresh anchor missing.'}

$statusOld='                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • exterior surface rendered";'
$statusNew='                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • contours "+(_showContours.Checked?"ON":"OFF")+" • edges "+(_showEdges.Checked?"ON":"OFF")+" • deformed "+(_showDeformed.Checked?"ON":"OFF");'
if($s.Contains($statusOld)){$s=$s.Replace($statusOld,$statusNew)}

# Source gates: never ship the old uniform-color path again.
foreach($token in @('_view.UpdateScalarsAndCameraAndRedraw();','data.ColorContours=_showContours.Checked;','CreateDisplaySpectrum','_showEdges.Checked','_showDeformed.Checked','_autoRange.Checked','public void SetDisplayRange')){
    if(-not $s.Contains($token)){throw "C10.13 post-processing token missing: $token"}
}
if($s.Contains('g.DrawString("VTK scalar bar"')){throw 'C10.13 grey scalar-bar placeholder remains.'}
Set-Content $p $s -Encoding UTF8
Write-Host 'C10.13 real contour LUT + deformation/edges/contours + auto/manual range options applied.' -ForegroundColor Green
