param([string]$Root)
$ErrorActionPreference='Stop'

$outlinePath = Join-Path $Root 'UserControls/ModelTree.AsterMaxOutline.cs'
$uiPath      = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$modelPath   = Join-Path $Root 'UserControls/ModelTree.cs'
foreach($p in @($outlinePath,$uiPath,$modelPath)){ if(!(Test-Path $p)){ throw "C10.29 missing: $p" } }

# ---------------- Outline: coalesce refreshes and double-buffer the projected tree ----------------
$o=[regex]::Replace((Get-Content $outlinePath -Raw),"\r\n?","`n")

$treeInit = @'
            _axOutline = new TreeView { Name = "asterMaxOutline", Dock = DockStyle.Fill,
                HideSelection = false, ShowLines = true, ShowRootLines = true,
                BackColor = Color.White, ForeColor = Color.FromArgb(34,42,53),
                Font = new Font("Segoe UI", 9), BorderStyle = BorderStyle.None };
'@
$treeNew = @'
            _axOutline = new TreeView { Name = "asterMaxOutline", Dock = DockStyle.Fill,
                HideSelection = false, ShowLines = true, ShowRootLines = true,
                BackColor = Color.White, ForeColor = Color.FromArgb(34,42,53),
                Font = new Font("Segoe UI", 9), BorderStyle = BorderStyle.None };
            AsterMaxEnableDoubleBuffering(_axOutline);
'@
if(-not $o.Contains('AsterMaxEnableDoubleBuffering(_axOutline);')){
  if(-not $o.Contains($treeInit)){ throw 'C10.29 outline tree init anchor missing.' }
  $o=$o.Replace($treeInit,$treeNew)
}

# Slow the polling slightly. Native operations still invalidate the stamp immediately.
$o=$o.Replace('_axOutlineTimer = new Timer { Interval = 300 };',
              '_axOutlineTimer = new Timer { Interval = 650 };')

# Move model-tree-changed notification out of the rebuild preamble so callbacks cannot
# recursively rebuild the projected tree mid-update.
$old = @'
            string sourceStamp = stamp.ToString();
            if (_axSourceStamp != sourceStamp) { _axSourceStamp=sourceStamp; AsterMaxModelTreeChanged?.Invoke(); }
            stamp.Append(_axResultStatus).Append(_axResultsCurrent).Append(String.Join("|",_axResultFields));
'@
$new = @'
            string sourceStamp = stamp.ToString();
            bool sourceChanged = _axSourceStamp != sourceStamp;
            if (sourceChanged) _axSourceStamp=sourceStamp;
            stamp.Append(_axResultStatus).Append(_axResultsCurrent).Append(String.Join("|",_axResultFields));
'@
if(-not $o.Contains('bool sourceChanged = _axSourceStamp != sourceStamp;')){
  if(-not $o.Contains($old)){ throw 'C10.29 source-change anchor missing.' }
  $o=$o.Replace($old,$new)
}

# EndUpdate -> one repaint -> then notify observers.
$finallyOld = '            finally { _axOutline.EndUpdate(); _axRefreshing = false; }'
$finallyNew = @'
            finally
            {
                _axOutline.EndUpdate();
                _axRefreshing = false;
                _axOutline.Invalidate();
            }
            if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();
'@
if(-not $o.Contains('if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();')){
  if(-not $o.Contains($finallyOld)){ throw 'C10.29 outline finalization anchor missing.' }
  $o=$o.Replace($finallyOld,$finallyNew.TrimEnd())
}

Set-Content $outlinePath $o -Encoding UTF8

# ---------------- ModelTree host: buffer Details and tabs ----------------
$m=[regex]::Replace((Get-Content $modelPath -Raw),"\r\n?","`n")
$styleAnchor='        private void AsterMaxStyleTree(CodersLabTreeView tree)'
$helper=@'
        private static void AsterMaxEnableDoubleBuffering(Control control)
        {
            if (control == null || control.IsDisposed) return;
            try
            {
                var p = typeof(Control).GetProperty("DoubleBuffered",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                if (p != null) p.SetValue(control, true, null);
            }
            catch { }
        }

'@
if(-not $m.Contains('private static void AsterMaxEnableDoubleBuffering(Control control)')){
  if(-not $m.Contains($styleAnchor)){ throw 'C10.29 ModelTree buffering helper anchor missing.' }
  $m=$m.Replace($styleAnchor,$helper+$styleAnchor)
}

$styleStart = @'
        private void AsterMaxStyleTree(CodersLabTreeView tree)
        {
            tree.BackColor = Color.White;
'@
$styleNew = @'
        private void AsterMaxStyleTree(CodersLabTreeView tree)
        {
            AsterMaxEnableDoubleBuffering(tree);
            tree.BackColor = Color.White;
'@
if(-not $m.Contains('AsterMaxEnableDoubleBuffering(tree);')){
  if(-not $m.Contains($styleStart)){ throw 'C10.29 tree style anchor missing.' }
  $m=$m.Replace($styleStart,$styleNew)
}

$detailsAnchor = @'
            _asterMaxDetailsPanel = new Panel
            {
                Name = "asterMaxDetailsPanel",
'@
$detailsNew = @'
            _asterMaxDetailsPanel = new Panel
            {
                Name = "asterMaxDetailsPanel",
'@
# Insert buffering after object initializer is complete, before header creation.
$detailsAfter = '            var header = new Label'
if(-not $m.Contains('AsterMaxEnableDoubleBuffering(_asterMaxDetailsPanel);')){
  $pos=$m.IndexOf($detailsAfter,$m.IndexOf('private void BuildAsterMaxDetailsPanel()'))
  if($pos -lt 0){ throw 'C10.29 details buffering anchor missing.' }
  $m=$m.Substring(0,$pos)+'            AsterMaxEnableDoubleBuffering(_asterMaxDetailsPanel);'+"`n`n"+$m.Substring($pos)
}

# Buffer tab host once when applying Mechanical presentation.
$applyLine='            tcGeometryModelResults.Font = new Font("Segoe UI Semibold", 9.0f);'
if(-not $m.Contains('AsterMaxEnableDoubleBuffering(tcGeometryModelResults);')){
  if(-not $m.Contains($applyLine)){ throw 'C10.29 tab buffer anchor missing.' }
  $m=$m.Replace($applyLine,'            AsterMaxEnableDoubleBuffering(tcGeometryModelResults);'+"`n"+$applyLine)
}
Set-Content $modelPath $m -Encoding UTF8

# ---------------- Ribbon: buffer TabControl, pages and FlowLayoutPanels ----------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")

$buildAnchor='        private void BuildAsterMaxTopChrome()'
$uiHelper=@'
        private static void AsterMaxEnableUiBuffering(Control control)
        {
            if (control == null || control.IsDisposed) return;
            try
            {
                var p = typeof(Control).GetProperty("DoubleBuffered",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                if (p != null) p.SetValue(control, true, null);
            }
            catch { }
        }

'@
if(-not $u.Contains('private static void AsterMaxEnableUiBuffering(Control control)')){
  if(-not $u.Contains($buildAnchor)){ throw 'C10.29 UI buffering helper anchor missing.' }
  $u=$u.Replace($buildAnchor,$uiHelper+$buildAnchor)
}

# Buffer ribbon immediately after construction.
$ribbonClose='                Appearance = TabAppearance.Normal'+"`n"+'            };'
$ribbonNew=$ribbonClose+"`n"+'            AsterMaxEnableUiBuffering(ribbon);'
if(-not $u.Contains('AsterMaxEnableUiBuffering(ribbon);')){
  if(-not $u.Contains($ribbonClose)){ throw 'C10.29 ribbon construction anchor missing.' }
  $u=$u.Replace($ribbonClose,$ribbonNew)
}

# Buffer page and flow host.
$pageAnchor='            var flow = new FlowLayoutPanel'
if(-not $u.Contains('AsterMaxEnableUiBuffering(page);')){
  $pos=$u.IndexOf($pageAnchor,$u.IndexOf('private TabPage BuildRibbonPage'))
  if($pos -lt 0){ throw 'C10.29 ribbon page anchor missing.' }
  $u=$u.Substring(0,$pos)+'            AsterMaxEnableUiBuffering(page);'+"`n"+$u.Substring($pos)
}

$flowAdd='            flow.Controls.AddRange(controls);'
$flowNew='            AsterMaxEnableUiBuffering(flow);'+"`n"+$flowAdd
if(-not $u.Contains('AsterMaxEnableUiBuffering(flow);')){
  if(-not $u.Contains($flowAdd)){ throw 'C10.29 ribbon flow anchor missing.' }
  $u=$u.Replace($flowAdd,$flowNew)
}

# Avoid forcing synchronous full-form redraw after initial UI setup.
$oldFinally=@'
            finally
            {
                ResumeLayout(true);
                PerformLayout();
            }
'@
$newFinally=@'
            finally
            {
                ResumeLayout(false);
                BeginInvoke(new Action(() => {
                    if (IsDisposed) return;
                    PerformLayout();
                    Invalidate(false);
                }));
            }
'@
if(-not $u.Contains('Invalidate(false);')){
  if(-not $u.Contains($oldFinally)){ throw 'C10.29 Apply UI finalization anchor missing.' }
  $u=$u.Replace($oldFinally,$newFinally)
}

Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.29: anti-flicker buffering + coalesced Outline refresh applied.' -ForegroundColor Green
