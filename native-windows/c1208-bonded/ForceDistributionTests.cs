using System;
using System.IO;
using System.Linq;
using System.Globalization;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using PrePoMax;

public static class ForceDistributionTests
{
    static JArray checks = new JArray();
    static void Check(string name, bool ok) { checks.Add(new JObject { ["name"]=name,["pass"]=ok }); if(!ok) throw new Exception(name); }
    public static JObject Fixture(int count, bool total)
    {
        // Real HEXA8 connectivity; these are export tests, not structural solves.
        int layers=(count+3)/4+1;
        var nodes=new JArray(); var elements=new JArray();
        for(int z=0;z<=layers;z++) for(int j=0;j<4;j++) nodes.Add(new JObject {
            ["id"]="N"+(z*4+j+1),["x"]=j==1||j==2?1:0,["y"]=j>=2?1:0,["z"]=z });
        for(int z=0;z<layers;z++) elements.Add(new JObject { ["id"]="E"+(z+1),["type"]="HEXA8",
            ["nodes"]=new JArray(Enumerable.Range(z*4+1,8).Select(i=>"N"+i)) });
        var force=new JObject { ["name"]="Force",["group"]="LOAD",["type"]=total?"nodal_force_total":"nodal_force_per_node" };
        string suffix=total?"_total_n":"_per_node_n";
        force["fx"+suffix]=13.0;force["fy"+suffix]=-26000.0;force["fz"+suffix]=0.0;
        if(total) force["distribution"]="UNIFORM_PER_SELECTED_NODE";
        return new JObject {
            ["schema"]="astermax-model-contract/v0",["name"]="Synthetic force definition",
            ["unit_system"]="MM_N_S_MPA",["analysis"]=new JObject { ["type"]="static_structural" },
            ["mesh"]=new JObject { ["nodes"]=nodes,["elements"]=elements,["node_groups"]=new JObject {
                ["FIXED"]=new JArray("N1","N2","N3","N4"),["LOAD"]=new JArray(Enumerable.Range(5,count).Select(i=>"N"+i)) } },
            ["materials"]=new JArray(new JObject { ["young_modulus_mpa"]=210000.0,["poisson"]=0.3 }),
            ["supports"]=new JArray(new JObject { ["name"]="Fixed",["type"]="fixed",["group"]="FIXED",["dx"]=0,["dy"]=0,["dz"]=0 }),
            ["loads"]=new JArray(force),["contacts"]=new JArray(),["bonded_ties"]=new JArray()
        };
    }
    static double Fy(string comm) {
        int start=comm.IndexOf("FORCE_NODALE=",StringComparison.Ordinal);
        if(start<0) throw new Exception("Production FORCE_NODALE absent");
        start=comm.IndexOf("FY=",start,StringComparison.Ordinal)+3;
        int end=comm.IndexOf(',',start);
        return Double.Parse(comm.Substring(start,end-start),CultureInfo.InvariantCulture);
    }
    static double Sum(double value,int count) {
        double sum=0,correction=0;
        for(int i=0;i<count;i++) { double y=value-correction;double t=sum+y;correction=(t-sum)-y;sum=t; }
        return sum;
    }
    static void Reject(string name,JObject c,string root) {
        string dir=Path.Combine(root,name),before=c.ToString(Formatting.None);
        try { AsterMaxCodeAsterNativeExporter.ExportContract(c,dir,"bad"); }
        catch(Exception ex) {
            if(!(ex is InvalidDataException) && !(ex is NotSupportedException)) throw;
            Check(name,!Directory.Exists(dir) && before==c.ToString(Formatting.None));return;
        }
        throw new Exception("Accepted invalid load: "+name);
    }
    public static JObject Run(string root) {
        Directory.CreateDirectory(root);checks=new JArray();
        foreach(int count in new[]{1,2,3,3299}) foreach(bool total in new[]{false,true}) {
            var c=Fixture(count,total); string before=c.ToString(Formatting.None);
            string dir=Path.Combine(root,(total?"total-":"per-node-")+count);
            var plan=AsterMaxForceDistribution.Build(c);
            var manifest=AsterMaxCodeAsterNativeExporter.ExportContract(c,dir,"force");
            double actual=Fy(File.ReadAllText(Path.Combine(dir,"force.comm")));
            double target=total?-26000.0:-26000.0*count;
            Check("actual comm resultant "+total+"/"+count,Math.Abs(Sum(actual,count)-target)<1e-8);
            Check("manifest and input unchanged "+total+"/"+count,(int)manifest["load_nodes"]==count &&
                Math.Abs((double)manifest["fy_total_n"]-target)<1e-8 && before==c.ToString(Formatting.None));
            Check("preview matches export "+total+"/"+count,plan.Fy==actual &&
                (bool)plan.Report["multi_node_per_node_warning"]==(!total&&count>1));
        }
        var remesh=Fixture(3,true);var oldPlan=AsterMaxForceDistribution.Build(remesh);
        ((JArray)remesh["mesh"]["node_groups"]["LOAD"]).Add("N8");
        var newPlan=AsterMaxForceDistribution.Build(remesh);
        Check("changed mesh selection recomputes total distribution",oldPlan.NodeCount==3&&newPlan.NodeCount==4&&oldPlan.Fy!=newPlan.Fy&&newPlan.FyTotal==-26000);
        var legacy=Fixture(3,true);((JObject)legacy["loads"][0]).Remove("distribution");
        Check("legacy total JSON preserved",AsterMaxForceDistribution.Build(legacy).Semantics=="LEGACY_TOTAL_DISTRIBUTED");
        var bad=Fixture(3,true);bad["mesh"]["node_groups"]["LOAD"]=new JArray();Reject("empty",bad,root);
        bad=Fixture(3,true);((JArray)bad["mesh"]["node_groups"]["LOAD"]).Add("N5");Reject("duplicate-selection",bad,root);
        bad=Fixture(3,true);bad["mesh"]["node_groups"]["LOAD"][0]="MISSING";Reject("stale-node",bad,root);
        bad=Fixture(3,true);((JArray)bad["mesh"]["nodes"]).Add(bad["mesh"]["nodes"][0].DeepClone());Reject("duplicate-mesh-id",bad,root);
        bad=Fixture(3,true);bad["unit_system"]="M_N_S_PA";Reject("metre-units",bad,root);
        bad=Fixture(3,true);bad["loads"][0]["fy_per_node_n"]=-1;Reject("mixed-semantics",bad,root);
        bad=Fixture(3,false);bad["loads"][0]["type"]="nodal_force_total";Reject("type-field-mismatch",bad,root);
        bad=Fixture(3,true);bad["loads"][0]["distribution"]="AREA";Reject("area-not-nodal",bad,root);
        bad=Fixture(3,true);((JArray)bad["loads"]).Add(new JObject { ["type"]="pressure",["value"]=1 });Reject("pressure-not-converted",bad,root);
        bad=Fixture(3,true);bad["loads"][0]["fy_total_n"]=Double.NaN;Reject("nan-force",bad,root);
        bad=Fixture(3,false);bad["loads"][0]["fy_per_node_n"]=Double.MaxValue;Reject("overflow-resultant",bad,root);
        bad=Fixture(3,true);bad["loads"][0]["fy_total_n"]="-26000";Reject("string-component",bad,root);
        bad=Fixture(3,true);bad["loads"][0]["fy_total_n"]=JValue.CreateNull();Reject("null-component",bad,root);
        var tiny=Fixture(3,true);tiny["loads"][0]["fy_total_n"]=-3e-25;
        var tinyDir=Path.Combine(root,"tiny");AsterMaxCodeAsterNativeExporter.ExportContract(tiny,tinyDir,"tiny");
        Check("actual comm preserves tiny nonzero force",Fy(File.ReadAllText(Path.Combine(tinyDir,"tiny.comm")))==-3e-25/3);
        string preview=AsterMaxForceDistribution.Describe(Fixture(3299,false),AsterMaxForceDistribution.Build(Fixture(3299,false)));
        Check("preview warns and identifies actual connection definitions",preview.Contains("ATENCIÓN")&&preview.Contains("3299")&&preview.Contains("0 contactos CONTINUE y 0 uniones bonded")&&preview.Contains("no convierte"));
        return new JObject { ["status"]="PASS",["checks"]=checks,["production_exporter_compiled"]=true,
            ["solver_execution"]="NOT_RUN",["gui_execution"]="NOT_RUN",["private_model_used"]=false };
    }
}
