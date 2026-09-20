param([string]$Root)
$ErrorActionPreference='Stop'
function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){throw "C10.18 anchor missing: $Old"}
    return $Text.Replace($Old,$New)
}
$project=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$p=Get-Content $project -Raw
$p=Replace-Required $p '<Compile Include="Forms\AsterMaxNativeUi.cs" />' ('<Compile Include="Forms\AsterMaxIntegratedResults.cs" />'+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxIntegratedResultsAudit.cs" />'+[Environment]::NewLine+'    <Compile Include="Forms\AsterMaxNativeUi.cs" />')
Set-Content $project $p -Encoding UTF8
foreach($name in @('AsterMaxIntegratedResults.cs','AsterMaxIntegratedResultsAudit.cs')) {
    Copy-Item (Join-Path $PSScriptRoot $name) (Join-Path $Root "PrePoMax/Forms/$name") -Force
}

$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$s=Get-Content $path -Raw
$s=Replace-Required $s '                _modelTree.EnableAsterMaxOutline();' ('                InitializeAsterMaxIntegratedResults();'+[Environment]::NewLine+'                _modelTree.EnableAsterMaxOutline();')
$s=Replace-Required $s '                StartAsterMaxPortableCadSmoke();' ('                StartAsterMaxPortableCadSmoke();'+[Environment]::NewLine+'                StartAsterMaxIntegratedAudit();')
Set-Content $path $s -Encoding UTF8

$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxButtonAudit.cs'
$s=Get-Content $path -Raw
$s=Replace-Required $s '            try { action(); }' '            try { if (!RouteAsterMaxIntegratedCommand(caption)) action(); RefreshAsterMaxResultAvailability(); }'
$s=Replace-Required $s '                tsslState.Text = "Command failed: " + caption;' ('                if(_asterMaxUiAuditMode) throw;'+[Environment]::NewLine+'                tsslState.Text = "Command failed: " + caption;')
Set-Content $path $s -Encoding UTF8

$path=Join-Path $Root 'PrePoMax/Forms/AsterMaxVtkResultsBinding.cs'
$s=Get-Content $path -Raw
$s=Replace-Required $s 'internal sealed class AsterMaxResultsViewportForm : Form' 'internal sealed partial class AsterMaxResultsViewportForm : Form'
$s=Replace-Required $s '_field.SelectedIndexChanged+=delegate { RefreshMetadata(); };' '_field.SelectedIndexChanged+=delegate { RenderScene(); ResultFieldChanged?.Invoke(SelectedResultField); };'
$s=Replace-Required $s '_scale.ValueChanged+=delegate { RefreshMetadata(); };' '_scale.ValueChanged+=delegate { RenderScene(); };'
$s=Replace-Required $s '            Shown+=delegate { RenderScene(); };' @'
            _rangeMin.ValueChanged+=delegate { if(!_autoRange.Checked) RenderScene(); };
            _rangeMax.ValueChanged+=delegate { if(!_autoRange.Checked) RenderScene(); };
            Shown+=delegate { RenderScene(); };
'@
$renderStart=@'
        private void RenderScene()
        {
            try
            {
                RefreshMetadata();
'@
$s=Replace-Required $s $renderStart @'
        private void RenderScene()
        {
            string renderStage="preflight";
            if(_axRendering) {
                // The active render owns completion status; nested UI events must not overwrite it.
                return;
            }
            if(!IsHandleCreated || !Visible) {
                LastRenderError=null;
                LastRenderSkipped=true;
                LastRenderSkipReason=!IsHandleCreated?"window handle is not created":"viewport is not visible";
                return;
            }
            _axRendering=true;
            LastRenderError=null;
            LastRenderSkipped=false;
            LastRenderSkipReason=null;
            try
            {
                renderStage="validate-model";
                ValidateModel?.Invoke();
                renderStage="refresh-metadata";
                RefreshMetadata();
'@
$old=@'
                if(_view!=null)
                {
                    _view.OnMouseLeftButtonUpSelection-=OnNativeVtkSelection;
                    _host.Controls.Remove(_view); _view.Dispose(); _view=null;
                }
                _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
                _host.Controls.Add(_view);
'@
$s=Replace-Required $s $old @'
                bool firstRender=_view==null;
                if(firstRender) {
                    renderStage="vtk-create";
                    bool vtkLoadCompleted=false;
                    _view=new vtkControl.vtkControl { Dock=DockStyle.Fill };
                    _view.Load+=delegate { vtkLoadCompleted=true; };
                    _host.Controls.Add(_view);
                    renderStage="vtk-load";
                    _view.Show();
                    _view.CreateControl();
                    Application.DoEvents();
                    if(!_view.IsHandleCreated || !vtkLoadCompleted)
                        throw new InvalidOperationException("vtkControl did not complete its WinForms Load lifecycle before renderer access.");
                } else {
                    renderStage="vtk-clear";
                    _view.OnMouseLeftButtonUpSelection-=OnNativeVtkSelection;
                    _view.Clear();
                }
'@
$s=Replace-Required $s '                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);' ('                renderStage="build-actor-data";'+[Environment]::NewLine+'                var data=AsterMaxVtkResultsBinding.BuildActorData(_bundle,_scene);')
$s=Replace-Required $s '                _view.SetScalarBarColorSpectrum(CreateDisplaySpectrum(colorContract));' ('                renderStage="scalar-spectrum";'+[Environment]::NewLine+'                _view.SetScalarBarColorSpectrum(CreateDisplaySpectrum(colorContract));')
$s=Replace-Required $s '                _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");' ('                renderStage="scalar-bar-text";'+[Environment]::NewLine+'                _view.SetScalarBarText(colorContract.Field,"",colorContract.Unit,"","");')
$s=Replace-Required $s '                _view.Controller_GetAnnotationText=NativeProbeAnnotation;' ('                renderStage="annotation-bind";'+[Environment]::NewLine+'                _view.Controller_GetAnnotationText=NativeProbeAnnotation;')
$s=Replace-Required $s '                _view.AddCells(data);' ('                renderStage="add-cells";'+[Environment]::NewLine+'                _view.AddCells(data);')
$s=Replace-Required $s '                _view.EdgesVisibility=_showEdges.Checked ? vtkControl.vtkEdgesVisibility.ElementEdges : vtkControl.vtkEdgesVisibility.NoEdges;' ('                renderStage="edge-visibility";'+[Environment]::NewLine+'                _view.EdgesVisibility=_showEdges.Checked ? vtkControl.vtkEdgesVisibility.ElementEdges : vtkControl.vtkEdgesVisibility.NoEdges;')
$s=Replace-Required $s '                _view.UpdateScalarsAndCameraAndRedraw();' ('                renderStage="scalar-format-redraw";'+[Environment]::NewLine+'                _view.UpdateScalarsAndCameraAndRedraw();')
$s=Replace-Required $s '                _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);' ('                renderStage="selection-mode";'+[Environment]::NewLine+'                _view.SetSelectBy(CaeGlobals.vtkSelectBy.Node);')
$s=Replace-Required $s '                _view.OnMouseLeftButtonUpSelection+=OnNativeVtkSelection;' ('                renderStage="selection-event";'+[Environment]::NewLine+'                _view.OnMouseLeftButtonUpSelection+=OnNativeVtkSelection;')
$s=Replace-Required $s '                _view.AdjustCameraDistanceAndClipping();' ('                renderStage="camera-fit";'+[Environment]::NewLine+'                if(firstRender) _view.AdjustCameraDistanceAndClipping();')
$s=Replace-Required $s '                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • scalar contours ' ('                renderStage="complete";'+[Environment]::NewLine+'                LastRenderError=null; LastRenderSkipped=false; LastRenderSkipReason=null;'+[Environment]::NewLine+'                RenderRevision++;'+[Environment]::NewLine+'                _status.Text=_scene.Field+" ["+_scene.Unit+"] • "+_bundle.NodeCount+" nodes / "+_bundle.ElementCount+" volume elements • scalar contours ')
$s=Replace-Required $s '                _status.Text="Render blocked: "+ex.GetType().Name;' ('                LastRenderError="stage="+renderStage+"; "+ex.ToString();'+[Environment]::NewLine+'                LastRenderSkipped=false;'+[Environment]::NewLine+'                LastRenderSkipReason=null;'+[Environment]::NewLine+'                try { System.IO.File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetTempPath(),"AsterMax-render-error.log"),LastRenderError); } catch {}'+[Environment]::NewLine+'                _status.Text="Render blocked @ "+renderStage+": "+ex.GetType().Name;')
$s=Replace-Required $s '                MessageBox.Show(this,"AsterMax results renderer blocked safely.\n\n"+ex.GetType().Name+": "+ex.Message,' ('                if(AuditMode) throw;'+[Environment]::NewLine+'                MessageBox.Show(this,"AsterMax results renderer blocked safely.\n\nStage: "+renderStage+"\n"+ex.GetType().Name+": "+ex.Message,')
$anchor=@'
                    "AsterMax Results",MessageBoxButtons.OK,MessageBoxIcon.Error);
            }
        }
'@
$s=Replace-Required $s $anchor @'
                    "AsterMax Results",MessageBoxButtons.OK,MessageBoxIcon.Error);
            }
            finally { _axRendering=false; }
        }
'@
# Both the ribbon viewport command and automatic solve handoff now use the docked workspace.
$modal='using(var viewport=new AsterMaxResultsViewportForm(_asterMaxLoadedResults)) viewport.ShowDialog(this);'
$s=Replace-Required $s $modal 'ShowAsterMaxIntegratedResult(null);'
Set-Content $path $s -Encoding UTF8
$solve=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=Get-Content $solve -Raw
$s=Replace-Required $s $modal 'ShowAsterMaxIntegratedResult(null);'
if($s.Contains('                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";')) {
    $s=$s.Replace('                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";', '                if(_asterMaxUiAuditMode) throw;'+[Environment]::NewLine+'                tsslState.Text="AsterMax Solve: BLOCKED / FAILED";')
}
Set-Content $solve $s -Encoding UTF8

$main=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$s=Get-Content $main -Raw
$anchor=@'
        public void ClearControls()
        {
            InvokeIfRequired(() =>
            {
'@
$s=Replace-Required $s $anchor ($anchor+[Environment]::NewLine+'                ResetAsterMaxIntegratedResults();')
Set-Content $main $s -Encoding UTF8
Write-Host 'C10.18 integrated Outline / graphics / result details applied with VTK lifecycle hardening and staged renderer diagnostics.'
