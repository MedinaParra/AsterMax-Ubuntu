param([string]$Root)
$ErrorActionPreference='Stop'
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$projectPath=Join-Path $Root 'PrePoMax/PrePoMax.csproj'
foreach($p in @($uiPath,$projectPath)){if(!(Test-Path $p)){throw "C10.49 audit missing: $p"}}
$auditPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxC1049ImportTelemetryAudit.cs'
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
        private void StartAsterMaxC1049ImportTelemetryAudit()
        {
            string directory=Environment.GetEnvironmentVariable("ASTERMAX_C1049_AUDIT_DIR");
            if(String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);
            int expectedParts=25, configured;
            if(Int32.TryParse(Environment.GetEnvironmentVariable("ASTERMAX_C1049_EXPECTED_PARTS"),out configured)&&configured>0) expectedParts=configured;
            int ticks=0;
            var timer=new Timer { Interval=250 };
            timer.Tick+=(s,e)=>
            {
                ticks++;
                int partCount=_controller!=null&&_controller.Model!=null&&_controller.Model.Geometry!=null?_controller.Model.Geometry.Parts.Count:0;
                bool idle=_controller!=null&&!IsStateWorking();
                int depth=_vtk==null?-1:_vtk.AsterMaxSceneBatchDepth;
                long flushes=_vtk==null?-1:_vtk.AsterMaxSceneBatchCameraFlushes;
                bool ready=idle&&partCount>=expectedParts&&depth==0&&flushes==1;
                if(!ready&&ticks<720) return;
                timer.Stop();timer.Dispose();
                var report=new JObject();bool pass=false;
                try
                {
                    int errors=_controller==null?-1:_controller.GetNumberOfErrors();
                    long addCells=_vtk==null?-1:_vtk.AsterMaxSceneBatchAddCellsCalls;
                    long renderRequests=_vtk==null?-1:_vtk.AsterMaxSceneBatchRenderRequests;
                    long deferredCamera=_vtk==null?-1:_vtk.AsterMaxSceneBatchDeferredCameraAdjusts;
                    report["release"]="C10.49-import-telemetry";
                    report["expected_parts"]=expectedParts;report["cad_bodies"]=partCount;
                    report["controller_errors"]=errors;report["scene_batch_depth"]=depth;
                    report["camera_flushes"]=flushes;report["deferred_camera_adjusts"]=deferredCamera;
                    report["add_cells_calls"]=addCells;report["render_requests_during_batch"]=renderRequests;
                    report["elapsed_ms_upper_bound_diagnostic_only"]=ticks*250;
                    report["timing_interpretation"]="Diagnostic readiness bound only; not a speedup/FPS benchmark.";
                    pass=ready&&errors==0&&addCells>0&&flushes==1;
                    report["pass"]=pass;
                    if(!pass) report["error"]="C10.49 import telemetry invariants failed.";
                }
                catch(Exception ex){report["pass"]=false;report["error"]=ex.ToString();}
                File.WriteAllText(Path.Combine(directory,"c1049-import-telemetry-report.json"),report.ToString(Formatting.Indented));
                Environment.ExitCode=pass?0:1;
                _c10209AuditShutdownDirectory=directory;
                BeginInvoke(new Action(()=>{if(_controller!=null)_controller.ModelChanged=false;Close();}));
            };
            timer.Start();
        }
    }
}
'@
Set-Content $auditPath $audit -Encoding UTF8
$p=[regex]::Replace((Get-Content $projectPath -Raw),"\r\n?","`n")
if(-not $p.Contains('Forms\AsterMaxC1049ImportTelemetryAudit.cs')){
  $anchor='<Compile Include="Forms\AsterMaxC1048LazyEdgesAudit.cs" />'
  if(-not $p.Contains($anchor)){throw 'C10.49 C1048 project audit anchor missing.'}
  $p=$p.Replace($anchor,$anchor+"`n    "+'<Compile Include="Forms\AsterMaxC1049ImportTelemetryAudit.cs" />')
}
Set-Content $projectPath $p -Encoding UTF8
$u=[regex]::Replace((Get-Content $uiPath -Raw),"\r\n?","`n")
if(-not $u.Contains('StartAsterMaxC1049ImportTelemetryAudit();')){
  $anchor='                StartAsterMaxC1048LazyEdgesAudit();'
  if(-not $u.Contains($anchor)){throw 'C10.49 C1048 startup audit anchor missing.'}
  $u=$u.Replace($anchor,$anchor+"`n                StartAsterMaxC1049ImportTelemetryAudit();")
}
Set-Content $uiPath $u -Encoding UTF8
Write-Host 'C10.49 runtime telemetry audit hook added.' -ForegroundColor Green
