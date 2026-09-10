param([string]$Root)
$ErrorActionPreference='Stop'

# C9.99.2 — Portable workspace for clean Windows installs.
# STEP import reaches Settings.Calculix.WorkDirectory directly in legacy code, so both
# SettingsContainer.GetWorkDirectory() and CalculixSettings.WorkDirectory must self-heal.
# This patch is intentionally idempotent because C9.92 delegates to it and some release
# workflows apply it explicitly again.

# 1) Harden SettingsContainer.GetWorkDirectory().
$settings = Join-Path $Root 'PrePoMax/Settings/SettingsContainer.cs'
$t = Get-Content $settings -Raw
$old = @'
        public string GetWorkDirectory()
        {
            string lastFileName = _general.LastFileName;
            if (_calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&
                Path.GetExtension(lastFileName) == ".pmx")
            {
                return Path.GetDirectoryName(lastFileName);
            }
            else return _calculix.WorkDirectory;
        }
'@
$new = @'
        public string GetWorkDirectory()
        {
            string lastFileName = _general != null ? _general.LastFileName : null;
            if (_calculix != null && _calculix.UsePmxFolderAsWorkDirectory && lastFileName != null && File.Exists(lastFileName) &&
                Path.GetExtension(lastFileName) == ".pmx")
            {
                string pmxDirectory = Path.GetDirectoryName(lastFileName);
                if (!String.IsNullOrWhiteSpace(pmxDirectory) && Directory.Exists(pmxDirectory)) return pmxDirectory;
            }
            if (_calculix != null) return _calculix.WorkDirectory;

            string localRoot = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(localRoot)) localRoot = Path.GetTempPath();
            string portableWork = Path.Combine(localRoot, "AsterMax", "Work");
            Directory.CreateDirectory(portableWork);
            return portableWork;
        }
'@
$settingsToken='string portableWork = Path.Combine(localRoot, "AsterMax", "Work");'
if($t.Contains($old)) {
    $t = $t.Replace($old,$new)
} elseif($t.Contains($settingsToken) -and $t.Contains('public string GetWorkDirectory()')) {
    Write-Host 'C9.99.2 SettingsContainer portable workspace already applied.' -ForegroundColor DarkGray
} else {
    throw 'SettingsContainer.GetWorkDirectory portable-workspace anchor/state not recognized'
}
Set-Content $settings $t -Encoding UTF8

# 2) Harden the legacy direct Settings.Calculix.WorkDirectory getter itself.
$calc = Join-Path $Root 'PrePoMax/Settings/CalculixSettings.cs'
$c = Get-Content $calc -Raw
$oldGetter = '            get { return Tools.GetGlobalPath(_workDirectory); }'
$newGetter = @'
            get
            {
                string path = null;
                try { path = Tools.GetGlobalPath(_workDirectory); }
                catch { path = null; }
                if (!String.IsNullOrWhiteSpace(path) && Directory.Exists(path)) return path;

                string localRoot = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                if (String.IsNullOrWhiteSpace(localRoot)) localRoot = Path.GetTempPath();
                string portableWork = Path.Combine(localRoot, "AsterMax", "Work");
                Directory.CreateDirectory(portableWork);
                _workDirectory = Tools.GetLocalPath(portableWork);
                return portableWork;
            }
'@
$calcToken='_workDirectory = Tools.GetLocalPath(portableWork);'
if($c.Contains($oldGetter)) {
    $c = $c.Replace($oldGetter,$newGetter)
} elseif($c.Contains($calcToken) -and $c.Contains('Directory.CreateDirectory(portableWork);')) {
    Write-Host 'C9.99.2 CalculixSettings portable workspace already applied.' -ForegroundColor DarkGray
} else {
    throw 'CalculixSettings.WorkDirectory portable-workspace anchor/state not recognized'
}
Set-Content $calc $c -Encoding UTF8

# 3) Startup diagnostic: resolve and create workspace before CAD import is possible.
$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $ui){
  $u = Get-Content $ui -Raw
  if(-not $u.Contains('AsterMax workspace initialization failed.')) {
    $anchor = '                Text = "AsterMax Mechanical";'
    $inject = @'
                Text = "AsterMax Mechanical";
                try
                {
                    string asterMaxWork = _controller != null && _controller.Settings != null
                        ? _controller.Settings.GetWorkDirectory() : null;
                    if (String.IsNullOrWhiteSpace(asterMaxWork) || !System.IO.Directory.Exists(asterMaxWork))
                        throw new InvalidOperationException("AsterMax workspace initialization failed.");
                }
                catch (Exception ex)
                {
                    throw new InvalidOperationException("AsterMax could not initialize a writable portable workspace.", ex);
                }
'@
    if(-not $u.Contains($anchor)){ throw 'AsterMaxNativeUi title anchor not found' }
    $u = $u.Replace($anchor,$inject)
    Set-Content $ui $u -Encoding UTF8
  } else {
    Write-Host 'C9.99.2 startup workspace diagnostic already applied.' -ForegroundColor DarkGray
  }
}

Write-Host 'C9.99.2 portable workspace patch PASS (idempotent).' -ForegroundColor Green
