using System;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization.Formatters.Binary;
using CaeGlobals;
using CaeMesh;
using CaeModel;
using Newtonsoft.Json.Linq;

// Windows/.NET Framework gate. Deserializes ONLY bytes created below from
// trusted synthetic objects, never a user PMX or other external stream.
public static class ForceNativeTests
{
    static int checks;
    static void Check(string name,bool pass) { if(!pass) throw new Exception(name); checks++; }
    static CLoad RoundTrip(CLoad force) {
        using(var stream=new MemoryStream()) {
            var formatter=new BinaryFormatter(); formatter.Serialize(stream,force);stream.Position=0;
            return (CLoad)formatter.Deserialize(stream);
        }
    }
    static string Fingerprint(Assembly app,FeModel model) {
        Type type=app.GetType("PrePoMax.AsterMaxModelFingerprint",true);
        object result=type.GetMethod("Extract").Invoke(null,new object[]{model});
        return (string)type.GetProperty("Sha256").GetValue(result,null);
    }
    public static JObject Run(Assembly app,string output) {
        checks=0;
        var original=new CLoad("Force","LOAD",RegionTypeEnum.NodeSetName,0,-26000,0,false,false,0);
        original.CreationIds=new[]{5,6};original.CreationData=new Selection();
        original.Active=false;original.Visible=false;original.Internal=true;
        CLoad total=original.WithForceDistribution(NodalForceDistribution.TotalUniformePorNodo);
        Check("explicit type and original unaffected",total is UniformTotalCLoad && original.GetType()==typeof(CLoad) && original.F2==total.F2);
        Check("selection and state preserved",total.RegionName==original.RegionName && total.RegionType==original.RegionType &&
            total.CreationIds.Length==2 && total.CreationIds[1]==6 && !total.Active && !total.Visible && total.Internal &&
            total.CreationData!=null && !Object.ReferenceEquals(total.CreationData,original.CreationData));
        total.CreationIds[0]=99;Check("copied selection does not mutate original",original.CreationIds[0]==5);
        CLoad round=RoundTrip(total);
        Check("total trusted roundtrip",round is UniformTotalCLoad && round.F2==-26000 && round.ForceDistribution==NodalForceDistribution.TotalUniformePorNodo);
        Check("existing CLoad trusted roundtrip remains per-node",RoundTrip(original).ForceDistribution==NodalForceDistribution.PorNodo);
        Check("explicit switch back preserves component values",total.WithForceDistribution(NodalForceDistribution.PorNodo).GetType()==typeof(CLoad));
        Type viewType=app.GetType("PrePoMax.ViewCLoad",true);
        object view=Activator.CreateInstance(viewType,new object[]{original});
        viewType.GetMethod("PopulateDropDownLists",new[]{typeof(string[]),typeof(string[]),typeof(string[])}).Invoke(view,new object[]{new[]{"LOAD","OTHER"},new string[0],new[]{"Default"}});
        viewType.GetProperty("ForceDistribution").SetValue(view,NodalForceDistribution.TotalUniformePorNodo,null);
        viewType.GetProperty("NodeSetName").SetValue(view,"OTHER",null);
        CLoad edited=(CLoad)viewType.GetMethod("GetBase").Invoke(view,null);
        Check("editor updates converted definition",edited is UniformTotalCLoad && edited.RegionName=="OTHER" && original.RegionName=="LOAD");

        var model=new FeModel("ForceNativeFixture");model.UnitSystem=new UnitSystem(UnitSystemType.MM_TON_S_C);
        model.Mesh.Nodes.Add(1,new FeNode(1,0,0,0));model.Mesh.Nodes.Add(2,new FeNode(2,1,0,0));
        model.Mesh.Nodes.Add(3,new FeNode(3,0,1,0));model.Mesh.Nodes.Add(4,new FeNode(4,0,0,1));
        model.Mesh.Elements.Add(1,new LinearTetraElement(1,new[]{1,2,3,4}));
        model.Mesh.NodeSets.Add("FIXED",new FeNodeSet("FIXED",new[]{1,2}));
        model.Mesh.NodeSets.Add("LOAD",new FeNodeSet("LOAD",new[]{3,4}));
        var steel=new Material("Steel");steel.AddProperty(new ElasticWithDensity(210000,0.3,7.85e-9));model.Materials.Add("Steel",steel);
        var step=new StaticStep("Step");step.AddBoundaryCondition(new FixedBC("Fixed","FIXED",RegionTypeEnum.NodeSetName,false));
        var perNode=new CLoad("Force","LOAD",RegionTypeEnum.NodeSetName,0,-26000,0,false,false,0);
        step.AddLoad(perNode);model.StepCollection.AddStep(step,false);
        string before=Fingerprint(app,model);
        step.Loads.Remove("Force");Check("StaticStep accepts total",step.AddLoad(perNode.WithForceDistribution(NodalForceDistribution.TotalUniformePorNodo)));
        Check("mode invalidates previous solution",before!=Fingerprint(app,model));
        var build=app.GetType("PrePoMax.AsterMaxModelContractBridge",true).GetMethod("Build");
        JObject contract=(JObject)build.Invoke(null,new object[]{model});
        Check("live model bridge carries explicit total",(string)contract["loads"][0]["type"]=="nodal_force_total" &&
            (double)contract["loads"][0]["fy_total_n"]==-26000 && contract["loads"][0]["fy_per_node_n"]==null);
        var exporter=app.GetType("PrePoMax.AsterMaxCodeAsterNativeExporter",true).GetMethod("ExportContract");
        var manifest=(JObject)exporter.Invoke(null,new object[]{contract,Path.Combine(output,"native-export"),"force"});
        Check("native compiled exporter uses divided force",(double)manifest["fy_per_node_n"]==-13000 && (double)manifest["fy_total_n"]==-26000);
        string oldScope=Fingerprint(app,model);model.Mesh.NodeSets["LOAD"].Labels=new[]{4};
        Check("changed selection invalidates previous solution",oldScope!=Fingerprint(app,model));
        contract=(JObject)build.Invoke(null,new object[]{model});
        manifest=(JObject)exporter.Invoke(null,new object[]{contract,Path.Combine(output,"changed-selection"),"force"});
        Check("changed live selection recomputes total",(double)manifest["fy_per_node_n"]==-26000 && (double)manifest["fy_total_n"]==-26000);
        var result=new JObject();result.Add("status","PASS");result.Add("checks",checks);
        result.Add("solver_execution","NOT_RUN");result.Add("interactive_gui_execution","NOT_RUN");
        result.Add("trusted_synthetic_model_and_editor_properties","PASS");return result;
    }
}
