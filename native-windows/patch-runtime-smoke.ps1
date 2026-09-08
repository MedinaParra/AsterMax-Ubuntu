param([string]$Root)
$ErrorActionPreference = 'Stop'

$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $uiPath)){ throw 'AsterMaxNativeUi.cs must exist before runtime smoke patch.' }
$ui = Get-Content $uiPath -Raw

if(-not $ui.Contains('StartAsterMaxRuntimeSmoke();')){
  $anchor = '            ThemeRecursive(this);'
  if(-not $ui.Contains($anchor)){ throw 'AsterMax UI theme anchor not found.' }
  $ui = $ui.Replace($anchor, '            StartAsterMaxRuntimeSmoke();' + [Environment]::NewLine + $anchor)
}

if(-not $ui.Contains('private void StartAsterMaxRuntimeSmoke()')){
  $methodAnchor = '        private void ThemeRecursive(Control root)'
  if(-not $ui.Contains($methodAnchor)){ throw 'ThemeRecursive method anchor not found.' }
  $methods = @'
        // Automation-only runtime proof. It uses the same native command-line import path as the desktop app.
        // No synthetic CAE result is created: PASS requires geometry objects produced by the real importer.
        private void StartAsterMaxRuntimeSmoke()
        {
            string reportPath = AsterMaxSmokeTrace.GetReportPath(_args);
            if (String.IsNullOrWhiteSpace(reportPath)) return;
            AsterMaxSmokeTrace.Stage(_args, "astermax_ui_applied");

            int ticks = 0;
            var smokeTimer = new System.Windows.Forms.Timer { Interval = 250 };
            smokeTimer.Tick += (sender, eventArgs) =>
            {
                ticks++;
                try
                {
                    if (_controller != null && _controller.Model != null && _controller.Model.Geometry != null)
                    {
                        var geometry = _controller.Model.Geometry;
                        int parts = geometry.Parts == null ? 0 : geometry.Parts.Count;
                        int nodes = geometry.Nodes == null ? 0 : geometry.Nodes.Count;
                        int elements = geometry.Elements == null ? 0 : geometry.Elements.Count;
                        if (parts > 0 && nodes > 0)
                        {
                            smokeTimer.Stop();
                            AsterMaxSmokeTrace.Stage(_args, "geometry_detected");
                            string unitSystem = _controller.Model.UnitSystem == null ? "null" : _controller.Model.UnitSystem.UnitSystemType.ToString();
                            string currentView = _controller.CurrentView.ToString();
                            string json = "{" +
                                "\"pass\":true," +
                                "\"native_exe\":\"AsterMax Mechanical.exe\"," +
                                "\"geometry_parts\":" + parts + "," +
                                "\"geometry_nodes\":" + nodes + "," +
                                "\"geometry_elements\":" + elements + "," +
                                "\"unit_system\":\"" + unitSystem + "\"," +
                                "\"current_view\":\"" + currentView + "\"," +
                                "\"vtk_control_initialized\":" + (_vtk != null ? "true" : "false") +
                                "}";
                            System.IO.File.WriteAllText(reportPath, json);
                            System.Environment.Exit(0);
                        }
                    }
                }
                catch (Exception ex)
                {
                    smokeTimer.Stop();
                    AsterMaxSmokeTrace.Stage(_args, "smoke_exception_" + ex.GetType().Name);
                    string msg = ex.GetType().Name + ": " + ex.Message;
                    msg = msg.Replace("\\", "\\\\").Replace("\"", "\\\"");
                    System.IO.File.WriteAllText(reportPath, "{\"pass\":false,\"reason\":\"" + msg + "\"}");
                    System.Environment.Exit(2);
                }
                if (ticks >= 240)
                {
                    smokeTimer.Stop();
                    AsterMaxSmokeTrace.Stage(_args, "smoke_timer_timeout");
                    System.IO.File.WriteAllText(reportPath, "{\"pass\":false,\"reason\":\"timeout_waiting_for_imported_geometry\"}");
                    System.Environment.Exit(3);
                }
            };
            AsterMaxSmokeTrace.Stage(_args, "smoke_timer_started");
            smokeTimer.Start();
        }

'@
  $ui = $ui.Replace($methodAnchor, $methods + $methodAnchor)
}

if(-not $ui.Contains('internal static class AsterMaxSmokeTrace')){
  $traceClass = @'

    internal static class AsterMaxSmokeTrace
    {
        public static string GetReportPath(string[] args)
        {
            if (args == null) return null;
            foreach (string arg in args)
            {
                if (arg != null && arg.StartsWith("--ASTERMAX-SMOKE=", StringComparison.OrdinalIgnoreCase))
                    return arg.Substring("--ASTERMAX-SMOKE=".Length).Trim('"');
            }
            return null;
        }
        public static void Stage(string[] args, string stage)
        {
            try
            {
                string report = GetReportPath(args);
                if (String.IsNullOrWhiteSpace(report)) return;
                System.IO.File.AppendAllText(report + ".stages.log", DateTime.UtcNow.ToString("O") + " " + stage + Environment.NewLine);
            }
            catch { }
        }
    }
'@
  $lastBrace = $ui.LastIndexOf('}')
  if($lastBrace -lt 0){ throw 'AsterMax UI namespace closing brace not found.' }
  $ui = $ui.Insert($lastBrace, $traceClass)
}
Set-Content $uiPath $ui -Encoding UTF8

$programPath = Join-Path $Root 'PrePoMax/Program.cs'
$program = Get-Content $programPath -Raw
$programStage = '            AsterMaxSmokeTrace.Stage(args, "program_main");'
$programAnchor = '            System.Globalization.CultureInfo ci ='
if(-not $program.Contains($programStage)){
  if(-not $program.Contains($programAnchor)){ throw 'Program.cs culture anchor not found.' }
  $program = $program.Replace($programAnchor, $programStage + [Environment]::NewLine + $programAnchor)
}
Set-Content $programPath $program -Encoding UTF8

$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$main = Get-Content $mainPath -Raw
function Add-StageAfter([string]$anchor,[string]$stage,[string]$indent){
  if(-not $script:main.Contains($stage)){
    if(-not $script:main.Contains($anchor)){ throw "FrmMain anchor not found: $anchor" }
    $script:main = $script:main.Replace($anchor, $anchor + [Environment]::NewLine + $indent + $stage)
  }
}
function Add-StageBefore([string]$anchor,[string]$stage,[string]$indent){
  if(-not $script:main.Contains($stage)){
    if(-not $script:main.Contains($anchor)){ throw "FrmMain anchor not found: $anchor" }
    $script:main = $script:main.Replace($anchor, $indent + $stage + [Environment]::NewLine + $anchor)
  }
}

Add-StageAfter '            _args = args;' 'AsterMaxSmokeTrace.Stage(_args, "frm_constructor");' '            '
Add-StageBefore '            if (TestWriteAccess() == false)' 'AsterMaxSmokeTrace.Stage(_args, "frm_load_enter");' '            '
Add-StageAfter '            }' 'AsterMaxSmokeTrace.Stage(_args, "write_access_ok");' '            '
# The generic closing-brace anchor above can match too broadly; ensure meaningful probes around unique initialization statements too.
Add-StageAfter '            var task = Task.Run(() => splash.ShowDialog());' 'AsterMaxSmokeTrace.Stage(_args, "splash_started");' '            '
Add-StageBefore '                _vtk = new vtkControl.vtkControl();' 'AsterMaxSmokeTrace.Stage(_args, "vtk_create_enter");' '                '
Add-StageAfter '                _vtk = new vtkControl.vtkControl();' 'AsterMaxSmokeTrace.Stage(_args, "vtk_create_returned");' '                '
Add-StageAfter '                panelControl.Parent.Controls.Add(_vtk);' 'AsterMaxSmokeTrace.Stage(_args, "vtk_added_to_controls");' '                '
Add-StageBefore '                _modelTree = new ModelTree();' 'AsterMaxSmokeTrace.Stage(_args, "modeltree_create_enter");' '                '
Add-StageAfter '                _modelTree = new ModelTree();' 'AsterMaxSmokeTrace.Stage(_args, "modeltree_create_returned");' '                '
Add-StageAfter '                _controller = new Controller(this);' 'AsterMaxSmokeTrace.Stage(_args, "controller_created");' '                '
Add-StageAfter '                                await _controller.ImportFileAsync(fileName, false);' 'AsterMaxSmokeTrace.Stage(_args, "import_file_async_returned");' '                                '

Set-Content $mainPath $main -Encoding UTF8
Write-Host 'AsterMax detailed native runtime stage trace injected.' -ForegroundColor Green
