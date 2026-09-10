param([string]$Root)
$ErrorActionPreference='Stop'

# C9.99 — Portable workspace for clean Windows installs.
# PrePoMax's default CalculixSettings.Reset() leaves WorkDirectory null. CAD/STEP import uses the
# common work-directory contract before meshing/solver stages, so a clean portable build can reach
# the file chooser and then fail with "The work directory does not exist.".
# AsterMax owns a solver-neutral workspace under LocalApplicationData and creates it on demand.

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

            string configured = null;
            try
            {
                if (_calculix != null) configured = _calculix.WorkDirectory;
            }
            catch
            {
                configured = null;
            }
            if (!String.IsNullOrWhiteSpace(configured) && Directory.Exists(configured)) return configured;

            string localRoot = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (String.IsNullOrWhiteSpace(localRoot)) localRoot = Path.GetTempPath();
            string portableWork = Path.Combine(localRoot, "AsterMax", "Work");
            Directory.CreateDirectory(portableWork);
            return portableWork;
        }
'@
if(-not $t.Contains($old)){ throw 'SettingsContainer.GetWorkDirectory anchor not found' }
$t = $t.Replace($old,$new)
Set-Content $settings $t -Encoding UTF8

# Add explicit startup/workspace diagnostics without changing solver physics.
$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(Test-Path $ui){
  $u = Get-Content $ui -Raw
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

Write-Host 'C9.99 portable workspace + STEP import prerequisite applied.' -ForegroundColor Green
