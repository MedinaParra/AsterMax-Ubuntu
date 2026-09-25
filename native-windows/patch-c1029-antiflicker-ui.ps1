param([string]$Root)
$ErrorActionPreference='Stop'

$outlinePath = Join-Path $Root 'UserControls/ModelTree.AsterMaxOutline.cs'
$uiPath      = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $outlinePath)){ throw 'C10.29 projected Outline source missing.' }
if(!(Test-Path $uiPath)){ throw 'C10.29 AsterMaxNativeUi source missing.' }

# ----------------------------------------------------------------------
# Projected Outline: double buffer + coalesced refresh
# ----------------------------------------------------------------------
$o=[regex]::Replace((Get-Content $outlinePath -Raw),"\r\n?","`n")

if(-not $o.Contains('private static void AxEnableDoubleBuffering(Control control)'))
{
    $classAnchor='    public partial class ModelTree'+"`n"+'    {'
    $helper=@'
    public partial class ModelTree
    {
        private static void AxEnableDoubleBuffering(Control control)
        {
            if(control==null || control.IsDisposed) return;
            try
            {
                var p=typeof(Control).GetProperty("DoubleBuffered",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                if(p!=null) p.SetValue(control,true,null);
            }
            catch { }
        }
'@
    if(-not $o.Contains($classAnchor)){ throw 'C10.29 ModelTree partial-class anchor missing.' }
    $o=$o.Replace($classAnchor,$helper.TrimEnd())
}

if(-not $o.Contains('AxEnableDoubleBuffering(_axOutline);'))
{
    $p=$o.IndexOf('_axOutline = new TreeView')
    if($p -lt 0){ throw 'C10.29 Outline constructor missing.' }
    $q=$o.IndexOf(';',$p)
    if($q -lt 0){ throw 'C10.29 Outline constructor terminator missing.' }
    $q++
    $o=$o.Substring(0,$q)+"`n            AxEnableDoubleBuffering(_axOutline);"+$o.Substring($q)
}

# Poll less aggressively. Explicit invalidation still happens through stamps.
$o=$o.Replace('_axOutlineTimer = new Timer { Interval = 300 };',
              '_axOutlineTimer = new Timer { Interval = 700 };')

# Delay AsterMaxModelTreeChanged until EndUpdate has completed. This prevents a
# callback from recursively refreshing the projection while it is being rebuilt.
if(-not $o.Contains('bool sourceChanged = _axSourceStamp != sourceStamp;'))
{
    $oldNotify='if (_axSourceStamp != sourceStamp) { _axSourceStamp=sourceStamp; AsterMaxModelTreeChanged?.Invoke(); }'
    $newNotify='bool sourceChanged = _axSourceStamp != sourceStamp; if (sourceChanged) _axSourceStamp=sourceStamp;'
    if(-not $o.Contains($oldNotify)){ throw 'C10.29 source notification anchor missing.' }
    $o=$o.Replace($oldNotify,$newNotify)
}

if(-not $o.Contains('if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();'))
{
    $oldFinally='            finally { _axOutline.EndUpdate(); _axRefreshing = false; }'
    $newFinally=@'
            finally
            {
                _axOutline.EndUpdate();
                _axRefreshing = false;
                _axOutline.Invalidate();
            }
            if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();
'@
    if(-not $o.Contains($oldFinally)){ throw 'C10.29 Outline EndUpdate anchor missing.' }
    $o=$o.Replace($oldFinally,$newFinally.TrimEnd())
}

Set-Content $outlinePath $o -Encoding UTF8

# ----------------------------------------------------------------------
# Ribbon: double buffer only pure WinForms chrome. Do not buffer vtkControl.
# ----------------------------------------------------------------------
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")

if(-not $u.Contains('private static void AsterMaxEnableChromeBuffering(Control control)'))
{
    $methodAnchor='        private void BuildAsterMaxTopChrome()'
    $helper=@'
        private static void AsterMaxEnableChromeBuffering(Control control)
        {
            if(control==null || control.IsDisposed) return;
            try
            {
                var p=typeof(Control).GetProperty("DoubleBuffered",
                    System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
                if(p!=null) p.SetValue(control,true,null);
            }
            catch { }
        }

'@
    if(-not $u.Contains($methodAnchor)){ throw 'C10.29 BuildAsterMaxTopChrome anchor missing.' }
    $u=$u.Replace($methodAnchor,$helper+$methodAnchor)
}

if(-not $u.Contains('AsterMaxEnableChromeBuffering(ribbon);'))
{
    $p=$u.IndexOf('var ribbon = new TabControl')
    if($p -lt 0){ throw 'C10.29 ribbon constructor missing.' }
    $q=$u.IndexOf('};',$p)
    if($q -lt 0){ throw 'C10.29 ribbon constructor terminator missing.' }
    $q+=2
    $u=$u.Substring(0,$q)+"`n            AsterMaxEnableChromeBuffering(ribbon);"+$u.Substring($q)
}

if(-not $u.Contains('AsterMaxEnableChromeBuffering(page);'))
{
    $method=$u.IndexOf('private TabPage BuildRibbonPage')
    if($method -lt 0){ throw 'C10.29 BuildRibbonPage missing.' }
    $flow=$u.IndexOf('var flow = new FlowLayoutPanel',$method)
    if($flow -lt 0){ throw 'C10.29 Ribbon flow constructor missing.' }
    $u=$u.Substring(0,$flow)+'AsterMaxEnableChromeBuffering(page);'+"`n            "+$u.Substring($flow)
}

if(-not $u.Contains('AsterMaxEnableChromeBuffering(flow);'))
{
    $add=$u.IndexOf('flow.Controls.AddRange(controls);',$u.IndexOf('private TabPage BuildRibbonPage'))
    if($add -lt 0){ throw 'C10.29 Ribbon flow add anchor missing.' }
    $u=$u.Substring(0,$add)+'AsterMaxEnableChromeBuffering(flow);'+"`n            "+$u.Substring($add)
}

# Do not force Refresh on the ribbon; let WinForms coalesce paint messages.
$u=$u.Replace('            ribbon.Refresh();'+"`n",'')
$u=$u.Replace('            titleBar.Refresh();'+"`n",'')

Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.29: anti-flicker projected Outline and Ribbon buffering applied.' -ForegroundColor Green
