param([string]$Root)
$ErrorActionPreference='Stop'

# C10.08.1 — automation-only admission gate for the packaged STEP/NetGen path.
# This adds no synthetic geometry or FEA values. PASS requires the production
# command-line importer to create real CAD entities and NetGen volume elements.

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(-not(Test-Path $uiPath)){ throw 'AsterMaxNativeUi.cs is required for the portable CAD smoke gate.' }
$ui=Get-Content $uiPath -Raw

if(-not $ui.Contains('StartAsterMaxPortableCadSmoke();')){
  $anchor='                ThemeRecursive(this);'
  if(-not $ui.Contains($anchor)){ throw 'C10.08.1 UI smoke-call anchor missing.' }
  $ui=$ui.Replace($anchor,'                StartAsterMaxPortableCadSmoke();'+[Environment]::NewLine+$anchor)
}

if(-not $ui.Contains('private void StartAsterMaxPortableCadSmoke()')){
  $anchor='        private void ThemeRecursive(Control root)'
  if(-not $ui.Contains($anchor)){ throw 'C10.08.1 UI smoke-method anchor missing.' }
  $method=@'
        private void StartAsterMaxPortableCadSmoke()
        {
            string reportPath = AsterMaxPortableCadSmokeTrace.GetReportPath(_args);
            if (String.IsNullOrWhiteSpace(reportPath)) return;

            AsterMaxPortableCadSmokeTrace.Stage(_args, "smoke_started");
            int ticks = 0;
            System.Threading.Tasks.Task<bool> meshTask = null;
            var smokeTimer = new System.Windows.Forms.Timer { Interval = 250 };
            smokeTimer.Tick += (sender, eventArgs) =>
            {
                ticks++;
                try
                {
                    if (_controller != null && _controller.Model != null && _controller.Model.Geometry != null)
                    {
                        var geometry = _controller.Model.Geometry;
                        int geometryParts = geometry.Parts == null ? 0 : geometry.Parts.Count;
                        int geometryNodes = geometry.Nodes == null ? 0 : geometry.Nodes.Count;
                        int geometryElements = geometry.Elements == null ? 0 : geometry.Elements.Count;
                        if (geometryParts > 0 && geometryNodes > 0)
                        {
                            if (meshTask == null)
                            {
                                string partName = null;
                                foreach (var entry in geometry.Parts) { partName = entry.Key; break; }
                                if (String.IsNullOrWhiteSpace(partName))
                                    throw new InvalidOperationException("Imported geometry has no meshable part name.");
                                AsterMaxPortableCadSmokeTrace.Stage(_args, "real_geometry_detected");
                                AsterMaxPortableCadSmokeTrace.Stage(_args, "netgen_volume_mesh_started");
                                meshTask = System.Threading.Tasks.Task.Run(() => _controller.CreateMesh(partName));
                                return;
                            }

                            if (!meshTask.IsCompleted) return;
                            if (!meshTask.GetAwaiter().GetResult())
                                throw new InvalidOperationException("NetGen volume mesh command returned false.");
                            if (_controller.Model.Mesh == null || _controller.Model.Mesh.Nodes == null ||
                                _controller.Model.Mesh.Elements == null || _controller.Model.Mesh.Nodes.Count < 1 ||
                                _controller.Model.Mesh.Elements.Count < 1)
                                throw new InvalidOperationException("NetGen returned no real volume mesh.");

                            string meshProofPath = reportPath + ".mesh.json";
                            string meshProof = "{" +
                                "\"pass\":true," +
                                "\"mesh_nodes\":" + _controller.Model.Mesh.Nodes.Count + "," +
                                "\"mesh_elements\":" + _controller.Model.Mesh.Elements.Count + "," +
                                "\"source\":\"real_native_generate_mesh\"," +
                                "\"fallback_allowed\":true," +
                                "\"fea_values_invented\":false" +
                                "}";
                            System.IO.File.WriteAllText(meshProofPath, meshProof, new System.Text.UTF8Encoding(false));

                            smokeTimer.Stop();
                            AsterMaxPortableCadSmokeTrace.Stage(_args, "netgen_volume_mesh_completed");
                            string unitSystem = _controller.Model.UnitSystem == null
                                ? "null" : _controller.Model.UnitSystem.UnitSystemType.ToString();
                            string json = "{" +
                                "\"pass\":true," +
                                "\"native_exe\":\"AsterMax Mechanical.exe\"," +
                                "\"cad_importer\":\"NetGen/NetGenMesher.exe\"," +
                                "\"geometry_parts\":" + geometryParts + "," +
                                "\"geometry_nodes\":" + geometryNodes + "," +
                                "\"geometry_elements\":" + geometryElements + "," +
                                "\"mesh_nodes\":" + _controller.Model.Mesh.Nodes.Count + "," +
                                "\"mesh_elements\":" + _controller.Model.Mesh.Elements.Count + "," +
                                "\"unit_system\":\"" + unitSystem + "\"," +
                                "\"fea_values_invented\":false" +
                                "}";
                            System.IO.File.WriteAllText(reportPath, json, new System.Text.UTF8Encoding(false));
                            System.Environment.Exit(0);
                        }
                    }
                }
                catch (Exception ex)
                {
                    smokeTimer.Stop();
                    AsterMaxPortableCadSmokeTrace.Stage(_args, "smoke_failed_" + ex.GetType().Name);
                    string reason=(ex.GetType().Name + ": " + ex.Message)
                        .Replace("\\", "\\\\").Replace("\"", "\\\"");
                    System.IO.File.WriteAllText(reportPath,
                        "{\"pass\":false,\"reason\":\"" + reason + "\",\"fea_values_invented\":false}",
                        new System.Text.UTF8Encoding(false));
                    System.Environment.Exit(2);
                }

                if (ticks >= 960)
                {
                    smokeTimer.Stop();
                    AsterMaxPortableCadSmokeTrace.Stage(_args, "smoke_timeout");
                    System.IO.File.WriteAllText(reportPath,
                        "{\"pass\":false,\"reason\":\"timeout_waiting_for_real_STEP_and_NetGen_mesh\",\"fea_values_invented\":false}",
                        new System.Text.UTF8Encoding(false));
                    System.Environment.Exit(3);
                }
            };
            smokeTimer.Start();
        }

'@
  $ui=$ui.Replace($anchor,$method+$anchor)
}

if(-not $ui.Contains('internal static class AsterMaxPortableCadSmokeTrace')){
  $trace=@'

    internal static class AsterMaxPortableCadSmokeTrace
    {
        public static string GetReportPath(string[] args)
        {
            if (args == null) return null;
            foreach (string arg in args)
                if (arg != null && arg.StartsWith("--ASTERMAX-SMOKE=", StringComparison.OrdinalIgnoreCase))
                    return arg.Substring("--ASTERMAX-SMOKE=".Length).Trim('"');
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
  $lastBrace=$ui.LastIndexOf('}')
  if($lastBrace -lt 0){ throw 'C10.08.1 UI namespace closing brace missing.' }
  $ui=$ui.Insert($lastBrace,$trace)
}

Set-Content $uiPath $ui -Encoding UTF8
Write-Host 'C10.08.1 real STEP + NetGen portable smoke gate injected.' -ForegroundColor Green
