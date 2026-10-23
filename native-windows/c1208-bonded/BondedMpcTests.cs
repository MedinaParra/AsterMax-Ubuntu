using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using PrePoMax;

// These are definition/export checks, not solver results. The separate native
// Windows gate verifies actual Code_Aster displacement, stress and equilibrium.
public static class AsterMaxC1208BondedTests
{
    private static readonly JArray Checks = new JArray();
    private static void Check(string name, bool pass)
    {
        Checks.Add(new JObject { ["name"] = name, ["status"] = pass ? "PASS" : "FAIL" });
        if (!pass) throw new InvalidOperationException("C12.08 bonded check failed: " + name);
    }
    private static JObject Node(string id, double x, double y, double z)
    { return new JObject { ["id"] = id, ["x"] = x, ["y"] = y, ["z"] = z }; }
    private static JObject Surface(string name, string element, params string[] nodes)
    {
        return new JObject { ["source_surface"] = name, ["elements"] = new JArray(new JObject {
            ["id"] = name, ["type"] = "TRIA3", ["source_element_id"] = element, ["source_face"] = "S1", ["nodes"] = new JArray(nodes)
        }) };
    }
    private static JObject Tie(string name, JObject master, JObject slave)
    { return new JObject { ["name"] = name, ["position_tolerance_mm"] = 3.0, ["adjust"] = false, ["master"] = master, ["slave"] = slave }; }
    private static JObject Contract()
    {
        return new JObject {
            ["schema"] = "astermax-model-contract/v0", ["name"] = "C1208 synthetic MPC definition fixture",
            ["unit_system"] = "MM_N_S_MPA", ["analysis"] = new JObject { ["type"] = "static_structural" },
            ["mesh"] = new JObject {
                ["nodes"] = new JArray(Node("N1",0,0,0),Node("N2",0,10,0),Node("N3",0,0,10),Node("N4",-10,0,0),
                    Node("N5",2.5,1,1),Node("N6",2.5,3,1),Node("N7",2.5,1,3),Node("N8",12.5,1,1)),
                ["elements"] = new JArray(
                    new JObject { ["id"]="E1", ["type"]="TETRA4", ["nodes"]=new JArray("N1","N2","N3","N4") },
                    new JObject { ["id"]="E2", ["type"]="TETRA4", ["nodes"]=new JArray("N5","N6","N7","N8") }),
                ["node_groups"] = new JObject { ["FIXED"] = new JArray("N4"), ["LOAD"] = new JArray("N6","N8"), ["AM_B1"]=new JArray("N1") }
            },
            ["bonded_ties"] = new JArray(Tie("Bond",Surface("Master","E1","N1","N2","N3"),Surface("Slave","E2","N5","N6","N7"))),
            ["contacts"] = new JArray(),
            ["materials"] = new JArray(new JObject { ["young_modulus_mpa"] = 210000.0, ["poisson"] = 0.3 }),
            ["supports"] = new JArray(new JObject { ["name"]="Fixed", ["type"]="fixed", ["group"]="FIXED", ["dx"]=0.0, ["dy"]=0.0, ["dz"]=0.0 }),
            ["loads"] = new JArray(new JObject { ["name"]="Force", ["type"]="nodal_force_per_node", ["group"]="LOAD", ["fx_per_node_n"]=0.0, ["fy_per_node_n"]=-26000.0, ["fz_per_node_n"]=0.0 })
        };
    }
    private static void Reject(string name, JObject contract, string fragment, string root)
    {
        string path = Path.Combine(root, name), before = contract.ToString(Formatting.None), message = null;
        try { AsterMaxCodeAsterNativeExporter.ExportContract(contract,path,"blocked"); }
        catch (InvalidDataException ex) { message = ex.Message; }
        Check(name, message != null && message.Contains(fragment) && !Directory.Exists(path) && before == contract.ToString(Formatting.None));
    }
    private static JObject RotationContract()
    {
        JObject c = Contract();
        JObject groups = (JObject)c["mesh"]["node_groups"];
        JArray supports = (JArray)c["supports"];
        foreach (JObject node in ((JArray)c["mesh"]["nodes"]).Take(5))
        {
            string id = (string)node["id"];
            if (id == "N4") continue;
            double x = (double)node["x"] + 10.0, y = (double)node["y"], z = (double)node["z"];
            groups[id] = new JArray(id);
            supports.Add(new JObject { ["name"]="Rot"+id, ["type"]="displacement", ["group"]=id,
                ["dx"]=-0.0002*z-0.0003*y, ["dy"]=0.0003*x-0.0001*z, ["dz"]=0.0001*y+0.0002*x });
        }
        JObject duplicate = (JObject)c["bonded_ties"][0].DeepClone(); duplicate["name"]="Duplicate";
        ((JArray)c["bonded_ties"]).Add(duplicate);
        return c;
    }
    private static JObject CycleContract()
    {
        JObject c = Contract();
        var nodes = new JArray(); var elements = new JArray(); var faces = new JObject[3];
        for (int body = 0; body < 3; body++)
        {
            int k=4*body;
            nodes.Add(Node("N"+(k+1),0,0,0)); nodes.Add(Node("N"+(k+2),0,10,0));
            nodes.Add(Node("N"+(k+3),0,0,10)); nodes.Add(Node("N"+(k+4),-10,0,0));
            elements.Add(new JObject { ["id"]="E"+(body+1), ["type"]="TETRA4", ["nodes"]=new JArray("N"+(k+1),"N"+(k+2),"N"+(k+3),"N"+(k+4)) });
            faces[body]=Surface("Face"+body,"E"+(body+1),"N"+(k+1),"N"+(k+2),"N"+(k+3));
        }
        c["mesh"]["nodes"]=nodes; c["mesh"]["elements"]=elements;
        c["bonded_ties"]=new JArray(Tie("AB",(JObject)faces[0].DeepClone(),(JObject)faces[1].DeepClone()),
            Tie("BC",(JObject)faces[1].DeepClone(),(JObject)faces[2].DeepClone()),
            Tie("CA",(JObject)faces[2].DeepClone(),(JObject)faces[0].DeepClone()));
        return c;
    }
    public static JObject Run(string root)
    {
        Directory.CreateDirectory(root);
        JObject contract=Contract(), original=(JObject)contract.DeepClone();
        string output=Path.Combine(root,"affine-gap");
        JObject manifest=AsterMaxCodeAsterNativeExporter.ExportContract(contract,output,"bonded");
        JObject report=(JObject)manifest["bonded_mpc_report"];
        Check("one tie three slave nodes nine independent rows",(int)report["tie_count"]==1 && (int)report["raw_rows"]==9 && (int)report["retained_rows"]==9);
        Check("actual 2.5 mm gap admitted and reported",Math.Abs((double)report["maximum_gap_mm"]-2.5)<1e-12 && (int)report["unmatched_slave_node_count"]==0);
        Check("contract and coordinates remain unchanged",JToken.DeepEquals(original,contract) && !(bool)report["geometry_adjusted"]);
        Check("per-node load unchanged",(string)manifest["load_semantics"]=="PER_NODE_CLOAD" && (double)manifest["fy_per_node_n"]==-26000.0 && (double)manifest["fy_total_n"]==-52000.0);
        string command=File.ReadAllText(Path.Combine(output,"bonded.comm")),mail=File.ReadAllText(Path.Combine(output,"bonded.mail"));
        Check("Code_Aster ordered singleton GROUP_NO MPC syntax",command.Contains("LIAISON_DDL=(") && command.Contains("_F(GROUP_NO=(") && !command.Contains("NOEUD=") && command.Contains("_F(CHARGE=bonded), _F(CHARGE=load)"));
        Check("bonded path has volumes only and no nonlinear contact",!mail.Contains("\nTRIA3\n") && !command.Contains("DEFI_CONTACT") && command.Contains("MECA_STATIQUE"));
        Check("singleton groups avoid existing node-group collision",mail.Split(new[]{"GROUP_NO NOM = AM_B1\n"},StringSplitOptions.None).Length==2 && (int)report["singleton_node_group_count"]>0);
        JObject evidence=JObject.Parse(File.ReadAllText(Path.Combine(output,"bonded.bonded-mpc.json")));
        var nodes=((JArray)contract["mesh"]["nodes"]).Cast<JObject>().ToDictionary(n=>(string)n["id"]);
        foreach(JObject binding in (JArray)evidence["bindings"])
        {
            double[] w=((JArray)binding["weights"]).Select(v=>(double)v).ToArray();
            string[] ids=((JArray)binding["master_nodes"]).Select(v=>(string)v).ToArray();
            JObject slave=nodes[(string)binding["slave_node"]];
            bool affine=Math.Abs(w.Sum()-1)<1e-12;
            foreach(string axis in new[]{"x","y","z"})
                affine &= Math.Abs(Enumerable.Range(0,4).Sum(i=>w[i]*(double)nodes[ids[i]][axis])-(double)slave[axis])<1e-12;
            Check("independent affine identity "+(string)binding["slave_node"],affine && w.Any(v=>v<0));
        }
        JObject duplicate=Contract();
        JObject second=(JObject)duplicate["bonded_ties"][0].DeepClone(); second["name"]="Duplicate";
        ((JArray)duplicate["bonded_ties"]).Add(second);
        JObject duplicateReport=AsterMaxBondedMpc.Build(duplicate).Report;
        Check("duplicate multipair slave equations rank filtered",(int)duplicateReport["raw_rows"]==18 && (int)duplicateReport["retained_rows"]==9 && (int)duplicateReport["redundant_rows"]==9);
        JObject cycle=AsterMaxBondedMpc.Build(CycleContract()).Report;
        Check("three-body shared corner cycle retains exact independent rank",(int)cycle["raw_rows"]==27 && (int)cycle["retained_rows"]==18 && (int)cycle["redundant_rows"]==9);
        JObject rotation=AsterMaxBondedMpc.Build(RotationContract()).Report;
        Check("nonzero imposed rigid rotation and fixed slave redundancy",(int)rotation["retained_rows"]==6 && (int)rotation["redundant_rows"]==12 && (int)rotation["support_redundant_rows"]==6);
        JObject partial=Contract(); partial["mesh"]["nodes"][6]["y"]=100.0;
        JObject partialReport=AsterMaxBondedMpc.Build(partial).Report;
        Check("outside-tolerance node explicitly enumerated",(int)partialReport["raw_rows"]==6 && (int)partialReport["unmatched_slave_node_count"]==1 && (string)partialReport["per_tie"][0]["unmatched_node_ids"][0]=="N7");
        JObject sameFace=Contract();
        ((JArray)sameFace["bonded_ties"][0]["master"]["elements"]).Add(sameFace["bonded_ties"][0]["master"]["elements"][0].DeepClone());
        JObject sameReport=AsterMaxBondedMpc.Build(sameFace).Report;
        Check("duplicate face explicitly counted without duplicate coupling",(int)sameReport["per_tie"][0]["duplicate_master_faces"]==1 && (int)sameReport["raw_rows"]==9);
        JObject bad=RotationContract(); bad["supports"][4]["dx"]=(double)bad["supports"][4]["dx"]+0.01;
        Reject("incompatible_nonzero_support",bad,"contradice",root);
        bad=Contract(); bad["bonded_ties"][0]["position_tolerance_mm"]=1.0; Reject("no_nodes_within_tolerance",bad,"ningún nodo",root);
        bad=Contract(); bad["bonded_ties"][0]["position_tolerance_mm"]=JValue.CreateNull(); Reject("explicit_tolerance_required",bad,"numérico",root);
        bad=Contract(); bad["bonded_ties"][0]["adjust"]=true; Reject("unsupported_adjust_rejected",bad,"Adjust=false",root);
        bad=Contract(); bad["mesh"]["nodes"][3]["x"]=0.0; Reject("degenerate_master_rejected",bad,"degenerado",root);
        bad=Contract(); bad["mesh"]["nodes"][3]["x"]=-0.001; Reject("excessive_gap_extrapolation_rejected",bad,"Extrapolación excesiva",root);
        bad=Contract(); bad["bonded_ties"][0]["master"]["elements"][0]["source_element_id"]="Absent"; Reject("missing_volume_rejected",bad,"inexistente",root);
        bad=Contract(); bad["bonded_ties"][0]["master"]["elements"][0]["nodes"][0]="N8"; Reject("face_volume_mismatch_rejected",bad,"no pertenece",root);
        bad=Contract(); bad["mesh"]["elements"][0]["type"]="TETRA10"; Reject("unsupported_bonded_family_rejected",bad,"TETRA4",root);
        bad=Contract(); bad["bonded_ties"]=JValue.CreateNull(); Reject("malformed_bonded_array_rejected",bad,"lista",root);
        JObject empty=Contract(); empty.Remove("bonded_ties");
        Check("older contracts retain unbonded path",AsterMaxBondedMpc.Build(empty).TieCount==0);
        return new JObject { ["status"]="PASS", ["source"]="COMPILED_PRODUCTION_CSHARP", ["checks"]=Checks, ["solver_execution"]="NOT_RUN", ["fea_results_claimed"]=false };
    }
}
