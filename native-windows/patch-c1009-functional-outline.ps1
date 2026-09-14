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
                if (outlineHeader != null) outlineHeader.BringToFront();
                toolStripContainer1.TopToolStripPanelVisible = false;
                toolStripContainer1.SendToBack();
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
                            using (var bitmap = new Bitmap(Width, Height))
                            {
                                DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height));
                                bitmap.Save(reportPath + ".outline.png", System.Drawing.Imaging.ImageFormat.Png);
                            }
'@
if(-not $u.Contains($anchor)){throw 'Portable outline smoke anchor missing.'}
$u=$u.Replace($anchor,$gate+[Environment]::NewLine+$anchor)
$u=$u.Replace('"\"pass\":true," +','"\"pass\":true," + "\"visible_outline_contains_cad_body\":true," +')
Set-Content $path $u -Encoding UTF8
Write-Host 'C10.09 functional Outline and native Code_Aster Run routing applied.'
