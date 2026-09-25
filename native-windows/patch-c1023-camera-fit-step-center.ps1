param([string]$Root)
$ErrorActionPreference='Stop'

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

# C10.23: the custom ribbon must not proxy hidden ToolStrip buttons for camera control.
# Drive the live native VTK viewport directly and use non-animated camera changes so a
# stale animation state cannot swallow later view commands.
$replacements = [ordered]@{
    'CommandTile("Fit", "VIEW", () => tsbZoomToFit.PerformClick())' = 'CommandTile("Fit", "VIEW", AsterMaxFitView)'
    'CommandTile("Isometric", "VIEW", () => tsbIsometric.PerformClick())' = 'CommandTile("Isometric", "VIEW", AsterMaxIsometricView)'
    'CommandTile("Fit", "CAMERA", () => tsbZoomToFit.PerformClick())' = 'CommandTile("Fit", "CAMERA", AsterMaxFitView)'
    'CommandTile("Front", "CAMERA", () => tsbFrontView.PerformClick())' = 'CommandTile("Front", "CAMERA", AsterMaxFrontView)'
    'CommandTile("Top", "CAMERA", () => tsbTopView.PerformClick())' = 'CommandTile("Top", "CAMERA", AsterMaxTopView)'
    'CommandTile("Right", "CAMERA", () => tsbRightView.PerformClick())' = 'CommandTile("Right", "CAMERA", AsterMaxRightView)'
    'CommandTile("Isometric", "CAMERA", () => tsbIsometric.PerformClick())' = 'CommandTile("Isometric", "CAMERA", AsterMaxIsometricView)'
}
foreach($kv in $replacements.GetEnumerator()) {
    if(-not $u.Contains($kv.Key)) { throw "C10.23 camera button anchor missing: $($kv.Key)" }
    $u = $u.Replace($kv.Key,$kv.Value)
}

$anchor = '        private TabPage BuildRibbonPage(string name, Control[] controls)'
$helpers = @'
        private void AsterMaxPrepareCamera()
        {
            if (_vtk == null || _vtk.IsDisposed) return;
            UpdateVtkControlSize();
            _vtk.Enabled = true;
            _vtk.Visible = true;
            _vtk.RenderingOn = true;
            _vtk.BringToFront();
        }

        private void AsterMaxFitView()
        {
            AsterMaxPrepareCamera();
            if (_vtk == null || _vtk.IsDisposed) return;
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

        private void AsterMaxFrontView()
        {
            AsterMaxPrepareCamera();
            if (_vtk == null || _vtk.IsDisposed) return;
            _vtk.SetFrontBackView(false, true);
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

        private void AsterMaxTopView()
        {
            AsterMaxPrepareCamera();
            if (_vtk == null || _vtk.IsDisposed) return;
            _vtk.SetTopBottomView(false, true);
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

        private void AsterMaxRightView()
        {
            AsterMaxPrepareCamera();
            if (_vtk == null || _vtk.IsDisposed) return;
            _vtk.SetLeftRightView(false, false);
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

        private void AsterMaxIsometricView()
        {
            AsterMaxPrepareCamera();
            if (_vtk == null || _vtk.IsDisposed) return;
            _vtk.SetIsometricView(false, true);
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

        private void AsterMaxCenterImportedGeometry()
        {
            if (_controller == null || _vtk == null || _vtk.IsDisposed) return;
            _vtk.RenderingOn = true;
            _controller.Redraw();
            UpdateVtkControlSize();
            _vtk.Visible = true;
            _vtk.Enabled = true;
            _vtk.BringToFront();
            _vtk.SetIsometricView(false, true);
            _vtk.SetZoomToFit(false);
            _vtk.Refresh();
        }

'@
if(-not $u.Contains($anchor)) { throw 'C10.23 helper insertion anchor missing.' }
$u = $u.Replace($anchor,$helpers+$anchor)
Set-Content $ui $u -Encoding UTF8

$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m = [regex]::Replace((Get-Content $main -Raw), "\r\n?", "`n")

# Interactive Import Geometry / STEP: center after all imported files are actually present.
$interactiveOld = '                    SetFrontBackView(true, true);   // animate must be true in order for the scale bar to work correctly'
$interactiveNew = '                    AsterMaxCenterImportedGeometry();'
if(-not $m.Contains($interactiveOld)) { throw 'C10.23 interactive STEP camera anchor missing.' }
$m = $m.Replace($interactiveOld,$interactiveNew)

# Command-line / startup STEP import: center immediately after the asynchronous CAD import completes.
$startupOld = '                                await _controller.ImportFileAsync(fileName, false);'
$startupNew = $startupOld + "`n" + '                                AsterMaxCenterImportedGeometry();'
if(-not $m.Contains($startupOld)) { throw 'C10.23 startup STEP camera anchor missing.' }
$m = $m.Replace($startupOld,$startupNew)

Set-Content $main $m -Encoding UTF8
Write-Host 'C10.23: direct VTK camera commands + automatic STEP centering applied.' -ForegroundColor Green
