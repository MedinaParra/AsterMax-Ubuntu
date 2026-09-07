using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using CaeMesh;

namespace PrePoMax.AsterMaxAI
{
    // C8.89 qualification harness.
    // Binds the three admitted C8.85 physical ROI centroids to actual CAD solid-surface geometry,
    // persists native FeMeshRefinement objects through PMX, reloads, then invokes the normal
    // Controller.CreateMesh -> BREP -> CreateMeshRefinementFile -> NetGen path. The observer seam
    // only copies the native-generated refinement file; it never injects or rewrites meshing input.
    internal sealed class AsterMaxNativeRoiConsumerHarness
    {
        private readonly Controller _controller;

        private sealed class RoiBinding
        {
            public string Name;
            public double X, Y, Z, Radius;
            public int FaceIndex, GeometryId;
            public double FaceCx, FaceCy, FaceCz, NearestDistance;
        }

        public AsterMaxNativeRoiConsumerHarness(Controller controller) { _controller = controller; }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_ROI_CONSUMER_FIXTURE"), "1", StringComparison.Ordinal)) return;

            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_ROI_CONSUMER_EVIDENCE_PATH");
            string stepPath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_ROI_CONSUMER_STEP_PATH");
            string pmxPath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_ROI_CONSUMER_PMX_PATH");
            string observerPath = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_CONSUMER_COPY_PATH");
            if (String.IsNullOrWhiteSpace(pmxPath)) pmxPath = Path.Combine(Path.GetTempPath(), "AsterMax_C889_NativeRoiConsumer.pmx");

            bool stepExists=false, stepMm=false, imported=false, roiBound=false, commandUsed=false;
            bool saved=false, reopened=false, roundtrip=false, netgen=false, observer=false, observerNonempty=false;
            int meshNodes=0, meshElements=0, distinctSurfaces=0; string meshTypes="", stepSha="", pmxSha="", observerSha="", error="";
            List<RoiBinding> bindings = new List<RoiBinding>();

            try
            {
                if (String.IsNullOrWhiteSpace(stepPath) || !File.Exists(stepPath)) throw new FileNotFoundException("C8.89 STEP fixture missing.", stepPath);
                stepExists=true;
                string raw=File.ReadAllText(stepPath);
                stepMm=raw.IndexOf(".MILLI., .METRE.", StringComparison.OrdinalIgnoreCase)>=0;
                if(!stepMm) throw new InvalidOperationException("C8.89 requires STEP explicitly declaring SI millimetres.");
                stepSha=HashFile(stepPath);

                if (_controller.Model == null || _controller.Model.Geometry == null || _controller.Model.Mesh == null ||
                    _controller.Model.Geometry.Parts.Count != 0 || _controller.Model.Mesh.Parts.Count != 0 ||
                    _controller.Model.Mesh.Nodes.Count != 0 || _controller.Model.Mesh.Elements.Count != 0)
                    throw new InvalidOperationException("C8.89 requires a clean startup model; refusing to overwrite model data.");

                _controller.ImportFile(stepPath, false);
                FeMesh geometry=_controller.Model.Geometry;
                imported=geometry!=null && geometry.Parts!=null && geometry.Parts.Count==1;
                if(!imported) throw new InvalidOperationException("Native STEP import did not produce exactly one geometry part for the C8.89 fixture.");

                BasePart part=geometry.Parts.First().Value;
                if(part==null || part.Visualization==null || part.Visualization.Cells==null || part.Visualization.CellIdsByFace==null)
                    throw new InvalidOperationException("Imported CAD part exposes no surface tessellation for ROI binding.");

                RoiBinding[] targets = new[] {
                    new RoiBinding { Name="ASTERMAX_ROI_01", X=523.9847282608696, Y=77.261104443986, Z=-241.44603894190513, Radius=65.18 },
                    new RoiBinding { Name="ASTERMAX_ROI_02", X=523.5116931818183, Y=75.31516373307211, Z=-12.244792492979217, Radius=59.31 },
                    new RoiBinding { Name="ASTERMAX_ROI_03", X=527.3222646454192, Y=5.000000000000004, Z=-144.03431616329792, Radius=47.85 }
                };

                foreach(RoiBinding target in targets)
                {
                    RoiBinding b=BindNearestSolidSurface(geometry, part, target);
                    if(!Finite(b.NearestDistance) || b.NearestDistance > target.Radius + 25.0)
                        throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                            "ROI {0} nearest CAD surface is {1:R} mm away, outside fail-closed ROI radius+tolerance {2:R} mm.",
                            target.Name,b.NearestDistance,target.Radius+25.0));
                    string[] partNames=geometry.GetPartNamesFromGeometryIds(new[]{b.GeometryId});
                    if(partNames==null || !partNames.Contains(part.Name))
                        throw new InvalidOperationException("Encoded CAD surface does not resolve back to the imported part: "+target.Name);
                    bindings.Add(b);
                }
                distinctSurfaces=bindings.Select(x=>x.GeometryId).Distinct().Count();
                roiBound=bindings.Count==3;

                foreach(RoiBinding b in bindings)
                {
                    FeMeshRefinement r=new FeMeshRefinement(b.Name);
                    r.MeshSize=18.0;
                    r.GeometryIds=new[]{b.GeometryId};
                    _controller.AddMeshRefinementCommand(r);
                }
                commandUsed=bindings.All(b=>_controller.Model.Geometry.MeshRefinements.ContainsKey(b.Name));
                if(!commandUsed) throw new InvalidOperationException("Controller.AddMeshRefinementCommand did not materialize all native ROI controls.");

                _controller.SaveToPmx(pmxPath);
                saved=File.Exists(pmxPath) && new FileInfo(pmxPath).Length>0;
                if(!saved) throw new InvalidOperationException("Native SaveToPmx produced no C8.89 PMX.");
                pmxSha=HashFile(pmxPath);

                _controller.Open(pmxPath);
                reopened=_controller.Model!=null && _controller.Model.Geometry!=null;
                if(!reopened) throw new InvalidOperationException("Native Open failed for C8.89 PMX.");

                roundtrip=true;
                foreach(RoiBinding b in bindings)
                {
                    if(!_controller.Model.Geometry.MeshRefinements.ContainsKey(b.Name)) { roundtrip=false; break; }
                    FeMeshRefinement r=_controller.Model.Geometry.MeshRefinements[b.Name];
                    if(Math.Abs(r.MeshSize-18.0)>1E-12 || r.GeometryIds==null || r.GeometryIds.Length!=1 || r.GeometryIds[0]!=b.GeometryId)
                    { roundtrip=false; break; }
                }
                if(!roundtrip) throw new InvalidOperationException("Native ROI refinement fields changed across PMX roundtrip.");

                if(!String.IsNullOrWhiteSpace(observerPath) && File.Exists(observerPath)) File.Delete(observerPath);
                string partName=_controller.Model.Geometry.Parts.First().Key;
                netgen=_controller.CreateMesh(partName);
                if(!netgen) throw new InvalidOperationException("Reloaded native Controller.CreateMesh returned false.");

                FeMesh mesh=_controller.Model.Mesh;
                meshNodes=mesh.Nodes==null?0:mesh.Nodes.Count;
                meshElements=mesh.Elements==null?0:mesh.Elements.Count;
                meshTypes=mesh.Elements==null?"":String.Join(",",mesh.Elements.Values.Select(e=>e.GetType().Name).Distinct().OrderBy(x=>x).ToArray());
                if(meshNodes<=0 || meshElements<=0) throw new InvalidOperationException("Reloaded NetGen produced no FE mesh.");

                observer=!String.IsNullOrWhiteSpace(observerPath) && File.Exists(observerPath);
                observerNonempty=observer && new FileInfo(observerPath).Length>0;
                if(!observerNonempty) throw new InvalidOperationException("Native refinement consumer observer captured no non-empty meshRefinement file.");
                observerSha=HashFile(observerPath);
                _controller.CurrentView=ViewGeometryModelResults.Model;
            }
            catch(Exception ex) { error=ex.GetType().Name+": "+ex.Message; }

            WriteEvidence(evidencePath,stepPath,pmxPath,observerPath,stepExists,stepMm,imported,roiBound,commandUsed,saved,reopened,roundtrip,
                netgen,observer,observerNonempty,meshNodes,meshElements,distinctSurfaces,meshTypes,stepSha,pmxSha,observerSha,bindings,error);
        }

        private static RoiBinding BindNearestSolidSurface(FeMesh geometry, BasePart part, RoiBinding target)
        {
            VisualizationData vis=part.Visualization;
            double best=Double.PositiveInfinity; int bestFace=-1; double bestCx=Double.NaN,bestCy=Double.NaN,bestCz=Double.NaN;
            for(int face=0; face<vis.FaceCount; face++)
            {
                int[] localCells=vis.CellIdsByFace[face];
                if(localCells==null || localCells.Length==0) continue;
                HashSet<int> nodeIds=new HashSet<int>();
                foreach(int localCell in localCells)
                {
                    if(localCell<0 || localCell>=vis.Cells.Length || vis.Cells[localCell]==null) continue;
                    foreach(int id in vis.Cells[localCell]) nodeIds.Add(id);
                }
                if(nodeIds.Count==0) continue;
                double cx=0,cy=0,cz=0; int n=0; double nearest=Double.PositiveInfinity;
                foreach(int id in nodeIds)
                {
                    FeNode node;
                    if(!geometry.Nodes.TryGetValue(id,out node) || node==null) continue;
                    cx+=node.X; cy+=node.Y; cz+=node.Z; n++;
                    double dx=node.X-target.X,dy=node.Y-target.Y,dz=node.Z-target.Z;
                    double d=Math.Sqrt(dx*dx+dy*dy+dz*dz); if(d<nearest) nearest=d;
                }
                if(n==0) continue;
                cx/=n;cy/=n;cz/=n;
                if(nearest<best) { best=nearest;bestFace=face;bestCx=cx;bestCy=cy;bestCz=cz; }
            }
            if(bestFace<0) throw new InvalidOperationException("No CAD solid surface could be resolved for "+target.Name);
            target.FaceIndex=bestFace;
            target.GeometryId=FeMesh.GetGeometryId(bestFace,(int)GeometryType.SolidSurface,part.PartId);
            target.FaceCx=bestCx;target.FaceCy=bestCy;target.FaceCz=bestCz;target.NearestDistance=best;
            return target;
        }

        private static bool Finite(double v) { return !Double.IsNaN(v)&&!Double.IsInfinity(v); }
        private static string HashFile(string path)
        {
            using(SHA256 s=SHA256.Create()) using(FileStream fs=File.OpenRead(path))
            { byte[] h=s.ComputeHash(fs); StringBuilder b=new StringBuilder(); foreach(byte x in h)b.Append(x.ToString("x2",CultureInfo.InvariantCulture)); return b.ToString(); }
        }
        private static string Json(string s) { return "\""+(s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ")+"\""; }
        private static string Num(double v) { return Finite(v)?v.ToString("R",CultureInfo.InvariantCulture):"null"; }

        private static void WriteEvidence(string path,string step,string pmx,string observerPath,bool stepExists,bool stepMm,bool imported,bool roiBound,
            bool commandUsed,bool saved,bool reopened,bool roundtrip,bool netgen,bool observer,bool observerNonempty,int nodes,int elements,int distinctSurfaces,
            string types,string stepSha,string pmxSha,string observerSha,List<RoiBinding> bindings,string error)
        {
            if(String.IsNullOrWhiteSpace(path)) return; string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            bool consumer=stepExists&&stepMm&&imported&&roiBound&&commandUsed&&saved&&reopened&&roundtrip&&netgen&&observerNonempty&&nodes>0&&elements>0&&String.IsNullOrEmpty(error);
            StringBuilder r=new StringBuilder();
            r.Append("[\n");
            for(int i=0;i<bindings.Count;i++)
            {
                RoiBinding b=bindings[i]; if(i>0)r.Append(",\n");
                r.Append("    {\"name\":").Append(Json(b.Name)).Append(",\"target_mm\":[").Append(Num(b.X)).Append(',').Append(Num(b.Y)).Append(',').Append(Num(b.Z))
                 .Append("],\"persistent_roi_radius_mm\":").Append(Num(b.Radius)).Append(",\"cad_face_index\":").Append(b.FaceIndex.ToString(CultureInfo.InvariantCulture))
                 .Append(",\"geometry_id\":").Append(b.GeometryId.ToString(CultureInfo.InvariantCulture)).Append(",\"cad_face_centroid_mm\":[").Append(Num(b.FaceCx)).Append(',').Append(Num(b.FaceCy)).Append(',').Append(Num(b.FaceCz))
                 .Append("],\"nearest_cad_tessellation_node_distance_mm\":").Append(Num(b.NearestDistance)).Append("}");
            }
            r.Append("\n  ]");
            string json="{\n"+
                "  \"schema\": \"astermax.c8.89.native-roi-cad-consumer.v1\",\n"+
                "  \"source_hotspot_workflow\": 34042958847,\n"+
                "  \"source_pareto_workflow\": 34064375691,\n"+
                "  \"source_local_h_mm\": 18.0,\n"+
                "  \"source_step_exists\": "+(stepExists?"true":"false")+",\n"+
                "  \"source_step_declares_si_millimetres\": "+(stepMm?"true":"false")+",\n"+
                "  \"source_step_sha256\": "+Json(stepSha)+",\n"+
                "  \"native_step_imported\": "+(imported?"true":"false")+",\n"+
                "  \"native_roi_geometry_binding_verified\": "+(roiBound?"true":"false")+",\n"+
                "  \"native_add_mesh_refinement_command_used\": "+(commandUsed?"true":"false")+",\n"+
                "  \"native_save_to_pmx_called\": "+(saved?"true":"false")+",\n"+
                "  \"native_open_pmx_roundtrip\": "+(reopened?"true":"false")+",\n"+
                "  \"native_refinement_roundtrip_verified\": "+(roundtrip?"true":"false")+",\n"+
                "  \"native_netgen_after_reload\": "+(netgen?"true":"false")+",\n"+
                "  \"native_refinement_observer_file_exists\": "+(observer?"true":"false")+",\n"+
                "  \"native_refinement_observer_nonempty\": "+(observerNonempty?"true":"false")+",\n"+
                "  \"native_refinement_consumer_verified\": "+(consumer?"true":"false")+",\n"+
                "  \"distinct_cad_surface_count\": "+distinctSurfaces.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"mesh_node_count\": "+nodes.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"mesh_element_count\": "+elements.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"mesh_element_types\": "+Json(types)+",\n"+
                "  \"c8_88_uncontrolled_fixture_mesh_element_count\": 2474,\n"+
                "  \"element_count_changed_vs_c8_88_fixture\": "+((elements>0&&elements!=2474)?"true":"false")+",\n"+
                "  \"roi_bindings\": "+r.ToString()+",\n"+
                "  \"pmx_sha256\": "+Json(pmxSha)+",\n"+
                "  \"native_refinement_observer_sha256\": "+Json(observerSha)+",\n"+
                "  \"step_path\": "+Json(step)+",\n"+
                "  \"pmx_path\": "+Json(pmx)+",\n"+
                "  \"observer_path\": "+Json(observerPath)+",\n"+
                "  \"solver_executed\": false,\n"+
                "  \"industrial_validation\": false,\n"+
                "  \"ansys_equivalence\": false,\n"+
                "  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,json,Encoding.UTF8);
        }
    }
}
