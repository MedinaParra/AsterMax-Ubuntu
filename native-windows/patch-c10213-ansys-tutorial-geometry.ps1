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
            const string auditPrefix = "--astermax-tutorial-audit=";
            const string inputPrefix = "--astermax-tutorial-input=";
            string[] commandLine = Environment.GetCommandLineArgs();
            string auditArg = commandLine.FirstOrDefault(x => x.StartsWith(auditPrefix, StringComparison.OrdinalIgnoreCase));
            string inputArg = commandLine.FirstOrDefault(x => x.StartsWith(inputPrefix, StringComparison.OrdinalIgnoreCase));
            if (auditArg == null) return;

            string directory = auditArg.Substring(auditPrefix.Length).Trim('"');
            string inputPath = inputArg == null ? null : inputArg.Substring(inputPrefix.Length).Trim('"');
            Directory.CreateDirectory(directory);

            var timer = new Timer { Interval = 1000 };
            timer.Tick += async (sender, args) =>
            {
                timer.Stop();
                try
                {
                    // The normal PrePoMax command-line import starts from FrmMain_Shown while
                    // some centering/message-box infrastructure may not yet own an HWND.
                    // Tutorial qualification therefore imports from this deferred UI callback,
                    // after the main form and VTK controls are fully created.
                    if (!IsHandleCreated)
                    {
                        timer.Start();
                        return;
                    }
                    if (String.IsNullOrWhiteSpace(inputPath) || !File.Exists(inputPath))
                        throw new FileNotFoundException("Tutorial STEP input is missing.", inputPath);

                    if (!New(ModelSpaceEnum.ThreeD, UnitSystemType.MM_TON_S_C))
                        throw new InvalidOperationException("Could not create a new mm-ton-s tutorial model.");

                    await _controller.ImportFileAsync(inputPath, false);
                    _controller.OpenedFileName = null;
                    Application.DoEvents();

                    FeModel model = _controller == null ? null : _controller.Model;
                    int geometryParts = model == null || model.Geometry == null ? 0 : model.Geometry.Parts.Count;
                    if (geometryParts <= 0)
                        throw new InvalidOperationException("Deferred tutorial STEP import completed without geometry.");

                    C10213RunTutorialGeometryAudit(directory, inputPath);
                    C1020RequestAuditExit(directory, 0);
                }
                catch (Exception ex)
                {
                    try { File.WriteAllText(Path.Combine(directory, "tutorial-geometry-error.txt"), ex.ToString()); }
                    catch { }
                    C1020RequestAuditExit(directory, 1);
                }
                finally
                {
                    timer.Dispose();
                }
            };
            timer.Start();
        }

        private void C10213RunTutorialGeometryAudit(string directory, string inputPath)
        {
            FeModel model = _controller.Model;
            var candidates = _controller.GetGeometryPartsWithoutSubParts();
            string[] names = candidates == null ? new string[0] : candidates.Select(x => x.Name).ToArray();
            string[] types = candidates == null ? new string[0] : candidates.Select(x => x.GetType().FullName).ToArray();

            var geometryInventory = new JArray();
            if (model.Geometry != null && model.Geometry.Parts != null)
            {
                foreach (var geometryEntry in model.Geometry.Parts)
                {
                    BasePart geometryPart = geometryEntry.Value;
                    var faceRows = new JArray();
                    VisualizationData visualization = geometryPart.Visualization;
                    if (visualization != null && visualization.CellIdsByFace != null)
                    {
                        for (int faceId = 0; faceId < visualization.FaceCount; faceId++)
                        {
                            HashSet<int> nodeIds = visualization.GetNodeIdsBySurface(faceId);
                            var faceNodes = nodeIds.Where(id => model.Geometry.Nodes.ContainsKey(id))
                                                   .Select(id => model.Geometry.Nodes[id]).ToArray();
                            double minX = faceNodes.Length == 0 ? Double.NaN : faceNodes.Min(n => n.X);
                            double minY = faceNodes.Length == 0 ? Double.NaN : faceNodes.Min(n => n.Y);
                            double minZ = faceNodes.Length == 0 ? Double.NaN : faceNodes.Min(n => n.Z);
                            double maxX = faceNodes.Length == 0 ? Double.NaN : faceNodes.Max(n => n.X);
                            double maxY = faceNodes.Length == 0 ? Double.NaN : faceNodes.Max(n => n.Y);
                            double maxZ = faceNodes.Length == 0 ? Double.NaN : faceNodes.Max(n => n.Z);
                            faceRows.Add(new JObject {
                                ["face_id"] = faceId,
                                ["area"] = visualization.FaceAreas != null && faceId < visualization.FaceAreas.Length
                                    ? visualization.FaceAreas[faceId] : Double.NaN,
                                ["type"] = visualization.FaceTypes != null && faceId < visualization.FaceTypes.Length
                                    ? visualization.FaceTypes[faceId].ToString() : null,
                                ["node_count"] = nodeIds.Count,
                                ["bounds"] = new JArray(minX, minY, minZ, maxX, maxY, maxZ)
                            });
                        }
                    }
                    geometryInventory.Add(new JObject {
                        ["name"] = geometryPart.Name,
                        ["type"] = geometryPart.GetType().FullName,
                        ["part_type"] = geometryPart.PartType.ToString(),
                        ["face_count"] = visualization == null || visualization.CellIdsByFace == null ? 0 : visualization.FaceCount,
                        ["faces"] = faceRows
                    });
                }
            }

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
            var meshInventory = new JArray();
            if (model.Mesh != null && model.Mesh.Parts != null)
            {
                foreach (var meshEntry in model.Mesh.Parts)
                {
                    BasePart meshPart = meshEntry.Value;
                    meshInventory.Add(new JObject {
                        ["name"] = meshPart.Name,
                        ["type"] = meshPart.GetType().FullName,
                        ["part_type"] = meshPart.PartType.ToString(),
                        ["nodes"] = meshPart.NodeLabels == null ? 0 : meshPart.NodeLabels.Length,
                        ["elements"] = meshPart.Labels == null ? 0 : meshPart.Labels.Length
                    });
                }
            }
            bool pass = names.Length > 0 && rows.All(x => (bool?)x["produced_mesh"] == true);

            JObject report = new JObject {
                ["release"] = "C10.20.13",
                ["purpose"] = "ANSYS tutorial exact-geometry import/mesh qualification",
                ["source_file"] = Path.GetFileName(inputPath),
                ["source_path"] = inputPath,
                ["geometry_part_count"] = model.Geometry == null ? 0 : model.Geometry.Parts.Count,
                ["geometry_inventory"] = geometryInventory,
                ["mesh_part_count"] = model.Mesh == null || model.Mesh.Parts == null ? 0 : model.Mesh.Parts.Count,
                ["mesh_inventory"] = meshInventory,
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
