param([string]$Root)
$ErrorActionPreference='Stop'

# C9.99.1 — Portable workspace for clean Windows installs.
# Root cause follow-up: STEP import still reaches Settings.Calculix.WorkDirectory directly in legacy code,
# bypassing SettingsContainer.GetWorkDirectory(). Therefore both access paths must self-heal.

function PortableWorkspaceBody {
@'
            string localRoot = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(localRoot)) localRoot = Path.GetTempPath();
            string portableWork = Path.Combine(localRoot, "AsterMax", "Work");
            Directory.CreateDirectory(portableWork);
'@
}

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
if($t.Contains($old)) { $t = $t.Replace($old,$new) }
elseif(-not $t.Contains('string portableWork = Path.Combine(localRoot, "AsterMax", "Work");')) { throw 'SettingsContainer.GetWorkDirectory anchor not found' }
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
if(-not $c.Contains($oldGetter)) { throw 'CalculixSettings.WorkDirectory getter anchor not found' }
$c = $c.Replace($oldGetter,$newGetter)
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
  }
}

Write-Host 'C9.99.1 direct + container workspace hardening applied.' -ForegroundColor Green
