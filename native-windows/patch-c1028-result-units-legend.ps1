param([string]$Root)
$ErrorActionPreference='Stop'

$scenePath = Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsScene.cs'
$viewPath  = Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
if(!(Test-Path $scenePath)){ throw 'C10.28 requires AsterMaxResultsScene.cs.' }
if(!(Test-Path $viewPath)){ throw 'C10.28 requires AsterMaxVtkResultsBinding.cs.' }

# --- Scene: add display-only scalar conversion. ---------------------------------------
$s = [regex]::Replace((Get-Content $scenePath -Raw), "\r\n?", "`n")
$sceneAnchor = @'
        public static double RecommendDeformationScale(AsterMaxResultsBundle bundle, double targetFraction)
'@
$sceneHelper = @'
        public AsterMaxResultsScene ConvertScalarDisplay(double factor, string unit)
        {
            if (!(factor > 0) || Double.IsNaN(factor) || Double.IsInfinity(factor))
                throw new ArgumentOutOfRangeException("factor");
            if (String.IsNullOrWhiteSpace(unit)) throw new ArgumentException("Display unit is required.", "unit");
            if (Math.Abs(factor - 1.0) < 1e-15 && String.Equals(Unit, unit, StringComparison.Ordinal))
                return this;
            return new AsterMaxResultsScene {
                Field = Field,
                Scalars = Scalars.Select(v => v * factor).ToArray(),
                DeformedCoordinates = DeformedCoordinates,
                Minimum = Minimum * factor,
                Maximum = Maximum * factor,
                MinimumNodeIndex = MinimumNodeIndex,
                MaximumNodeIndex = MaximumNodeIndex,
                DeformationScale = DeformationScale,
                Unit = unit
            };
        }

'@
if(-not $s.Contains('ConvertScalarDisplay(double factor, string unit)')){
    if(-not $s.Contains($sceneAnchor)){ throw 'C10.28 scene helper anchor missing.' }
    $s = $s.Replace($sceneAnchor, $sceneHelper + $sceneAnchor)
}
Set-Content $scenePath $s -Encoding UTF8

# --- Viewport controls + conversion. --------------------------------------------------
$v = [regex]::Replace((Get-Content $viewPath -Raw), "\r\n?", "`n")

$fieldAnchor = '        private readonly ComboBox _field;'
$fieldInsert = @'
        private readonly ComboBox _field;
        private readonly ComboBox _displayUnit;
        private readonly ComboBox _numberFormat;
        private readonly NumericUpDown _legendBands;
        private double _displayScalarFactor = 1.0;
'@
if(-not $v.Contains('private readonly ComboBox _displayUnit;')){
    if(-not $v.Contains($fieldAnchor)){ throw 'C10.28 viewport field anchor missing.' }
    $v = $v.Replace($fieldAnchor,$fieldInsert.TrimEnd())
}

$initAnchor = '            _field.Items.AddRange(bundle.AvailableFields()); _field.SelectedIndex=Math.Min(1,_field.Items.Count-1);'
$initNew = @'
            _field.Items.AddRange(bundle.AvailableFields()); _field.SelectedIndex=Math.Min(1,_field.Items.Count-1);
            _displayUnit=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=76 };
            _numberFormat=new ComboBox { DropDownStyle=ComboBoxStyle.DropDownList, Width=92 };
            _numberFormat.Items.AddRange(new object[]{"Auto","Decimal","Científico"}); _numberFormat.SelectedIndex=0;
            _legendBands=new NumericUpDown { Minimum=5, Maximum=16, Value=9, Width=50 };
            UpdateAsterMaxDisplayUnits();
'@
if(-not $v.Contains('_numberFormat.Items.AddRange')){
    if(-not $v.Contains($initAnchor)){ throw 'C10.28 unit control init anchor missing.' }
    $v = $v.Replace($initAnchor,$initNew.TrimEnd())
}

$controlsAnchor = '            top.Controls.Add(new Label {Text="Deformation x",AutoSize=true,Padding=new Padding(12,7,0,0)}); top.Controls.Add(_scale);'
$controlsNew = @'
            top.Controls.Add(new Label {Text="Unidades",AutoSize=true,Padding=new Padding(8,7,0,0)}); top.Controls.Add(_displayUnit);
            top.Controls.Add(new Label {Text="Formato",AutoSize=true,Padding=new Padding(8,7,0,0)}); top.Controls.Add(_numberFormat);
            top.Controls.Add(new Label {Text="Bandas",AutoSize=true,Padding=new Padding(8,7,0,0)}); top.Controls.Add(_legendBands);
            top.Controls.Add(new Label {Text="Deformación x",AutoSize=true,Padding=new Padding(12,7,0,0)}); top.Controls.Add(_scale);
'@
if(-not $v.Contains('top.Controls.Add(_displayUnit)')){
    if(-not $v.Contains($controlsAnchor)){ throw 'C10.28 toolbar control anchor missing.' }
    $v = $v.Replace($controlsAnchor,$controlsNew.TrimEnd())
}

$eventAnchor = '_field.SelectedIndexChanged+=delegate { RenderScene(); ResultFieldChanged?.Invoke(SelectedResultField); };'
$eventNew = @'
_field.SelectedIndexChanged+=delegate { UpdateAsterMaxDisplayUnits(); RenderScene(); ResultFieldChanged?.Invoke(SelectedResultField); };
            _displayUnit.SelectedIndexChanged+=delegate { RenderScene(); };
            _numberFormat.SelectedIndexChanged+=delegate { RenderScene(); };
            _legendBands.ValueChanged+=delegate { RenderScene(); };
'@
if($v.Contains($eventAnchor) -and -not $v.Contains('_displayUnit.SelectedIndexChanged')){
    $v = $v.Replace($eventAnchor,$eventNew.TrimEnd())
}
elseif(-not $v.Contains('_displayUnit.SelectedIndexChanged')){ throw 'C10.28 field event anchor missing.' }

$refreshAnchor = '        private void RefreshMetadata()'
$helpers = @'
        private void UpdateAsterMaxDisplayUnits()
        {
            if (_displayUnit == null || _field == null || _field.SelectedItem == null) return;
            string previous = _displayUnit.SelectedItem as string;
            string source = String.Equals((string)_field.SelectedItem, "Equivalent Stress", StringComparison.Ordinal)
                ? _bundle.StressUnit : _bundle.LengthUnit;
            string[] items;
            if (AsterMaxIsStressUnit(source)) items = new[]{"Pa","kPa","MPa","GPa"};
            else items = new[]{"µm","mm","cm","m"};
            _displayUnit.BeginUpdate();
            try
            {
                _displayUnit.Items.Clear();
                _displayUnit.Items.AddRange(items);
                int index = Array.IndexOf(items, previous);
                if (index < 0) index = Array.IndexOf(items, source);
                _displayUnit.SelectedIndex = index >= 0 ? index : 0;
            }
            finally { _displayUnit.EndUpdate(); }
        }

        private static bool AsterMaxIsStressUnit(string unit)
        {
            return unit=="Pa" || unit=="kPa" || unit=="MPa" || unit=="GPa";
        }

        private static double AsterMaxUnitToSi(string unit)
        {
            switch (unit)
            {
                case "Pa": return 1.0;
                case "kPa": return 1e3;
                case "MPa": return 1e6;
                case "GPa": return 1e9;
                case "µm": case "um": return 1e-6;
                case "mm": return 1e-3;
                case "cm": return 1e-2;
                case "m": return 1.0;
                default: throw new NotSupportedException("Unidad de resultados no soportada: " + unit);
            }
        }

        private static double AsterMaxDisplayFactor(string source, string target)
        {
            bool sourceStress=AsterMaxIsStressUnit(source), targetStress=AsterMaxIsStressUnit(target);
            if(sourceStress != targetStress) throw new InvalidOperationException("Conversión incompatible: "+source+" → "+target);
            return AsterMaxUnitToSi(source) / AsterMaxUnitToSi(target);
        }

        private string AsterMaxScalarBarFormat()
        {
            string mode = _numberFormat == null ? "Auto" : _numberFormat.SelectedItem as string;
            if (mode == "Decimal") return "F3";
            if (mode == "Científico") return "E3";
            return "G4";
        }

'@
if(-not $v.Contains('private void UpdateAsterMaxDisplayUnits()')){
    if(-not $v.Contains($refreshAnchor)){ throw 'C10.28 metadata helper anchor missing.' }
    $v = $v.Replace($refreshAnchor,$helpers+$refreshAnchor)
}

$sceneLine = '            _scene=AsterMaxResultsScene.Build(_bundle,(string)_field.SelectedItem,deformationScale);'
$sceneNew = @'
            var rawScene=AsterMaxResultsScene.Build(_bundle,(string)_field.SelectedItem,deformationScale);
            string displayUnit=_displayUnit.SelectedItem as string;
            if(String.IsNullOrEmpty(displayUnit)) displayUnit=rawScene.Unit;
            _displayScalarFactor=AsterMaxDisplayFactor(rawScene.Unit,displayUnit);
            _scene=rawScene.ConvertScalarDisplay(_displayScalarFactor,displayUnit);
'@
if($v.Contains($sceneLine)) {
    $v=$v.Replace($sceneLine,$sceneNew.TrimEnd())
}
elseif(-not $v.Contains('_displayScalarFactor=AsterMaxDisplayFactor')){ throw 'C10.28 scene conversion anchor missing.' }

# Probe value is stored in source units; convert only for display.
$probeLine = '            double value=_bundle.ProbeNode(node,_scene.Field);'
$probeNew = '            double value=_bundle.ProbeNode(node,_scene.Field) * _displayScalarFactor;'
if($v.Contains($probeLine)) {
    $v=$v.Replace($probeLine,$probeNew)
}
elseif(-not $v.Contains('ProbeNode(node,_scene.Field) * _displayScalarFactor')){ throw 'C10.28 probe conversion anchor missing.' }

# Evidence summary remains truthful but follows selected display units.
$evidenceProbe = '_bundle.ProbeNode((int)_probeNode.Value-1,_scene.Field));'
$evidenceNew = '_bundle.ProbeNode((int)_probeNode.Value-1,_scene.Field)*_displayScalarFactor);'
if($v.Contains($evidenceProbe)) {
    $v=$v.Replace($evidenceProbe,$evidenceNew)
}

# Auto/manual spectrum follows user-selected number of bands.
$autoSpectrum = '            if(_autoRange.Checked) return contract.CreateVtkSpectrum();'
$autoNew = @'
            if(_autoRange.Checked)
            {
                var autoSpectrum=contract.CreateVtkSpectrum();
                autoSpectrum.NumberOfColors=(int)_legendBands.Value;
                return autoSpectrum;
            }
'@
if($v.Contains($autoSpectrum)) {
    $v=$v.Replace($autoSpectrum,$autoNew.TrimEnd())
}
elseif(-not $v.Contains('autoSpectrum.NumberOfColors=(int)_legendBands.Value')){ throw 'C10.28 auto spectrum anchor missing.' }

$v=$v.Replace('            spectrum.NumberOfColors=12;','            spectrum.NumberOfColors=(int)_legendBands.Value;')

# Native scalar bar formatting is the circled visualization in the user screenshot.
$barText = '                _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");'
$barNew = @'
                _view.SetScalarBarNumberFormat(AsterMaxScalarBarFormat());
                _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");
'@
if($v.Contains($barText) -and -not $v.Contains('_view.SetScalarBarNumberFormat(AsterMaxScalarBarFormat())')){
    $v=$v.Replace($barText,$barNew.TrimEnd())
}
elseif(-not $v.Contains('_view.SetScalarBarNumberFormat(AsterMaxScalarBarFormat())')){ throw 'C10.28 scalar bar format anchor missing.' }

# Improve the detached/custom numeric legend too.
$legendFormatOld = 'g.DrawString(v.ToString("G6",System.Globalization.CultureInfo.InvariantCulture),f,Brushes.Black,x+w+8,yy-7);'
$legendFormatNew = 'g.DrawString(AsterMaxFormatLegendValue(v),f,Brushes.Black,x+w+8,yy-7);'
if($v.Contains($legendFormatOld)) {
    $v=$v.Replace($legendFormatOld,$legendFormatNew)
}

$legendClassAnchor = '        private sealed class AsterMaxLegendPanel : Control'
$legendHelper = @'
        private static string AsterMaxFormatLegendValue(double value)
        {
            double a=Math.Abs(value);
            if(a==0) return "0";
            if(a>=0.001 && a<1000000) return value.ToString("0.###",System.Globalization.CultureInfo.InvariantCulture);
            return value.ToString("0.###E+00",System.Globalization.CultureInfo.InvariantCulture);
        }

'@
if(-not $v.Contains('private static string AsterMaxFormatLegendValue(double value)')){
    if(-not $v.Contains($legendClassAnchor)){ throw 'C10.28 legend helper anchor missing.' }
    $v=$v.Replace($legendClassAnchor,$legendHelper+$legendClassAnchor)
}

foreach($token in @('_displayUnit','_numberFormat','_legendBands','ConvertScalarDisplay','SetScalarBarNumberFormat(AsterMaxScalarBarFormat())','AsterMaxDisplayFactor')){
    if(-not $v.Contains($token) -and $token -ne 'ConvertScalarDisplay'){ throw "C10.28 viewport token missing: $token" }
}
Set-Content $viewPath $v -Encoding UTF8

Write-Host 'C10.28: selectable result units + clean scalar-bar formatting + configurable contour bands applied.' -ForegroundColor Green
