param([string]$Root)
$ErrorActionPreference = 'Stop'

$uiPath = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $uiPath)){ throw 'AsterMaxNativeUi.cs must exist before runtime smoke patch.' }
$ui = Get-Content $uiPath -Raw

if(-not $ui.Contains('StartAsterMaxRuntimeSmoke();')){
  $anchor = '            ThemeRecursive(this);'
  if(-not $ui.Contains($anchor)){ throw 'AsterMax UI theme anchor not found.' }
  $ui = $ui.Replace($anchor, "            StartAsterMaxRuntimeSmoke();`r`n" + $anchor)
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
                System.IO.File.AppendAllText(report + ".stages.log",
                    DateTime.UtcNow.ToString("O") + " " + stage + Environment.NewLine);
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

# Instrument startup stages before the WinForms message loop and through native initialization.
$programPath = Join-Path $Root 'PrePoMax/Program.cs'
$program = Get-Content $programPath -Raw
if(-not $program.Contains('AsterMaxSmokeTrace.Stage(args, "program_main");')){
  $program = $program.Replace('        {`r`n            System.Globalization.CultureInfo ci =', '        {`r`n            AsterMaxSmokeTrace.Stage(args, "program_main");`r`n            System.Globalization.CultureInfo ci =')
  if(-not $program.Contains('AsterMaxSmokeTrace.Stage(args, "program_main");')){
    $program = $program.Replace("        {`n            System.Globalization.CultureInfo ci =", "        {`n            AsterMaxSmokeTrace.Stage(args, \"program_main\");`n            System.Globalization.CultureInfo ci =")
  }
}
Set-Content $programPath $program -Encoding UTF8

$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$main = Get-Content $mainPath -Raw
if(-not $main.Contains('AsterMaxSmokeTrace.Stage(_args, "frm_constructor");')){
  $main = $main.Replace('            _args = args;', '            _args = args;`r`n            AsterMaxSmokeTrace.Stage(_args, "frm_constructor");')
}
if(-not $main.Contains('AsterMaxSmokeTrace.Stage(_args, "frm_load_enter");')){
  $main = $main.Replace('        private void FrmMain_Load(object sender, EventArgs e)`r`n        {', '        private void FrmMain_Load(object sender, EventArgs e)`r`n        {`r`n            AsterMaxSmokeTrace.Stage(_args, "frm_load_enter");')
}
if(-not $main.Contains('AsterMaxSmokeTrace.Stage(_args, "controller_created");')){
  $main = $main.Replace('                _controller = new Controller(this);', '                _controller = new Controller(this);`r`n                AsterMaxSmokeTrace.Stage(_args, "controller_created");')
}
if(-not $main.Contains('AsterMaxSmokeTrace.Stage(_args, "import_file_async_returned");')){
  $main = $main.Replace('                                await _controller.ImportFileAsync(fileName, false);', '                                await _controller.ImportFileAsync(fileName, false);`r`n                                AsterMaxSmokeTrace.Stage(_args, "import_file_async_returned");')
}
Set-Content $mainPath $main -Encoding UTF8

Write-Host 'AsterMax native runtime smoke harness and stage trace injected.' -ForegroundColor Green
