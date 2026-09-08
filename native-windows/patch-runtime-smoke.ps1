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
            if (_args == null) return;
            string reportPath = null;
            foreach (string arg in _args)
            {
                if (arg != null && arg.StartsWith("--ASTERMAX-SMOKE=", StringComparison.OrdinalIgnoreCase))
                {
                    reportPath = arg.Substring("--ASTERMAX-SMOKE=".Length).Trim('"');
                    break;
                }
            }
            if (String.IsNullOrWhiteSpace(reportPath)) return;

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
                    string msg = ex.GetType().Name + ": " + ex.Message;
                    msg = msg.Replace("\\", "\\\\").Replace("\"", "\\\"");
                    System.IO.File.WriteAllText(reportPath, "{\"pass\":false,\"reason\":\"" + msg + "\"}");
                    System.Environment.Exit(2);
                }

                if (ticks >= 480)
                {
                    smokeTimer.Stop();
                    System.IO.File.WriteAllText(reportPath, "{\"pass\":false,\"reason\":\"timeout_waiting_for_imported_geometry\"}");
                    System.Environment.Exit(3);
                }
            };
            smokeTimer.Start();
        }

'@
  $ui = $ui.Replace($methodAnchor, $methods + $methodAnchor)
}

Set-Content $uiPath $ui -Encoding UTF8
Write-Host 'AsterMax native runtime smoke harness injected.' -ForegroundColor Green
