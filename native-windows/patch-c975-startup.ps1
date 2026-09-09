param([string]$Root)
$ErrorActionPreference = 'Stop'
$mainPath=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$t=Get-Content $mainPath -Raw
$old=@'
            catch
            {
                // If no error the splash is closed latter
                splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
            }
'@
$new=@'
            catch (Exception ex)
            {
                string log = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "AsterMax-startup-error.txt");
                System.IO.File.WriteAllText(log, ex.ToString());
                AsterMaxSmokeTrace.Stage(_args, "startup_failed_" + ex.ToString());
                if (splash != null && splash.IsHandleCreated)
                    splash.BeginInvoke((MethodInvoker)delegate () { splash.Close(); });
                if (String.IsNullOrWhiteSpace(AsterMaxSmokeTrace.GetReportPath(_args)))
                    MessageBox.Show("AsterMax could not initialize.\n" + ex.Message + "\nDetails: " + log,
                                    "AsterMax Mechanical", MessageBoxButtons.OK, MessageBoxIcon.Error);
                Close();
                return;
            }
'@
if(-not $t.Contains($old)){throw 'Startup catch anchor missing'}
$t=$t.Replace($old,$new)
$t=$t.Replace('            // Set vtk control size', '            if (_controller == null || _modelTree == null || _vtk == null) return;' + [Environment]::NewLine + '            // Set vtk control size')
$t=$t.Replace('if (this.WindowState == FormWindowState.Minimized && _frmAnimation.Visible)', 'if (_frmAnimation != null && this.WindowState == FormWindowState.Minimized && _frmAnimation.Visible)')
Set-Content $mainPath $t -Encoding UTF8
