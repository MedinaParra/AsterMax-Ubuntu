param([string]$Root)
$ErrorActionPreference='Stop'

function Replace-Required([string]$Text,[string]$Old,[string]$New) {
    $lf=[string][char]10; $cr=[string][char]13
    $Text=$Text.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $Old=$Old.Replace($cr+$lf,$lf).Replace($cr,$lf)
    $New=$New.Replace($cr+$lf,$lf).Replace($cr,$lf)
    if(-not $Text.Contains($Old)){ throw "C10.20.11 mesh telemetry anchor missing: $Old" }
    return $Text.Replace($Old,$New)
}

# Expose the actual native NetGen process exit code. This is diagnostic state only.
$netgenPath=Join-Path $Root 'CaeJob/NetgenJob.cs'
$lf=[string][char]10; $cr=[string][char]13
$n=(Get-Content $netgenPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)

$n=Replace-Required $n '        [NonSerialized] private object _myLock;' @'
        [NonSerialized] private object _myLock;
        [NonSerialized] private int? _asterMaxExitCode;
'@

$n=Replace-Required $n '        public JobStatus JobStatus { get { return _jobStatus; } }' @'
        public JobStatus JobStatus { get { return _jobStatus; } }
        public int? AsterMaxExitCode { get { return _asterMaxExitCode; } }
'@

$n=Replace-Required $n '            _jobStatus = JobStatus.Running;' @'
            _asterMaxExitCode = null;
            _jobStatus = JobStatus.Running;
'@

$n=Replace-Required $n '                        int exitCode = _exe.ExitCode;
                        AddDataToOutput("NetGen process exit code: " + exitCode);
                        _jobStatus = exitCode == 0 ? JobStatus.OK : JobStatus.Failed;' @'
                        int exitCode = _exe.ExitCode;
                        _asterMaxExitCode = exitCode;
                        AddDataToOutput("NetGen process exit code: " + exitCode);
                        _jobStatus = exitCode == 0 ? JobStatus.OK : JobStatus.Failed;
'@
Set-Content $netgenPath $n -Encoding UTF8

# Record a terminal meshing signal from the real Controller.CreateMesh worker.
$controllerPath=Join-Path $Root 'PrePoMax/Controller.cs'
$c=(Get-Content $controllerPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
if(-not $c.Contains('using System.Threading;'))
{
    $c=Replace-Required $c 'using System.Threading.Tasks;' "using System.Threading.Tasks;`nusing System.Threading;"
}
if(-not $c.Contains('using System.Diagnostics;'))
{
    $c=Replace-Required $c 'using System.ComponentModel;' "using System.ComponentModel;`nusing System.Diagnostics;"
}

$c=Replace-Required $c '        protected NetgenJob _netgenJob;' @'
        protected NetgenJob _netgenJob;
        [NonSerialized] protected ManualResetEventSlim _asterMaxMeshAuditTerminal;
        [NonSerialized] protected string _asterMaxLastMeshRoute;
        [NonSerialized] protected string _asterMaxLastMeshJobStatus;
        [NonSerialized] protected int? _asterMaxLastMeshExitCode;
        [NonSerialized] protected int? _asterMaxLastBrepExitCode;
        [NonSerialized] protected bool _asterMaxLastMeshGenerationSucceeded;
        [NonSerialized] protected bool _asterMaxLastMeshImportSucceeded;
        [NonSerialized] protected string _asterMaxLastMeshError;
        [NonSerialized] protected Stopwatch _asterMaxLastMeshStopwatch;
'@

$meshIdle=@'
        public bool MeshJobIdle
        {
            get
            {
                if (_netgenJob != null && _netgenJob.JobStatus == JobStatus.Running) return false;
                else return true;
            }
        }
'@
$meshAudit=@'
        public bool MeshJobIdle
        {
            get
            {
                if (_netgenJob != null && _netgenJob.JobStatus == JobStatus.Running) return false;
                else return true;
            }
        }
        private ManualResetEventSlim AsterMaxMeshAuditTerminal
        {
            get
            {
                if (_asterMaxMeshAuditTerminal == null) _asterMaxMeshAuditTerminal = new ManualResetEventSlim(false);
                return _asterMaxMeshAuditTerminal;
            }
        }
        public void AsterMaxResetMeshAudit()
        {
            AsterMaxMeshAuditTerminal.Reset();
            _asterMaxLastMeshRoute = null;
            _asterMaxLastMeshJobStatus = null;
            _asterMaxLastMeshExitCode = null;
            _asterMaxLastBrepExitCode = null;
            _asterMaxLastMeshGenerationSucceeded = false;
            _asterMaxLastMeshImportSucceeded = false;
            _asterMaxLastMeshError = null;
            _asterMaxLastMeshStopwatch = Stopwatch.StartNew();
        }
        public bool AsterMaxWaitMeshAudit(int milliseconds)
        {
            return AsterMaxMeshAuditTerminal.Wait(milliseconds);
        }
        public string AsterMaxLastMeshRoute { get { return _asterMaxLastMeshRoute; } }
        public string AsterMaxLastMeshJobStatus { get { return _asterMaxLastMeshJobStatus; } }
        public int? AsterMaxLastMeshExitCode { get { return _asterMaxLastMeshExitCode; } }
        public int? AsterMaxLastBrepExitCode { get { return _asterMaxLastBrepExitCode; } }
        public bool AsterMaxLastMeshGenerationSucceeded { get { return _asterMaxLastMeshGenerationSucceeded; } }
        public bool AsterMaxLastMeshImportSucceeded { get { return _asterMaxLastMeshImportSucceeded; } }
        public string AsterMaxLastMeshError { get { return _asterMaxLastMeshError; } }
        public double AsterMaxLastMeshDurationMs
        {
            get { return _asterMaxLastMeshStopwatch == null ? 0 : _asterMaxLastMeshStopwatch.Elapsed.TotalMilliseconds; }
        }
'@
$c=Replace-Required $c $meshIdle $meshAudit

$createOld=@'
        public bool CreateMesh(string partName)
        {
            GeometryPart part = (GeometryPart)_model.Geometry.Parts[partName];
            //
            if (part.CADFileData == null) return CreateMeshFromStl(part);
            else return CreateMeshFromBrep(part);
        }
'@
$createNew=@'
        public bool CreateMesh(string partName)
        {
            bool auditMesh = !String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("ASTERMAX_C1020_AUDIT_DIR"));
            if (auditMesh && (_asterMaxLastMeshStopwatch == null || !_asterMaxLastMeshStopwatch.IsRunning))
                AsterMaxResetMeshAudit();
            try
            {
                GeometryPart part = (GeometryPart)_model.Geometry.Parts[partName];
                //
                if (part.CADFileData == null)
                {
                    if (auditMesh && String.IsNullOrWhiteSpace(_asterMaxLastMeshRoute)) _asterMaxLastMeshRoute = "STL";
                    return CreateMeshFromStl(part);
                }
                else
                {
                    if (auditMesh) _asterMaxLastMeshRoute = "BREP";
                    return CreateMeshFromBrep(part);
                }
            }
            catch (Exception ex)
            {
                if (auditMesh) _asterMaxLastMeshError = ex.ToString();
                throw;
            }
            finally
            {
                if (auditMesh)
                {
                    if (_netgenJob != null)
                    {
                        _asterMaxLastMeshJobStatus = _netgenJob.JobStatus.ToString();
                        _asterMaxLastMeshExitCode = _netgenJob.AsterMaxExitCode;
                    }
                    if (_asterMaxLastMeshStopwatch != null) _asterMaxLastMeshStopwatch.Stop();
                    AsterMaxMeshAuditTerminal.Set();
                }
            }
        }
'@
$c=Replace-Required $c $createOld $createNew

$stlOld=@'
            _netgenJob.Submit();
            // Job completed
            if (_netgenJob.JobStatus == JobStatus.OK)
            {
                ImportGeneratedMesh(volFileName, part, false);
                return true;
            }
            else return false;
'@
$stlNew=@'
            _netgenJob.Submit();
            // Job completed
            bool auditMesh = !String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("ASTERMAX_C1020_AUDIT_DIR"));
            if (_netgenJob.JobStatus == JobStatus.OK)
            {
                if (auditMesh)
                {
                    _asterMaxLastMeshGenerationSucceeded = true;
                    if (String.IsNullOrWhiteSpace(_asterMaxLastMeshRoute)) _asterMaxLastMeshRoute = "STL";
                }
                try
                {
                    ImportGeneratedMesh(volFileName, part, false);
                    if (auditMesh) _asterMaxLastMeshImportSucceeded = true;
                    return true;
                }
                catch
                {
                    if (auditMesh) _asterMaxLastMeshImportSucceeded = false;
                    throw;
                }
            }
            else
            {
                if (auditMesh) _asterMaxLastMeshGenerationSucceeded = false;
                return false;
            }
'@
$c=Replace-Required $c $stlOld $stlNew

# C10.20.8 has already inserted the BREP -> STL fallback by the time this patch runs.
$brepOld=@'
            _netgenJob.Submit();
            // Job completed
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
'@
$brepNew=@'
            _netgenJob.Submit();
            // Job completed
            bool auditMesh = !String.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("ASTERMAX_C1020_AUDIT_DIR"));
            if (auditMesh) _asterMaxLastBrepExitCode = _netgenJob.AsterMaxExitCode;
            if (_netgenJob.JobStatus == JobStatus.OK && File.Exists(volFileName) && new FileInfo(volFileName).Length > 0)
            {
                if (auditMesh) _asterMaxLastMeshGenerationSucceeded = true;
                //bool convertToSecondOrder = meshingParameters.SecondOrder && !meshingParameters.MidsideNodesOnGeometry;
                try
                {
                    ImportGeneratedMesh(volFileName, part, true);
                    if (auditMesh) _asterMaxLastMeshImportSucceeded = true;
                    return true;
                }
                catch
                {
                    if (auditMesh) _asterMaxLastMeshImportSucceeded = false;
                    throw;
                }
            }

            if (auditMesh)
            {
                _asterMaxLastMeshGenerationSucceeded = false;
                _asterMaxLastMeshRoute = "STL_FALLBACK";
            }
            _form.WriteDataToOutput("BREP_MESH failed for part '" + part.Name +
                                    "'. Retrying with the existing STL_MESH path.");
            bool stlFallbackOk = CreateMeshFromSolidStl(part);
            if (stlFallbackOk)
            {
                _form.WriteDataToOutput("STL_MESH fallback completed for part '" + part.Name + "'.");
                return true;
            }
'@
$c=Replace-Required $c $brepOld $brepNew
Set-Content $controllerPath $c -Encoding UTF8

# Replace polling-based audit wait with a terminal signal from Controller.CreateMesh.
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs'
$a=(Get-Content $auditPath -Raw).Replace($cr+$lf,$lf).Replace($cr,$lf)
$pattern='(?s)        private JObject C10208ExerciseRealGenerateMesh\(string directory,FeModel model\).*?(?=\n        private JObject C10208SmokeResultCommand)'
if(-not [regex]::IsMatch($a,$pattern)){ throw 'C10.20.11 C10208ExerciseRealGenerateMesh method anchor missing.' }
$method=@'
        private async Task<JObject> C10208ExerciseRealGenerateMesh(string directory,FeModel model)
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

            _controller.AsterMaxResetMeshAudit();
            var monotonic=System.Diagnostics.Stopwatch.StartNew();
            C10208ClickRibbonButton("Mesh","Generate Mesh");
            // Controller mesh import uses UI-thread Invoke. Never block that thread
            // while waiting for the worker: resume on the WinForms context after await.
            bool terminalObserved=await Task.Run(() => _controller.AsterMaxWaitMeshAudit(180000));
            monotonic.Stop();

            // Allow the command's UI continuation to publish its Ready state before
            // the audit mutates the model. The timeout remains a separate failure.
            var readyDeadline=System.Diagnostics.Stopwatch.StartNew();
            while (terminalObserved && IsStateWorking() && readyDeadline.ElapsedMilliseconds < 10000)
                await Task.Delay(25);

            bool deadlineExpired=!terminalObserved;
            int ribbonNodesAfter=model.Mesh==null?0:model.Mesh.Nodes.Count;
            int ribbonElementsAfter=model.Mesh==null?0:model.Mesh.Elements.Count;
            bool ribbonProducedMesh=ribbonNodesAfter>nodesBefore && ribbonElementsAfter>elementsBefore;
            string terminalJobStatus=_controller.AsterMaxLastMeshJobStatus;
            int? processExitCode=_controller.AsterMaxLastMeshExitCode;
            int? brepExitCode=_controller.AsterMaxLastBrepExitCode;
            string route=_controller.AsterMaxLastMeshRoute;
            bool generationSucceeded=_controller.AsterMaxLastMeshGenerationSucceeded;
            bool importSucceeded=_controller.AsterMaxLastMeshImportSucceeded;
            string terminalError=_controller.AsterMaxLastMeshError;
            bool generationFailure=terminalObserved && !generationSucceeded;
            bool importFailure=terminalObserved && generationSucceeded && !importSucceeded;

            bool pass=geometryParts==1 && candidateNames.Length==1 && terminalObserved && !deadlineExpired && !IsStateWorking() &&
                      generationSucceeded && importSucceeded && ribbonProducedMesh;
            JObject result=new JObject {
                ["tab"]="Mesh",["command"]="Generate Mesh",["pass"]=pass,
                ["geometry_parts"]=geometryParts,
                ["mesh_candidate_count"]=candidateNames.Length,
                ["mesh_candidate_names"]=new JArray(candidateNames),
                ["mesh_candidate_types"]=new JArray(candidateTypes),
                ["meshing_parameter_count"]=meshingParameterCount,
                ["deadline_expired"]=deadlineExpired,
                ["terminal_signal_observed"]=terminalObserved,
                ["terminal_job_status"]=terminalJobStatus,
                ["process_exit_code"]=processExitCode,
                ["brep_process_exit_code"]=brepExitCode,
                ["mesh_route"]=route,
                ["duration_ms"]=monotonic.Elapsed.TotalMilliseconds,
                ["controller_duration_ms"]=_controller.AsterMaxLastMeshDurationMs,
                ["generation_succeeded"]=generationSucceeded,
                ["import_succeeded"]=importSucceeded,
                ["generation_failure"]=generationFailure,
                ["import_failure"]=importFailure,
                ["terminal_error"]=terminalError,
                ["nodes_before"]=nodesBefore,
                ["nodes_after"]=ribbonNodesAfter,
                ["elements_before"]=elementsBefore,
                ["elements_after"]=ribbonElementsAfter,
                ["mesh_created"]=ribbonProducedMesh,
                ["base_directory"]=baseDirectory,
                ["work_directory"]=workDirectory,
                ["work_directory_present"]=!String.IsNullOrWhiteSpace(workDirectory) && Directory.Exists(workDirectory),
                ["netgen_exe"]=netgenExe,
                ["netgen_exe_present"]=File.Exists(netgenExe),
                ["execution"]="REAL_NATIVE_GENERATE_MESH_RIBBON_COMMAND",
                ["synchronization"]="CONTROLLER_TERMINAL_SIGNAL",
                ["fixture_replacement_follows"]=true,
                ["evidence"]=pass ?
                    "Generate Mesh produced and imported a non-empty native mesh. This command smoke is distinct from the deterministic HE8 solver fixture that follows." :
                    "Generate Mesh did not reach a verified terminal generation/import state; see explicit deadline/job/exit/route fields."
            };
            File.WriteAllText(Path.Combine(directory,"mesh-command-diagnostic.json"),result.ToString(Formatting.Indented));
            return result;
        }
'@
$a=[regex]::Replace($a,$pattern,$method.TrimEnd(),1)
$a=Replace-Required $a '            timer.Tick += (s, e) =>' '            timer.Tick += async (s, e) =>'
$a=Replace-Required $a '                    ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);' '                    await ExecuteAsterMaxC1020WorkflowConformanceAudit(directory);'
$a=Replace-Required $a '        private void ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)' '        private async Task ExecuteAsterMaxC1020WorkflowConformanceAudit(string directory)'
$a=Replace-Required $a 'C10208RecordCommandSmoke(directory, commandSmoke, C10208ExerciseRealGenerateMesh(directory, model));' 'C10208RecordCommandSmoke(directory, commandSmoke, await C10208ExerciseRealGenerateMesh(directory, model));'
Set-Content $auditPath $a -Encoding UTF8

# Native close/command guards use the status text as a busy sentinel. Retain
# solve diagnostics in the tooltip, but release that sentinel on every outcome.
$solvePath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeSolveTransaction.cs'
$s=[regex]::Replace((Get-Content $solvePath -Raw),"\r\n?","`n")
$s=Replace-Required $s '                _asterMaxSolveInProgress=false;' @'
                _asterMaxSolveInProgress=false;
                if(!IsDisposed && !Disposing && tsslState.Text.StartsWith("AsterMax Solve:", StringComparison.Ordinal))
                {
                    tsslState.ToolTipText=tsslState.Text;
                    tsslState.Text=CaeGlobals.Globals.ReadyText;
                }
'@
$s=Replace-Required $s 'tsslState.Text="AsterMax Solve: no active solve to cancel";' 'tsslState.ToolTipText="AsterMax Solve: no active solve to cancel";'
Set-Content $solvePath $s -Encoding UTF8

$buttonPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxButtonAudit.cs'
$b=[regex]::Replace((Get-Content $buttonPath -Raw),"\r\n?","`n")
$b=Replace-Required $b 'tsslState.Text="AsterMax Solve: model editing is locked while the solve is running";' 'tsslState.ToolTipText="AsterMax Solve: model editing is locked while the solve is running";'
Set-Content $buttonPath $b -Encoding UTF8

Write-Host 'C10.20.11 terminal-signal Generate Mesh telemetry applied.' -ForegroundColor Green
