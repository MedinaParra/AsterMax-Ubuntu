param([string]$Root)
$ErrorActionPreference='Stop'
$main=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$controller=Join-Path $Root 'PrePoMax/Controller.cs'
$globals=Join-Path $Root 'PrePoMax/Globals.cs'
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'

# Product captions are not the native binary file-format version.
$g=Get-Content $globals -Raw
$g=$g.Replace('AsterMax Mechanical — Native PMV','AsterMax Mechanical C9.76')
Set-Content $globals $g -Encoding UTF8
$c=Get-Content $controller -Raw
foreach($anchor in @('Encoding.ASCII.GetBytes(Globals.ProgramName)','fileVersion != Globals.ProgramName')){
 if(-not $c.Contains($anchor)){throw "Project format anchor missing: $anchor"}
}
$c=$c.Replace('Encoding.ASCII.GetBytes(Globals.ProgramName)','Encoding.ASCII.GetBytes("AsterMax v1.4.0")')
$c=$c.Replace('fileVersion != Globals.ProgramName','fileVersion != "AsterMax v1.4.0" && fileVersion != "PrePoMax v1.4.0"')
Set-Content $controller $c -Encoding UTF8
$m=Get-Content $main -Raw
$m=$m.Replace('PrePoMax files','AsterMax projects')
$m=$m.Replace('PrePoMax history','AsterMax history')
Set-Content $main $m -Encoding UTF8

$ui=Get-Content $uiPath -Raw
$ui=$ui.Replace('using System;','using System;' + [Environment]::NewLine + 'using CaeGlobals;' + [Environment]::NewLine + 'using CaeModel;' + [Environment]::NewLine + 'using CaeMesh;')
$ui=$ui.Replace('TET4 baseline • TET10 next gate','Linear and second-order volume meshes')
$anchor='            Controls.Add(ribbon);'
$replacement=@'
            ribbon.SelectedIndexChanged += (sender, eventArgs) =>
                AsterMaxSelectWorkspace(ribbon.SelectedTab.Text);
            Controls.Add(ribbon);
'@
if(-not $ui.Contains($anchor)){throw 'Ribbon selection anchor missing'}
$ui=$ui.Replace($anchor,$replacement)
$anchor='        private void PolishNativeWorkspace()'
$methods=@'
        private void AsterMaxSelectWorkspace(string tab)
        {
            if (_controller == null || !_controller.ModelInitialized) return;
            if (tab == "Geometry" || tab == "Mesh")
                _controller.CurrentView = ViewGeometryModelResults.Geometry;
            else if (tab == "Model" || tab == "Connections" || tab == "Environment" || tab == "Solution")
                _controller.CurrentView = ViewGeometryModelResults.Model;
            else if (tab == "Results" && _controller.ResultsInitialized)
                _controller.CurrentView = ViewGeometryModelResults.Results;
        }

        private string AsterMaxProjectMeshHash()
        {
            using (var stream = new System.IO.MemoryStream())
            using (var writer = new System.IO.BinaryWriter(stream)) {
                writer.Write(_controller.Model.UnitSystem.UnitSystemType.ToString());
                foreach (var mesh in new CaeMesh.FeMesh[] { _controller.Model.Geometry, _controller.Model.Mesh }) {
                    writer.Write(mesh.Parts.Count);
                    var nodeIds = new System.Collections.Generic.List<int>(mesh.Nodes.Keys);
                    nodeIds.Sort();
                    writer.Write(nodeIds.Count);
                    foreach (int id in nodeIds) {
                        var node = mesh.Nodes[id];
                        writer.Write(id); writer.Write(node.X); writer.Write(node.Y); writer.Write(node.Z);
                    }
                    var elementIds = new System.Collections.Generic.List<int>(mesh.Elements.Keys);
                    elementIds.Sort();
                    writer.Write(elementIds.Count);
                    foreach (int id in elementIds) {
                        var element = mesh.Elements[id];
                        writer.Write(id); writer.Write(element.PartId);
                        writer.Write(element.GetType().FullName);
                        writer.Write(element.NodeIds.Length);
                        foreach (int nodeId in element.NodeIds) writer.Write(nodeId);
                    }
                }
                writer.Flush();
                using (var sha = System.Security.Cryptography.SHA256.Create())
                    return BitConverter.ToString(sha.ComputeHash(stream.ToArray())).Replace("-", "").ToLowerInvariant();
            }
        }

'@
if(-not $ui.Contains($anchor)){throw 'Workspace methods anchor missing'}
$ui=$ui.Replace($anchor,$methods+$anchor)
$ui=$ui.Replace('            System.Threading.Tasks.Task<bool> meshTask = null;','            System.Threading.Tasks.Task<bool> meshTask = null;' + [Environment]::NewLine + '            System.Threading.Tasks.Task<bool> projectTask = null;')
$anchor='                            AsterMaxSmokeTrace.Stage(_args, "volume_mesh_completed");'
$replacement=@'
                            if (projectTask == null) {
                                AsterMaxSelectWorkspace("Mesh");
                                if (_controller.CurrentView != ViewGeometryModelResults.Geometry || !tsmiCreateMesh.Enabled)
                                    throw new Exception("Mesh ribbon did not activate native geometry commands");
                                AsterMaxSelectWorkspace("Model");
                                if (_controller.CurrentView != ViewGeometryModelResults.Model)
                                    throw new Exception("Model ribbon did not activate native model workspace");
                                string expectedHash = AsterMaxProjectMeshHash();
                                string projectPath = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(reportPath), "AsterMax revision.pmx");
                                AsterMaxSmokeTrace.Stage(_args, "project_roundtrip_started");
                                projectTask = System.Threading.Tasks.Task.Run(() => {
                                    _controller.SaveToPmx(projectPath);
                                    if (!System.IO.File.Exists(projectPath)) throw new Exception("Project was not saved");
                                    _controller.Open(projectPath);
                                    if (AsterMaxProjectMeshHash() != expectedHash)
                                        throw new Exception("Geometry, mesh connectivity or units changed after reopen");
                                    return true;
                                });
                                return;
                            }
                            if (!projectTask.IsCompleted) return;
                            if (!projectTask.GetAwaiter().GetResult()) throw new Exception("Project roundtrip failed");
                            AsterMaxSmokeTrace.Stage(_args, "project_roundtrip_passed");
                            AsterMaxSmokeTrace.Stage(_args, "volume_mesh_completed");
'@
if(-not $ui.Contains($anchor)){throw 'Roundtrip smoke anchor missing'}
$ui=$ui.Replace($anchor,$replacement)
$anchor='                                "\"native_exe\":\"AsterMax Mechanical.exe\"," +'
$replacement=@'
                                "\"project_roundtrip\":true," +
                                "\"workspace_navigation\":true," +
                                "\"mesh_geometry_sha256\":\"" + AsterMaxProjectMeshHash() + "\"," +
                                "\"native_exe\":\"AsterMax Mechanical.exe\"," +
'@
if(-not $ui.Contains($anchor)){throw 'Roundtrip JSON anchor missing'}
$ui=$ui.Replace($anchor,$replacement)
Set-Content $uiPath $ui -Encoding UTF8
