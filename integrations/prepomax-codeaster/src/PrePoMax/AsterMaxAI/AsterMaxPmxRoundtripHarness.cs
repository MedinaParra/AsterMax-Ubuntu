using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using CaeGlobals;
using CaeMesh;
using CaeModel;

namespace PrePoMax.AsterMaxAI
{
    // CI-only harness. Uses the native INP importer to create a valid FE part/mesh, then
    // real CaeModel BC/load objects and Controller PMX persistence. No solver is executed.
    internal sealed class AsterMaxPmxRoundtripHarness
    {
        private readonly Controller _controller;
        private readonly vtkControl.vtkControl _vtk;
        private readonly AsterMaxNativeVtkAnchorLayer _anchors;

        public AsterMaxPmxRoundtripHarness(Controller controller, vtkControl.vtkControl vtk, AsterMaxNativeVtkAnchorLayer anchors)
        { _controller = controller; _vtk = vtk; _anchors = anchors; }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_PMX_ROUNDTRIP_FIXTURE"), "1", StringComparison.Ordinal)) return;
            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_PMX_ROUNDTRIP_EVIDENCE_PATH");
            string pmxPath = Environment.GetEnvironmentVariable("ASTERMAX_PMX_ROUNDTRIP_PATH");
            if (String.IsNullOrWhiteSpace(pmxPath)) pmxPath = Path.Combine(Path.GetTempPath(), "AsterMax_C858_StructuralFixture.pmx");
            string inpPath = Path.ChangeExtension(pmxPath, ".inp");

            bool seedImported=false, built=false, saved=false, reopened=false, fixedOk=false, forceOk=false;
            long bytes=0; string sha256=""; string error=""; int nativeWidgets=-1;
            try
            {
                if (_controller.Model == null || _controller.Model.Mesh == null ||
                    _controller.Model.Mesh.Nodes.Count != 0 || _controller.Model.StepCollection.StepsList.Count != 0)
                    throw new InvalidOperationException("C8.58 requires a clean startup model; refusing to overwrite user/model data.");

                WriteSeedInp(inpPath);
                _controller.ImportFile(inpPath, false); // native PrePoMax INP path creates a valid mesh part
                seedImported = _controller.Model != null && _controller.Model.Mesh != null &&
                               _controller.Model.Mesh.Nodes.ContainsKey(1) && _controller.Model.Mesh.Nodes.ContainsKey(2) &&
                               _controller.Model.Mesh.Elements.Count > 0 && _controller.Model.Mesh.Parts.Count > 0;
                if (!seedImported) throw new InvalidOperationException("Native INP seed import did not create the expected FE part/mesh.");

                AddStructuralFixture(_controller.Model);
                built=true;
                _controller.SaveToPmx(pmxPath);
                saved=File.Exists(pmxPath) && new FileInfo(pmxPath).Length>0;
                if(saved){bytes=new FileInfo(pmxPath).Length;sha256=HashFile(pmxPath);}
                if(!saved) throw new InvalidOperationException("SaveToPmx produced no non-empty PMX file.");

                _controller.Open(pmxPath); // native extension dispatch -> OpenPmx
                reopened=_controller.Model!=null && _controller.Model.Mesh!=null && _controller.Model.Mesh.Parts.Count>0;
                if(!reopened) throw new InvalidOperationException("OpenPmx did not restore a model with FE parts.");

                fixedOk=HasExpectedAnchor(_controller.Model,"FIXTURE_FIXED",0,0,0);
                forceOk=HasExpectedAnchor(_controller.Model,"FIXTURE_FORCE_1000N_X",100,0,0);
                if(_anchors!=null)_anchors.RefreshNativeAnchors();
                nativeWidgets=ReadNativeWidgetCount(_vtk);
            }
            catch(Exception ex){error=ex.GetType().Name+": "+ex.Message;}
            WriteEvidence(evidencePath,pmxPath,seedImported,built,saved,reopened,fixedOk,forceOk,bytes,sha256,nativeWidgets,error);
        }

        private static void WriteSeedInp(string path)
        {
            string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            // Coordinates are explicitly millimetres. A single C3D4 gives PMX a real FE part/topology.
            string inp="*HEADING\r\nASTERMAX C8.58 PMX ROUNDTRIP SEED - UNITS MM\r\n"+
                       "*NODE\r\n1, 0., 0., 0.\r\n2, 100., 0., 0.\r\n3, 0., 10., 0.\r\n4, 0., 0., 10.\r\n"+
                       "*ELEMENT, TYPE=C3D4, ELSET=ASTERMAX_PART\r\n1, 1, 2, 3, 4\r\n";
            File.WriteAllText(path,inp,Encoding.ASCII);
        }

        private static void AddStructuralFixture(FeModel model)
        {
            if(model.Mesh.Nodes.Count<4 || model.Mesh.Elements.Count<1 || model.Mesh.Parts.Count<1)
                throw new InvalidOperationException("Imported FE seed is incomplete.");
            if(model.StepCollection.StepsList.Count!=0)
                throw new InvalidOperationException("Unexpected analysis steps in seed model.");

            model.Mesh.AddNodeSet(new FeNodeSet("FIXED_SET",new int[]{1}));
            model.Mesh.AddNodeSet(new FeNodeSet("FORCE_SET",new int[]{2}));
            StaticStep step=new StaticStep("STATIC_STRUCTURAL_FIXTURE");
            if(!step.AddBoundaryCondition(new FixedBC("FIXTURE_FIXED","FIXED_SET",RegionTypeEnum.NodeSetName,false)))
                throw new InvalidOperationException("FixedBC rejected by StaticStep.");
            if(!step.AddLoad(new CLoad("FIXTURE_FORCE_1000N_X","FORCE_SET",RegionTypeEnum.NodeSetName,1000.0,0.0,0.0,false,false,0.0)))
                throw new InvalidOperationException("CLoad rejected by StaticStep.");
            model.StepCollection.AddStep(step,false);
        }

        private static bool HasExpectedAnchor(object model,string name,double x,double y,double z)
        {
            object target=FindNamedStepItem(model,name); if(target==null)return false;
            try{
                MethodInfo resolver=typeof(AsterMaxRegionBindingInspector).GetMethod("ResolveAnchor",BindingFlags.NonPublic|BindingFlags.Static);
                object resolution=resolver==null?null:resolver.Invoke(null,new object[]{model,target}); if(resolution==null)return false;
                Type rt=resolution.GetType(); FieldInfo rf=rt.GetField("_resolved",BindingFlags.NonPublic|BindingFlags.Instance); FieldInfo xf=rt.GetField("_xyz",BindingFlags.NonPublic|BindingFlags.Instance);
                if(rf==null||xf==null||!(rf.GetValue(resolution) is bool)||!(bool)rf.GetValue(resolution))return false;
                double[] xyz=xf.GetValue(resolution) as double[]; if(xyz==null||xyz.Length<3)return false; const double eps=1e-9;
                return Math.Abs(xyz[0]-x)<eps&&Math.Abs(xyz[1]-y)<eps&&Math.Abs(xyz[2]-z)<eps;
            }catch{return false;}
        }

        private static object FindNamedStepItem(object model,string name)
        {
            IEnumerable steps=ReadMember(ReadMember(model,"StepCollection"),"StepsList") as IEnumerable; if(steps==null)return null;
            foreach(object step in steps)foreach(string member in new[]{"BoundaryConditions","Loads"}){
                IEnumerable items=ReadMember(step,member) as IEnumerable; if(items==null)continue;
                foreach(object raw in items){object target=ReadMember(raw,"Value")??raw;if(String.Equals(Convert.ToString(ReadMember(target,"Name"),CultureInfo.InvariantCulture),name,StringComparison.Ordinal))return target;}
            } return null;
        }

        private static object ReadMember(object target,string name)
        { if(target==null)return null; PropertyInfo p=target.GetType().GetProperty(name,BindingFlags.Public|BindingFlags.Instance|BindingFlags.IgnoreCase);if(p!=null)return p.GetValue(target,null);FieldInfo f=target.GetType().GetField(name,BindingFlags.Public|BindingFlags.Instance|BindingFlags.IgnoreCase);return f==null?null:f.GetValue(target); }

        private static int ReadNativeWidgetCount(vtkControl.vtkControl vtk)
        { try{FieldInfo f=vtk==null?null:vtk.GetType().GetField("_arrowWidgets",BindingFlags.NonPublic|BindingFlags.Instance);object c=f==null?null:f.GetValue(vtk);IDictionary d=c as IDictionary;if(d!=null)return d.Count;PropertyInfo p=c==null?null:c.GetType().GetProperty("Count");object v=p==null?null:p.GetValue(c,null);int n;return v!=null&&Int32.TryParse(v.ToString(),out n)?n:-1;}catch{return -1;} }

        private static string HashFile(string path)
        { using(SHA256 sha=SHA256.Create())using(FileStream fs=File.OpenRead(path)){byte[] h=sha.ComputeHash(fs);StringBuilder sb=new StringBuilder();foreach(byte b in h)sb.Append(b.ToString("x2",CultureInfo.InvariantCulture));return sb.ToString();} }
        private static string Json(string s){return "\""+(s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ")+"\"";}

        private static void WriteEvidence(string path,string pmxPath,bool seedImported,bool built,bool saved,bool reopened,bool fixedOk,bool forceOk,long bytes,string sha,int widgets,string error)
        {
            if(String.IsNullOrWhiteSpace(path))return;string dir=Path.GetDirectoryName(path);if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            bool verified=seedImported&&built&&saved&&reopened&&fixedOk&&forceOk&&widgets>=2&&String.IsNullOrEmpty(error);
            string json="{\n"+
                "  \"schema\": \"astermax.native-pmx-roundtrip.v2\",\n"+
                "  \"fixture_uses_real_caemodel_types\": true,\n"+
                "  \"native_inp_seed_imported\": "+(seedImported?"true":"false")+",\n"+
                "  \"native_save_to_pmx_called\": "+(built?"true":"false")+",\n"+
                "  \"pmx_file_exists_nonzero\": "+(saved?"true":"false")+",\n"+
                "  \"native_open_pmx_roundtrip\": "+(reopened?"true":"false")+",\n"+
                "  \"fixed_roundtrip_xyz_verified\": "+(fixedOk?"true":"false")+",\n"+
                "  \"force_roundtrip_xyz_verified\": "+(forceOk?"true":"false")+",\n"+
                "  \"pmx_bytes\": "+bytes.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"pmx_sha256\": "+Json(sha)+",\n"+
                "  \"native_arrow_widget_count\": "+widgets.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"loaded_pmx_fixture_proven\": "+(verified?"true":"false")+",\n"+
                "  \"solver_executed\": false,\n  \"solver_verified\": false,\n  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n"+
                "  \"pmx_path\": "+Json(pmxPath)+",\n  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,json,Encoding.UTF8);
        }
    }
}
