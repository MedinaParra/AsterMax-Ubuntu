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

# Trace delayed startup; native WinForms exceptions must not be hidden behind modal dialogs in CI.
$t=Get-Content $mainPath -Raw
foreach($anchor in @('_controller.Settings.General.ApplyFormSize(this);','_controller.Redraw();','_vtk.SetZoomFactor(1000);','if (File.Exists(fileName))','if (New(ModelSpaceEnum.ThreeD, unitSystemType))','await _controller.ImportFileAsync(fileName, false);')){
 if(-not $t.Contains($anchor)){throw "Startup trace anchor missing: $anchor"}
 $t=$t.Replace($anchor, 'AsterMaxSmokeTrace.Stage(_args, "before_' + $anchor.Replace('"','').Replace(';','') + '");' + [Environment]::NewLine + $anchor)
}
$t=$t.Replace('                    ExceptionTools.Show(this, ex);', '                    AsterMaxSmokeTrace.Stage(_args, "import_exception_" + ex.ToString());' + [Environment]::NewLine + '                    ExceptionTools.Show(this, ex);')
Set-Content $mainPath $t -Encoding UTF8
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$ui=Get-Content $uiPath -Raw
$anchor='                    AsterMaxSmokeTrace.Stage(_args, "smoke_timer_timeout");'
$replacement=@'
                    AsterMaxSmokeTrace.Stage(_args, "smoke_timer_timeout");
                    try {
                        var rect = Screen.PrimaryScreen.Bounds;
                        using (var bitmap = new System.Drawing.Bitmap(rect.Width, rect.Height))
                        using (var graphics = System.Drawing.Graphics.FromImage(bitmap)) {
                            graphics.CopyFromScreen(rect.Location, System.Drawing.Point.Empty, rect.Size);
                            bitmap.Save(reportPath + ".png", System.Drawing.Imaging.ImageFormat.Png);
                        }
                        foreach (Form form in Application.OpenForms)
                            AsterMaxSmokeTrace.Stage(_args, "open_form_" + form.Name + "_" + form.Text);
                    } catch (Exception captureError) {
                        AsterMaxSmokeTrace.Stage(_args, "capture_error_" + captureError.Message);
                    }
'@
if(-not $ui.Contains($anchor)){throw 'Smoke timeout anchor missing'}
Set-Content $uiPath ($ui.Replace($anchor,$replacement)) -Encoding UTF8

# CAD and meshing need a writable scratch directory even without a legacy solver installation.
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$c=Get-Content $controllerPath -Raw
$anchor='            _settings.LoadFromFile();'
$replacement=@'
            _settings.LoadFromFile();
            if (String.IsNullOrWhiteSpace(_settings.Calculix.WorkDirectory) ||
                !System.IO.Directory.Exists(_settings.Calculix.WorkDirectory))
            {
                string cadWorkDirectory = System.IO.Path.Combine(
                    System.Environment.GetFolderPath(System.Environment.SpecialFolder.LocalApplicationData),
                    "AsterMax", "CAD", System.Diagnostics.Process.GetCurrentProcess().Id.ToString());
                System.IO.Directory.CreateDirectory(cadWorkDirectory);
                _settings.Calculix.WorkDirectory = cadWorkDirectory;
            }
'@
if(-not $c.Contains($anchor)){throw 'Controller settings initialization anchor missing'}
Set-Content $controllerPath ($c.Replace($anchor,$replacement)) -Encoding UTF8

# Extend the same runtime test through real NetGen volume meshing.
$ui=Get-Content $uiPath -Raw
$ui=$ui.Replace('            int ticks = 0;', '            int ticks = 0;' + [Environment]::NewLine + '            System.Threading.Tasks.Task<bool> meshTask = null;')
$anchor='                            smokeTimer.Stop();'
$first=$ui.IndexOf($anchor)
if($first -lt 0){throw 'Geometry gate anchor missing'}
$mesh=@'
                            if (meshTask == null) {
                                string partName = null;
                                foreach (var entry in geometry.Parts) { partName = entry.Key; break; }
                                AsterMaxSmokeTrace.Stage(_args, "volume_mesh_started");
                                meshTask = System.Threading.Tasks.Task.Run(() => _controller.CreateMesh(partName));
                                return;
                            }
                            if (!meshTask.IsCompleted) return;
                            if (!meshTask.GetAwaiter().GetResult()) throw new Exception("NetGen volume mesh failed");
                            if (_controller.Model.Mesh == null || _controller.Model.Mesh.Elements.Count == 0)
                                throw new Exception("NetGen returned no volume elements");
                            AsterMaxSmokeTrace.Stage(_args, "volume_mesh_completed");
'@
$ui=$ui.Insert($first,$mesh+[Environment]::NewLine)
$anchor='                                "\"geometry_parts\":" + parts + "," +'
$replacement=@'
                                "\"mesh_nodes\":" + _controller.Model.Mesh.Nodes.Count + "," +
                                "\"mesh_elements\":" + _controller.Model.Mesh.Elements.Count + "," +
                                "\"geometry_parts\":" + parts + "," +
'@
if(-not $ui.Contains($anchor)){throw 'Geometry JSON anchor missing'}
$ui=$ui.Replace($anchor,$replacement)
$anchor='                            System.IO.File.WriteAllText(reportPath, json);'
$replacement=@'
                            _controller.Redraw();
                            tsbZoomToFit_Click(null, EventArgs.Empty);
                            Refresh();
                            try {
                                var rect = Bounds;
                                using (var bitmap = new System.Drawing.Bitmap(rect.Width, rect.Height))
                                using (var graphics = System.Drawing.Graphics.FromImage(bitmap)) {
                                    graphics.CopyFromScreen(rect.Location, System.Drawing.Point.Empty, rect.Size);
                                    bitmap.Save(reportPath + ".png", System.Drawing.Imaging.ImageFormat.Png);
                                }
                            } catch (Exception captureError) {
                                AsterMaxSmokeTrace.Stage(_args, "capture_error_" + captureError.Message);
                            }
                            System.IO.File.WriteAllText(reportPath, json);
'@
$ui=$ui.Replace($anchor,$replacement)
Set-Content $uiPath $ui -Encoding UTF8
