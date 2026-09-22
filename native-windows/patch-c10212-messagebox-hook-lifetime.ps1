param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $lf=[string][char]10; $cr=[string][char]13
    $Text=$Text.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $Old=$Old.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $New=$New.Replace($cr+$lf,$lf).Replace($cr,$lf)
    if(-not $Text.Contains($Old)){ throw "C10.20.12 MessageBox hook lifetime anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$programPath=Join-Path $Root 'PrePoMax/Program.cs'
$lf=[string][char]10; $cr=[string][char]13
$p=(Get-Content $programPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)

$old=@'
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new FrmMain(args));
'@
$new=@'
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            try
            {
                Application.Run(new FrmMain(args));
            }
            finally
            {
                // MessageBoxManager.Register installs a per-thread WH_CALLWNDPROCRET hook.
                // Pair its lifetime explicitly with the WinForms message loop so no native
                // hook callback survives the UI loop during process teardown.
                MessageBoxManager.Unregister();
            }
'@
$p=Replace-Required $p $old $new
Set-Content $programPath $p -Encoding UTF8

Write-Host 'C10.20.12 MessageBoxManager hook lifetime cleanup applied.' -ForegroundColor Green
