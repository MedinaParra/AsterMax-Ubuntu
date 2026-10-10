param([string]$Root)
$ErrorActionPreference='Stop'

$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$projectPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
foreach($p in @($uiPath,$projectPath)){ if(!(Test-Path $p)){ throw "C10.47 audit missing: $p" } }

$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1047SceneBatchAudit.cs'
$audit=@'
using System;
using System.IO;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void StartAsterMaxC1047SceneBatchAudit()
        {
            string directory = Environment.GetEnvironmentVariable("ASTERMAX_C1047_AUDIT_DIR");
            if (String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);

            int expectedParts = 25;
            int configured;
            if (Int32.TryParse(Environment.GetEnvironmentVariable("ASTERMAX_C1047_EXPECTED_PARTS"), out configured) && configured > 0)
                expectedParts = configured;

            int ticks = 0;
            var timer = new Timer { Interval = 250 };
            timer.Tick += (s, e) =>
            {
                ticks++;
                int partCount = _controller != null && _controller.Model != null && _controller.Model.Geometry != null
                    ? _controller.Model.Geometry.Parts.Count : 0;
                bool idle = _controller != null && !IsStateWorking();
                bool ready = idle && partCount >= expectedParts;
                if (!ready && ticks < 720) return;

                timer.Stop();
                timer.Dispose();
                bool pass = false;
                var report = new JObject();
                try
                {
                    int errors = _controller == null ? -1 : _controller.GetNumberOfErrors();
                    long deferred = _vtk == null ? -1 : _vtk.AsterMaxSceneBatchDeferredCameraAdjusts;
                    long flushes = _vtk == null ? -1 : _vtk.AsterMaxSceneBatchCameraFlushes;
                    int depth = _vtk == null ? -1 : _vtk.AsterMaxSceneBatchDepth;
                    report["release"] = "C10.47-vtk-scene-batch";
                    report["expected_parts"] = expectedParts;
                    report["cad_bodies"] = partCount;
                    report["controller_errors"] = errors;
                    report["idle"] = idle;
                    report["elapsed_ms_upper_bound"] = ticks * 250;
                    report["deferred_camera_adjusts"] = deferred;
                    report["batch_camera_flushes"] = flushes;
                    report["batch_depth_after_import"] = depth;
                    report["camera_adjust_calls_avoided_lower_bound"] = deferred > flushes ? deferred - flushes : 0;
                    pass = ready && errors == 0 && deferred > 0 && flushes == 1 && depth == 0;
                    report["pass"] = pass;
                    if (!pass)
                        report["error"] = "CAD import did not finish with a balanced scene batch and exactly one camera flush.";
                }
                catch (Exception ex)
                {
                    report["pass"] = false;
                    report["error"] = ex.ToString();
                }

                File.WriteAllText(Path.Combine(directory, "c1047-scene-batch-report.json"), report.ToString(Formatting.Indented));
                Environment.ExitCode = pass ? 0 : 1;
                _c10209AuditShutdownDirectory = directory;
                if (_controller != null) _controller.ModelChanged = false;
                BeginInvoke(new Action(() => Close()));
            };
            timer.Start();
        }
    }
}
'@
Set-Content $auditPath $audit -Encoding UTF8

$p=[regex]::Replace((Get-Content $projectPath -Raw),"\r\n?","`n")
if(-not $p.Contains('Forms\AsterMaxC1047SceneBatchAudit.cs')){
    $anchor='<Compile Include="Forms\AsterMaxC1043ImportAudit.cs" />'
    if(-not $p.Contains($anchor)){ throw 'C10.47 C1043 audit project anchor missing.' }
    $p=$p.Replace($anchor,$anchor+"`n    "+'<Compile Include="Forms\AsterMaxC1047SceneBatchAudit.cs" />')
}
Set-Content $projectPath $p -Encoding UTF8

$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
if(-not $u.Contains('StartAsterMaxC1047SceneBatchAudit();')){
    $anchor='                StartAsterMaxC1043ImportAudit();'
    if(-not $u.Contains($anchor)){ throw 'C10.47 C1043 audit startup anchor missing.' }
    $u=$u.Replace($anchor,$anchor+"`n                StartAsterMaxC1047SceneBatchAudit();")
}
Set-Content $uiPath $u -Encoding UTF8

Write-Host 'C10.47 runtime scene-batch audit hook applied.' -ForegroundColor Green
