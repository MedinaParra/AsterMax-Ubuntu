param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    if(-not $Text.Contains($Old)){ throw "C10.20.8 anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

$mainPath=Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
$m=[regex]::Replace((Get-Content $mainPath -Raw),"\\r\\n?","\\n")
$meshingPopup='                    MessageBoxes.ShowError("Errors occurred during meshing. Please check the output window.");'
$meshingAudit='                    if(!_asterMaxUiAuditMode) MessageBoxes.ShowError("Errors occurred during meshing. Please check the output window.");'
$m=Replace-Required $m $meshingPopup $meshingAudit
Set-Content $mainPath $m -Encoding UTF8

# Preserve native NetGen meshing output during the C10.20 audit.
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$controller=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$netgenOutputOld=@'
        void netgenJobMeshing_AppendOutput(string data)
        {
            _form.WriteDataToOutput(data);
        }
'@
$netgenOutputNew=@'
        void netgenJobMeshing_AppendOutput(string data)
        {
            _form.WriteDataToOutput(data);
            try
            {
                string auditDirectory=Environment.GetEnvironmentVariable("ASTERMAX_C1020_AUDIT_DIR");
                if(!String.IsNullOrWhiteSpace(auditDirectory))
                {
                    Directory.CreateDirectory(auditDirectory);
                    File.AppendAllText(Path.Combine(auditDirectory,"netgen-mesh-output.log"),
                        DateTime.UtcNow.ToString("O")+" "+data+Environment.NewLine);
                }
            }
            catch { }
        }
'@
$netgenOutputOld=[regex]::Replace($netgenOutputOld,"\r\n?","`n")
$netgenOutputNew=[regex]::Replace($netgenOutputNew,"\r\n?","`n")
if($controller.Contains($netgenOutputOld))
{
    $controller=$controller.Replace($netgenOutputOld,$netgenOutputNew)
}
elseif(-not $controller.Contains('netgen-mesh-output.log'))
{
    throw 'C10.20.8 NetGen output diagnostic anchor missing.'
}
Set-Content $controllerPath $controller -Encoding UTF8

# NetgenJob must not report a crashed native mesher as OK.
$netgenJobPath=Join-Path $Root 'CaeJob/NetgenJob.cs'
$netgenJob=[regex]::Replace((Get-Content $netgenJobPath -Raw),"\r\n?","`n")
$netgenStatusOld=@'
                if (_exe.WaitForExit(ms) && _outputWaitHandle.WaitOne(ms) && _errorWaitHandle.WaitOne(ms))
                {
                    // Process completed. Check process.ExitCode here.
                    // after Kill() _jobStatus is Killed
                    if (_jobStatus == JobStatus.Running) _jobStatus = JobStatus.OK;
                }
'@
$netgenStatusNew=@'
                if (_exe.WaitForExit(ms) && _outputWaitHandle.WaitOne(ms) && _errorWaitHandle.WaitOne(ms))
                {
                    // A native crash must never be promoted to a successful mesh job.
                    if (_jobStatus == JobStatus.Running)
                    {
                        int exitCode = _exe.ExitCode;
                        AddDataToOutput("NetGen process exit code: " + exitCode);
                        _jobStatus = exitCode == 0 ? JobStatus.OK : JobStatus.Failed;
                    }
                }
'@
$netgenStatusOld=[regex]::Replace($netgenStatusOld,"\r\n?","`n")
$netgenStatusNew=[regex]::Replace($netgenStatusNew,"\r\n?","`n")
if($netgenJob.Contains($netgenStatusOld))
{
    $netgenJob=$netgenJob.Replace($netgenStatusOld,$netgenStatusNew)
}
elseif(-not $netgenJob.Contains('NetGen process exit code: '))
{
    throw 'C10.20.8 NetgenJob exit-code integrity anchor missing.'
}
Set-Content $netgenJobPath $netgenJob -Encoding UTF8

# BREP volume meshing can terminate in native NetGen with an access violation on otherwise
# valid CAD. Fall back to PrePoMax's existing STL_MESH production path; never synthesize a mesh.
$controller=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")
$brepReturnOld=@'
            if (_netgenJob.JobStatus == JobStatus.OK)
            {
                //bool convertToSecondOrder = meshingParameters.SecondOrder && !meshingParameters.MidsideNodesOnGeometry;
                ImportGeneratedMesh(volFileName, part, true);
                return true;
            }
            else return false;
        }
        private void CreateMeshRefinementFile
'@
$brepReturnNew=@'
            if (_netgenJob.JobStatus == JobStatus.OK && File.Exists(volFileName) && new FileInfo(volFileName).Length > 0)
            {
                //bool convertToSecondOrder = meshingParameters.SecondOrder && !meshingParameters.MidsideNodesOnGeometry;
                ImportGeneratedMesh(volFileName, part, true);
                return true;
            }

            _form.WriteDataToOutput("BREP_MESH failed for part '" + part.Name +
                                    "'. Retrying with the existing STL_MESH path.");
            bool stlFallbackOk = CreateMeshFromSolidStl(part);
            if (stlFallbackOk)
            {
                _form.WriteDataToOutput("STL_MESH fallback completed for part '" + part.Name + "'.");
                return true;
            }
            _form.WriteDataToOutput("STL_MESH fallback also failed for part '" + part.Name + "'.");
            return false;
        }
        private void CreateMeshRefinementFile
'@
$brepReturnOld=[regex]::Replace($brepReturnOld,"\r\n?","`n")
$brepReturnNew=[regex]::Replace($brepReturnNew,"\r\n?","`n")
if($controller.Contains($brepReturnOld))
{
    $controller=$controller.Replace($brepReturnOld,$brepReturnNew)
}
elseif(-not $controller.Contains('STL_MESH fallback completed for part'))
{
    throw 'C10.20.8 BREP-to-STL fallback anchor missing.'
}
Set-Content $controllerPath $controller -Encoding UTF8

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=[regex]::Replace((Get-Content $auditPath -Raw),"\r\n?","`n")

# C10.20.3-C10.20.7 changed behavior without updating the session's embedded release.
$a=$a.Replace('["release"] = "C10.20.2"','["release"] = "C10.20.8"')
$a=$a.Replace('B01-C10.20.pmx','B01-C10.20.8.pmx')

$rowsAnchor=@'
            var rows = new JArray();
            var previousStates = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
'@
$rowsNew=@'
            var rows = new JArray();
            var commandSmoke = new JArray();
            var previousStates = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
'@
$rowsAnchor=[regex]::Replace($rowsAnchor,"\r\n?","`n")
$rowsNew=[regex]::Replace($rowsNew,"\r\n?","`n")
$a=Replace-Required $a $rowsAnchor $rowsNew

$materialAnchor=@'
            FeModel model = _controller.Model;
            if (model.Materials.Count == 0)
'@
$materialNew=@'
            FeModel model = _controller.Model;
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Model", "Materials", _frmMaterial, () => model.Materials.Count));
            if (model.Materials.Count == 0)
'@
$materialAnchor=[regex]::Replace($materialAnchor,"\r\n?","`n")
$materialNew=[regex]::Replace($materialNew,"\r\n?","`n")
$a=Replace-Required $a $materialAnchor $materialNew

$meshAnchor='            C1020PopulateB01Mesh(model);'
$meshNew=@'
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Mesh", "Mesh Controls", _frmMeshingParameters,
                    () => _controller.GetMeshingParameters().Length));
            C10208RecordCommandSmoke(directory, commandSmoke, C10208ExerciseRealGenerateMesh(directory, model));
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Materiales", "Asignar seccion", _frmSection, () => model.Sections.Count));

            // The real Generate Mesh smoke proves the native command path. Replace that
            // non-deterministic tetra mesh with the controlled HE8 B01 solver fixture.
            C1020PopulateB01Mesh(model);
'@
$meshNew=[regex]::Replace($meshNew,"\r\n?","`n").TrimEnd()
$a=Replace-Required $a $meshAnchor $meshNew

$stepAnchor='            C1020PopulateB01StaticStructural(model);'
$stepNew=@'
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Environment", "Analysis Step", _frmStep,
                    () => model.StepCollection.StepsList.Count));
            C1020PopulateB01StaticStructural(model);
'@
$stepNew=[regex]::Replace($stepNew,"\r\n?","`n").TrimEnd()
$a=Replace-Required $a $stepAnchor $stepNew

$analysisAnchor='            C1020RevealOutlineNode("ax-analysis");'
$analysisNew=@'
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Environment", "Supports", _frmBoundaryCondition,
                    () => model.StepCollection.StepsList.Sum(s => s.BoundaryConditions.Count)));
            C10208RecordCommandSmoke(directory, commandSmoke,
                C10208SmokeEditorCommand("Environment", "Loads", _frmLoad,
                    () => model.StepCollection.StepsList.Sum(s => s.Loads.Count)));
            C1020RevealOutlineNode("ax-analysis");
'@
$analysisNew=[regex]::Replace($analysisNew,"\r\n?","`n").TrimEnd()
$a=Replace-Required $a $analysisAnchor $analysisNew

$resultAnchor=@'
            _modelTree.SelectAsterMaxResultField(resultField);
            Application.DoEvents();
            C1020CaptureStage(directory, rows, previousStates, 9, "results", "Results", "results",
'@
$resultNew=@'
            _modelTree.SelectAsterMaxResultField(resultField);
            Application.DoEvents();
            foreach (string command in new[] { "Contours", "Deformed" })
                C10208RecordCommandSmoke(directory, commandSmoke, C10208SmokeResultCommand("Results", command));
            foreach (string command in new[] { "Fit", "Isometric" })
                C10208RecordCommandSmoke(directory, commandSmoke, C10208SmokeResultCommand("View", command));
            C1020CaptureStage(directory, rows, previousStates, 9, "results", "Results", "results",
'@
$resultAnchor=[regex]::Replace($resultAnchor,"\r\n?","`n")
$resultNew=[regex]::Replace($resultNew,"\r\n?","`n")
$a=Replace-Required $a $resultAnchor $resultNew

$sessionAnchor=@'
                    ["solver"] = "native Windows Code_Aster",
                    ["fea_values_invented"] = false,
                    ["rows"] = rows,
'@
$sessionNew=@'
                    ["solver"] = "native Windows Code_Aster",
                    ["fea_values_invented"] = false,
                    ["command_execution_smoke"] = commandSmoke,
                    ["rows"] = rows,
'@
$sessionAnchor=[regex]::Replace($sessionAnchor,"\r\n?","`n")
$sessionNew=[regex]::Replace($sessionNew,"\r\n?","`n")
$a=Replace-Required $a $sessionAnchor $sessionNew

$helperAnchor='        private void C1020ClickRibbonButton(string caption)'
$helpers=@'
        private void C10208RecordCommandSmoke(string directory,JArray rows,JObject row)
        {
            rows.Add(row);
            File.WriteAllText(Path.Combine(directory,"command-execution-smoke.json"),
                new JObject {
                    ["release"]="C10.20.8",
                    ["pass"]=rows.All(x => (bool?)x["pass"] == true),
                    ["commands"]=rows,
                    ["fea_values_invented"]=false
                }.ToString(Formatting.Indented));
            if((bool?)row["pass"]!=true)
                throw new InvalidOperationException("Functional command smoke failed: "+(string)row["command"]+
                    " | "+(string)row["evidence"]);
        }

        private JObject C10208SmokeEditorCommand(string tab,string caption,Form editor,Func<int> mutationCount)
        {
            if(editor==null) return new JObject {
                ["tab"]=tab,["command"]=caption,["pass"]=false,["evidence"]="Native editor form is null."
            };
            CloseAllForms();
            Application.DoEvents();
            int before=mutationCount();
            C10208ClickRibbonButton(tab,caption);
            DateTime deadline=DateTime.UtcNow.AddSeconds(5);
            while(!editor.Visible && DateTime.UtcNow<deadline)
            {
                Application.DoEvents();
                System.Threading.Thread.Sleep(25);
            }
            bool opened=editor.Visible;
            string title=editor.Text;
            CloseAllForms();
            Application.DoEvents();
            bool hidden=!editor.Visible;
            int after=mutationCount();
            bool pass=opened && hidden && before==after;
            return new JObject {
                ["tab"]=tab,["command"]=caption,["pass"]=pass,
                ["opened_native_editor"]=opened,["editor_hidden_without_accept"]=hidden,
                ["editor_type"]=editor.GetType().FullName,["editor_title"]=title,
                ["model_count_before"]=before,["model_count_after"]=after,
                ["evidence"]=pass ? "Native editor opened and was dismissed without mutating the fixture." :
                    "Editor did not open/hide correctly or the model changed during a non-destructive smoke."
            };
        }

        private JObject C10208ExerciseRealGenerateMesh(string directory,FeModel model)
        {
            CloseAllForms();
            Application.DoEvents();
            _controller.CurrentView=ViewGeometryModelResults.Geometry;

            var candidates=_controller.GetGeometryPartsWithoutSubParts();
            string[] candidateNames=candidates==null ? new string[0] : candidates.Select(x => x.Name).ToArray();
            string[] candidateTypes=candidates==null ? new string[0] : candidates.Select(x => x.GetType().FullName).ToArray();
            int geometryParts=model.Geometry==null?0:model.Geometry.Parts.Count;
            int meshingParameterCount=_controller.GetMeshingParameters()==null?0:_controller.GetMeshingParameters().Length;
            int nodesBefore=model.Mesh==null?0:model.Mesh.Nodes.Count;
            int elementsBefore=model.Mesh==null?0:model.Mesh.Elements.Count;
            string baseDirectory=AppDomain.CurrentDomain.BaseDirectory;
            string netgenExe=Path.Combine(baseDirectory,"NetGen","NetGenMesher.exe");
            string workDirectory=null;
            try { workDirectory=_controller.Settings.GetWorkDirectory(); } catch { }

            File.WriteAllText(Path.Combine(directory,"mesh-command-preflight.json"),
                new JObject {
                    ["geometry_parts"]=geometryParts,
                    ["mesh_candidate_count"]=candidateNames.Length,
                    ["mesh_candidate_names"]=new JArray(candidateNames),
                    ["mesh_candidate_types"]=new JArray(candidateTypes),
                    ["meshing_parameter_count"]=meshingParameterCount,
                    ["base_directory"]=baseDirectory,
                    ["work_directory"]=workDirectory,
                    ["work_directory_present"]=!String.IsNullOrWhiteSpace(workDirectory) && Directory.Exists(workDirectory),
                    ["netgen_exe"]=netgenExe,
                    ["netgen_exe_present"]=File.Exists(netgenExe),
                    ["fea_values_invented"]=false
                }.ToString(Formatting.Indented));

            C10208ClickRibbonButton("Mesh","Generate Mesh");

            DateTime deadline=DateTime.UtcNow.AddSeconds(180);
            bool sawWorking=IsStateWorking();
            bool sawWorkingThenReady=false;
            while(DateTime.UtcNow<deadline)
            {
                Application.DoEvents();
                bool working=IsStateWorking();
                if(working) sawWorking=true;
                int currentElements=model.Mesh==null?0:model.Mesh.Elements.Count;
                if(currentElements>elementsBefore) break;
                if(sawWorking && !working)
                {
                    sawWorkingThenReady=true;
                    break;
                }
                System.Threading.Thread.Sleep(50);
            }

            bool timedOut=IsStateWorking() && DateTime.UtcNow>=deadline;
            int ribbonNodesAfter=model.Mesh==null?0:model.Mesh.Nodes.Count;
            int ribbonElementsAfter=model.Mesh==null?0:model.Mesh.Elements.Count;
            bool ribbonProducedMesh=ribbonNodesAfter>nodesBefore && ribbonElementsAfter>elementsBefore;

            bool directDiagnosticAttempted=false;
            bool directDiagnosticCompleted=false;
            bool directDiagnosticReturned=false;
            bool directDiagnosticProducedMesh=false;
            bool directDiagnosticTimedOut=false;
            string directDiagnosticError=null;
            int diagnosticNodesAfter=ribbonNodesAfter;
            int diagnosticElementsAfter=ribbonElementsAfter;
            if(!ribbonProducedMesh && !timedOut && candidateNames.Length==1)
            {
                directDiagnosticAttempted=true;
                try
                {
                    Task<bool> diagnosticTask=Task.Run(() => _controller.CreateMesh(candidateNames[0]));
                    DateTime diagnosticDeadline=DateTime.UtcNow.AddSeconds(120);
                    while(!diagnosticTask.IsCompleted && DateTime.UtcNow<diagnosticDeadline)
                    {
                        Application.DoEvents();
                        System.Threading.Thread.Sleep(50);
                    }
                    if(!diagnosticTask.IsCompleted)
                    {
                        directDiagnosticTimedOut=true;
                        try { _controller.StopNetGenJob(); } catch { }
                    }
                    else
                    {
                        directDiagnosticCompleted=true;
                        directDiagnosticReturned=diagnosticTask.GetAwaiter().GetResult();
                    }
                    diagnosticNodesAfter=model.Mesh==null?0:model.Mesh.Nodes.Count;
                    diagnosticElementsAfter=model.Mesh==null?0:model.Mesh.Elements.Count;
                    directDiagnosticProducedMesh=diagnosticNodesAfter>nodesBefore && diagnosticElementsAfter>elementsBefore;
                }
                catch(Exception ex)
                {
                    directDiagnosticError=ex.ToString();
                }
            }

            bool pass=geometryParts==1 && candidateNames.Length==1 && !timedOut && ribbonProducedMesh;
            JObject result=new JObject {
                ["tab"]="Mesh",["command"]="Generate Mesh",["pass"]=pass,
                ["geometry_parts"]=geometryParts,
                ["mesh_candidate_count"]=candidateNames.Length,
                ["mesh_candidate_names"]=new JArray(candidateNames),
                ["mesh_candidate_types"]=new JArray(candidateTypes),
                ["meshing_parameter_count"]=meshingParameterCount,
                ["saw_working_state"]=sawWorking,
                ["saw_working_then_ready"]=sawWorkingThenReady,
                ["timed_out"]=timedOut,
                ["nodes_before"]=nodesBefore,
                ["ribbon_nodes_after"]=ribbonNodesAfter,
                ["elements_before"]=elementsBefore,
                ["ribbon_elements_after"]=ribbonElementsAfter,
                ["ribbon_produced_mesh"]=ribbonProducedMesh,
                ["direct_diagnostic_attempted"]=directDiagnosticAttempted,
                ["direct_diagnostic_completed"]=directDiagnosticCompleted,
                ["direct_diagnostic_returned"]=directDiagnosticReturned,
                ["direct_diagnostic_produced_mesh"]=directDiagnosticProducedMesh,
                ["direct_diagnostic_timed_out"]=directDiagnosticTimedOut,
                ["direct_diagnostic_nodes_after"]=diagnosticNodesAfter,
                ["direct_diagnostic_elements_after"]=diagnosticElementsAfter,
                ["direct_diagnostic_error"]=directDiagnosticError,
                ["base_directory"]=baseDirectory,
                ["work_directory"]=workDirectory,
                ["work_directory_present"]=!String.IsNullOrWhiteSpace(workDirectory) && Directory.Exists(workDirectory),
                ["netgen_exe"]=netgenExe,
                ["netgen_exe_present"]=File.Exists(netgenExe),
                ["execution"]="REAL_NATIVE_CREATE_MESH_COMMAND",
                ["evidence"]=pass ? "Generate Mesh produced a non-empty native mesh through the real ribbon command before the deterministic HE8 fixture replaced it." :
                    "Generate Mesh did not produce a real non-empty mesh through the ribbon path; bounded direct native diagnostic evidence is attached."
            };
            File.WriteAllText(Path.Combine(directory,"mesh-command-diagnostic.json"),result.ToString(Formatting.Indented));
            return result;
        }

        private JObject C10208SmokeResultCommand(string tab,string caption)
        {
            Exception failure=null;
            try
            {
                C10208ClickRibbonButton(tab,caption);
                Application.DoEvents();
            }
            catch(Exception ex){ failure=ex; }
            bool viewport=_axEmbeddedResults!=null && _axEmbeddedResults.Visible;
            bool renderOk=viewport && _axEmbeddedResults.LastRenderError==null && !_axEmbeddedResults.LastRenderSkipped;
            bool pass=failure==null && renderOk;
            return new JObject {
                ["tab"]=tab,["command"]=caption,["pass"]=pass,
                ["integrated_viewport_visible"]=viewport,["render_ok"]=renderOk,
                ["error"]=failure==null?null:failure.Message,
                ["evidence"]=pass ? "Command executed against the live integrated results viewport." :
                    "Result/view command failed or left the integrated renderer invalid."
            };
        }

        private void C10208ClickRibbonButton(string tab,string caption)
        {
            var ribbon=Controls["asterMaxRibbon"] as TabControl;
            if(ribbon==null) throw new InvalidOperationException("AsterMax ribbon is missing.");
            TabPage page=ribbon.TabPages.Cast<TabPage>()
                .FirstOrDefault(x => String.Equals(x.Text,tab,StringComparison.Ordinal));
            if(page==null) throw new InvalidOperationException("Ribbon tab not found: "+tab);
            Button button=AxButtons(page)
                .FirstOrDefault(x => String.Equals(x.Text,caption,StringComparison.Ordinal));
            if(button==null) throw new InvalidOperationException("Ribbon command not found: "+tab+"/"+caption);
            ribbon.SelectedTab=page;
            Application.DoEvents();
            button.PerformClick();
            Application.DoEvents();
        }

'@
$helpers=[regex]::Replace($helpers,"\r\n?","`n")
$a=Replace-Required $a $helperAnchor ($helpers+$helperAnchor)
Set-Content $auditPath $a -Encoding UTF8

$crossPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceCrossChecks.cs'
$c=[regex]::Replace((Get-Content $crossPath -Raw),"\r\n?","`n")
$crossAnchor=@'
            try
            {
                bool sameInstance=_asterMaxSolveFrozenModelInstance!=null && _controller!=null &&
'@
$crossNew=@'
            try
            {
                string commandSmokePath=Path.Combine(directory,"command-execution-smoke.json");
                if(!File.Exists(commandSmokePath))
                {
                    add("command_execution_smoke","NOT_EXERCISED",
                        "Functional ribbon-command smoke artifact was not produced.",null);
                }
                else
                {
                    JObject evidence=JObject.Parse(File.ReadAllText(commandSmokePath));
                    JArray commands=evidence["commands"] as JArray;
                    bool generateMesh=commands!=null && commands.Any(x =>
                        String.Equals((string)x["command"],"Generate Mesh",StringComparison.Ordinal) &&
                        (bool?)x["pass"]==true &&
                        ((int?)x["ribbon_elements_after"] ?? (int?)x["elements_after"] ?? 0) >
                        ((int?)x["elements_before"] ?? 0));
                    bool pass=(bool?)evidence["pass"]==true && commands!=null && commands.Count>=11 && generateMesh;
                    add("command_execution_smoke",pass?"PASS":"FAIL",
                        pass ? "Workflow executed native editor, meshing and integrated-result ribbon commands." :
                               "One or more required functional ribbon commands were not executed successfully.",
                        new JObject { ["file"]="command-execution-smoke.json",["command_count"]=commands==null?0:commands.Count,
                                      ["real_generate_mesh"]=generateMesh });
                }
            }
            catch(Exception ex)
            {
                add("command_execution_smoke","FAIL",ex.Message,null);
            }

            try
            {
                bool sameInstance=_asterMaxSolveFrozenModelInstance!=null && _controller!=null &&
'@
$crossAnchor=[regex]::Replace($crossAnchor,"\r\n?","`n")
$crossNew=[regex]::Replace($crossNew,"\r\n?","`n")
$c=Replace-Required $c $crossAnchor $crossNew
Set-Content $crossPath $c -Encoding UTF8

Write-Host 'C10.20.8 functional command execution smoke audit applied.' -ForegroundColor Green
