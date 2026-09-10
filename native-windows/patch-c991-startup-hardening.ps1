param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-InFile([string]$Path,[string]$Old,[string]$New){
  $p=Join-Path $Root $Path
  $t=Get-Content $p -Raw
  if(-not $t.Contains($Old)){ throw "Anchor not found: $Path :: $Old" }
  $t=$t.Replace($Old,$New)
  Set-Content $p $t -Encoding UTF8
}

$path='PrePoMax/Forms/FrmMain.cs'

# Upstream FrmMain_Load swallows initialization exceptions. Preserve the original flow but surface the root cause
# and prevent FrmMain_Shown from dereferencing a partially initialized Controller/VTK state.
Replace-InFile $path @'
            catch
            {
                // If no error the splash is closed latter
                splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
            }
'@ @'
            catch (Exception ex)
            {
                // AsterMax: never silently continue with a partially initialized native workspace.
                try
                {
                    if (splash != null && !splash.IsDisposed && splash.IsHandleCreated)
                        splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
                }
                catch { }
                MessageBoxes.ShowError("AsterMax startup initialization failed." + Environment.NewLine + Environment.NewLine + ex.ToString());
            }
'@

Replace-InFile $path @'
        private void FrmMain_Shown(object sender, EventArgs e)
        {
            // Set vtk control size
            UpdateVtkControlSize();
            //
            _vtk.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom;
'@ @'
        private void FrmMain_Shown(object sender, EventArgs e)
        {
            // AsterMax startup gate: FrmMain_Load may have failed before Controller/VTK initialization.
            if (_controller == null || _vtk == null)
            {
                MessageBoxes.ShowError("AsterMax Mechanical could not initialize the native workspace. Controller or VTK is unavailable. Restart the application and report the startup initialization message shown before this one.");
                return;
            }
            // Set vtk control size
            UpdateVtkControlSize();
            //
            _vtk.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Bottom;
'@

# Protect the first dereference inside the delayed async Shown callback. Settings should normally be present,
# but a missing/corrupt settings state must not crash the whole GUI.
Replace-InFile $path @'
                // Set form size
                _controller.Settings.General.ApplyFormSize(this);
                // Vtk
'@ @'
                // Set form size
                if (_controller.Settings != null && _controller.Settings.General != null)
                    _controller.Settings.General.ApplyFormSize(this);
                // Vtk
'@

# Splash is auxiliary UI. A failed/closed splash must never kill the main application.
Replace-InFile $path @'
                // Close splash 
                splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
'@ @'
                // Close splash
                try
                {
                    if (splash != null && !splash.IsDisposed && splash.IsHandleCreated)
                        splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
                }
                catch { }
'@

Write-Host 'C9.91 startup hardening applied.'
