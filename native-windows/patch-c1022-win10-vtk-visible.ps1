param([string]$Root)
$ErrorActionPreference='Stop'

$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m = [regex]::Replace((Get-Content $main -Raw), "\r\n?", "`n")

# PrePoMax performs an off-screen warm-up render during FrmMain_Shown.  The upstream
# code hides the VTK control after that warm-up.  In the AsterMax chrome this can leave
# the placeholder/panelControl visible above an otherwise initialized renderer.
$warmPattern = '(?m)^(?<indent>\s*)_vtk\.Left -= _vtk\.Width;\s*\n\k<indent>_vtk\.Visible = false;'
$warmMatch = [regex]::Match($m, $warmPattern)
if(-not $warmMatch.Success) { throw 'C10.22 VTK warm-up visibility anchor missing.' }
$i = $warmMatch.Groups['indent'].Value
$warmNew = $i + '_vtk.Left -= _vtk.Width;' + "`n" +
           $i + '_vtk.Visible = true;' + "`n" +
           $i + '_vtk.Enabled = true;' + "`n" +
           $i + '_vtk.BringToFront();' + "`n" +
           $i + 'UpdateVtkControlSize();' + "`n" +
           $i + '_vtk.RenderingOn = true;' + "`n" +
           $i + '_vtk.Refresh();'
$m = [regex]::Replace($m, $warmPattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($x) $warmNew }, 1)
Set-Content $main $m -Encoding UTF8

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

# Re-assert the real native VTK viewport after the custom ribbon/workspace modifies
# docking and Z-order.  This is intentionally presentation-only.
$old = @'
            if (_vtk != null)
            {
                _vtk.BackColor = Color.FromArgb(250, 250, 250);
'@
$new = @'
            if (_vtk != null)
            {
                UpdateVtkControlSize();
                _vtk.Enabled = true;
                _vtk.Visible = true;
                _vtk.RenderingOn = true;
                _vtk.BringToFront();
                _vtk.BackColor = Color.FromArgb(250, 250, 250);
'@
if(-not $u.Contains($old)) { throw 'C10.22 AsterMax viewport anchor missing.' }
$u = $u.Replace($old,$new)

# The native workspace must remain above the title/ribbon sibling choreography.
$layoutOld = @'
                ResumeLayout(true);
                PerformLayout();
'@
$layoutNew = @'
                ResumeLayout(true);
                PerformLayout();
                if (_vtk != null)
                {
                    UpdateVtkControlSize();
                    _vtk.Enabled = true;
                    _vtk.Visible = true;
                    _vtk.RenderingOn = true;
                    _vtk.BringToFront();
                    _vtk.Refresh();
                }
'@
if(-not $u.Contains($layoutOld)) { throw 'C10.22 ApplyAsterMaxNativeUi final layout anchor missing.' }
$u = $u.Replace($layoutOld,$layoutNew)
Set-Content $ui $u -Encoding UTF8

Write-Host 'C10.22: native VTK viewport forced visible and front-most after Windows UI startup.' -ForegroundColor Green
