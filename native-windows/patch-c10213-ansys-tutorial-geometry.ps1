param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $lf=[string][char]10; $cr=[string][char]13
    $Text=$Text.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $Old=$Old.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $New=$New.Replace($cr+$lf,$lf).Replace($cr,$lf)
    if(-not $Text.Contains($Old)){ throw "C10.20.13 tutorial audit anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$lf=[string][char]10; $cr=[string][char]13
$a=(Get-Content $auditPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)

$signature='        private void ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)'
$helpers=@'
        private void StartAsterMaxC10213TutorialGeometryAudit()
        {
            const string prefix = "--astermax-tutorial-audit=";
            string arg = Environment.GetCommandLineArgs()
                .FirstOrDefault(x => x.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));
            if (arg == null) return;

            string directory = arg.Substring(prefix.Length).Trim('"');
            Directory.CreateDirectory(directory);
            int attempts = 0;
            var timer = new Timer { Interval = 1000 };
            timer.Tick += (sender, args) =>
            {
                attempts++;
                try
                {
                    FeModel model = _controller == null ? null : _controller.Model;
                    int geometryParts = model == null || model.Geometry == null ? 0 : model.Geometry.Parts.Count;
                    if (geometryParts <= 0 && attempts < 90) return;

                    timer.Stop();
                    timer.Dispose();
                    if (geometryParts <= 0)
                        throw new InvalidOperationException("Tutorial STEP import did not produce geometry within 90 s.");

                    C10213RunTutorialGeometryAudit(directory);
                    C1020RequestAuditExit(directory, 0);
                }
                catch (Exception ex)
                {
                    try { File.WriteAllText(Path.Combine(directory, "tutorial-geometry-error.txt"), ex.ToString()); }
                    catch { }
                    timer.Stop();
                    timer.Dispose();
                    C1020RequestAuditExit(directory, 1);
                }
            };
            timer.Start();
        }

        private void C10213RunTutorialGeometryAudit(string directory)
        {
            FeModel model = _controller.Model;
            var candidates = _controller.GetGeometryPartsWithoutSubParts();
            string[] names = candidates == null ? new string[0] : candidates.Select(x => x.Name).ToArray();
            string[] types = candidates == null ? new string[0] : candidates.Select(x => x.GetType().FullName).ToArray();

            var rows = new JArray();
            int nodesBefore = model.Mesh == null ? 0 : model.Mesh.Nodes.Count;
            int elementsBefore = model.Mesh == null ? 0 : model.Mesh.Elements.Count;

            foreach (string partName in names)
            {
                int beforeNodes = model.Mesh == null ? 0 : model.Mesh.Nodes.Count;
                int beforeElements = model.Mesh == null ? 0 : model.Mesh.Elements.Count;
                bool completed = false;
                bool returned = false;
                string error = null;
                DateTime started = DateTime.UtcNow;
                try
                {
                    Task<bool> task = Task.Run(() => _controller.CreateMesh(partName));
                    DateTime deadline = DateTime.UtcNow.AddSeconds(180);
                    while (!task.IsCompleted && DateTime.UtcNow < deadline)
                    {
                        Application.DoEvents();
                        System.Threading.Thread.Sleep(50);
                    }
                    if (!task.IsCompleted)
                    {
                        try { _controller.StopNetGenJob(); } catch { }
                        error = "TIMEOUT";
                    }
                    else
                    {
                        completed = true;
                        returned = task.GetAwaiter().GetResult();
                    }
                }
                catch (Exception ex) { error = ex.ToString(); }

                int afterNodes = model.Mesh == null ? 0 : model.Mesh.Nodes.Count;
                int afterElements = model.Mesh == null ? 0 : model.Mesh.Elements.Count;
                bool produced = afterNodes > beforeNodes && afterElements > beforeElements;

                rows.Add(new JObject {
                    ["part"] = partName,
                    ["completed"] = completed,
                    ["create_mesh_returned"] = returned,
                    ["produced_mesh"] = produced,
                    ["nodes_before"] = beforeNodes,
                    ["nodes_after"] = afterNodes,
                    ["elements_before"] = beforeElements,
                    ["elements_after"] = afterElements,
                    ["elapsed_s"] = (DateTime.UtcNow - started).TotalSeconds,
                    ["error"] = error
                });
            }

            int nodesAfter = model.Mesh == null ? 0 : model.Mesh.Nodes.Count;
            int elementsAfter = model.Mesh == null ? 0 : model.Mesh.Elements.Count;
            bool pass = names.Length > 0 && rows.All(x => (bool?)x["produced_mesh"] == true);

            JObject report = new JObject {
                ["release"] = "C10.20.13",
                ["purpose"] = "ANSYS tutorial exact-geometry import/mesh qualification",
                ["source_file"] = _args != null && _args.Length > 0 ? Path.GetFileName(_args[0]) : null,
                ["geometry_part_count"] = model.Geometry == null ? 0 : model.Geometry.Parts.Count,
                ["mesh_candidate_count"] = names.Length,
                ["candidate_names"] = new JArray(names),
                ["candidate_types"] = new JArray(types),
                ["nodes_before"] = nodesBefore,
                ["nodes_after"] = nodesAfter,
                ["elements_before"] = elementsBefore,
                ["elements_after"] = elementsAfter,
                ["parts"] = rows,
                ["pass"] = pass,
                ["fea_values_invented"] = false
            };
            File.WriteAllText(Path.Combine(directory, "tutorial-geometry-audit.json"),
                              report.ToString(Formatting.Indented));
            if (!pass)
                throw new InvalidOperationException("One or more exact ANSYS tutorial geometry parts failed native meshing.");
        }

'@
$a=Replace-Required $a $signature ($helpers+$signature)
Set-Content $auditPath $a -Encoding UTF8

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u=(Get-Content $uiPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
$call='                StartAsterMaxC1020WorkflowConformanceAudit();'
$u=Replace-Required $u $call ($call+$lf+'                StartAsterMaxC10213TutorialGeometryAudit();')
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.20.13 exact ANSYS tutorial geometry audit applied.' -ForegroundColor Green
