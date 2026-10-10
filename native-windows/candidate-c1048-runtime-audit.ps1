param([string]$Root)
$ErrorActionPreference='Stop'
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$projectPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
foreach($p in @($uiPath,$projectPath)){if(!(Test-Path $p)){throw "C10.48 audit missing: $p"}}
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1048LazyEdgesAudit.cs'
$audit=@'
using System;
using System.IO;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using vtkControl;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void StartAsterMaxC1048LazyEdgesAudit()
        {
            string directory = Environment.GetEnvironmentVariable("ASTERMAX_C1048_AUDIT_DIR");
            if (String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);
            int expectedParts = 25;
            int configured;
            if (Int32.TryParse(Environment.GetEnvironmentVariable("ASTERMAX_C1048_EXPECTED_PARTS"), out configured) && configured > 0)
                expectedParts = configured;

            int ticks = 0;
            var timer = new Timer { Interval = 250 };
            timer.Tick += (s, e) =>
            {
                ticks++;
                int partCount = _controller != null && _controller.Model != null && _controller.Model.Geometry != null
                    ? _controller.Model.Geometry.Parts.Count : 0;
                bool idle = _controller != null && !IsStateWorking();
                long cameraFlushes = _vtk == null ? -1 : _vtk.AsterMaxSceneBatchCameraFlushes;
                int batchDepth = _vtk == null ? -1 : _vtk.AsterMaxSceneBatchDepth;
                long deferred = _vtk == null ? -1 : _vtk.AsterMaxDeferredElementEdgeActors;
                long materializedBefore = _vtk == null ? -1 : _vtk.AsterMaxMaterializedElementEdgeActors;
                int remainingBefore = _vtk == null ? -1 : _vtk.AsterMaxDeferredElementEdgesRemaining;
                bool sceneComplete = idle && partCount >= expectedParts && batchDepth == 0 && cameraFlushes == 1;
                if (!sceneComplete && ticks < 720) return;

                timer.Stop();
                timer.Dispose();
                var report = new JObject();
                bool pass = false;
                try
                {
                    int errorsBefore = _controller == null ? -1 : _controller.GetNumberOfErrors();
                    bool initialNoEdges = _vtk != null && _vtk.EdgesVisibility == vtkEdgesVisibility.NoEdges;
                    bool deferredPhasePass = sceneComplete && initialNoEdges && deferred > 0 &&
                                             materializedBefore == 0 && remainingBefore == deferred;

                    // EdgesVisibility setter and lazy materialization are synchronous on this UI thread.
                    if (_vtk != null) _vtk.EdgesVisibility = vtkEdgesVisibility.ElementEdges;

                    long materializedAfter = _vtk == null ? -1 : _vtk.AsterMaxMaterializedElementEdgeActors;
                    int remainingAfter = _vtk == null ? -1 : _vtk.AsterMaxDeferredElementEdgesRemaining;
                    int errorsAfter = _controller == null ? -1 : _controller.GetNumberOfErrors();
                    bool elementEdgesMode = _vtk != null && _vtk.EdgesVisibility == vtkEdgesVisibility.ElementEdges;
                    bool materializePhasePass = elementEdgesMode && materializedAfter == deferred && remainingAfter == 0;

                    // Return to the lightweight display mode to exercise the reverse visibility transition too.
                    if (_vtk != null) _vtk.EdgesVisibility = vtkEdgesVisibility.NoEdges;

                    report["release"] = "C10.48-lazy-element-edges";
                    report["expected_parts"] = expectedParts;
                    report["cad_bodies"] = partCount;
                    report["elapsed_ms_upper_bound"] = ticks * 250;
                    report["initial_edges_visibility"] = initialNoEdges ? "NoEdges" : (_vtk == null ? "NoVtk" : "Other");
                    report["deferred_edge_actors"] = deferred;
                    report["materialized_before_toggle"] = materializedBefore;
                    report["remaining_before_toggle"] = remainingBefore;
                    report["materialized_after_toggle"] = materializedAfter;
                    report["remaining_after_toggle"] = remainingAfter;
                    report["deferred_phase_pass"] = deferredPhasePass;
                    report["materialize_phase_pass"] = materializePhasePass;
                    report["controller_errors_before"] = errorsBefore;
                    report["controller_errors_after"] = errorsAfter;
                    report["batch_depth"] = batchDepth;
                    report["camera_flushes"] = cameraFlushes;
                    pass = deferredPhasePass && materializePhasePass && errorsBefore == 0 && errorsAfter == 0;
                    report["pass"] = pass;
                    if (!pass) report["error"] = "Lazy edge deferral/materialization invariants failed.";
                }
                catch(Exception ex)
                {
                    report["pass"] = false;
                    report["error"] = ex.ToString();
                }

                File.WriteAllText(Path.Combine(directory,"c1048-lazy-edges-report.json"), report.ToString(Formatting.Indented));
                Environment.ExitCode = pass ? 0 : 1;
                _c10209AuditShutdownDirectory = directory;
                BeginInvoke(new Action(() =>
                {
                    if (_controller != null) _controller.ModelChanged = false;
                    Close();
                }));
            };
            timer.Start();
        }
    }
}
'@
Set-Content $auditPath $audit -Encoding UTF8
$p=[regex]::Replace((Get-Content $projectPath -Raw),"\r\n?","`n")
if(-not $p.Contains('Forms\AsterMaxC1048LazyEdgesAudit.cs')){
  $anchor='<Compile Include="Forms\AsterMaxC1047SceneBatchAudit.cs" />'
  if(-not $p.Contains($anchor)){throw 'C10.48 C1047 audit project anchor missing.'}
  $p=$p.Replace($anchor,$anchor+"`n    "+'<Compile Include="Forms\AsterMaxC1048LazyEdgesAudit.cs" />')
}
Set-Content $projectPath $p -Encoding UTF8
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
if(-not $u.Contains('StartAsterMaxC1048LazyEdgesAudit();')){
  $anchor='                StartAsterMaxC1047SceneBatchAudit();'
  if(-not $u.Contains($anchor)){throw 'C10.48 C1047 startup anchor missing.'}
  $u=$u.Replace($anchor,$anchor+"`n                StartAsterMaxC1048LazyEdgesAudit();")
}
Set-Content $uiPath $u -Encoding UTF8
Write-Host 'C10.48 runtime audit hook added: NoEdges defer -> ElementEdges materialize -> NoEdges round trip.' -ForegroundColor Green
