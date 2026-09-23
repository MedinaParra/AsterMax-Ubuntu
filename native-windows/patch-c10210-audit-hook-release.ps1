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

# MessageBoxManager owns a thread-local WH_CALLWNDPROCRET hook. Windows still
# destroys its input-service windows after CLR shutdown; leaving that hook
# installed invokes a managed callback after the runtime has stopped.
# Balance Register on the same UI thread, including exceptional exits.
$programPath=Join-Path $Root 'PrePoMax/Program.cs'
$p=(Get-Content $programPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
$p=Replace-Required $p '            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new FrmMain(args));' '            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new FrmMain(args));
            }
            finally
            {
                MessageBoxManager.Unregister();
            }'
Set-Content $programPath $p -Encoding UTF8

Write-Host 'C10.20.10 audit-only keyboard hook release applied.' -ForegroundColor Green
