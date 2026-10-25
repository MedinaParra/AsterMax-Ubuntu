using System;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using CaeMesh;

namespace PrePoMax.AsterMaxAI
{
    // CI-only harness. Imports an actual STEP file through Controller.ImportFile and qualifies
    // dimensional scale against known millimetre extents. It never runs or verifies a solver.
    internal sealed class AsterMaxStepMmHarness
    {
        private readonly Controller _controller;

        public AsterMaxStepMmHarness(Controller controller)
        {
            _controller = controller;
        }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_STEP_MM_FIXTURE"), "1", StringComparison.Ordinal)) return;
            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_STEP_MM_EVIDENCE_PATH");
            string stepPath = Environment.GetEnvironmentVariable("ASTERMAX_STEP_MM_PATH");
            bool sourceExists=false, sourceDeclaresMm=false, imported=false, bboxFinite=false, scaleOk=false;
            bool meterScaleSignature=false, micrometreScaleSignature=false;
            int partCount=0, geometryNodeCount=0;
            double dx=Double.NaN,dy=Double.NaN,dz=Double.NaN;
            string sha256="", error="";
            try
            {
                if (String.IsNullOrWhiteSpace(stepPath) || !File.Exists(stepPath))
                    throw new FileNotFoundException("C8.59 STEP fixture is missing.", stepPath);
                sourceExists=true;
                string source=File.ReadAllText(stepPath);
                sourceDeclaresMm=source.IndexOf(".MILLI., .METRE.",StringComparison.OrdinalIgnoreCase)>=0;
                if(!sourceDeclaresMm) throw new InvalidOperationException("STEP fixture does not explicitly declare millimetre SI length units.");
                sha256=HashFile(stepPath);

                if (_controller.Model == null || _controller.Model.Geometry == null ||
                    _controller.Model.Geometry.Parts.Count != 0 || _controller.Model.Mesh.Parts.Count != 0)
                    throw new InvalidOperationException("C8.59 requires a clean startup model; refusing to overwrite user/model data.");

                // Pinned upstream native path: .stp/.step -> ImportCADAssemblyFile(... STEP_ASSEMBLY_SPLIT_TO_COMPOUNDS).
                _controller.ImportFile(stepPath,false);
                FeMesh geometry=_controller.Model==null?null:_controller.Model.Geometry;
                imported=geometry!=null && geometry.Parts!=null && geometry.Parts.Count>0;
                if(!imported) throw new InvalidOperationException("Native STEP import produced no geometry parts.");
                partCount=geometry.Parts.Count;
                geometryNodeCount=geometry.Nodes==null?0:geometry.Nodes.Count;
                BoundingBox bb=geometry.BoundingBox;
                if(bb==null) throw new InvalidOperationException("Imported geometry has no bounding box.");
                dx=bb.MaxX-bb.MinX; dy=bb.MaxY-bb.MinY; dz=bb.MaxZ-bb.MinZ;
                bboxFinite=FinitePositive(dx)&&FinitePositive(dy)&&FinitePositive(dz);
                if(!bboxFinite) throw new InvalidOperationException("Imported STEP bounding box is non-finite or degenerate.");

                // Pinned fixture extents are 537 x 162 x 254 mm. Tolerance allows tessellation/reader noise,
                // but rejects the catastrophic x1000 and /1000 scale signatures explicitly.
                const double ex=537.0, ey=162.0, ez=254.0, tol=0.25;
                scaleOk=Math.Abs(dx-ex)<=tol && Math.Abs(dy-ey)<=tol && Math.Abs(dz-ez)<=tol;
                meterScaleSignature=NearScale(dx,ex,0.001) && NearScale(dy,ey,0.001) && NearScale(dz,ez,0.001);
                micrometreScaleSignature=NearScale(dx,ex,1000.0) && NearScale(dy,ey,1000.0) && NearScale(dz,ez,1000.0);
                if(!scaleOk) throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                    "STEP/mm dimensional gate failed. Observed extents {0:R} x {1:R} x {2:R}; expected 537 x 162 x 254 mm.",dx,dy,dz));
            }
            catch(Exception ex){error=ex.GetType().Name+": "+ex.Message;}
            WriteEvidence(evidencePath,stepPath,sourceExists,sourceDeclaresMm,imported,bboxFinite,scaleOk,
                          meterScaleSignature,micrometreScaleSignature,partCount,geometryNodeCount,dx,dy,dz,sha256,error);
        }

        private static bool FinitePositive(double v){return !Double.IsNaN(v)&&!Double.IsInfinity(v)&&v>0;}
        private static bool NearScale(double observed,double expected,double factor)
        { double target=expected*factor; return Math.Abs(observed-target)<=Math.Max(1E-6,Math.Abs(target)*0.002); }
        private static string HashFile(string path)
        { using(SHA256 sha=SHA256.Create())using(FileStream fs=File.OpenRead(path)){byte[] h=sha.ComputeHash(fs);StringBuilder sb=new StringBuilder();foreach(byte b in h)sb.Append(b.ToString("x2",CultureInfo.InvariantCulture));return sb.ToString();} }
        private static string Json(string s){return "\""+(s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ")+"\"";}
        private static string Num(double v){return (Double.IsNaN(v)||Double.IsInfinity(v))?"null":v.ToString("R",CultureInfo.InvariantCulture);}

        private static void WriteEvidence(string path,string stepPath,bool sourceExists,bool sourceDeclaresMm,bool imported,
            bool bboxFinite,bool scaleOk,bool meterSignature,bool microSignature,int parts,int nodes,double dx,double dy,double dz,string sha,string error)
        {
            if(String.IsNullOrWhiteSpace(path))return; string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            bool qualified=sourceExists&&sourceDeclaresMm&&imported&&bboxFinite&&scaleOk&&!meterSignature&&!microSignature&&String.IsNullOrEmpty(error);
            string json="{\n"+
                "  \"schema\": \"astermax.native-step-mm-scale-gate.v1\",\n"+
                "  \"native_controller_import_file_called\": true,\n"+
                "  \"step_source_exists\": "+(sourceExists?"true":"false")+",\n"+
                "  \"step_source_declares_si_millimetres\": "+(sourceDeclaresMm?"true":"false")+",\n"+
                "  \"step_sha256\": "+Json(sha)+",\n"+
                "  \"native_step_imported\": "+(imported?"true":"false")+",\n"+
                "  \"geometry_part_count\": "+parts.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"geometry_node_count\": "+nodes.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"observed_extent_x_mm\": "+Num(dx)+",\n  \"observed_extent_y_mm\": "+Num(dy)+",\n  \"observed_extent_z_mm\": "+Num(dz)+",\n"+
                "  \"expected_extents_mm\": [537.0,162.0,254.0],\n"+
                "  \"bounding_box_finite\": "+(bboxFinite?"true":"false")+",\n"+
                "  \"meter_scale_signature_detected\": "+(meterSignature?"true":"false")+",\n"+
                "  \"x1000_scale_signature_detected\": "+(microSignature?"true":"false")+",\n"+
                "  \"step_mm_scale_qualified\": "+(qualified?"true":"false")+",\n"+
                "  \"mesh_generated\": false,\n  \"solver_executed\": false,\n  \"solver_verified\": false,\n  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n"+
                "  \"step_path\": "+Json(stepPath)+",\n  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,json,Encoding.UTF8);
        }
    }
}
