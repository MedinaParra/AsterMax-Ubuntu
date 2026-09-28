using System;
using System.IO;
using System.Drawing;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void C1034CaptureScreen(string path)
        {
            Activate(); Application.DoEvents();
            using(var bitmap=new Bitmap(Width,Height))
            using(var graphics=Graphics.FromImage(bitmap)) {
                graphics.CopyFromScreen(Location,Point.Empty,Size);
                bitmap.Save(path,System.Drawing.Imaging.ImageFormat.Png);
            }
        }
        private void StartAsterMaxC1034OutlineAudit()
        {
            string directory=Environment.GetEnvironmentVariable("ASTERMAX_C1034_AUDIT_DIR");
            if(String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);
            int ticks=0;
            var timer=new Timer { Interval=1000 };
            timer.Tick += (s,e) => {
                ticks++;
                bool ready=_controller!=null && _controller.Model!=null && _controller.Model.Geometry!=null && _controller.Model.Geometry.Parts.Count>=2 && !IsStateWorking();
                if(!ready && ticks<70) return;
                timer.Stop();timer.Dispose();
                bool pass=false;
                try {
                    if(!ready) throw new InvalidOperationException("Two-body STEP did not finish importing within 70 seconds.");
                    WindowState=FormWindowState.Maximized; Application.DoEvents();
                    AsterMaxFitView();
                    var report=JObject.FromObject(_modelTree.AuditAsterMaxMechanicalOutline());
                    report["caption"]=Text;report["release"]="C10.34";
                    report["cad_bodies"]=_controller.Model.Geometry.Parts.Count;
                    report["caption_pass"]=Text.Contains("C10.34");
                    pass=(bool)report["pass"] && (bool)report["caption_pass"];
                    report["pass"]=pass;
                    File.WriteAllText(Path.Combine(directory,"mechanical-tree-report.json"),report.ToString(Formatting.Indented));
                    C1034CaptureScreen(Path.Combine(directory,"mechanical-tree-window.png"));
                    using(var bmp=new Bitmap(_modelTree.Width,_modelTree.Height)) {
                        _modelTree.DrawToBitmap(bmp,new Rectangle(0,0,bmp.Width,bmp.Height));
                        bmp.Save(Path.Combine(directory,"mechanical-tree.png"),System.Drawing.Imaging.ImageFormat.Png);
                    }
                } catch(Exception ex) {
                    File.WriteAllText(Path.Combine(directory,"mechanical-tree-report.json"),new JObject { ["pass"]=false,["error"]=ex.ToString() }.ToString());
                }
                try { C1034CaptureScreen(Path.Combine(directory,"mechanical-tree-window.png")); } catch { }
                Environment.ExitCode=pass?0:1;
                _c10209AuditShutdownDirectory=directory;
                if(_controller!=null) _controller.ModelChanged=false;
                BeginInvoke(new Action(()=>Close()));
            };
            timer.Start();
        }
    }
}
