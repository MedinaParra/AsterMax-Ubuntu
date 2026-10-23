using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using PrePoMax;

// Model-definition fixtures only. These checks compile the production exporter
// and planner; they do not execute Code_Aster or fabricate a result field.
public static class AsterMaxC1207ContactTests
{
    private static readonly JArray Checks = new JArray();
    private static void Check(string name, bool pass)
    {
        Checks.Add(new JObject { ["name"] = name, ["status"] = pass ? "PASS" : "FAIL" });
        if (!pass) throw new InvalidOperationException("C12.07 contact topology check failed: " + name);
    }

    private static string[] Ids(string prefix, int count = 3)
    {
        return Enumerable.Range(1, count).Select(i => prefix + i.ToString("000", CultureInfo.InvariantCulture)).ToArray();
    }

    private static JObject Surface(string name, string group, string idPrefix, string[] nodes)
    {
        var faces = new JArray();
        for (int i = 0; i < nodes.Length; i += 3)
            faces.Add(new JObject {
                ["id"] = idPrefix + (i / 3 + 1).ToString("000", CultureInfo.InvariantCulture),
                ["type"] = "TRIA3", ["source_element_id"] = "EV1", ["source_face"] = "S1",
                ["nodes"] = new JArray(nodes.Skip(i).Take(3))
            });
        return new JObject { ["source_surface"] = name, ["group"] = group, ["elements"] = faces };
    }

    private static JObject Pair(int index, string[] master, string[] slave)
    {
        string tag = index.ToString("000", CultureInfo.InvariantCulture);
        return new JObject {
            ["name"] = "Contacto " + index,
            ["surface_interaction"] = "Frictionless",
            ["method"] = "SurfaceToSurface", ["formulation"] = "CONTINUE",
            ["friction"] = "SANS", ["friction_coefficient"] = 0.0,
            ["friction_stick_slope"] = JValue.CreateNull(),
            ["small_sliding"] = false, ["adjust"] = true,
            ["contact_init"] = "OUI",
            ["master"] = Surface("Master " + index, "AM_M" + tag, "M" + tag, master),
            ["slave"] = Surface("Slave " + index, "AM_S" + tag, "S" + tag, slave)
        };
    }

    private static JObject Contract(JArray contacts)
    {
        var ids = new HashSet<string>(new[] { "V1", "V2", "V3", "V4" }, StringComparer.Ordinal);
        foreach (JObject contact in contacts.OfType<JObject>())
            foreach (string role in new[] { "master", "slave" })
            {
                JArray faces = contact[role] == null ? null : contact[role]["elements"] as JArray;
                if (faces != null)
                    foreach (JObject face in faces.OfType<JObject>())
                        foreach (JToken node in (JArray)face["nodes"]) ids.Add((string)node);
            }
        var nodes = new JArray(ids.OrderBy(x => x, StringComparer.Ordinal).Select((id, i) => new JObject {
            ["id"] = id, ["x"] = i, ["y"] = 0.0, ["z"] = 0.0
        }));
        return new JObject {
            ["schema"] = "astermax-model-contract/v0", ["name"] = "C1207 topology fixture - not FEA evidence",
            ["unit_system"] = "MM_N_S_MPA", ["analysis"] = new JObject { ["type"] = "static_structural" },
            ["mesh"] = new JObject {
                ["nodes"] = nodes,
                ["elements"] = new JArray(new JObject { ["id"] = "EV1", ["type"] = "TETRA4", ["nodes"] = new JArray("V1", "V2", "V3", "V4") }),
                ["node_groups"] = new JObject { ["FIXED"] = new JArray("V1"), ["LOAD"] = new JArray("V2") }
            },
            ["contacts"] = contacts,
            ["materials"] = new JArray(new JObject { ["young_modulus_mpa"] = 210000.0, ["poisson"] = 0.3 }),
            ["supports"] = new JArray(new JObject { ["name"] = "Fixed", ["type"] = "fixed", ["group"] = "FIXED", ["dx"] = 0, ["dy"] = 0, ["dz"] = 0 }),
            ["loads"] = new JArray(new JObject { ["name"] = "Load", ["type"] = "nodal_force_per_node", ["group"] = "LOAD", ["fx_per_node_n"] = -1.0, ["fy_per_node_n"] = 0, ["fz_per_node_n"] = 0 })
        };
    }

    private static JArray Normalize(JObject contract, out JObject report)
    {
        return AsterMaxContactTopology.Normalize((JArray)contract["contacts"], (JArray)contract["mesh"]["nodes"], out report);
    }

    private static HashSet<string> SurfaceNodes(JObject contact, string role)
    {
        return new HashSet<string>(((JArray)contact[role]["elements"]).Cast<JObject>()
            .SelectMany(f => ((JArray)f["nodes"]).Select(n => (string)n)), StringComparer.Ordinal);
    }

    private static bool SlaveDisjoint(JArray contacts)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (JObject contact in contacts)
            foreach (string node in SurfaceNodes(contact, "slave")) if (!seen.Add(node)) return false;
        return true;
    }

    private static void RejectBeforeWrite(string name, JObject contract, string expected, string root)
    {
        string output = Path.Combine(root, name);
        string before = contract.ToString(Formatting.None);
        string error = null;
        try { AsterMaxCodeAsterNativeExporter.ExportContract(contract, output, "blocked"); }
        catch (InvalidDataException ex) { error = ex.Message; }
        Check(name, error != null && error.Contains(expected) && !Directory.Exists(output) && contract.ToString(Formatting.None) == before);
    }

    private static int[] BruteForce(JArray contacts)
    {
        int n = contacts.Count;
        // Enumerate assignments in lexical zone order, independently of 2-SAT.
        for (int bits = 0; bits < (1 << n); bits++)
        {
            int[] selected = new int[n];
            var seen = new HashSet<string>(StringComparer.Ordinal);
            bool valid = true;
            for (int i = 0; i < n && valid; i++)
            {
                selected[i] = (bits >> (n - 1 - i)) & 1;
                JObject contact = (JObject)contacts[i];
                if (selected[i] == 1 && ((bool?)contact["orientation_locked"] == true || (bool?)contact["master_slave_locked"] == true)) { valid = false; break; }
                foreach (string node in SurfaceNodes(contact, selected[i] == 0 ? "slave" : "master"))
                    if (!seen.Add(node)) { valid = false; break; }
            }
            if (valid) return selected;
        }
        return null;
    }

    public static JObject Run(string root)
    {
        Directory.CreateDirectory(root);
        JObject report;
        JArray normalized = Normalize(Contract(new JArray()), out report);
        Check("empty contact list stays empty", normalized.Count == 0 && (string)report["status"] == "UNCHANGED");

        JObject disjoint = Contract(new JArray(Pair(1, Ids("A"), Ids("B")), Pair(2, Ids("C"), Ids("D"))));
        normalized = Normalize(disjoint, out report);
        Check("valid original roles remain unchanged", JToken.DeepEquals(normalized, disjoint["contacts"]) && (int)report["swapped_count"] == 0);
        JObject objectContacts = (JObject)disjoint.DeepClone(); objectContacts["contacts"] = new JObject { ["name"] = "Malformed pair container" };
        RejectBeforeWrite("object contact container rejected before output", objectContacts, "contacts debe ser una lista", root);
        JObject stringContacts = (JObject)disjoint.DeepClone(); stringContacts["contacts"] = "not an array";
        RejectBeforeWrite("string contact container rejected before output", stringContacts, "contacts debe ser una lista", root);
        JObject nullContacts = (JObject)disjoint.DeepClone(); nullContacts["contacts"] = JValue.CreateNull();
        RejectBeforeWrite("explicit null contact container rejected before output", nullContacts, "contacts debe ser una lista", root);
        JObject absentContacts = Contract(new JArray()); absentContacts.Remove("contacts");
        JObject absentManifest = AsterMaxCodeAsterNativeExporter.ExportContract(absentContacts, Path.Combine(root, "no-contact-export"), "no-contact");
        Check("absent optional contacts remains a linear model", (int)absentManifest["contact_pair_count"] == 0 && (string)absentManifest["contact_solver_path"] == "MECA_STATIQUE");

        string[] center = Ids("C", 12);
        var starContacts = new JArray(Pair(1, Ids("A", 12), center), Pair(2, Ids("B", 12), center), Pair(3, Ids("D", 12), center));
        ((JObject)starContacts[1])["friction"] = "COULOMB";
        ((JObject)starContacts[1])["friction_coefficient"] = 0.31;
        ((JObject)starContacts[1])["friction_stick_slope"] = 12500.0;
        ((JObject)starContacts[1])["small_sliding"] = true;
        ((JObject)starContacts[1])["adjust"] = false;
        ((JObject)starContacts[1])["custom_contact_property"] = "retained exactly";
        JObject star = Contract(starContacts);
        string originalText = star.ToString(Formatting.None);
        normalized = Normalize(star, out report);
        Check("12-node star resolves all slave conflicts", SlaveDisjoint(normalized) && (int)report["swapped_count"] == 2 && (int)report["remaining_conflict_count"] == 0);
        Check("star audit counts exact shared FE nodes", (int)report["original_conflict_count"] == 3 && ((JArray)report["original_conflicts"]).All(c => (int)c["shared_node_count"] == 12));
        Check("deterministic original preference retains first zone", !(bool)report["zones"][0]["swapped"] && (bool)report["zones"][1]["swapped"] && (bool)report["zones"][2]["swapped"]);
        Check("normalization leaves caller contract byte-for-byte unchanged", star.ToString(Formatting.None) == originalText);
        bool preserves = true;
        for (int i = 0; i < starContacts.Count; i++)
        {
            JObject before = (JObject)starContacts[i]; JObject after = (JObject)normalized[i];
            foreach (JProperty property in before.Properties().Where(p => p.Name != "master" && p.Name != "slave"))
                preserves &= JToken.DeepEquals(property.Value, after[property.Name]);
            bool swap = (bool)report["zones"][i]["swapped"];
            preserves &= JToken.DeepEquals(before["master"], after[swap ? "slave" : "master"]);
            preserves &= JToken.DeepEquals(before["slave"], after[swap ? "master" : "slave"]);
        }
        Check("all face IDs, connectivity, law, friction and properties preserved", preserves);
        Check("audit identifies changed numerical orientation and source groups", (bool)report["numerical_orientation_changed"] && (string)report["zones"][1]["exported_slave_group"] == "AM_M002" && (string)report["zones"][1]["original_slave_group"] == "AM_S002");
        JObject againReport;
        JArray again = Normalize(star, out againReport);
        Check("repeated planning is deterministic", JToken.DeepEquals(again, normalized) && JToken.DeepEquals(againReport, report));

        JObject chain = Contract(new JArray(Pair(1, Ids("A"), Ids("B")), Pair(2, Ids("C"), Ids("B")), Pair(3, Ids("D"), Ids("C"))));
        chain["contacts"][2]["orientation_locked"] = true;
        normalized = Normalize(chain, out report);
        Check("global chain solution avoids local-greedy dead end", SlaveDisjoint(normalized) && (bool)report["zones"][0]["swapped"] && !(bool)report["zones"][1]["swapped"] && !(bool)report["zones"][2]["swapped"]);
        Check("explicit orientation lock remains original", (bool)report["zones"][2]["orientation_locked"] && JToken.DeepEquals(chain["contacts"][2], normalized[2]));
        JObject triangle = Contract(new JArray(Pair(1, Ids("A"), Ids("B")), Pair(2, Ids("B"), Ids("C")), Pair(3, Ids("C"), Ids("A"))));
        normalized = Normalize(triangle, out report);
        Check("orientable simple cycle is accepted", SlaveDisjoint(normalized) && (string)report["status"] == "UNCHANGED");

        var impossible = new JArray();
        string[] bodies = new[] { "A", "B", "C", "D" };
        int edge = 0;
        for (int a = 0; a < bodies.Length; a++) for (int b = a + 1; b < bodies.Length; b++) impossible.Add(Pair(++edge, Ids(bodies[a]), Ids(bodies[b])));
        RejectBeforeWrite("multi-cycle infeasible topology blocked before export", Contract(impossible), "No existe una orientación", root);
        JObject locked = Contract(new JArray(Pair(1, Ids("A"), Ids("C")), Pair(2, Ids("B"), Ids("C"))));
        locked["contacts"][0]["orientation_locked"] = true;
        locked["contacts"][1]["master_slave_locked"] = true;
        RejectBeforeWrite("incompatible explicit role locks preserved and rejected", locked, "Orientaciones bloqueadas", root);
        RejectBeforeWrite("same-pair master-slave overlap rejected", Contract(new JArray(Pair(1, new[] { "N1", "N2", "N3" }, new[] { "N1", "N4", "N5" }))), "comparten 1 nodos reales", root);

        JObject missing = (JObject)disjoint.DeepClone();
        missing["contacts"][0]["slave"]["elements"][0]["nodes"][0] = "MISSING";
        RejectBeforeWrite("missing FE node rejected before output", missing, "MISSING no existe", root);
        JObject duplicate = (JObject)disjoint.DeepClone();
        duplicate["contacts"][0]["slave"]["elements"][0]["nodes"][1] = duplicate["contacts"][0]["slave"]["elements"][0]["nodes"][0].DeepClone();
        RejectBeforeWrite("degenerate contact face rejected", duplicate, "nodo duplicado", root);
        JObject duplicateMesh = (JObject)disjoint.DeepClone();
        ((JArray)duplicateMesh["mesh"]["nodes"]).Add(duplicateMesh["mesh"]["nodes"][0].DeepClone());
        RejectBeforeWrite("duplicate mesh node identity rejected", duplicateMesh, "identificador de nodo", root);
        JObject invalid = (JObject)disjoint.DeepClone(); invalid["contacts"][0]["valid"] = false;
        RejectBeforeWrite("active invalid contact rejected", invalid, "contacto activo", root);
        JObject inactive = Contract(new JArray(new JObject { ["name"] = "Disabled broken contact", ["active"] = false, ["valid"] = false }));
        normalized = Normalize(inactive, out report);
        Check("inactive invalid contact omitted without exporting its surfaces", normalized.Count == 0 && (int)report["inactive_contact_count"] == 1);
        JObject invalidLock = (JObject)disjoint.DeepClone(); invalidLock["contacts"][0]["orientation_locked"] = "true";
        RejectBeforeWrite("ambiguous orientation lock type rejected", invalidLock, "debe ser un valor booleano", root);

        JObject exact = Contract(new JArray(Pair(1, new[] { "A1", "A10", "A100" }, new[] { "N1", "N10", "N100" }), Pair(2, new[] { "B1", "B10", "B100" }, new[] { "N2", "N20", "N200" })));
        foreach (JObject node in (JArray)exact["mesh"]["nodes"]) { node["x"] = 0.0; node["y"] = 0.0; node["z"] = 0.0; }
        normalized = Normalize(exact, out report);
        Check("node identities use exact IDs not prefixes or coincident coordinates", (string)report["status"] == "UNCHANGED" && JToken.DeepEquals(normalized, exact["contacts"]));

        string exportDir = Path.Combine(root, "production-star-export");
        JObject manifest = AsterMaxCodeAsterNativeExporter.ExportContract(star, exportDir, "star");
        string comm = File.ReadAllText(Path.Combine(exportDir, "star.comm"));
        Check("production exporter emits corrected master-slave groups", comm.Contains("GROUP_MA_MAIT='AM_S002', GROUP_MA_ESCL='AM_M002'") && comm.Contains("GROUP_MA_MAIT='AM_M001', GROUP_MA_ESCL='AM_S001'"));
        Check("production exporter preserves contact law and coefficient", comm.Contains("FORMULATION='CONTINUE'") && comm.Contains("FROTTEMENT='COULOMB'") && comm.Contains("CONTACT_INIT='OUI', COULOMB=0.31"));
        Check("ten nonlinear increments retained and final MED selected", comm.Contains("JUSQU_A=1.0, NOMBRE=10") && comm.Contains("IMPR_RESU(FORMAT='MED', UNITE=81, RESU=_F(RESULTAT=result, INST=1.0))"));
        Check("contact displacement table selects same final instant", comm.Contains("NOM_CMP=('DX','DY','DZ'), INST=1.0") && !comm.Contains("TOUT_ORDRE='OUI'"));
        Check("manifest persists one-based role audit and final result time", (double)manifest["exported_result_time"] == 1.0 && (int)manifest["contact_orientation_report"]["zones"][1]["zone_index"] == 2 && JToken.DeepEquals(manifest, JObject.Parse(File.ReadAllText(Path.Combine(exportDir, "star.native-export.json")))));
        string[] mailLines = File.ReadAllLines(Path.Combine(exportDir, "star.mail"));
        bool facesKept = true;
        foreach (JObject contact in starContacts)
            foreach (string role in new[] { "master", "slave" })
                foreach (JObject face in (JArray)contact[role]["elements"])
                {
                    string expected = (string)face["id"] + " " + String.Join(" ", ((JArray)face["nodes"]).Select(n => (string)n));
                    facesKept &= mailLines.Count(line => line == expected) == 1;
                }
        Check("production mail keeps every skin ID and connectivity exactly once", facesKept);
        Check("production export leaves original contract unchanged", star.ToString(Formatting.None) == originalText);
        Check("model definition export does not claim solver results", (string)manifest["solver_execution"] == "NOT_RUN" && !(bool)manifest["fea_results_claimed"]);

        var random = new Random(1207);
        const int randomCases = 160;
        int satisfiable = 0, rejected = 0;
        for (int sample = 0; sample < randomCases; sample++)
        {
            int n = 1 + random.Next(6);
            var contacts = new JArray();
            for (int i = 0; i < n; i++)
            {
                string[] pool = Enumerable.Range(1, 24).OrderBy(x => random.Next()).Select(x => "R" + x.ToString("000", CultureInfo.InvariantCulture)).ToArray();
                int leftSize = random.Next(2) == 0 ? 3 : 6;
                JObject pair = Pair(i + 1, pool.Take(leftSize).ToArray(), pool.Skip(leftSize).Take(3).ToArray());
                if (random.Next(5) == 0) pair["orientation_locked"] = true;
                contacts.Add(pair);
            }
            int[] expected = BruteForce(contacts);
            JObject c = Contract(contacts);
            JArray actual = null; JObject actualReport = null;
            try { actual = Normalize(c, out actualReport); }
            catch (InvalidDataException) { if (expected != null) throw; }
            if (expected == null) { if (actual != null) throw new InvalidOperationException("2-SAT accepted a brute-force impossible fixture."); rejected++; }
            else
            {
                if (actual == null || !SlaveDisjoint(actual)) throw new InvalidOperationException("2-SAT failed a brute-force feasible fixture.");
                for (int i = 0; i < n; i++)
                    if ((bool)actualReport["zones"][i]["swapped"] != (expected[i] == 1)) throw new InvalidOperationException("2-SAT violated lexical original preference.");
                satisfiable++;
            }
        }
        Check("160 seeded partial-overlap topologies match independent exhaustive oracle", satisfiable > 0 && rejected > 0 && satisfiable + rejected == randomCases);

        return new JObject {
            ["candidate"] = "C12.07", ["status"] = "PASS", ["checks"] = Checks,
            ["random_exhaustive_comparisons"] = randomCases,
            ["random_feasible"] = satisfiable, ["random_infeasible"] = rejected,
            ["production_csharp_compilation"] = "PASS", ["solver_execution"] = "NOT_RUN",
            ["gui_execution"] = "NOT_RUN", ["fea_results_claimed"] = false
        };
    }
}
