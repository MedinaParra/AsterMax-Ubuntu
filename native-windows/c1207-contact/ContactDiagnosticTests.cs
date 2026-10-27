using System;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using PrePoMax;

// Tests of production preflight only; coordinates are not solver fixtures.
public static class ContactDiagnosticTests
{
    static int checks;
    static void Check(bool value, string name) { if (!value) throw new Exception(name); checks++; }
    static JObject Surface(string name, params string[] nodes) {
        return new JObject { ["source_surface"] = name, ["group"] = name,
            ["elements"] = new JArray(new JObject { ["id"] = name, ["type"] = "TRIA3", ["nodes"] = new JArray(nodes) }) };
    }
    static JObject Pair(int i, JObject m, JObject s) {
        return new JObject { ["name"] = "Pair" + i, ["master"] = m.DeepClone(), ["slave"] = s.DeepClone(),
            ["formulation"] = "CONTINUE", ["friction"] = "SANS" };
    }
    static JArray Nodes(JArray pairs) {
        return new JArray(pairs.Cast<JObject>().SelectMany(p => new[] { "master", "slave" }
            .SelectMany(r => ((JArray)p[r]["elements"][0]["nodes"]).Select(n => (string)n)))
            .Distinct().Select(n => new JObject { ["id"] = n }));
    }
    static JObject Reject(JArray pairs) {
        string before = pairs.ToString(Formatting.None);
        JObject report = null;
        try { AsterMaxContactTopology.Normalize(pairs, Nodes(pairs), out report); }
        catch (InvalidDataException ex) {
            Check(pairs.ToString(Formatting.None) == before, "failure mutated source");
            Check(report != null && JToken.DeepEquals(report, JObject.Parse((string)ex.Data["contact_topology_report"])), "failure report not retained");
            Check((string)report["solver_execution"] == "NOT_RUN", "claims solve");
            Check(ex.Message.Contains("bonded") && ex.Message.Contains("superficies"), "actionable law/surface diagnosis absent");
            return report;
        }
        throw new Exception("Expected unsatisfiable topology");
    }
    public static JObject Run(string output) {
        checks = 0;
        var a = Surface("A", "A1", "A2", "A3");
        var b = Surface("B", "B1", "B2", "B3");
        var c = Surface("C", "C1", "C2", "C3");
        JObject report;
        var reversed = new JArray(Pair(1,a,b), Pair(2,b,a));
        string original = reversed.ToString(Formatting.None);
        var result = AsterMaxContactTopology.Normalize(reversed, Nodes(reversed), out report);
        Check(result.Count == 2 && reversed.ToString(Formatting.None) == original, "reverse pair silently removed or changed");
        Check(report["duplicate_pair_candidates"] is JArray, "duplicate pair diagnostic absent in baseline");
        Check((string)report["duplicate_pair_candidates"][0]["kind"] == "REVERSED_MESH_FACE_PAIR", "reverse duplicate unidentified");
        var same = new JArray(Pair(1,a,b), Pair(2,a,b));
        result = AsterMaxContactTopology.Normalize(same, Nodes(same), out report);
        Check(result.Count == 2 && (int)report["swapped_count"] == 1, "same duplicate changed existing role policy");
        Check((string)report["duplicate_pair_candidates"][0]["kind"] == "SAME_MESH_FACE_PAIR", "same duplicate unidentified");

        // A shared edge is still two shared slave nodes; it is not an area overlap.
        var edge = new JArray(Pair(1,a,Surface("Edge1", "X1","X2","X3")), Pair(2,b,Surface("Edge2", "X1","X2","X4")));
        foreach (JObject pair in edge) pair["orientation_locked"] = true;
        report = Reject(edge);
        Check((int)report["constraints"][0]["shared_node_count"] == 2 && (int)report["constraints"][0]["shared_mesh_face_count"] == 0, "edge misclassified as face");
        Check((string)report["constraints"][0]["overlap_kind"] == "SHARED_NODES_ONLY", "edge diagnosis wrong");
        edge[1]["slave"] = Surface("Corner", "X1","X5","X6");
        report = Reject(edge);
        Check((int)report["constraints"][0]["shared_node_count"] == 1, "corner incorrectly ignored");

        var triple = new JArray(Pair(1,a,b),Pair(2,a,b),Pair(3,a,b));
        report = Reject(triple);
        Check((int)report["forbidden_role_combination_count"] == 6, "master conflicts missing");
        Check(((JArray)report["constraints"]).Any(x => (string)x["original_role_a"] == "master"), "failure only reports original slaves");
        Check(((JArray)report["constraints"]).All(x => (int)x["shared_mesh_face_count"] == 1), "shared face missed");
        Check((string)report["identity_scope"] == "CURRENT_EXPORTED_MESH_ONLY", "mesh IDs claimed persistent");
        // More than six original conflicts: no truncation in machine-readable evidence.
        var many = new JArray(Enumerable.Range(1,5).Select(i=>Pair(i,a,b)));
        report = Reject(many);
        Check((int)report["original_conflict_count"] == 10 && ((JArray)report["constraints"]).Count == 20, "full conflicts truncated");
        Directory.CreateDirectory(output);
        File.WriteAllText(Path.Combine(output,"blocked-topology-example.json"),report.ToString());
        var stale = new JArray(Pair(1,a,b));
        var nodes = Nodes(stale); nodes.RemoveAt(0);
        try { AsterMaxContactTopology.Normalize(stale,nodes,out report); throw new Exception("stale mesh accepted"); }
        catch(InvalidDataException ex) { Check(ex.Message.Contains("no existe en la malla"),"wrong stale ID diagnostic"); }
        // No coordinate matching or mm/m assumptions enter this ID-only preflight.
        var independent = new JArray(Pair(1,a,b),Pair(2,c,Surface("D","D1","D2","D3")));
        result = AsterMaxContactTopology.Normalize(independent,Nodes(independent),out report);
        Check(result.Count==2 && (string)report["status"]=="UNCHANGED", "disjoint geometry changed");
        return new JObject { ["status"]="PASS", ["checks"]=checks, ["solver_execution"]="NOT_RUN", ["gui_execution"]="NOT_RUN" };
    }
}
