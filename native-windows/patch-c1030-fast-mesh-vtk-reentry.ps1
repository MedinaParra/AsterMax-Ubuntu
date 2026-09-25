param([string]$Root)
$ErrorActionPreference='Stop'

$meshPath = Join-Path $Root 'CaeMesh/Parts/MeshingParameters.cs'
$vtkPath  = Join-Path $Root 'vtkControl/vtkControl.cs'
$vtkDesigner = Join-Path $Root 'vtkControl/vtkControl.Designer.cs'
$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
foreach($p in @($meshPath,$vtkPath,$vtkDesigner,$uiPath)){ if(!(Test-Path $p)){ throw "C10.30 missing: $p" } }

# ----------------------------------------------------------------------
# Faster default mesh for iterative work: linear TET4.
# Existing projects retain their saved setting; only new/default meshing
# parameters change from second-order=true to false.
# ----------------------------------------------------------------------
$m=[regex]::Replace((Get-Content $meshPath -Raw),"\r\n?","`n")
if($m.Contains('_secondOrder = true;')){
    $m=$m.Replace('_secondOrder = true;','_secondOrder = false;   // AsterMax fast-preview default: TET4; enable TET10 for final solve')
}
elseif(-not $m.Contains('AsterMax fast-preview default')){
    throw 'C10.30 MeshingParameters SecondOrder default anchor missing.'
}
Set-Content $meshPath $m -Encoding UTF8

# ----------------------------------------------------------------------
# VTK render re-entry guard.
# Prevent vtkRenderWindow.Render()/pipeline UpdateInformation from being
# re-entered by nested WinForms paint/message processing.
# ----------------------------------------------------------------------
$v=[regex]::Replace((Get-Content $vtkPath -Raw),"\r\n?","`n")
$fieldAnchor='        private object myLock = new object();'
$fieldNew=@'
        private object myLock = new object();
        private bool _asterMaxRenderRequestActive;
        private bool _asterMaxRenderPending;
'@
if(-not $v.Contains('_asterMaxRenderRequestActive')){
    if(-not $v.Contains($fieldAnchor)){ throw 'C10.30 vtk render guard field anchor missing.' }
    $v=$v.Replace($fieldAnchor,$fieldNew.TrimEnd())
}

# Coalesce render requests while a render/pipeline request is active.
$renderOld=@'
        private void RenderSceene()
        {
            if (_renderingOn) this.Invalidate();
        }
'@
$renderNew=@'
        private void RenderSceene()
        {
            if (!_renderingOn || IsDisposed || !IsHandleCreated) return;
            if (_asterMaxRenderRequestActive)
            {
                _asterMaxRenderPending = true;
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(new Action(RenderSceene));
                return;
            }
            Invalidate();
        }
'@
if(-not $v.Contains('if (_asterMaxRenderRequestActive)')){
    if(-not $v.Contains($renderOld)){ throw 'C10.30 RenderSceene anchor missing.' }
    $v=$v.Replace($renderOld,$renderNew)
}
Set-Content $vtkPath $v -Encoding UTF8

$d=[regex]::Replace((Get-Content $vtkDesigner -Raw),"\r\n?","`n")
$paintStart=$d.IndexOf('        protected override void OnPaint(System.Windows.Forms.PaintEventArgs e)')
if($paintStart -lt 0){ throw 'C10.30 vtk OnPaint method missing.' }
$visibleStart=$d.IndexOf('        protected override void OnVisibleChanged', $paintStart)
if($visibleStart -lt 0){ throw 'C10.30 vtk OnPaint end anchor missing.' }
$oldPaint=$d.Substring($paintStart,$visibleStart-$paintStart)
if(-not $oldPaint.Contains('_renderWindow.Render()')){ throw 'C10.30 vtk OnPaint Render anchor missing.' }

$newPaint=@'
        protected override void OnPaint(System.Windows.Forms.PaintEventArgs e)
        {
            if (_asterMaxRenderRequestActive)
            {
                _asterMaxRenderPending = true;
                base.OnPaint(e);
                return;
            }

            _asterMaxRenderRequestActive = true;
            try
            {
                if (this._renderWindow != null && _renderingOn && this.Visible)
                {
                    this.SyncRenderWindowSize();
                    if (this._renderWindow.GetInteractor() != this._renderWindowInteractor)
                        this.AttachInteractor();

                    this._renderWindow.Render();
                }
            }
            finally
            {
                _asterMaxRenderRequestActive = false;
                bool again = _asterMaxRenderPending;
                _asterMaxRenderPending = false;
                if (again && _renderingOn && !IsDisposed && IsHandleCreated)
                    BeginInvoke(new System.Action(() => { if (!IsDisposed) Invalidate(); }));
            }
            base.OnPaint(e);
        }


'@
$d=$d.Substring(0,$paintStart)+$newPaint+$d.Substring($visibleStart)
Set-Content $vtkDesigner $d -Encoding UTF8

# ----------------------------------------------------------------------
# Tell the user what the default strategy actually is in the Ribbon.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
$u=$u.Replace('InfoCard("NetGen nativo • tamaño global y refinamientos locales")',
              'InfoCard("Rápido: TET4 lineal • Final: activar TET10 • NetGen nativo")')
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.30: TET4 fast-preview default + VTK re-entry render guard applied.' -ForegroundColor Green
