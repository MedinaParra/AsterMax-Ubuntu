param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $lf=[string][char]10
    $cr=[string][char]13
    $Text=$Text.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $Old=$Old.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $New=$New.Replace($cr+$lf,$lf).Replace($cr,$lf)
    if(-not $Text.Contains($Old)){ throw "C10.20.10 audit hook-release anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$mainPath=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$lf=[string][char]10
$cr=[string][char]13
$m=(Get-Content $mainPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)

$old=@'
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.cleanup.enter", e);
                    _controller.Settings.General.SaveFormSize(this);
'@
$new=@'
                    C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.cleanup.enter", e);

                    // Audit-only shutdown: release the process-wide WH_KEYBOARD_LL hook before
                    // native VTK/window handles are destroyed. Normal interactive close behavior
                    // is intentionally unchanged.
                    if (!String.IsNullOrWhiteSpace(_c10209AuditShutdownDirectory) && _keyboardHook != null)
                    {
                        C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.keyboard_hook_uninstall.before", e);
                        _keyboardHook.KeyDown -= KeyboardHook_KeyDown;
                        _keyboardHook.Uninstall();
                        _keyboardHook = null;
                        C10209TraceShutdown(c10209AuditDirectory, "FrmMain_FormClosing.keyboard_hook_uninstall.after", e);
                    }

                    _controller.Settings.General.SaveFormSize(this);
'@
$m=Replace-Required $m $old $new
# A completed automated audit owns a disposable fixture. Interactive projects must
# retain their save prompt; active jobs still go through the existing close guards.
$m=Replace-Required $m '                else if (_controller.ModelChanged)' '                else if (_controller.ModelChanged && String.IsNullOrWhiteSpace(_c10209AuditShutdownDirectory))'
Set-Content $mainPath $m -Encoding UTF8

# VTK holds native references after managed Dispose. Disable its Win32 event
# procedure while the HWND is still valid, not later from a finalizer.
$vtkPath=Join-Path $Root 'vtkControl/vtkControl.Designer.cs'
$v=(Get-Content $vtkPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
$v=Replace-Required $v '                if (disposing)
                {
                    if (components != null)' '                if (disposing)
                {
                    if (_renderWindowInteractor != null) _renderWindowInteractor.Disable();
                    if (components != null)'
$v=Replace-Required $v '        protected override void OnHandleDestroyed(System.EventArgs e)
        {' '        protected override void OnHandleDestroyed(System.EventArgs e)
        {
            if (_renderWindowInteractor != null) _renderWindowInteractor.Disable();'
Set-Content $vtkPath $v -Encoding UTF8

# PrePoMax registers a managed WH_CALLWNDPROCRET callback through MessageBoxManager
# on the main STA thread but upstream does not unregister it. During CLR teardown,
# MSCTF destroys its hidden thread message window and USER32 can invoke this stale
# managed hook after managed/unmanaged transitions have been disabled, producing
# c0020001 / STATUS_FATAL_USER_CALLBACK_EXCEPTION (0xC000041D).
#
# Always release the thread hook after the WinForms message loop returns and before
# the CLR begins process shutdown. This is not audit-only: it fixes the real app
# lifecycle while preserving MessageBoxManager behavior for the entire UI session.
$programPath=Join-Path $Root 'PrePoMax/Program.cs'
$p=(Get-Content $programPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
$programOld=@'
            MessageBoxManager.Register();
            //
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new FrmMain(args));
'@
$programNew=@'
            MessageBoxManager.Register();
            //
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                Application.Run(new FrmMain(args));
            }
            finally
            {
                MessageBoxManager.Unregister();
            }
'@
$p=Replace-Required $p $programOld $programNew
Set-Content $programPath $p -Encoding UTF8

Write-Host 'C10.20.10 shutdown hook release applied (keyboard, VTK, MessageBoxManager).' -ForegroundColor Green
