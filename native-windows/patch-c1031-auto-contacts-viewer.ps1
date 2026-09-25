param([string]$Root)
$ErrorActionPreference='Stop'

$outlinePath = Join-Path $Root 'UserControls/ModelTree.AsterMaxOutline.cs'
$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$vtkPath = Join-Path $Root 'vtkControl/vtkControl.cs'
$integratedPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxIntegratedResults.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
foreach($p in @($outlinePath,$controllerPath,$vtkPath,$integratedPath,$uiPath,$mainPath)){ if(!(Test-Path $p)){ throw "C10.31 missing: $p" } }

# ----------------------------------------------------------------------
# 1. Projected Outline emits a dedicated contact-pair selection event.
# ----------------------------------------------------------------------
$o=[regex]::Replace((Get-Content $outlinePath -Raw),"\r\n?","`n")
$eventAnchor='        public event Action AsterMaxModelTreeChanged;'
if(-not $o.Contains('AsterMaxContactPairSelected')){
  if(-not $o.Contains($eventAnchor)){ throw 'C10.31 outline event anchor missing.' }
  $o=$o.Replace($eventAnchor,$eventAnchor+"`n        public event Action<string> AsterMaxContactPairSelected;")
}
$afterAnchor='                AsterMaxModelViewRequested?.Invoke();'+"`n"+'                SelectAsterMaxSource(e.Node);'
$afterNew=@'
                var sourceNode=e.Node.Tag as TreeNode;
                var cp=sourceNode==null ? null : sourceNode.Tag as CaeModel.ContactPair;
                if(cp!=null) {
                    AsterMaxContactPairSelected?.Invoke(cp.Name);
                    return;
                }
                AsterMaxModelViewRequested?.Invoke();
                SelectAsterMaxSource(e.Node);
'@
if(-not $o.Contains('AsterMaxContactPairSelected?.Invoke(cp.Name)')){
  if(-not $o.Contains($afterAnchor)){ throw 'C10.31 outline AfterSelect anchor missing.' }
  $o=$o.Replace($afterAnchor,$afterNew.TrimEnd())
}
Set-Content $outlinePath $o -Encoding UTF8

# ----------------------------------------------------------------------
# 2. Native contact-pair highlight: master red, slave blue.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$old='                    DrawContactPair(contactPair, Color.Red, Color.Red, vtkRendererLayer.Selection, false);'
$new='                    DrawContactPair(contactPair, contactPair.MasterColor, contactPair.SlaveColor, vtkRendererLayer.Selection, false);'
if(-not $c.Contains($new)){
  if(-not $c.Contains($old)){ throw 'C10.31 HighlightContactPairs color anchor missing.' }
  $c=$c.Replace($old,$new)
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# 3. VTK display-only opacity control for contact inspection.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$renderAnchor='        // Render'+"`n"+'        private void RenderSceene()'
$vtkHelper=@'
        public void SetAllActorOpacity(double opacity)
        {
            if (opacity < 0) opacity = 0;
            if (opacity > 1) opacity = 1;
            foreach (var entry in _actors)
            {
                if (entry.Value != null && entry.Value.GeometryProperty != null)
                    entry.Value.GeometryProperty.SetOpacity(opacity);
            }
            RenderSceene();
        }

'@
if(-not $v.Contains('public void SetAllActorOpacity(double opacity)')){
  if(-not $v.Contains($renderAnchor)){ throw 'C10.31 vtk opacity anchor missing.' }
  $v=$v.Replace('        // Render'+"`n",$vtkHelper+'        // Render'+"`n")
}
Set-Content $vtkPath $v -Encoding UTF8

# ----------------------------------------------------------------------
# 4. Contact inspection mode: transparent geometry, no mesh edges,
#    red master, blue slave, and automatic exit on normal model view.
# ----------------------------------------------------------------------
$i=[regex]::Replace((Get-Content $integratedPath -Raw),"\r\n?","`n")
$fieldAnchor='        private bool _axRefreshingResults;'
$fieldNew=@'
        private bool _axRefreshingResults;
        private bool _axContactInspectMode;
        private vtkControl.vtkEdgesVisibility _axContactPreviousEdges;
'@
if(-not $i.Contains('_axContactInspectMode')){
  if(-not $i.Contains($fieldAnchor)){ throw 'C10.31 contact inspector field anchor missing.' }
  $i=$i.Replace($fieldAnchor,$fieldNew.TrimEnd())
}

$initAnchor='            _modelTree.AsterMaxModelTreeChanged += RefreshAsterMaxResultAvailability;'
if(-not $i.Contains('AsterMaxContactPairSelected += ShowAsterMaxContactPair')){
  if(-not $i.Contains($initAnchor)){ throw 'C10.31 integrated-results subscription anchor missing.' }
  $i=$i.Replace($initAnchor,$initAnchor+"`n            _modelTree.AsterMaxContactPairSelected += ShowAsterMaxContactPair;")
}

$modelWorkspaceAnchor='        private void ShowAsterMaxModelWorkspace()'+"`n"+'        {'
if(-not $i.Contains('AsterMaxExitContactInspection();')){
  if(-not $i.Contains($modelWorkspaceAnchor)){ throw 'C10.31 model workspace anchor missing.' }
  $i=$i.Replace($modelWorkspaceAnchor,$modelWorkspaceAnchor+"`n            AsterMaxExitContactInspection();")
}

$disposeAnchor='        private void DisposeAsterMaxResultView()'
$contactMethods=@'
        private void ShowAsterMaxContactPair(string contactPairName)
        {
            if (_controller == null || _vtk == null || String.IsNullOrWhiteSpace(contactPairName)) return;

            if (_axEmbeddedResults != null && !_axEmbeddedResults.IsDisposed) _axEmbeddedResults.Hide();
            if (_axResultDetailsHost != null) _axResultDetailsHost.Hide();
            if (_axSolutionInformation != null) _axSolutionInformation.Hide();
            if (panelControl != null && !panelControl.IsDisposed) panelControl.Show();

            var cp=_controller.GetContactPair(contactPairName);
            if(cp==null) return;

            cp.MasterColor=Color.Red;
            cp.SlaveColor=Color.RoyalBlue;

            if(!_axContactInspectMode)
            {
                _axContactPreviousEdges=_vtk.EdgesVisibility;
                _axContactInspectMode=true;
            }

            _modelTree.SetGeometryTab();
            ModelTree_ViewEvent(ViewType.Geometry);
            _controller.DrawGeometry(false);

            _vtk.SetAllActorOpacity(0.18);
            _vtk.EdgesVisibility=vtkControl.vtkEdgesVisibility.NoEdges;
            _controller.ClearSelectionHistory();
            _controller.HighlightContactPairs(new[]{contactPairName});
            _vtk.SetZoomToFit(false);
        }

        private void AsterMaxExitContactInspection()
        {
            if(!_axContactInspectMode || _vtk==null || _vtk.IsDisposed) return;
            _axContactInspectMode=false;
            _vtk.SetAllActorOpacity(1.0);
            _vtk.EdgesVisibility=_axContactPreviousEdges;
            if(_controller!=null) _controller.ClearSelectionHistory();
        }

'@
if(-not $i.Contains('private void ShowAsterMaxContactPair(string contactPairName)')){
  if(-not $i.Contains($disposeAnchor)){ throw 'C10.31 contact method insertion anchor missing.' }
  $i=$i.Replace($disposeAnchor,$contactMethods+$disposeAnchor)
}
Set-Content $integratedPath $i -Encoding UTF8

# ----------------------------------------------------------------------
# 5. Automatic contact generation after successful multi-part meshing.
#    Uses the real PrePoMax ContactSearch and AutoCreateContactPairs path.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$helperAnchor='        private static void AsterMaxEnableChromeBuffering(Control control)'
$autoHelper=@'
        private void AsterMaxAutoGenerateContacts()
        {
            if (_controller == null || _controller.Model == null || _controller.Model.Mesh == null) return;
            if (_controller.Model.Mesh.Parts == null || _controller.Model.Mesh.Parts.Count < 2) return;
            if (_controller.GetContactPairNames().Length > 0) return;

            string interactionName;
            string[] interactionNames=_controller.GetSurfaceInteractionNames();
            if(interactionNames.Length==0)
            {
                interactionName="AsterMax Auto Contact";
                var interaction=new CaeModel.SurfaceInteraction(interactionName);
                interaction.AddProperty(new CaeModel.SurfaceBehavior());
                _controller.AddSurfaceInteractionCommand(interaction);
            }
            else interactionName=interactionNames[0];

            double maxDiagonal=0;
            foreach(var entry in _controller.Model.Mesh.Parts)
                if(entry.Value!=null && entry.Value.BoundingBox!=null)
                    maxDiagonal=Math.Max(maxDiagonal,entry.Value.BoundingBox.GetDiagonal());
            if(!(maxDiagonal>0)) return;

            double distance=Math.Max(maxDiagonal*0.001,1e-9);
            var search=new CaeMesh.ContactSearch(_controller.Model.Mesh,_controller.Model.Geometry);
            search.GroupContactPairsBy=CaeMesh.GroupContactPairsByEnum.ByParts;
            var filter=CaeMesh.ContactSearchNamespace.GeometryFilterEnum.Solid |
                       CaeMesh.ContactSearchNamespace.GeometryFilterEnum.Shell |
                       CaeMesh.ContactSearchNamespace.GeometryFilterEnum.ShellEdge;
            var items=search.FindContactPairs(distance,35.0,filter,false);
            if(items==null || items.Count==0)
            {
                tsslState.Text="Auto-contactos: no se detectaron superficies dentro de la tolerancia.";
                return;
            }

            // FrmSearchContactPairs is created during FrmMain initialization, so its
            // native method-name table is already initialized here.
            var pairs=new List<Forms.SearchContactPair>();
            foreach(var item in items)
            {
                var p=new Forms.SearchContactPair(item.Name,false,distance);
                p.Type=Forms.SearchContactPairType.Contact;
                p.SurfaceInteractionName=interactionName;
                p.ContactPairMethod=Forms.FrmSearchContactPairs.ContactPairMethodNames[1];
                p.MasterSlaveItem=item;
                pairs.Add(p);
            }

            var before=new HashSet<string>(_controller.GetContactPairNames());
            _controller.AutoCreateContactPairs(pairs);
            int created=0;
            foreach(string name in _controller.GetContactPairNames())
            {
                if(before.Contains(name)) continue;
                var cp=_controller.GetContactPair(name);
                cp.MasterColor=Color.Red;
                cp.SlaveColor=Color.RoyalBlue;
                created++;
            }
            tsslState.Text="Auto-contactos: "+created+" par(es) creados. Seleccione uno para inspeccionarlo.";
        }

'@
if(-not $u.Contains('private void AsterMaxAutoGenerateContacts()')){
  if(-not $u.Contains($helperAnchor)){ throw 'C10.31 auto-contact helper anchor missing.' }
  $u=$u.Replace($helperAnchor,$autoHelper+$helperAnchor)
}

# Add an explicit Ribbon command as well as the automatic post-mesh path.
$connInfo='                InfoCard("Contactos y restricciones usan el árbol nativo y el scoping real"),'
$connNew=@'
                CommandTile("Auto contactos", "CONEXIONES", AsterMaxAutoGenerateContacts, true),
                InfoCard("Detección automática por proximidad • rojo master • azul slave"),
'@
if(-not $u.Contains('CommandTile("Auto contactos"')){
  if(-not $u.Contains($connInfo)){ throw 'C10.31 Connections ribbon anchor missing.' }
  $u=$u.Replace($connInfo,$connNew.TrimEnd())
}
Set-Content $uiPath $u -Encoding UTF8

# Automatic run after successful multi-part mesh, only when no contacts already exist.
$m=[regex]::Replace((Get-Content $mainPath -Raw),"\r\n?","`n")
$meshAnchor='                _controller.UpdateExplodedView(true);'
$meshNew=@'
                _controller.UpdateExplodedView(true);
                if(errors.Count==0 && partNames.Length>1 && _controller.GetContactPairNames().Length==0)
                    BeginInvoke(new Action(AsterMaxAutoGenerateContacts));
'@
if(-not $m.Contains('BeginInvoke(new Action(AsterMaxAutoGenerateContacts))')){
  if(-not $m.Contains($meshAnchor)){ throw 'C10.31 post-mesh auto-contact anchor missing.' }
  $m=$m.Replace($meshAnchor,$meshNew.TrimEnd())
}
Set-Content $mainPath $m -Encoding UTF8

Write-Host 'C10.31: automatic contact pairs + red/blue transparent geometry contact viewer applied.' -ForegroundColor Green
