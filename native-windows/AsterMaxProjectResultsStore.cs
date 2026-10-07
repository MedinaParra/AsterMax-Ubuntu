using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    // PMX remains the model format. This atomic sidecar points to an immutable result snapshot.
    internal static class AsterMaxProjectResultsStore
    {
        public static string ManifestPath(string project) { return project+".astermax-results.json"; }
        public static string Hash(string path)
        {
            using(var sha=SHA256.Create())
            using(var stream=File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        public static void SaveEmpty(string project,string status)
        {
            Publish(ManifestPath(project),new JObject { ["schema"]="astermax-project-results/v1", ["status"]=status });
        }
        public static void Save(string project,AsterMaxResultsBundle bundle,string fingerprint,
                                string medFile,string messFile)
        {
            if(bundle.ResultModelFingerprintSha256!=fingerprint)
                throw new InvalidDataException("Cannot persist results for another model revision.");
            var qualification=AsterMaxMechanicalQualification.Evaluate(bundle);
            if(qualification.Status=="BLOCKED")
                throw new InvalidDataException(qualification.Describe());
            string projectDirectory=Path.GetDirectoryName(Path.GetFullPath(project));
            string relative=Path.Combine(Path.GetFileName(project)+".astermax-results",Guid.NewGuid().ToString("N"));
            string directory=Path.Combine(projectDirectory,relative);
            Directory.CreateDirectory(directory);
            string copy=Path.Combine(directory,"bundle.json");
            File.Copy(bundle.SourceFile,copy,false);
            File.Copy(Path.Combine(Path.GetDirectoryName(bundle.SourceFile),"mechanical-qualification.json"),
                      Path.Combine(directory,"mechanical-qualification.json"),false);
            // Raw evidence is carried when this session owns the genuine solver transaction.
            if(!String.IsNullOrWhiteSpace(medFile) && File.Exists(medFile))
                File.Copy(medFile,Path.Combine(directory,Path.GetFileName(medFile)),false);
            if(!String.IsNullOrWhiteSpace(messFile) && File.Exists(messFile))
                File.Copy(messFile,Path.Combine(directory,Path.GetFileName(messFile)),false);
            Publish(ManifestPath(project),new JObject {
                ["schema"]="astermax-project-results/v1", ["status"]="CURRENT",
                ["model_fingerprint_sha256"]=fingerprint,
                ["result_directory"]=relative, ["bundle_sha256"]=Hash(copy),
                ["qualification_sha256"]=Hash(Path.Combine(directory,"mechanical-qualification.json"))
            });
        }
        public static AsterMaxResultsBundle Load(string project,string fingerprint)
        {
            string manifest=ManifestPath(project);
            if(!File.Exists(manifest)) return null;
            var root=JObject.Parse(File.ReadAllText(manifest));
            if((string)root["schema"]!="astermax-project-results/v1")
                throw new InvalidDataException("Unsupported project results sidecar.");
            if((string)root["status"]!="CURRENT") return null;
            if((string)root["model_fingerprint_sha256"]!=fingerprint)
                throw new InvalidDataException("Saved results belong to another model revision.");
            string relative=(string)root["result_directory"];
            string parent=Path.GetDirectoryName(Path.GetFullPath(project))+Path.DirectorySeparatorChar;
            if(String.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative))
                throw new InvalidDataException("Invalid relative result directory.");
            string directory=Path.GetFullPath(Path.Combine(parent,relative));
            if(!directory.StartsWith(parent,StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Results must remain inside the project directory.");
            string bundleFile=Path.Combine(directory,"bundle.json");
            string qualificationFile=Path.Combine(directory,"mechanical-qualification.json");
            if(Hash(bundleFile)!=(string)root["bundle_sha256"] ||
               Hash(qualificationFile)!=(string)root["qualification_sha256"])
                throw new InvalidDataException("Saved result files failed their SHA-256 checks.");
            var bundle=AsterMaxResultsBundle.Load(bundleFile);
            if(bundle.ResultModelFingerprintSha256!=fingerprint)
                throw new InvalidDataException("Bundle revision differs from the saved project.");
            if(AsterMaxMechanicalQualification.Evaluate(bundle).Status=="BLOCKED")
                throw new InvalidDataException("Saved qualification no longer admits these results.");
            return bundle;
        }
        private static void Publish(string path,JObject value)
        {
            string temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try
            {
                File.WriteAllText(temp,value.ToString(),new UTF8Encoding(false));
                if(File.Exists(path)) File.Replace(temp,path,null);
                else File.Move(temp,path);
            }
            finally { if(File.Exists(temp)) File.Delete(temp); }
        }
    }

    public partial class FrmMain
    {
        // Restore can enter Application.DoEvents while vtkControl completes its WinForms Load.
        // The fresh-process audit timer must never re-enter that in-flight restore and close the
        // main window underneath the first renderer initialization.
        private bool _asterMaxProjectResultsRestoreInProgress;

        private void StartAsterMaxC1041ReopenAudit()
        {
            string directory=Environment.GetEnvironmentVariable("ASTERMAX_C1041_REOPEN_AUDIT_DIR");
            if(String.IsNullOrWhiteSpace(directory)) return;
            _asterMaxUiAuditMode=true;
            int attempts=0;
            var timer=new System.Windows.Forms.Timer { Interval=500 };
            timer.Tick+=(sender,args)=> {
                // DoEvents inside the initial VTK render can pump this timer. Deferring here is
                // mandatory: observing the bundle field alone does not mean Restore has returned.
                if(_asterMaxProjectResultsRestoreInProgress) return;
                if(_asterMaxLoadedResults==null && ++attempts<60) return;
                timer.Stop();timer.Dispose();
                Directory.CreateDirectory(directory);
                try
                {
                    if(_asterMaxLoadedResults==null) throw new InvalidDataException("No persisted results were recovered.");
                    _asterMaxLoadedResults.RequireCurrentModel(_controller.Model);
                    ShowAsterMaxIntegratedResult(null);
                    bool rendered=_axEmbeddedResults!=null && _axEmbeddedResults.Visible &&
                        _axEmbeddedResults.LastRenderError==null && !_axEmbeddedResults.LastRenderSkipped;
                    bool staleRejected=false;
                    var set=_controller.Model.Mesh.NodeSets.Values.FirstOrDefault(x=>x.Labels!=null && x.Labels.Length>0);
                    if(set==null) throw new InvalidDataException("No scope is available for the stale-result regression.");
                    int before=set.Labels[0];
                    try
                    {
                        set.Labels[0]=_controller.Model.Mesh.Nodes.Keys.First(x=>x!=before);
                        try { _asterMaxLoadedResults.RequireCurrentModel(_controller.Model); }
                        catch(InvalidDataException) { staleRejected=true; }
                    }
                    finally { set.Labels[0]=before; }
                    _asterMaxLoadedResults.RequireCurrentModel(_controller.Model);
                    bool pass=rendered && staleRejected;
                    File.WriteAllText(Path.Combine(directory,"fresh-process-reopen.json"),new JObject {
                        ["status"]=pass ? "PASS" : "FAIL",
                        ["process_id"]=System.Diagnostics.Process.GetCurrentProcess().Id,
                        ["bundle_sha256"]=AsterMaxProjectResultsStore.Hash(_asterMaxLoadedResults.SourceFile),
                        ["model_fingerprint_sha256"]=_asterMaxLoadedResults.ResultModelFingerprintSha256,
                        ["nodes"]=_asterMaxLoadedResults.NodeCount, ["elements"]=_asterMaxLoadedResults.ElementCount,
                        ["displacement_max_mm"]=_asterMaxLoadedResults.TotalDeformation.Max(),
                        ["von_mises_max_mpa"]=_asterMaxLoadedResults.EquivalentStress.Max(),
                        ["results_rendered"]=rendered, ["scope_change_rejected_old_results"]=staleRejected,
                        ["restore_in_progress_at_audit"]=_asterMaxProjectResultsRestoreInProgress,
                        ["solver_execution_in_reopen_process"]="NOT_RUN"
                    }.ToString());
                    C1034CaptureScreen(Path.Combine(directory,"fresh-process-reopen.png"));
                    // The command-line PMX open can still own the transient Opening state
                    // when this fresh-process audit has already proved result recovery. End
                    // only that matching state before closing so the headless run never blocks
                    // on the interactive "task running" confirmation dialog.
                    SetStateReady(Globals.OpeningText);
                    C1020RequestAuditExit(directory,pass ? 0 : 1);
                }
                catch(Exception ex)
                {
                    File.WriteAllText(Path.Combine(directory,"fresh-process-reopen.json"),new JObject {
                        ["status"]="FAIL", ["error"]=ex.ToString()
                    }.ToString());
                    SetStateReady(Globals.OpeningText);
                    C1020RequestAuditExit(directory,1);
                }
            };
            timer.Start();
        }
        public void PersistAsterMaxProjectResults(string project)
        {
            InvokeIfRequired(() => {
                if(_asterMaxSolveInProgress) throw new InvalidOperationException("Wait for Solve to finish before saving results.");
                if(_asterMaxLoadedResults==null) { AsterMaxProjectResultsStore.SaveEmpty(project,"NONE"); return; }
                try { _asterMaxLoadedResults.RequireCurrentModel(_controller.Model); }
                catch(InvalidDataException) { AsterMaxProjectResultsStore.SaveEmpty(project,"STALE"); return; }
                AsterMaxProjectResultsStore.Save(project,_asterMaxLoadedResults,
                    AsterMaxModelFingerprint.Extract(_controller.Model).Sha256,
                    _asterMaxSolveTransaction==null ? null : _asterMaxSolveTransaction.MedFile,
                    _asterMaxSolveTransaction==null ? null : _asterMaxSolveTransaction.MessFile);
            });
        }
        public void RestoreAsterMaxProjectResults(string project)
        {
            InvokeIfRequired(() => {
                if(_asterMaxProjectResultsRestoreInProgress) return;
                _asterMaxProjectResultsRestoreInProgress=true;
                try
                {
                    if(!File.Exists(AsterMaxProjectResultsStore.ManifestPath(project))) return;
                    try
                    {
                        var bundle=AsterMaxProjectResultsStore.Load(project,AsterMaxModelFingerprint.Extract(_controller.Model).Sha256);
                        if(bundle==null) return;
                        bundle.RequireCurrentModel(_controller.Model);
                        _asterMaxLoadedResults=bundle;
                        _asterMaxPreviousResultsRetained=false;
                        ShowAsterMaxIntegratedResult(null);
                        tsslState.Text="Resultados recuperados para la revision actual del modelo.";
                    }
                    catch(Exception ex)
                    {
                        _asterMaxLoadedResults=null;
                        ShowAsterMaxModelWorkspace();
                        RefreshAsterMaxResultAvailability();
                        tsslState.Text="Resultados guardados rechazados: "+ex.Message;
                    }
                }
                finally
                {
                    _asterMaxProjectResultsRestoreInProgress=false;
                }
            });
        }
    }
}
