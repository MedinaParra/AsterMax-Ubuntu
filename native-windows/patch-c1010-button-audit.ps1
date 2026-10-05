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
$u=$u.Replace($anchor,'                            smokeTimer.Stop();'+[Environment]::NewLine+'                            AuditAsterMaxButtons(reportPath);'+[Environment]::NewLine+$anchor)
$u=$u.Replace('Height = 118,','Height = 132,').Replace('Height = 62,','Height = 74,')
$u=$u.Replace('C10.09','C10.10.1')
Set-Content $path $u -Encoding UTF8
$g=Join-Path $Root 'PrePoMax/Globals.cs'
Set-Content $g ((Get-Content $g -Raw).Replace('AsterMax Mechanical C10.09','AsterMax Mechanical C10.10.1')) -Encoding UTF8

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

                if (step.GetType() != typeof(StaticStep) || step.Nlgeom || !step.Active || !step.Valid)
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
$anchor='            JObject root = new JObject();'
if(-not $b.Contains($anchor)){throw 'Model feature validation anchor missing.'}
$b=$b.Replace($anchor,@'
            if (model.Constraints.Values.Any(x => x.Active) || model.ContactPairs.Values.Any(x => x.Active) ||
                model.InitialConditions.Values.Any(x => x.Active) ||
                model.StepCollection.StepsList.Any(s => s.DefinedFields.Values.Any(x => x.Active)))
                throw new NotSupportedException("Active contacts, constraints, initial conditions or defined fields are not supported by this Code_Aster bridge.");
            JObject root = new JObject();
'@)
$anchor='                return regionName;'
if(-not $b.Contains($anchor)){throw 'Node group validation anchor missing.'}
$b=$b.Replace($anchor,@'
                var set = model.Mesh.NodeSets[regionName];
                if (set.Labels == null || set.Labels.Length == 0 || set.Labels.Any(id => !model.Mesh.Nodes.ContainsKey(id)))
                    throw new InvalidOperationException("Node group is empty or contains missing mesh nodes: " + regionName);
                return regionName;
'@)
Set-Content $bridge $b -Encoding UTF8

# Use native part labels as well as element sets when checking material coverage.
$gatePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
$q=Get-Content $gatePath -Raw
$legacyAnchor='                    if (section.RegionType != CaeGlobals.RegionTypeEnum.ElementSetName ||'
$newAnchor='                    int[] regionElementIds = null;'
$start=$q.IndexOf($legacyAnchor)
if($start -ge 0) {
    $legacyLoop='                    foreach (int id in set.Labels)'
    $end=$q.IndexOf($legacyLoop, $start)
    if($end -lt 0){throw 'Material coverage legacy loop anchor missing.'}
    $replacement=@'
                    int[] regionElementIds = null;
                    if (section.RegionType == CaeGlobals.RegionTypeEnum.ElementSetName)
                    {
                        if (model.Mesh.ElementSets == null || String.IsNullOrWhiteSpace(section.RegionName) ||
                            !model.Mesh.ElementSets.ContainsKey(section.RegionName) ||
                            model.Mesh.ElementSets[section.RegionName] == null)
                        {
                            r.MissingSectionRegionCount++;
                            continue;
                        }
                        regionElementIds = model.Mesh.ElementSets[section.RegionName].Labels;
                    }
                    else if (section.RegionType == CaeGlobals.RegionTypeEnum.PartName)
                    {
                        if (model.Mesh.Parts == null || String.IsNullOrWhiteSpace(section.RegionName) ||
                            !model.Mesh.Parts.ContainsKey(section.RegionName) ||
                            model.Mesh.Parts[section.RegionName] == null)
                        {
                            r.MissingSectionRegionCount++;
                            continue;
                        }
                        regionElementIds = model.Mesh.Parts[section.RegionName].Labels;
                    }
                    else
                    {
                        r.MissingSectionRegionCount++;
                        continue;
                    }
                    if (regionElementIds == null || regionElementIds.Length == 0)
                    {
                        r.MissingSectionRegionCount++;
                        continue;
                    }
                    foreach (int id in regionElementIds)
'@
    $q=$q.Substring(0,$start)+$replacement+$q.Substring($end+$legacyLoop.Length)
} elseif($q.Contains($newAnchor) -and $q.Contains('CaeGlobals.RegionTypeEnum.PartName')) {
    Write-Host 'C10.10.1 material coverage gate already supports PartName regions.' -ForegroundColor DarkGray
} else {
    throw 'Material coverage region anchor/state not recognized.'
}
Set-Content $gatePath $q -Encoding UTF8

# Native export must enforce coverage instead of applying the only material to unassigned elements.
$exporter=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
$e=Get-Content $exporter -Raw
$anchor='            JObject contract=AsterMaxModelContractBridge.Build(model);'
if(-not $e.Contains($anchor)){throw 'Native exporter assignment validation anchor missing.'}
$e=$e.Replace($anchor,@'
            var assignment = AsterMaxAssignmentQualityGate.Evaluate(model);
            if (assignment.Status != "READY")
                throw new InvalidOperationException("Material assignment incomplete: " + String.Join("; ", assignment.Issues));
            if (model.Materials.Values.Any(m => !m.Active || !m.Valid))
                throw new InvalidOperationException("Material must be active and valid before export.");
            JObject contract=AsterMaxModelContractBridge.Build(model);
'@)
Set-Content $exporter $e -Encoding UTF8

# Add the bundled reference catalogue alongside existing/custom libraries.
$libraryForm=Join-Path $Root 'PrePoMax/Forms/31_Material/FrmMaterialLibrary.cs'
$l=Get-Content $libraryForm -Raw
$anchor='                LoadMaterialLibraryFromFile(fileName);'
if(-not $l.Contains($anchor)){throw 'Material library loader anchor missing.'}
$l=$l.Replace($anchor,$anchor+@'

                string referenceLibrary = Path.Combine(Application.StartupPath, "AsterMaxReferenceMaterials.lib");
                if (File.Exists(referenceLibrary)) LoadMaterialLibraryFromFile(referenceLibrary);
'@)
Set-Content $libraryForm $l -Encoding UTF8
Write-Host 'C10.10.1 native icons, accessible commands and live button audit applied.'
