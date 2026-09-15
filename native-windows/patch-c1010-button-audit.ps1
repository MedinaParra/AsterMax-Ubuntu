param([string]$Root)
$ErrorActionPreference='Stop'
Copy-Item (Join-Path $PSScriptRoot 'AsterMaxButtonAudit.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxButtonAudit.cs') -Force
Copy-Item (Join-Path $PSScriptRoot 'AsterMaxWorkflowStates.cs') (Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowStates.cs') -Force
$proj=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $proj -Raw
$anchor='<Compile Include="Forms\AsterMaxNativeUi.cs" />'
if(-not $p.Contains($anchor)){throw 'Native UI project anchor missing.'}
$p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxButtonAudit.cs" />')
$p=$p.Replace($anchor,$anchor+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxWorkflowStates.cs" />')
Set-Content $proj $p -Encoding UTF8
$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=Get-Content $path -Raw
$anchor='            b.Click += (s, e) => action();'
if(-not $u.Contains($anchor)){throw 'Command factory event anchor missing.'}
$u=$u.Replace($anchor,@'
            ConfigureAsterMaxButton(b, text, group, action);
            b.Click += (s, e) => InvokeAsterMaxCommand(text, action);
'@)
$anchor='            ribbon.TabPages.Add(BuildRibbonPage("View", new Control[] {'
if(-not $u.Contains($anchor)){throw 'View ribbon anchor missing.'}
$u=$u.Replace($anchor,$anchor+[Environment]::NewLine+'                CommandTile("Auditoria", "REPORT", () => OpenAsterMaxButtonAuditReport()),')
$u=$u.Replace('                _modelTree.EnableAsterMaxOutline();',@'
                _modelTree.AsterMaxSectionStates = BuildAsterMaxSectionStates;
                _modelTree.AsterMaxAnalysisTypeRequested += SelectAsterMaxAnalysisType;
                _modelTree.EnableAsterMaxOutline();
'@)
$u=$u.Replace('StateCard("Analysis", "Static Structural")','StateCard("Analysis", "Type Analysis")')
$anchor='                            string outlinePart = null;'
if(-not $u.Contains($anchor)){throw 'Portable smoke audit anchor missing.'}
$u=$u.Replace($anchor,'                            AuditAsterMaxButtons(reportPath);'+[Environment]::NewLine+$anchor)
$u=$u.Replace('Height = 118,','Height = 132,').Replace('Height = 62,','Height = 74,')
$u=$u.Replace('C10.09','C10.10')
Set-Content $path $u -Encoding UTF8
$g=Join-Path $Root 'PrePoMax/Globals.cs'
Set-Content $g ((Get-Content $g -Raw).Replace('AsterMax Mechanical C10.09','AsterMax Mechanical C10.10')) -Encoding UTF8

# The projection uses the original native image lists; no decorative status is invented.
$tree=Join-Path $Root 'UserControls/ModelTree.AsterMaxOutline.cs'
$t=Get-Content $tree -Raw
$t=$t.Replace('            tcGeometryModelResults.Visible = false;',@'
            _axOutline.ImageList = ilIcons;
            tcGeometryModelResults.Visible = false;
'@)
$anchor='                _axOutline.Nodes.Add(project);'
if(-not $t.Contains($anchor)){throw 'Outline root anchor missing.'}
$t=$t.Replace($anchor,$anchor+[Environment]::NewLine+'                AxApplyNativeIcons(_axOutline.Nodes);')
$method=@'
        private void AxApplyNativeIcons(TreeNodeCollection nodes)
        {
            foreach (TreeNode node in nodes) {
                TreeNode source = node.Tag as TreeNode;
                string key = source == null ? "" : source.StateImageKey;
                if (!ilIcons.Images.ContainsKey(key) && ilIcons.Images.ContainsKey(key + ".ico")) key += ".ico";
                if (!ilIcons.Images.ContainsKey(key)) {
                    switch (node.Name) {
                        case "ax-project": case "ax-model": case "ax-coordinates": case "ax-global": key="Geometry.ico"; break;
                        case "ax-connections": key="Contact.ico"; break;
                        case "ax-mesh": key="Mesh.ico"; break;
                        case "ax-selections": key="Node_set.ico"; break;
                        case "ax-analysis": key="Step.ico"; break;
                        case "ax-solution": key="Field_output.ico"; break;
                        default:
                            key = source != null && source.Parent == _geomParts ? "GeomPart.ico" : "BasePart.ico";
                            break;
                    }
                }
                node.ImageKey=key; node.SelectedImageKey=key;
                AxApplyNativeIcons(node.Nodes);
            }
        }

'@
$anchor='        public bool AsterMaxOutlineHasGeometry(string partName)'
if(-not $t.Contains($anchor)){throw 'Outline icon method anchor missing.'}
$t=$t.Replace($anchor,$method+$anchor)
Set-Content $tree $t -Encoding UTF8

$bridge=Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
$b=Get-Content $bridge -Raw
$anchor='                if (step is InitialStep) continue;'
if(-not $b.Contains($anchor)){throw 'Study type validation anchor missing.'}
$b=$b.Replace($anchor,$anchor+@'

                if (!(step is StaticStep) || step.Nlgeom || !step.Active)
                    throw new NotSupportedException("Code_Aster bridge currently supports one active linear static study only. Selected: " + step.GetType().Name);
'@)
$b=$b.Replace('                    FixedBC fixedBc = bcEntry.Value as FixedBC;',@'
                    if (!bcEntry.Value.Active || !bcEntry.Value.Valid)
                        throw new NotSupportedException("Inactive or invalid support: " + bcEntry.Key);
                    FixedBC fixedBc = bcEntry.Value as FixedBC;
'@)
$b=$b.Replace('                    CLoad cload = loadEntry.Value as CLoad;',@'
                    if (!loadEntry.Value.Active || !loadEntry.Value.Valid)
                        throw new NotSupportedException("Inactive or invalid load: " + loadEntry.Key);
                    CLoad cload = loadEntry.Value as CLoad;
'@)
Set-Content $bridge $b -Encoding UTF8
Write-Host 'C10.10 native icons, accessible commands and live button audit applied.'
