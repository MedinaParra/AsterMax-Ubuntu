using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        // Test-only exception mode. It is enabled only by the explicit command-line audit switch;
        // normal distributed-binary exception handling never changes because an environment variable exists.
        private bool _asterMaxUiAuditMode;

        private static string AsterMaxIntegratedAuditDirectoryFromCommandLine()
        {
            const string prefix="--astermax-c1018-ui-audit=";
            string argument=Environment.GetCommandLineArgs()
                .FirstOrDefault(x=>x.StartsWith(prefix,StringComparison.OrdinalIgnoreCase));
            return argument==null?null:argument.Substring(prefix.Length).Trim('"');
        }

        private void StartAsterMaxIntegratedAudit()
        {
            string directory=AsterMaxIntegratedAuditDirectoryFromCommandLine();
            if(String.IsNullOrWhiteSpace(directory)) return;
            _asterMaxUiAuditMode=true;
            var timer=new Timer { Interval=1500 };
            timer.Tick+=(s,e)=> {
                timer.Stop(); timer.Dispose();
                Directory.CreateDirectory(directory);
                var checks=new JArray();
                Action<string,bool> check=(name,pass)=> {
                    checks.Add(new JObject { ["case"]=name,["pass"]=pass });
                    if(!pass) throw new InvalidOperationException("C10.18 UI check failed: "+name);
                };
                try
                {
                    // A real native model is solved by the installed Windows Code_Aster.
                    // No result arrays or solver outputs are fabricated by this audit.
                    var model=CreateAsterMaxStatusFixture();
                    typeof(Controller).GetField("_model",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(_controller,model);
                    RegenerateTree();
                    AuditAsterMaxButtons(Path.Combine(directory,"BUTTON_AUDIT"));
                    Action<string> click=caption=> {
                        var ribbon=(TabControl)Controls["asterMaxRibbon"];
                        foreach(TabPage page in ribbon.TabPages) foreach(Button button in AxButtons(page)) if(button.Text==caption) {
                            ribbon.SelectedTab=page; Application.DoEvents();
                            button.PerformClick(); Application.DoEvents(); return;
                        }
                        throw new InvalidOperationException("Button not found: "+caption);
                    };
                    click("Solve");
                    check("solve_button_loaded_real_results",_asterMaxLoadedResults!=null && _asterMaxSolveTransaction.State==AsterMaxSolveState.SolutionCurrent);
                    check("viewport_embedded_not_modal",_axEmbeddedResults!=null && !_axEmbeddedResults.TopLevel && _axEmbeddedResults.Parent==splitContainer2.Panel1 && _axEmbeddedResults.Visible);
                    check("outline_and_details_visible",_modelTree.Visible && _axResultDetailsHost.Visible && _axResultDetailsHost.Parent==splitContainer1.Panel1);
                    check("no_results_popup",Application.OpenForms.Cast<Form>().All(f=>!(f is AsterMaxResultsViewportForm)||!f.TopLevel));
                    foreach(string field in _asterMaxLoadedResults.AvailableFields()) {
                        int before=_axEmbeddedResults.RenderRevision;
                        string previous=_axEmbeddedResults.SelectedResultField;
                        _modelTree.SelectAsterMaxResultField(field); Application.DoEvents();
                        check("tree_select_"+field,_axEmbeddedResults.SelectedResultField==field &&
                            _axEmbeddedResults.LastRenderError==null && !_axEmbeddedResults.LastRenderSkipped &&
                            (field==previous || _axEmbeddedResults.RenderRevision>before));
                    }
                    foreach(string caption in new[]{"Contours","Deformed","Edges"}) {
                        bool before=caption=="Contours"?_axEmbeddedResults.ContoursVisible:caption=="Deformed"?_axEmbeddedResults.DeformationVisible:_axEmbeddedResults.MeshEdgesVisible;
                        int revision=_axEmbeddedResults.RenderRevision;
                        click(caption);
                        bool after=caption=="Contours"?_axEmbeddedResults.ContoursVisible:caption=="Deformed"?_axEmbeddedResults.DeformationVisible:_axEmbeddedResults.MeshEdgesVisible;
                        check("button_toggle_"+caption,before!=after && _axEmbeddedResults.RenderRevision>revision &&
                            _axEmbeddedResults.LastRenderError==null && !_axEmbeddedResults.LastRenderSkipped);
                        click(caption);
                    }
                    foreach(string caption in new[]{"Front","Top","Right","Isometric","Fit"}) {
                        click(caption);
                        check("camera_button_invoked_"+caption,_axEmbeddedResults.Visible &&
                            _axEmbeddedResults.LastRenderError==null && !_axEmbeddedResults.LastRenderSkipped);
                    }
                    _modelTree.SelectAsterMaxResultField("Equivalent Stress");
                    _axEmbeddedResults.CaptureNativeFramebuffer(Path.Combine(directory,"integrated-vtk-framebuffer.png"));
                    using(var bitmap=new Bitmap(Width,Height)) {
                        DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height)); bitmap.Save(Path.Combine(directory,"integrated-workspace.png"));
                    }
                    var view=_axEmbeddedResults;
                    ShowAsterMaxModelWorkspace();
                    check("return_to_model",panelControl.Visible && !view.Visible && !_axResultDetailsHost.Visible);
                    click("FEA Viewport");
                    check("reopen_reuses_view",Object.ReferenceEquals(view,_axEmbeddedResults) && view.Visible);
                    ShowAsterMaxIntegratedResult("__information__");
                    check("solution_information_embedded",_axSolutionInformation.Visible && _axSolutionInformation.Text.Contains("SolutionCurrent"));
                    var editedNode=model.Mesh.Nodes[1];
                    editedNode.X+=0.1;
                    model.Mesh.Nodes[1]=editedNode;
                    RefreshAsterMaxResultAvailability();
                    check("model_edit_hides_stale_results",!view.Visible);
                    bool rejected=false;
                    try { ShowAsterMaxIntegratedResult("Equivalent Stress"); } catch { rejected=true; }
                    check("stale_result_rejected",rejected && !view.Visible);
                    ResetAsterMaxIntegratedResults();
                    check("reset_clears_result_ownership",_axEmbeddedResults==null && _asterMaxLoadedResults==null && view.IsDisposed);
                    File.WriteAllText(Path.Combine(directory,"UI_AUDIT.json"),new JObject {
                        ["pass"]=true,["checks"]=checks,["solver"]="real native Windows Code_Aster",
                        ["audit_mode"]="explicit command-line switch",
                        ["scope"]="Integrated results, result buttons, camera invocation, tree, lifecycle and stale rejection; editing buttons inventoried separately, not all executed."
                    }.ToString());
                    Environment.Exit(0);
                }
                catch(Exception ex) {
                    File.WriteAllText(Path.Combine(directory,"UI_AUDIT.json"),new JObject{["pass"]=false,["checks"]=checks,["error"]=ex.ToString()}.ToString());
                    Environment.Exit(1);
                }
            };
            timer.Start();
        }
    }
}
