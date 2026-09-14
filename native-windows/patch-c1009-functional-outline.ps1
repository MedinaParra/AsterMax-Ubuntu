param([string]$Root)
$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot 'ModelTree.AsterMaxOutline.cs'
Copy-Item $source (Join-Path $Root 'UserControls/ModelTree.AsterMaxOutline.cs') -Force
$project=Join-Path $Root 'UserControls/UserControls.csproj'
$p=Get-Content $project -Raw
$anchor='<Compile Include="ModelTree.cs">'
if(-not $p.Contains($anchor)){throw 'Native ModelTree project anchor missing.'}
$p=$p.Replace($anchor,'<Compile Include="ModelTree.AsterMaxOutline.cs" />'+[Environment]::NewLine+$anchor)
Set-Content $project $p -Encoding UTF8

$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $path -Raw
$anchor='                PolishNativeWorkspace();'
if(-not $u.Contains($anchor)){throw 'Native workspace anchor missing.'}
$u=$u.Replace($anchor,$anchor+@'

                // Explicit ownership and docking: the live ModelTree must occupy the left panel.
                splitContainer1.Panel1Collapsed = false;
                splitContainer1.Panel1.Padding = new Padding(0);
                if (_modelTree.Parent != splitContainer1.Panel1)
                    splitContainer1.Panel1.Controls.Add(_modelTree);
                _modelTree.Dock = DockStyle.Fill;
                _modelTree.Visible = true;
                _modelTree.EnableAsterMaxOutline();
                _modelTree.AsterMaxSolveRequested += RunAsterMaxNativeSolve;
                _modelTree.BringToFront();
                var outlineHeader = splitContainer1.Panel1.Controls["asterMaxOutlineHeader"];
                if (outlineHeader != null) outlineHeader.SendToBack();
                toolStripContainer1.TopToolStripPanelVisible = false;
                // WinForms docks in reverse z-order: Fill must be processed after Top/Bottom.
                toolStripContainer1.BringToFront();
                splitContainer1.Panel1.PerformLayout();
'@)
Set-Content $path $u -Encoding UTF8

# Native context-menu Run was still targeting the inherited job executable.
$main=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m=Get-Content $main -Raw
$old=@'
        private void RunAnalysis(string jobName)
        {
            RunAnalysis(jobName, false);
        }
'@
$new=@'
        private void RunAnalysis(string jobName)
        {
            RunAsterMaxNativeSolve();
        }
'@
if(-not $m.Contains($old)){throw 'Native RunAnalysis routing anchor missing.'}
$m=$m.Replace($old,$new)
Set-Content $main $m -Encoding UTF8

# Fail the portable admission when the actual imported body is absent from the visible outline.
$u=Get-Content $path -Raw
$anchor='                            smokeTimer.Stop();'
$gate=@'
                            string outlinePart = null;
                            foreach (var entry in geometry.Parts) { outlinePart = entry.Key; break; }
                            if (!_modelTree.AsterMaxOutlineHasGeometry(outlinePart))
                                throw new InvalidOperationException("Visible Outline does not contain the imported CAD body.");
                            var ribbon = Controls["asterMaxRibbon"];
                            if (ribbon == null || !ribbon.Visible || ribbon.Height < 70 ||
                                toolStripContainer1.Top < ribbon.Bottom)
                                throw new InvalidOperationException("Workspace overlaps the command ribbon.");
                            using (var bitmap = new Bitmap(Width, Height))
                            {
                                DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height));
                                bitmap.Save(reportPath + ".outline.png", System.Drawing.Imaging.ImageFormat.Png);
                            }
'@
if(-not $u.Contains($anchor)){throw 'Portable outline smoke anchor missing.'}
$u=$u.Replace($anchor,$gate+[Environment]::NewLine+$anchor)
$u=$u.Replace('"\"pass\":true," +','"\"pass\":true," + "\"visible_outline_contains_cad_body\":true," +')
$u=$u.Replace('CommandTile("Materials", "MODEL", () => tsmiModel.PerformClick()),',
    'CommandTile("Materials", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateMaterial_Click(null, EventArgs.Empty))),')
$u=$u.Replace('                InfoCard("Supports and loads remain connected to native scoping"),',@'
                CommandTile("Analysis Step", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateStep_Click(null, EventArgs.Empty))),
                CommandTile("Supports", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateBC_Click(null, EventArgs.Empty))),
                CommandTile("Loads", "MODEL", () => AsterMaxC1004MaterialAction(() => tsmiCreateLoad_Click(null, EventArgs.Empty))),
'@)
$u=$u.Replace('C10.08','C10.09')
Set-Content $path $u -Encoding UTF8
$globals=Join-Path $Root 'PrePoMax/Globals.cs'
$g=(Get-Content $globals -Raw).Replace('AsterMax Mechanical C10.08','AsterMax Mechanical C10.09')
Set-Content $globals $g -Encoding UTF8

# Drain stdout/stderr concurrently. Sequential ReadToEnd can deadlock on a full error pipe.
# Capability probes must begin their timeout before waiting for either redirected stream.
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $solve -Raw
$s=$s.Replace(@'
                string stdout=p.StandardOutput.ReadToEnd();
                string stderr=p.StandardError.ReadToEnd();
                p.WaitForExit();
'@,@'
                var stdoutTask=p.StandardOutput.ReadToEndAsync();
                var stderrTask=p.StandardError.ReadToEndAsync();
                p.WaitForExit();
                string stdout=stdoutTask.GetAwaiter().GetResult();
                string stderr=stderrTask.GetAwaiter().GetResult();
'@)
$s=$s.Replace(@'
                    string stdout=process.StandardOutput.ReadToEnd();
                    string stderr=process.StandardError.ReadToEnd();
'@,@'
                    var stdoutTask=process.StandardOutput.ReadToEndAsync();
                    var stderrTask=process.StandardError.ReadToEndAsync();
'@)
$s=$s.Replace('                    p["exit_code"]=process.ExitCode;',@'
                    string stdout=stdoutTask.GetAwaiter().GetResult();
                    string stderr=stderrTask.GetAwaiter().GetResult();
                    p["exit_code"]=process.ExitCode;
'@)
Set-Content $solve $s -Encoding UTF8
Write-Host 'C10.09 functional Outline and native Code_Aster Run routing applied.'
