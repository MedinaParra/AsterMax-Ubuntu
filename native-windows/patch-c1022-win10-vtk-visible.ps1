param([string]$Root)
$ErrorActionPreference='Stop'

$main = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m = [regex]::Replace((Get-Content $main -Raw), "\r\n?", "`n")

# Upstream performs an off-screen warm-up and then hides VTK. Replace the first
# post-warm-up hide with a real visible, enabled viewport.
$hidePattern = '(?m)^(?<indent>\s*)_vtk\.Visible = false;'
$hide = [regex]::Match($m, $hidePattern)
if(-not $hide.Success) { throw 'C10.22 VTK post-warmup hide anchor missing.' }
$i = $hide.Groups['indent'].Value
$show = $i + '_vtk.Visible = true;' + "`n" +
        $i + '_vtk.Enabled = true;' + "`n" +
        $i + '_vtk.RenderingOn = true;' + "`n" +
        $i + 'UpdateVtkControlSize();' + "`n" +
        $i + '_vtk.BringToFront();' + "`n" +
        $i + '_vtk.Refresh();'
$m = [regex]::Replace($m, $hidePattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($x) $show }, 1)
Set-Content $main $m -Encoding UTF8

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

# The current UI chain already schedules a post-layout viewport pass. Strengthen that
# existing pass instead of depending on an older exact block.
$anchor = '                    UpdateVtkControlSize();'
$inject = @'
                    UpdateVtkControlSize();
                    _vtk.Enabled = true;
                    _vtk.Visible = true;
                    _vtk.RenderingOn = true;
'@
if(-not $u.Contains($anchor)) { throw 'C10.22 post-layout VTK size anchor missing.' }
$u = $u.Replace($anchor, $inject)

# Also make the workspace setup itself fail-open to the real VTK surface.
$back = '                _vtk.BackColor = Color.FromArgb(250, 250, 250);'
$backNew = @'
                _vtk.Enabled = true;
                _vtk.Visible = true;
                _vtk.RenderingOn = true;
                _vtk.BringToFront();
                _vtk.BackColor = Color.FromArgb(250, 250, 250);
'@
if(-not $u.Contains($back)) { throw 'C10.22 AsterMax viewport background anchor missing.' }
$u = $u.Replace($back, $backNew)
Set-Content $ui $u -Encoding UTF8

Write-Host 'C10.22: native VTK viewport forced visible and front-most after Windows UI startup.' -ForegroundColor Green
