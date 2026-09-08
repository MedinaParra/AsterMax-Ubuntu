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

# Instrument startup stages through native initialization using simple anchors.
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

$constructorStage = '            AsterMaxSmokeTrace.Stage(_args, "frm_constructor");'
$constructorAnchor = '            _args = args;'
if(-not $main.Contains($constructorStage)){
  if(-not $main.Contains($constructorAnchor)){ throw 'FrmMain constructor args anchor not found.' }
  $main = $main.Replace($constructorAnchor, $constructorAnchor + [Environment]::NewLine + $constructorStage)
}

$loadStage = '            AsterMaxSmokeTrace.Stage(_args, "frm_load_enter");'
$loadAnchor = '            if (TestWriteAccess() == false)'
if(-not $main.Contains($loadStage)){
  if(-not $main.Contains($loadAnchor)){ throw 'FrmMain load write-access anchor not found.' }
  $main = $main.Replace($loadAnchor, $loadStage + [Environment]::NewLine + $loadAnchor)
}

$controllerStage = '                AsterMaxSmokeTrace.Stage(_args, "controller_created");'
$controllerAnchor = '                _controller = new Controller(this);'
if(-not $main.Contains($controllerStage)){
  if(-not $main.Contains($controllerAnchor)){ throw 'FrmMain controller anchor not found.' }
  $main = $main.Replace($controllerAnchor, $controllerAnchor + [Environment]::NewLine + $controllerStage)
}

$importStage = '                                AsterMaxSmokeTrace.Stage(_args, "import_file_async_returned");'
$importAnchor = '                                await _controller.ImportFileAsync(fileName, false);'
if(-not $main.Contains($importStage)){
  if(-not $main.Contains($importAnchor)){ throw 'FrmMain import anchor not found.' }
  $main = $main.Replace($importAnchor, $importAnchor + [Environment]::NewLine + $importStage)
}

Set-Content $mainPath $main -Encoding UTF8
Write-Host 'AsterMax native runtime smoke harness and stage trace injected.' -ForegroundColor Green
