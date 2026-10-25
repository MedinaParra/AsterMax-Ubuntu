using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using CaeMesh;

namespace PrePoMax.AsterMaxAI
{
    // C8.88 qualification harness: prove that native FeMeshRefinement objects survive a real PMX roundtrip.
    // GeometryIds are persistence sentinels only; this increment does NOT claim ROI->CAD selection binding.
    internal sealed class AsterMaxNativeRefinementPersistenceHarness
    {
        private readonly Controller _controller;
        public AsterMaxNativeRefinementPersistenceHarness(Controller controller) { _controller = controller; }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_PERSISTENCE_FIXTURE"), "1", StringComparison.Ordinal)) return;
            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_PERSISTENCE_EVIDENCE_PATH");
            string pmxPath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_PERSISTENCE_PMX_PATH");
            if (String.IsNullOrWhiteSpace(pmxPath)) pmxPath = Path.Combine(Path.GetTempPath(), "AsterMax_C888_NativeRefinement.pmx");

            bool modelReady=false, inserted=false, saved=false, reopened=false, namesOk=false, sizesOk=false, idsOk=false;
            long bytes=0; string sha="", error="";
            try
            {
                if (_controller.Model == null || _controller.Model.Geometry == null || _controller.Model.Mesh == null)
                    throw new InvalidOperationException("C8.88 requires a loaded STEP/mm model before native refinement persistence qualification.");
                if (_controller.Model.Geometry.Parts == null || _controller.Model.Geometry.Parts.Count == 0 ||
                    _controller.Model.Mesh.Elements == null || _controller.Model.Mesh.Elements.Count == 0)
                    throw new InvalidOperationException("C8.88 requires STEP geometry plus a generated FE mesh.");
                modelReady=true;

                string[] names = { "ASTERMAX_ROI_01", "ASTERMAX_ROI_02", "ASTERMAX_ROI_03" };
                int[][] sentinels = { new[]{101,102,103}, new[]{201,202,203}, new[]{301,302,303} };
                foreach (string n in names)
                    if (_controller.Model.Geometry.MeshRefinements.ContainsKey(n))
                        throw new InvalidOperationException("Refusing to overwrite existing native mesh refinement: " + n);

                for (int i=0;i<names.Length;i++)
                {
                    FeMeshRefinement r = new FeMeshRefinement(names[i]);
                    r.MeshSize = 18.0;
                    r.GeometryIds = sentinels[i];
                    // Direct collection insertion intentionally isolates the PMX persistence seam.
                    // Native Controller selection binding remains a later gate.
                    _controller.Model.Geometry.MeshRefinements.Add(r.Name, r);
                }
                inserted = _controller.Model.Geometry.MeshRefinements.Count >= 3;
                if (!inserted) throw new InvalidOperationException("Native FeMeshRefinement collection rejected C8.88 entries.");

                _controller.SaveToPmx(pmxPath);
                saved = File.Exists(pmxPath) && new FileInfo(pmxPath).Length > 0;
                if (!saved) throw new InvalidOperationException("SaveToPmx produced no C8.88 PMX evidence.");
                bytes = new FileInfo(pmxPath).Length; sha = HashFile(pmxPath);

                _controller.Open(pmxPath);
                reopened = _controller.Model != null && _controller.Model.Geometry != null && _controller.Model.Geometry.MeshRefinements != null;
                if (!reopened) throw new InvalidOperationException("OpenPmx failed to restore native mesh-refinement collection.");

                namesOk = names.All(n => _controller.Model.Geometry.MeshRefinements.ContainsKey(n));
                sizesOk = names.All(n => Math.Abs(_controller.Model.Geometry.MeshRefinements[n].MeshSize - 18.0) <= 1E-12);
                idsOk = true;
                for (int i=0;i<names.Length;i++)
                {
                    int[] ids = _controller.Model.Geometry.MeshRefinements[names[i]].GeometryIds;
                    if (ids == null || !ids.SequenceEqual(sentinels[i])) { idsOk=false; break; }
                }
                if (!(namesOk && sizesOk && idsOk)) throw new InvalidOperationException("FeMeshRefinement fields changed across PMX roundtrip.");
            }
            catch (Exception ex) { error = ex.GetType().Name + ": " + ex.Message; }
            WriteEvidence(evidencePath, pmxPath, modelReady, inserted, saved, reopened, namesOk, sizesOk, idsOk, bytes, sha, error);
        }

        private static string HashFile(string path)
        {
            using (SHA256 s=SHA256.Create()) using (FileStream fs=File.OpenRead(path))
            { byte[] h=s.ComputeHash(fs); StringBuilder b=new StringBuilder(); foreach(byte x in h)b.Append(x.ToString("x2",CultureInfo.InvariantCulture)); return b.ToString(); }
        }
        private static string Json(string s) { return "\"" + (s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ") + "\""; }
        private static void WriteEvidence(string path,string pmx,bool ready,bool inserted,bool saved,bool reopened,bool names,bool sizes,bool ids,long bytes,string sha,string error)
        {
            if (String.IsNullOrWhiteSpace(path)) return; string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            bool verified=ready&&inserted&&saved&&reopened&&names&&sizes&&ids&&String.IsNullOrEmpty(error);
            string json="{\n"+
                "  \"schema\": \"astermax.c8.88.native-femeshrefinement-persistence.v1\",\n"+
                "  \"source_local_h_mm\": 18.0,\n"+
                "  \"source_pareto_workflow\": 34064375691,\n"+
                "  \"source_pareto_best_candidate\": \"adaptive-h18\",\n"+
                "  \"native_femeshrefinement_object_type_used\": true,\n"+
                "  \"step_mesh_model_ready\": "+(ready?"true":"false")+",\n"+
                "  \"native_refinements_inserted\": "+(inserted?"true":"false")+",\n"+
                "  \"native_save_to_pmx_called\": "+(saved?"true":"false")+",\n"+
                "  \"native_open_pmx_roundtrip\": "+(reopened?"true":"false")+",\n"+
                "  \"refinement_names_roundtrip_verified\": "+(names?"true":"false")+",\n"+
                "  \"mesh_size_18mm_roundtrip_verified\": "+(sizes?"true":"false")+",\n"+
                "  \"geometry_id_payload_roundtrip_verified\": "+(ids?"true":"false")+",\n"+
                "  \"native_femeshrefinement_persistence_verified\": "+(verified?"true":"false")+",\n"+
                "  \"native_roi_geometry_binding_verified\": false,\n"+
                "  \"native_refinement_consumer_verified\": false,\n"+
                "  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n"+
                "  \"pmx_bytes\": "+bytes.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"pmx_sha256\": "+Json(sha)+",\n"+
                "  \"pmx_path\": "+Json(pmx)+",\n  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,json,Encoding.UTF8);
        }
    }
}
