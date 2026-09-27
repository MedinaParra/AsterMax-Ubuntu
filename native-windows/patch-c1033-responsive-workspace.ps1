param([string]$Root)
$ErrorActionPreference='Stop'

$viewPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
$integratedPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($viewPath,$integratedPath,$uiPath)){ if(!(Test-Path $p)){ throw "C10.33 missing: $p" } }

# ----------------------------------------------------------------------
# 1. Results toolbar: deterministic two-row responsive layout.
#    The previous single FlowLayoutPanel wrapped unpredictably at 1366x768
#    and under Windows DPI scaling, clipping controls and status text.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $viewPath -Raw),"\r\n?","`n")

$topOld='            var top=new FlowLayoutPanel { Dock=DockStyle.Top, Height=82, Padding=new Padding(10,8,10,6), BackColor=Color.White, AutoScroll=true, WrapContents=true };'
$topNew=@'
            var top=new TableLayoutPanel {
                Name="asterMaxResultsToolbar", Dock=DockStyle.Top,
                AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink,
                Padding=new Padding(6,4,6,3), Margin=new Padding(0),
                BackColor=Color.White, ColumnCount=1, RowCount=3
            };
            top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100F));
            top.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            top.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            top.RowStyles.Add(new RowStyle(SizeType.Absolute,20F));
'@
if($v.Contains($topOld)){
    $v=$v.Replace($topOld,$topNew.TrimEnd())
}
elseif(-not $v.Contains('Name="asterMaxResultsToolbar"')){
    throw 'C10.33 results toolbar anchor missing.'
}

# Compact widths scale much better on 1280/1366 px screens while remaining usable.
$v=$v.Replace('_field=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=210 };',
              '_field=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=170 };')
$v=$v.Replace('_displayUnit=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=76 };',
              '_displayUnit=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=68 };')
$v=$v.Replace('_numberFormat=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=92 };',
              '_numberFormat=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=82 };')
$v=$v.Replace('_legendBands=new NumericUpDown { Minimum=5, Maximum=16, Value=9, Width=50 };',
              '_legendBands=new NumericUpDown { Minimum=5, Maximum=16, Value=9, Width=46 };')
$v=$v.Replace('_scale=new NumericUpDown { DecimalPlaces=3, Minimum=0, Maximum=100000, Width=105 };',
              '_scale=new NumericUpDown { DecimalPlaces=3, Minimum=0, Maximum=100000, Width=82 };')
$v=$v.Replace('_rangeMin=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=92, Enabled=false };',
              '_rangeMin=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=78, Enabled=false };')
$v=$v.Replace('_rangeMax=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=92, Enabled=false };',
              '_rangeMax=new NumericUpDown { DecimalPlaces=4, Minimum=-1000000000M, Maximum=1000000000M, Width=78, Enabled=false };')
$v=$v.Replace('var render=new Button { Text="Update result", AutoSize=true };',
              'var render=new Button { Text="Actualizar", AutoSize=true, Height=26, Padding=new Padding(8,0,8,0) };')
$v=$v.Replace('var capture=new Button { Text="Capture evidence PNG", AutoSize=true };',
              'var capture=new Button { Text="Capturar PNG", AutoSize=true, Height=26, Padding=new Padding(8,0,8,0) };')

# Replace the old one-dimensional control stream with two logical rows plus status.
$controlsPattern='(?ms)\s*top\.Controls\.Add\(new Label \{Text="Result".*?top\.Controls\.Add\(_status\);'
$controlsNew=@'
            _showDeformed.Text="Deformada";
            _showContours.Text="Contornos";
            _showEdges.Text="Aristas";
            _autoRange.Text="Rango auto";

            var primary=new FlowLayoutPanel {
                Dock=DockStyle.Fill, AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink,
                FlowDirection=FlowDirection.LeftToRight, WrapContents=true,
                Margin=new Padding(0), Padding=new Padding(0,0,0,1), BackColor=Color.White
            };
            var secondary=new FlowLayoutPanel {
                Dock=DockStyle.Fill, AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink,
                FlowDirection=FlowDirection.LeftToRight, WrapContents=true,
                Margin=new Padding(0), Padding=new Padding(0), BackColor=Color.White
            };

            primary.Controls.Add(new Label {Text="Resultado",AutoSize=true,Padding=new Padding(0,6,0,0)});
            primary.Controls.Add(_field);
            primary.Controls.Add(new Label {Text="Unidades",AutoSize=true,Padding=new Padding(5,6,0,0)});
            primary.Controls.Add(_displayUnit);
            primary.Controls.Add(new Label {Text="Formato",AutoSize=true,Padding=new Padding(5,6,0,0)});
            primary.Controls.Add(_numberFormat);
            primary.Controls.Add(new Label {Text="Bandas",AutoSize=true,Padding=new Padding(5,6,0,0)});
            primary.Controls.Add(_legendBands);
            primary.Controls.Add(new Label {Text="Deform. x",AutoSize=true,Padding=new Padding(5,6,0,0)});
            primary.Controls.Add(_scale);
            primary.Controls.Add(render);
            primary.Controls.Add(capture);

            secondary.Controls.Add(_showDeformed);
            secondary.Controls.Add(_showContours);
            secondary.Controls.Add(_showEdges);
            secondary.Controls.Add(_autoRange);
            secondary.Controls.Add(new Label {Text="Mín",AutoSize=true,Padding=new Padding(5,6,0,0)});
            secondary.Controls.Add(_rangeMin);
            secondary.Controls.Add(new Label {Text="Máx",AutoSize=true,Padding=new Padding(3,6,0,0)});
            secondary.Controls.Add(_rangeMax);

            foreach(Control c in primary.Controls) c.Margin=new Padding(2,1,2,1);
            foreach(Control c in secondary.Controls) c.Margin=new Padding(2,1,2,1);

            _status.AutoSize=false;
            _status.Dock=DockStyle.Fill;
            _status.Height=20;
            _status.Padding=new Padding(2,2,0,0);
            _status.AutoEllipsis=true;

            top.Controls.Add(primary,0,0);
            top.Controls.Add(secondary,0,1);
            top.Controls.Add(_status,0,2);'@
$v2=[regex]::Replace($v,$controlsPattern,"`n"+$controlsNew.TrimEnd(),1)
if($v2 -eq $v -and -not $v.Contains('var primary=new FlowLayoutPanel')){
    throw 'C10.33 result control stream anchor missing.'
}
$v=$v2

# Compact result-details panel. In integrated mode this panel is docked below the
# project tree, so fixed 300+ px content previously got clipped at 768p.
$v=$v.Replace('var right=new Panel { Dock=DockStyle.Right, Width=270, Padding=new Padding(14), BackColor=Color.White };',
              'var right=new Panel { Dock=DockStyle.Right, Width=245, Padding=new Padding(8), BackColor=Color.White, AutoScroll=true };')
$v=$v.Replace('Dock=DockStyle.Top, Height=30, Font=new Font("Segoe UI Semibold",10F)',
              'Dock=DockStyle.Top, Height=22, Font=new Font("Segoe UI Semibold",9.2F)')
$v=$v.Replace('Dock=DockStyle.Top, Height=28, Font=new Font("Segoe UI",9F,FontStyle.Bold)',
              'Dock=DockStyle.Top, Height=20, Font=new Font("Segoe UI",8.5F,FontStyle.Bold)')
$v=$v.Replace('_legend=new AsterMaxLegendPanel { Dock=DockStyle.Top, Height=260, Margin=new Padding(0,6,0,10) };',
              '_legend=new AsterMaxLegendPanel { Dock=DockStyle.Top, Height=210, Margin=new Padding(0,4,0,6) };')
$v=$v.Replace('_maxLabel=new Label { Dock=DockStyle.Top, Height=42, Font=new Font("Consolas",9F), AutoEllipsis=true };',
              '_maxLabel=new Label { Dock=DockStyle.Top, Height=31, Font=new Font("Consolas",8.4F), AutoEllipsis=true };')
$v=$v.Replace('_minLabel=new Label { Dock=DockStyle.Top, Height=42, Font=new Font("Consolas",9F), AutoEllipsis=true };',
              '_minLabel=new Label { Dock=DockStyle.Top, Height=31, Font=new Font("Consolas",8.4F), AutoEllipsis=true };')
$v=$v.Replace('var probeTitle=new Label { Text="Nodal probe", Dock=DockStyle.Top, Height=26, Font=new Font("Segoe UI",9F,FontStyle.Bold) };',
              'var probeTitle=new Label { Text="Sonda nodal", Dock=DockStyle.Top, Height=20, Font=new Font("Segoe UI",8.5F,FontStyle.Bold) };')
$v=$v.Replace('_probeLabel=new Label { Dock=DockStyle.Top, Height=52, Font=new Font("Consolas",9F), Padding=new Padding(0,8,0,0) };',
              '_probeLabel=new Label { Dock=DockStyle.Top, Height=38, Font=new Font("Consolas",8.3F), Padding=new Padding(0,4,0,0) };')
$v=$v.Replace('_integrityLabel=new Label { Dock=DockStyle.Bottom, Height=58, Text="SOURCE: real Code_Aster results bundle',
              '_integrityLabel=new Label { Dock=DockStyle.Bottom, Height=44, Text="SOURCE: real Code_Aster results bundle')

foreach($token in @('asterMaxResultsToolbar','var primary=new FlowLayoutPanel','primary.Controls.Add(_displayUnit)','secondary.Controls.Add(_rangeMin)','Text="Actualizar"','Text="Capturar PNG"')){
    if(-not $v.Contains($token)){ throw "C10.33 viewport token missing: $token" }
}
Set-Content $viewPath $v -Encoding UTF8

# -----------------------------------------------------------------------
# 2. Integrated workspace proportions: narrower Outline, compact Details,
#    smaller output console, more VTK viewport.
# ----------------------------------------------------------------------
$i=[regex]::Replace((Get-Content $integratedPath -Raw),"\r\n?","`n")

$detailsOld='_axResultDetailsHost = new Panel { Name="asterMaxResultDetails", Dock=DockStyle.Bottom, Height=250, BackColor=Color.White };'
$detailsNew='_axResultDetailsHost = new Panel { Name="asterMaxResultDetails", Dock=DockStyle.Bottom, Height=210, BackColor=Color.White, AutoScroll=true };'
if($i.Contains($detailsOld)){$i=$i.Replace($detailsOld,$detailsNew)}
elseif(-not $i.Contains('Height=210, BackColor=Color.White, AutoScroll=true')){ throw 'C10.33 integrated details host anchor missing.' }

$showAnchor='                _axResultDetailsHost.Show();'
if(-not $i.Contains('AsterMaxApplyResponsiveWorkspaceLayout();')){
    if(-not $i.Contains($showAnchor)){ throw 'C10.33 integrated result show anchor missing.' }
    $i=$i.Replace($showAnchor,$showAnchor+"`n                AsterMaxApplyResponsiveWorkspaceLayout();")
}

$disposeAnchor='        private void DisposeAsterMaxResultView()'
$layoutMethod=@'
        private void AsterMaxApplyResponsiveWorkspaceLayout()
        {
            if (splitContainer1 != null && !splitContainer1.IsDisposed)
            {
                splitContainer1.Panel1MinSize=210;
                if(splitContainer1.Width>620)
                {
                    int usable=Math.Max(0,splitContainer1.Width-splitContainer1.SplitterWidth);
                    int left=Math.Max(220,Math.Min(295,(int)Math.Round(usable*0.205)));
                    int maxLeft=Math.Max(220,usable-360);
                    if(left>maxLeft) left=maxLeft;
                    if(left>=splitContainer1.Panel1MinSize && left<usable)
                        splitContainer1.SplitterDistance=left;
                }
            }

            if (_axResultDetailsHost != null && !_axResultDetailsHost.IsDisposed && splitContainer1 != null)
            {
                int available=Math.Max(0,splitContainer1.Panel1.ClientSize.Height);
                _axResultDetailsHost.Height=Math.Max(185,Math.Min(215,available/2));
            }

            if (splitContainer2 != null && !splitContainer2.IsDisposed && splitContainer2.Height>300)
            {
                splitContainer2.Panel2MinSize=58;
                int outputHeight=splitContainer2.Height<520 ? 68 : 82;
                int distance=splitContainer2.Height-splitContainer2.SplitterWidth-outputHeight;
                int maxDistance=splitContainer2.Height-splitContainer2.SplitterWidth-splitContainer2.Panel2MinSize;
                distance=Math.Min(distance,maxDistance);
                if(distance>80) splitContainer2.SplitterDistance=distance;
            }
        }

'@
if(-not $i.Contains('private void AsterMaxApplyResponsiveWorkspaceLayout()')){
    if(-not $i.Contains($disposeAnchor)){ throw 'C10.33 layout insertion anchor missing.' }
    $i=$i.Replace($disposeAnchor,$layoutMethod+$disposeAnchor)
}
Set-Content $integratedPath $i -Encoding UTF8

# ----------------------------------------------------------------------
# 3. Ribbon uses less vertical space while preserving the 32 px icons.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$ribbonPos=$u.IndexOf('Name = "asterMaxRibbon"')
if($ribbonPos -lt 0){throw 'C10.33 ribbon missing.'}
$tail=$u.Substring($ribbonPos)
$hm=[regex]::Match($tail,'(?m)^(?<i>\s*)Height\s*=\s*132,\s*$')
if($hm.Success){
    $abs=$ribbonPos+$hm.Index
    $u=$u.Substring(0,$abs)+$hm.Groups['i'].Value+'Height = 122,'+$u.Substring($abs+$hm.Length)
}
elseif(-not $tail.Contains('Height = 122,')){throw 'C10.33 ribbon height anchor missing.'}

$cmdStart=$u.IndexOf('        private Button CommandTile(')
$cmdEnd=$u.IndexOf('        private Image CreateAsterMaxRibbonIcon(', $cmdStart)
if($cmdStart -lt 0 -or $cmdEnd -lt 0){throw 'C10.33 CommandTile anchors missing.'}
$cmd=$u.Substring($cmdStart,$cmdEnd-$cmdStart)
$cmd=$cmd.Replace('Width = text.Length > 13 ? 124 : 104,','Width = text.Length > 13 ? 112 : 94,')
$cmd=$cmd.Replace('Height = 82,','Height = 76,')
$cmd=$cmd.Replace('Padding = new Padding(4, 5, 4, 3),','Padding = new Padding(3, 3, 3, 2),')
$u=$u.Substring(0,$cmdStart)+$cmd+$u.Substring($cmdEnd)
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.33: responsive 1366x768/DPI-aware results workspace + compact ribbon applied.' -ForegroundColor Green
