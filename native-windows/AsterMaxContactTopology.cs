using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    /// <summary>
    /// Plans CONTINUE contact roles using real mesh node identities. Code_Aster
    /// requires the slave nodes of distinct zones to be disjoint. No geometry,
    /// node, face, contact law or model object is changed by this planner.
    /// Reversing roles changes the numerical contact discretization; the audit
    /// records it and the resulting solve still requires convergence/validation.
    /// </summary>
    public static class AsterMaxContactTopology
    {
        public const string Version = "C12.08-contact-diagnostics-v2";

        private sealed class Zone
        {
            public JObject Contact;
            public string Name;
            public bool Locked;
            // Choice 0 retains the original slave; choice 1 uses the original master.
            public HashSet<string>[] SlaveChoices;
        }

        private sealed class Conflict
        {
            public int A;
            public int B;
            public int Count;
            public readonly List<string> Sample = new List<string>();
        }

        public static JArray Normalize(JArray sourceContacts, JArray meshNodes, out JObject report)
        {
            var zones = new List<Zone>();
            int inactive = 0;
            foreach (JToken item in sourceContacts ?? new JArray())
            {
                JObject contact = item as JObject;
                if (contact == null) throw new InvalidDataException("El contrato de contacto contiene un par inválido.");
                string name = (string)contact["name"] ?? "Contacto " + (zones.Count + 1).ToString(CultureInfo.InvariantCulture);
                if (!ReadBoolean(contact, "active", true, name)) { inactive++; continue; }
                if (!ReadBoolean(contact, "valid", true, name))
                    throw new InvalidDataException("El contacto activo '" + name + "' no es válido. Revise sus superficies antes de resolver.");
                zones.Add(new Zone {
                    Contact = contact,
                    Name = name,
                    Locked = ReadBoolean(contact, "orientation_locked", false, name) |
                             ReadBoolean(contact, "master_slave_locked", false, name)
                });
            }

            var meshIds = new HashSet<string>(StringComparer.Ordinal);
            if (zones.Count > 0)
            {
                if (meshNodes == null) throw new InvalidDataException("Faltan los nodos reales de la malla para validar los contactos.");
                foreach (JToken item in meshNodes)
                {
                    JObject node = item as JObject;
                    string id = node == null ? null : ReadId(node["id"]);
                    if (String.IsNullOrWhiteSpace(id) || !meshIds.Add(id))
                        throw new InvalidDataException("La malla contiene un identificador de nodo vacío o duplicado: " + (id ?? "<vacío>"));
                }
            }

            var incidence = new Dictionary<string, List<int>>(StringComparer.Ordinal);
            for (int i = 0; i < zones.Count; i++)
            {
                Zone zone = zones[i];
                HashSet<string> slave = ReadSurfaceNodes(zone, "slave", meshIds);
                HashSet<string> master = ReadSurfaceNodes(zone, "master", meshIds);
                string[] overlap = slave.Intersect(master, StringComparer.Ordinal).OrderBy(x => x, StringComparer.Ordinal).ToArray();
                if (overlap.Length > 0)
                    throw new InvalidDataException("Contacto '" + zone.Name + "' (zona " + (i + 1) + "): las superficies maestra y esclava comparten " +
                        overlap.Length + " nodos reales (" + String.Join(", ", overlap.Take(12)) + "). Revise la selección de superficies o la unión de la malla; no se puede exportar como contacto entre superficies independientes.");
                zone.SlaveChoices = new[] { slave, master };
                for (int choice = 0; choice < 2; choice++)
                    foreach (string node in zone.SlaveChoices[choice])
                    {
                        List<int> choices;
                        if (!incidence.TryGetValue(node, out choices)) incidence[node] = choices = new List<int>();
                        choices.Add(2 * i + choice);
                    }
            }

            // One forbidden pair per pair of choices, even when thousands of
            // nodes are shared. The node samples are only diagnostic evidence.
            var constraints = new Dictionary<long, Conflict>();
            foreach (var entry in incidence.OrderBy(x => x.Key, StringComparer.Ordinal))
            {
                List<int> choices = entry.Value;
                for (int a = 0; a < choices.Count; a++)
                    for (int b = a + 1; b < choices.Count; b++)
                    {
                        int left = Math.Min(choices[a], choices[b]);
                        int right = Math.Max(choices[a], choices[b]);
                        if (left / 2 == right / 2) continue;
                        long key = ((long)left << 32) | (uint)right;
                        Conflict conflict;
                        if (!constraints.TryGetValue(key, out conflict))
                            constraints[key] = conflict = new Conflict { A = left, B = right };
                        conflict.Count++;
                        if (conflict.Sample.Count < 12) conflict.Sample.Add(entry.Key);
                    }
            }
            Conflict[] ordered = constraints.Values.OrderBy(x => x.A).ThenBy(x => x.B).ToArray();
            Conflict[] original = ordered.Where(x => x.A % 2 == 0 && x.B % 2 == 0).ToArray();
            int[] selected = new int[zones.Count];
            if (original.Length > 0)
            {
                var graph = new List<int>[2 * zones.Count];
                for (int i = 0; i < graph.Length; i++) graph[i] = new List<int>();
                foreach (Conflict conflict in ordered)
                {
                    // not (a and b) => a implies not b, b implies not a.
                    graph[conflict.A].Add(conflict.B ^ 1);
                    graph[conflict.B].Add(conflict.A ^ 1);
                }
                for (int i = 0; i < selected.Length; i++) selected[i] = zones[i].Locked ? 0 : -1;
                if (!IsSatisfiable(graph, selected))
                {
                    report = FailureReport(zones, ordered, original, inactive);
                    throw Impossible(zones, original, report);
                }

                // Deterministic lexicographic preference for original roles.
                // This is not a claim to minimize the total number of swaps.
                for (int i = 0; i < selected.Length; i++)
                {
                    if (selected[i] >= 0) continue;
                    selected[i] = 0;
                    if (!IsSatisfiable(graph, selected)) selected[i] = 1;
                }
            }
            foreach (Conflict conflict in ordered)
                if (selected[conflict.A / 2] == conflict.A % 2 && selected[conflict.B / 2] == conflict.B % 2)
                    throw new InvalidOperationException("La comprobación interna de la orientación de contactos ha fallado.");

            var normalized = new JArray();
            var auditZones = new JArray();
            int swappedCount = 0;
            for (int i = 0; i < zones.Count; i++)
            {
                Zone zone = zones[i];
                JObject clone = (JObject)zone.Contact.DeepClone();
                JObject originalMaster = (JObject)zone.Contact["master"];
                JObject originalSlave = (JObject)zone.Contact["slave"];
                bool swapped = selected[i] == 1;
                if (swapped)
                {
                    clone["master"] = originalSlave.DeepClone();
                    clone["slave"] = originalMaster.DeepClone();
                    swappedCount++;
                }
                normalized.Add(clone);
                auditZones.Add(new JObject {
                    ["zone_index"] = i + 1,
                    ["contact_name"] = zone.Name,
                    ["original_master_surface"] = SurfaceName(originalMaster),
                    ["original_slave_surface"] = SurfaceName(originalSlave),
                    ["exported_master_surface"] = SurfaceName((JObject)clone["master"]),
                    ["exported_slave_surface"] = SurfaceName((JObject)clone["slave"]),
                    ["original_master_group"] = (string)originalMaster["group"],
                    ["original_slave_group"] = (string)originalSlave["group"],
                    ["exported_master_group"] = (string)clone["master"]["group"],
                    ["exported_slave_group"] = (string)clone["slave"]["group"],
                    ["swapped"] = swapped,
                    ["orientation_locked"] = zone.Locked
                });
            }
            var auditConflicts = new JArray();
            foreach (Conflict conflict in original)
                auditConflicts.Add(new JObject {
                    ["zone_a"] = conflict.A / 2 + 1,
                    ["zone_b"] = conflict.B / 2 + 1,
                    ["contact_a"] = zones[conflict.A / 2].Name,
                    ["contact_b"] = zones[conflict.B / 2].Name,
                    ["shared_node_count"] = conflict.Count,
                    ["node_sample"] = new JArray(conflict.Sample)
                });
            report = new JObject {
                ["version"] = Version,
                ["status"] = swappedCount == 0 ? "UNCHANGED" : "REORIENTED",
                ["policy"] = "GLOBAL_2SAT_PREFER_ORIGINAL_IN_ZONE_ORDER",
                ["swapped_count"] = swappedCount,
                ["original_conflict_count"] = original.Length,
                ["resolved_conflict_count"] = original.Length,
                ["remaining_conflict_count"] = 0,
                ["inactive_contact_count"] = inactive,
                ["numerical_orientation_changed"] = swappedCount > 0,
                ["duplicate_pair_candidates"] = DuplicatePairs(zones),
                ["zones"] = auditZones,
                ["original_conflicts"] = auditConflicts
            };
            return normalized;
        }

        private static string ReadId(JToken value)
        {
            return value != null && value.Type == JTokenType.String ? (string)value : null;
        }

        private static bool ReadBoolean(JObject obj, string key, bool fallback, string name)
        {
            JToken value = obj[key];
            if (value == null) return fallback;
            if (value.Type != JTokenType.Boolean)
                throw new InvalidDataException("Contacto '" + name + "': " + key + " debe ser un valor booleano.");
            return (bool)value;
        }

        private static string SurfaceName(JObject surface)
        {
            return (string)surface["source_surface"] ?? (string)surface["group"];
        }

        private static HashSet<string> ReadSurfaceNodes(Zone zone, string role, HashSet<string> meshIds)
        {
            JObject surface = zone.Contact[role] as JObject;
            JArray faces = surface == null ? null : surface["elements"] as JArray;
            if (faces == null || faces.Count == 0 || String.IsNullOrWhiteSpace((string)surface["group"]))
                throw new InvalidDataException("Contacto '" + zone.Name + "': falta la superficie " + role + " o sus caras de malla.");
            var nodes = new HashSet<string>(StringComparer.Ordinal);
            foreach (JToken item in faces)
            {
                JObject face = item as JObject;
                JArray connectivity = face == null ? null : face["nodes"] as JArray;
                string type = face == null ? null : (string)face["type"];
                int required = type == "TRIA3" ? 3 : type == "QUAD4" ? 4 : type == "TRIA6" ? 6 : type == "QUAD8" ? 8 : 0;
                if (required == 0 || connectivity == null || connectivity.Count != required)
                    throw new InvalidDataException("Contacto '" + zone.Name + "', superficie " + SurfaceName(surface) + ": conectividad de cara " + (type ?? "<vacía>") + " inválida.");
                var faceNodes = new HashSet<string>(StringComparer.Ordinal);
                foreach (JToken token in connectivity)
                {
                    string id = ReadId(token);
                    if (String.IsNullOrWhiteSpace(id) || !meshIds.Contains(id))
                        throw new InvalidDataException("Contacto '" + zone.Name + "', superficie " + SurfaceName(surface) + ": el nodo " + (id ?? "<vacío>") + " no existe en la malla exportada.");
                    if (!faceNodes.Add(id))
                        throw new InvalidDataException("Contacto '" + zone.Name + "': la cara contiene el nodo duplicado " + id + ".");
                    nodes.Add(id);
                }
            }
            return nodes;
        }

        // Keep all forbidden role combinations, not only the first six original
        // slave overlaps. A visible overlap alone is not an unsatisfiability
        // proof: swaps may resolve it, while master/master conflicts can prevent
        // those swaps. These are current-mesh identities, never persistent CAD IDs.
        private static JObject FailureReport(List<Zone> zones, Conflict[] all, Conflict[] original, int inactive)
        {
            var conflicts = new JArray();
            var keys = zones.Select(z => new[] { FaceKeys((JObject)z.Contact["slave"]),
                FaceKeys((JObject)z.Contact["master"]) }).ToArray();
            foreach (Conflict c in all)
            {
                string roleA = c.A % 2 == 0 ? "slave" : "master";
                string roleB = c.B % 2 == 0 ? "slave" : "master";
                JObject a = (JObject)zones[c.A / 2].Contact[roleA];
                JObject b = (JObject)zones[c.B / 2].Contact[roleB];
                var facesA = keys[c.A / 2][c.A % 2];
                var facesB = keys[c.B / 2][c.B % 2];
                int commonFaces = facesA.Intersect(facesB, StringComparer.Ordinal).Count();
                conflicts.Add(new JObject {
                    ["zone_a"] = c.A / 2 + 1, ["zone_b"] = c.B / 2 + 1,
                    ["contact_a"] = zones[c.A / 2].Name, ["contact_b"] = zones[c.B / 2].Name,
                    ["original_role_a"] = roleA, ["original_role_b"] = roleB,
                    ["surface_a"] = SurfaceName(a), ["surface_b"] = SurfaceName(b),
                    ["group_a"] = (string)a["group"], ["group_b"] = (string)b["group"],
                    ["shared_node_count"] = c.Count, ["node_sample"] = new JArray(c.Sample),
                    ["shared_mesh_face_count"] = commonFaces,
                    ["overlap_kind"] = commonFaces > 0 ? "SHARED_MESH_FACE" : "SHARED_NODES_ONLY",
                    ["note"] = "La coincidencia de nodos no demuestra solape geométrico de área."
                });
            }
            return new JObject {
                ["schema"] = "astermax-contact-preflight-failure/v1",
                ["version"] = Version, ["status"] = "BLOCKED",
                ["reason"] = "NO_DISJOINT_SLAVE_ORIENTATION",
                ["solver_execution"] = "NOT_RUN", ["model_modified"] = false,
                ["original_conflict_count"] = original.Length,
                ["forbidden_role_combination_count"] = all.Length,
                ["inactive_contact_count"] = inactive,
                ["identity_scope"] = "CURRENT_EXPORTED_MESH_ONLY",
                ["constraints"] = conflicts,
                ["zones"] = new JArray(zones.Select((z, i) => new JObject {
                    ["zone_index"] = i + 1, ["contact_name"] = z.Name,
                    ["master"] = z.Contact["master"].DeepClone(),
                    ["slave"] = z.Contact["slave"].DeepClone(), ["orientation_locked"] = z.Locked
                })),
                ["duplicate_pair_candidates"] = DuplicatePairs(zones),
                ["locked_zones"] = new JArray(zones.Select((z, i) => new { z, i }).Where(x => x.z.Locked)
                    .Select(x => new JObject { ["zone_index"] = x.i + 1, ["contact_name"] = x.z.Name })),
                ["mechanical_action"] = "REVIEW_DEFINITION_NO_AUTOMATIC_LAW_CONVERSION"
            };
        }

        private static HashSet<string> FaceKeys(JObject surface)
        {
            return new HashSet<string>(((JArray)surface["elements"]).Cast<JObject>().Select(f =>
                (string)f["type"] + ":" + new JArray(((JArray)f["nodes"]).Select(n => (string)n)
                    .OrderBy(n => n, StringComparer.Ordinal)).ToString(Newtonsoft.Json.Formatting.None)), StringComparer.Ordinal);
        }

        private static JArray DuplicatePairs(List<Zone> zones)
        {
            // Matching mesh faces are evidence for review, not authority to erase
            // a two-pass contact or pick between potentially different laws.
            var keys = zones.Select(z => new[] { FaceKeys((JObject)z.Contact["master"]),
                FaceKeys((JObject)z.Contact["slave"]) }).ToArray();
            var result = new JArray();
            for (int a = 0; a < zones.Count; a++)
                for (int b = a + 1; b < zones.Count; b++)
                {
                    bool same = keys[a][0].SetEquals(keys[b][0]) && keys[a][1].SetEquals(keys[b][1]);
                    bool reversed = keys[a][0].SetEquals(keys[b][1]) && keys[a][1].SetEquals(keys[b][0]);
                    if (same || reversed) result.Add(new JObject {
                        ["zone_a"] = a + 1, ["zone_b"] = b + 1,
                        ["contact_a"] = zones[a].Name, ["contact_b"] = zones[b].Name,
                        ["kind"] = reversed ? "REVERSED_MESH_FACE_PAIR" : "SAME_MESH_FACE_PAIR",
                        ["action"] = "REVIEW_ONLY_NO_PAIR_REMOVED"
                    });
                }
            return result;
        }

        private static Exception Impossible(List<Zone> zones, Conflict[] original, JObject report)
        {
            string detail = String.Join("; ", original.Take(6).Select(c =>
                "'" + zones[c.A / 2].Name + "' (zona " + (c.A / 2 + 1) + ") y '" + zones[c.B / 2].Name + "' (zona " + (c.B / 2 + 1) +
                "): " + c.Count + " nodos esclavos comunes [" + String.Join(", ", c.Sample) + "]" +
                " (superficies '" + SurfaceName((JObject)zones[c.A / 2].Contact["slave"]) + "' / '" +
                SurfaceName((JObject)zones[c.B / 2].Contact["slave"]) + "')"));
            string locked = String.Join(", ", zones.Where(z => z.Locked).Select(z => z.Name));
            var error = new InvalidDataException("No existe una orientación maestra/esclava compatible con todos los contactos CONTINUE. " + detail +
                ". Mostrados " + Math.Min(6, original.Length) + " de " + original.Length + " cruces originales; comprobadas " +
                (int)report["forbidden_role_combination_count"] + " combinaciones de roles incompatibles" +
                (locked.Length == 0 ? "" : ". Orientaciones bloqueadas: " + locked) +
                ". Revise las superficies indicadas en Conexiones. CONTINUE es contacto unilateral, no una unión soldada. " +
                "Si la intención física es bonded, revise las uniones Tie y los contactos activos sobre esas interfaces; no se convierten automáticamente. " +
                "No se ha ejecutado Code_Aster.");
            error.Data["contact_topology_report"] = report.ToString(Newtonsoft.Json.Formatting.None);
            return error;
        }

        private static bool IsSatisfiable(List<int>[] baseGraph, int[] selected)
        {
            int count = baseGraph.Length;
            var graph = new List<int>[count];
            var reverse = new List<int>[count];
            for (int i = 0; i < count; i++) { graph[i] = new List<int>(baseGraph[i]); reverse[i] = new List<int>(); }
            for (int i = 0; i < selected.Length; i++)
                if (selected[i] >= 0) graph[2 * i + (selected[i] ^ 1)].Add(2 * i + selected[i]);
            for (int i = 0; i < count; i++) foreach (int target in graph[i]) reverse[target].Add(i);

            // Iterative Kosaraju avoids recursion depth depending on model size.
            var visited = new bool[count];
            var next = new int[count];
            var order = new List<int>(count);
            var stack = new Stack<int>();
            for (int start = 0; start < count; start++)
            {
                if (visited[start]) continue;
                stack.Push(start); visited[start] = true;
                while (stack.Count > 0)
                {
                    int at = stack.Peek();
                    if (next[at] < graph[at].Count)
                    {
                        int target = graph[at][next[at]++];
                        if (!visited[target]) { visited[target] = true; stack.Push(target); }
                    }
                    else { stack.Pop(); order.Add(at); }
                }
            }
            var component = new int[count];
            for (int i = 0; i < count; i++) component[i] = -1;
            int label = 0;
            for (int i = order.Count - 1; i >= 0; i--)
            {
                int start = order[i];
                if (component[start] >= 0) continue;
                stack.Push(start); component[start] = label;
                while (stack.Count > 0)
                {
                    int at = stack.Pop();
                    foreach (int target in reverse[at])
                        if (component[target] < 0) { component[target] = label; stack.Push(target); }
                }
                label++;
            }
            for (int i = 0; i < selected.Length; i++) if (component[2 * i] == component[2 * i + 1]) return false;
            return true;
        }
    }
}
