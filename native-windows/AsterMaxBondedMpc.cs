using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    /// <summary>
    /// Linear, small-displacement welded ties for nonmatching TETRA4 meshes.
    /// The adjacent master tetra's affine field is evaluated at the ACTUAL
    /// slave position, including an explicitly admitted gap. No mesh is moved.
    /// Partition of unity and coordinate reproduction preserve all six rigid
    /// modes and the moment of the internal constraint forces across a gap.
    /// This is a massless affine kinematic extension, not a meshed weld material.
    ///
    /// Code_Aster U4.44.01 sections 5.7 / 5.13 (v16, 09/03/2024):
    /// https://code-aster.org/doc/v16/man_u/u4/u4.44.01.pdf
    /// LIAISON_DDL accepts ordered GROUP_NO/DDL/COEF_MULT relations. LIAISON_MAIL
    /// MASSIF instead projects out-of-volume points to the boundary, so plain
    /// translation equality there does not reproduce rotation across a gap.
    /// </summary>
    public static class AsterMaxBondedMpc
    {
        public const string Version = "C12.08-bonded-mpc-v1";
        public const double MaximumAbsoluteWeight = 100.0;
        public const double RankRelativeTolerance = 1.0e-12;
        private const int MaximumReducedRowTerms = 4096;
        private const long MaximumBasisTerms = 8000000;
        private static readonly string[] Axes = { "DX", "DY", "DZ" };

        internal sealed class Node
        {
            internal string Id;
            internal int Index;
            internal double X, Y, Z;
        }
        internal sealed class Tetra
        {
            internal string Id;
            internal int[] Nodes;
            internal double[] Inverse;
            internal double Scale;
        }
        internal sealed class Face
        {
            internal string Key;
            internal int[] Nodes;
            internal Tetra Tetra;
            internal double[] Min, Max, Center;
        }
        internal sealed class Tree
        {
            internal double[] Min, Max;
            internal Tree Left, Right;
            internal Face[] Faces;
        }
        internal sealed class Binding
        {
            internal string TieName;
            internal int Slave;
            internal Tetra Master;
            internal double[] Weights;
            internal double Gap, AffineResidual;
            internal int[] RowNodes;
            internal double[] Coefficients;
            internal int ExportedAxes;
        }

        public sealed class Plan
        {
            internal Node[] Nodes;
            internal readonly List<Binding> Bindings = new List<Binding>();
            internal readonly Dictionary<int, string> NodeGroups = new Dictionary<int, string>();
            public JObject Report { get; internal set; }
            public int TieCount { get { return (int)Report["tie_count"]; } }
            public int EquationCount { get { return (int)Report["retained_rows"]; } }

            // Modern Code_Aster accepts ordered node GROUPS in LIAISON_DDL.
            // Singleton groups retain unambiguous coefficient-to-node ordering.
            public void AppendNodeGroups(List<string> mail, HashSet<string> usedNames)
            {
                var usedNodes = new SortedSet<int>();
                foreach (Binding b in Bindings)
                    if (b.ExportedAxes != 0)
                        foreach (int n in b.RowNodes) usedNodes.Add(n);
                int serial = 0;
                foreach (int n in usedNodes)
                {
                    string name;
                    do { name = "AM_B" + (++serial).ToString("X", CultureInfo.InvariantCulture); }
                    while (!usedNames.Add(name));
                    NodeGroups.Add(n, name);
                    mail.Add("GROUP_NO NOM = " + name);
                    mail.Add(Nodes[n].Id);
                    mail.Add("FINSF");
                }
                Report["singleton_node_group_count"] = NodeGroups.Count;
            }

            public string AddToCommand(string command)
            {
                if (EquationCount == 0) return command;
                if (NodeGroups.Count == 0) throw new InvalidOperationException("C12.08 bonded node groups were not written.");
                var lines = new StringBuilder();
                lines.Append("# C12.08 affine welded ties at actual slave coordinates; mesh unchanged.\n");
                lines.Append("bonded = AFFE_CHAR_MECA(\n    MODELE=model,\n    LIAISON_DDL=(\n");
                foreach (Binding b in Bindings)
                {
                    for (int axis = 0; axis < 3; axis++)
                    {
                        if ((b.ExportedAxes & (1 << axis)) == 0) continue;
                        lines.Append("        _F(GROUP_NO=(");
                        foreach (int n in b.RowNodes) lines.Append("'").Append(NodeGroups[n]).Append("',");
                        lines.Append("), DDL=(");
                        foreach (int n in b.RowNodes) lines.Append("'").Append(Axes[axis]).Append("',");
                        lines.Append("), COEF_MULT=(");
                        foreach (double c in b.Coefficients) lines.Append(Number(c)).Append(',');
                        lines.Append("), COEF_IMPO=0.0),\n");
                    }
                }
                lines.Append("    ),\n)\n\n");
                const string loadAnchor = "load = AFFE_CHAR_MECA(";
                const string excitation = "_F(CHARGE=load)";
                if (!command.Contains(loadAnchor) || !command.Contains(excitation))
                    throw new InvalidOperationException("C12.08 bonded command insertion anchors are missing.");
                command = command.Replace(loadAnchor, lines.ToString() + loadAnchor);
                return command.Replace(excitation, "_F(CHARGE=bonded), " + excitation);
            }

            public void WriteBindings(string fileName)
            {
                if (TieCount == 0) return;
                using (var stream = new StreamWriter(fileName, false, new UTF8Encoding(false)))
                using (var writer = new JsonTextWriter(stream))
                {
                    writer.Formatting = Formatting.None;
                    writer.WriteStartObject();
                    writer.WritePropertyName("schema"); writer.WriteValue("astermax-bonded-bindings/v1");
                    writer.WritePropertyName("report"); Report.WriteTo(writer);
                    writer.WritePropertyName("bindings"); writer.WriteStartArray();
                    foreach (Binding b in Bindings)
                    {
                        writer.WriteStartObject();
                        writer.WritePropertyName("tie"); writer.WriteValue(b.TieName);
                        writer.WritePropertyName("slave_node"); writer.WriteValue(Nodes[b.Slave].Id);
                        writer.WritePropertyName("master_element"); writer.WriteValue(b.Master.Id);
                        writer.WritePropertyName("master_nodes"); writer.WriteStartArray();
                        foreach (int n in b.Master.Nodes) writer.WriteValue(Nodes[n].Id);
                        writer.WriteEndArray();
                        writer.WritePropertyName("weights"); writer.WriteStartArray();
                        foreach (double w in b.Weights) writer.WriteValue(w);
                        writer.WriteEndArray();
                        writer.WritePropertyName("distance_mm"); writer.WriteValue(b.Gap);
                        writer.WritePropertyName("affine_residual_mm"); writer.WriteValue(b.AffineResidual);
                        writer.WritePropertyName("exported_axes"); writer.WriteStartArray();
                        for (int axis = 0; axis < 3; axis++)
                            if ((b.ExportedAxes & (1 << axis)) != 0) writer.WriteValue(Axes[axis]);
                        writer.WriteEndArray(); writer.WriteEndObject();
                    }
                    writer.WriteEndArray(); writer.WriteEndObject();
                }
            }
        }

        public static Plan Build(JObject contract)
        {
            if (contract == null) throw new ArgumentNullException("contract");
            JToken token = contract["bonded_ties"];
            if (token != null && !(token is JArray))
                throw Error("El campo bonded_ties debe ser una lista de uniones soldadas.");
            JArray ties = token as JArray ?? new JArray();
            var result = new Plan();
            var perTie = new JArray();
            result.Report = new JObject
            {
                ["schema"] = "astermax-bonded-mpc/v1",
                ["version"] = Version,
                ["status"] = ties.Count == 0 ? "NO_BONDED_TIES" : "READY",
                ["algorithm"] = "TETRA4_AFFINE_AT_ACTUAL_SLAVE",
                ["kinematics"] = "SMALL_DISPLACEMENT_AFFINE_EXTENSION",
                ["geometry_adjusted"] = false,
                ["tie_count"] = ties.Count,
                ["raw_rows"] = 0,
                ["retained_rows"] = 0,
                ["redundant_rows"] = 0,
                ["support_redundant_rows"] = 0,
                ["unmatched_slave_node_count"] = 0,
                ["maximum_gap_mm"] = 0.0,
                ["maximum_abs_weight"] = 0.0,
                ["maximum_affine_residual_mm"] = 0.0,
                ["maximum_allowed_abs_weight"] = MaximumAbsoluteWeight,
                ["rank_relative_tolerance"] = RankRelativeTolerance,
                ["singleton_node_group_count"] = 0,
                ["per_tie"] = perTie,
                ["solver_execution"] = "NOT_RUN"
            };
            if (ties.Count == 0) return result;

            JObject mesh = contract["mesh"] as JObject;
            JArray nodeArray = mesh == null ? null : mesh["nodes"] as JArray;
            JArray elementArray = mesh == null ? null : mesh["elements"] as JArray;
            JObject groups = mesh == null ? null : mesh["node_groups"] as JObject;
            if (nodeArray == null || elementArray == null || groups == null)
                throw Error("Las uniones soldadas requieren nodos, elementos y grupos de nodos válidos.");
            var nodes = new List<Node>(nodeArray.Count);
            var nodeById = new Dictionary<string, Node>(StringComparer.Ordinal);
            foreach (JObject item in nodeArray)
            {
                string id = RequiredId(item["id"], "nodo");
                if (nodeById.ContainsKey(id)) throw Error("Nodo duplicado: " + id);
                var n = new Node { Id = id, Index = nodes.Count, X = Finite(item["x"], id), Y = Finite(item["y"], id), Z = Finite(item["z"], id) };
                nodeById.Add(id, n); nodes.Add(n);
            }
            result.Nodes = nodes.ToArray();
            var elements = new Dictionary<string, JObject>(StringComparer.Ordinal);
            foreach (JObject item in elementArray)
            {
                string id = RequiredId(item["id"], "elemento");
                if (elements.ContainsKey(id)) throw Error("Elemento duplicado: " + id);
                elements.Add(id, item);
            }
            var tetraCache = new Dictionary<string, Tetra>(StringComparer.Ordinal);
            Dictionary<int, double>[] prescribed = ReadSupports(contract["supports"] as JArray, groups, nodeById);
            var bases = new RankBasis[3];
            for (int axis = 0; axis < 3; axis++) bases[axis] = new RankBasis(prescribed[axis]);
            var tieNames = new HashSet<string>(StringComparer.Ordinal);

            foreach (JObject tie in ties)
            {
                string name = (string)tie["name"];
                if (String.IsNullOrWhiteSpace(name) || !tieNames.Add(name))
                    throw Error("Cada unión soldada debe tener un nombre único no vacío.");
                double tolerance = Finite(tie["position_tolerance_mm"], "tolerancia de " + name);
                if (tolerance <= 0) throw Error("La tolerancia de la unión '" + name + "' debe ser mayor que cero.");
                JToken adjust = tie["adjust"];
                if (adjust == null || adjust.Type != JTokenType.Boolean || adjust.Value<bool>())
                    throw Error("La unión '" + name + "' requiere Adjust=false. El acoplamiento conserva las coordenadas originales.");
                int masterDuplicates, slaveDuplicates;
                Face[] masters = ReadSurface(tie["master"] as JObject, name, "maestra", elements, nodeById, tetraCache, result.Nodes, out masterDuplicates);
                Face[] slaves = ReadSurface(tie["slave"] as JObject, name, "esclava", elements, nodeById, tetraCache, result.Nodes, out slaveDuplicates);
                Tree tree = BuildTree(masters, 0, masters.Length);
                int[] slaveNodes = slaves.SelectMany(f => f.Nodes).Distinct().OrderBy(i => i).ToArray();
                var unmatched = new JArray();
                var audit = new JObject
                {
                    ["name"] = name,
                    ["master_surface"] = (string)tie["master"]["source_surface"],
                    ["slave_surface"] = (string)tie["slave"]["source_surface"],
                    ["position_tolerance_mm"] = tolerance,
                    ["slave_node_count"] = slaveNodes.Length,
                    ["bound_node_count"] = 0,
                    ["unmatched_node_count"] = 0,
                    ["unmatched_node_ids"] = unmatched,
                    ["duplicate_master_faces"] = masterDuplicates,
                    ["duplicate_slave_faces"] = slaveDuplicates,
                    ["raw_rows"] = 0,
                    ["retained_rows"] = 0,
                    ["redundant_rows"] = 0,
                    ["support_redundant_rows"] = 0,
                    ["maximum_gap_mm"] = 0.0,
                    ["maximum_abs_weight"] = 0.0,
                    ["maximum_affine_residual_mm"] = 0.0
                };
                foreach (int slave in slaveNodes)
                {
                    Face nearest = null;
                    double distance2 = tolerance * tolerance * (1.0 + 1.0e-12);
                    FindNearest(tree, result.Nodes[slave], result.Nodes, ref nearest, ref distance2);
                    if (nearest == null) { unmatched.Add(result.Nodes[slave].Id); continue; }
                    Binding binding = MakeBinding(name, slave, nearest.Tetra, Math.Sqrt(Math.Max(0, distance2)), result.Nodes);
                    result.Bindings.Add(binding);
                    Increment(audit, "bound_node_count", 1);
                    Increment(audit, "raw_rows", 3);
                    Maximum(audit, "maximum_gap_mm", binding.Gap);
                    Maximum(audit, "maximum_abs_weight", binding.Weights.Max(w => Math.Abs(w)));
                    Maximum(audit, "maximum_affine_residual_mm", binding.AffineResidual);
                    for (int axis = 0; axis < 3; axis++)
                    {
                        bool supportOnly;
                        if (bases[axis].Add(binding.RowNodes, binding.Coefficients, slave, name + "/" + result.Nodes[slave].Id + "/" + Axes[axis], out supportOnly))
                        {
                            binding.ExportedAxes |= 1 << axis;
                            Increment(audit, "retained_rows", 1);
                        }
                        else
                        {
                            Increment(audit, "redundant_rows", 1);
                            if (supportOnly) Increment(audit, "support_redundant_rows", 1);
                        }
                    }
                }
                audit["unmatched_node_count"] = unmatched.Count;
                if ((int)audit["bound_node_count"] == 0)
                    throw Error("La unión '" + name + "' no tiene ningún nodo esclavo dentro de su tolerancia explícita de " + Number(tolerance) + " mm. Revise las superficies y la tolerancia.");
                perTie.Add(audit);
                foreach (string count in new[] { "raw_rows", "retained_rows", "redundant_rows", "support_redundant_rows" })
                    Increment(result.Report, count, (int)audit[count]);
                Increment(result.Report, "unmatched_slave_node_count", unmatched.Count);
                foreach (string max in new[] { "maximum_gap_mm", "maximum_abs_weight", "maximum_affine_residual_mm" })
                    Maximum(result.Report, max, (double)audit[max]);
            }
            result.Report["candidate_binding_count"] = result.Bindings.Count;
            result.Report["unique_bound_slave_nodes"] = result.Bindings.Select(b => b.Slave).Distinct().Count();
            result.Report["rank_basis_terms"] = bases.Sum(b => b.TermCount);
            result.Report["maximum_rank_row_terms"] = bases.Max(b => b.MaximumRowTerms);
            result.Report["unmatched_nodes_note"] = "Los nodos fuera de la tolerancia explícita no se unen; se enumeran por unión y no se desplaza la malla.";
            return result;
        }

        private static Dictionary<int, double>[] ReadSupports(JArray supports, JObject groups, Dictionary<string, Node> nodes)
        {
            if (supports == null) throw Error("Falta la definición de apoyos para verificar las uniones soldadas.");
            var values = new[] { new Dictionary<int, double>(), new Dictionary<int, double>(), new Dictionary<int, double>() };
            foreach (JObject support in supports)
            {
                string group = (string)support["group"];
                JArray ids = String.IsNullOrWhiteSpace(group) ? null : groups[group] as JArray;
                if (ids == null || ids.Count == 0) throw Error("Grupo de apoyo vacío o inexistente: " + group);
                for (int axis = 0; axis < 3; axis++)
                {
                    JToken token = support[Axes[axis].ToLowerInvariant()];
                    if (token == null || token.Type == JTokenType.Null) continue;
                    double value = Finite(token, "desplazamiento impuesto " + group);
                    foreach (JToken id in ids)
                    {
                        Node node;
                        if (!nodes.TryGetValue((string)id, out node)) throw Error("Nodo inexistente en apoyo: " + (string)id);
                        double previous;
                        if (values[axis].TryGetValue(node.Index, out previous))
                        {
                            if (Math.Abs(previous - value) > 1.0e-12 * Math.Max(1.0, Math.Max(Math.Abs(previous), Math.Abs(value))))
                                throw Error("Apoyos incompatibles en " + node.Id + "/" + Axes[axis] + ".");
                            // Repeated DDL_IMPO in distinct loads can itself have
                            // duplicate Lagrange multipliers. Do not silently
                            // edit a user's support definition in a tie planner.
                            throw Error("El apoyo " + node.Id + "/" + Axes[axis] + " está impuesto más de una vez. Unifique los grupos de apoyo antes de resolver uniones soldadas.");
                        }
                        values[axis].Add(node.Index, value);
                    }
                }
            }
            return values;
        }

        private static Face[] ReadSurface(JObject surface, string tie, string role, Dictionary<string, JObject> elements,
            Dictionary<string, Node> nodes, Dictionary<string, Tetra> cache, Node[] allNodes, out int duplicates)
        {
            JArray faces = surface == null ? null : surface["elements"] as JArray;
            if (faces == null || faces.Count == 0) throw Error("La unión '" + tie + "' tiene una superficie " + role + " vacía.");
            var unique = new Dictionary<string, Face>(StringComparer.Ordinal);
            duplicates = 0;
            foreach (JObject raw in faces)
            {
                if (!String.Equals((string)raw["type"], "TRIA3", StringComparison.OrdinalIgnoreCase))
                    throw Error("C12.08 admite uniones soldadas TETRA4/TRIA3; superficie " + role + " de '" + tie + "'.");
                string source = (string)raw["source_element_id"];
                JObject element;
                if (String.IsNullOrWhiteSpace(source) || !elements.TryGetValue(source, out element))
                    throw Error("Elemento maestro/esclavo inexistente en unión '" + tie + "': " + source);
                Tetra tetra;
                if (!cache.TryGetValue(source, out tetra))
                {
                    if (!String.Equals((string)element["type"], "TETRA4", StringComparison.OrdinalIgnoreCase))
                        throw Error("C12.08 admite uniones soldadas sobre TETRA4. Elemento: " + source);
                    int[] connectivity = ReadConnectivity(element["nodes"] as JArray, 4, nodes, source);
                    tetra = MakeTetra(source, connectivity, allNodes);
                    cache.Add(source, tetra);
                }
                int[] fn = ReadConnectivity(raw["nodes"] as JArray, 3, nodes, tie + "/" + role);
                if (fn.Any(n => !tetra.Nodes.Contains(n)))
                    throw Error("La cara de la unión '" + tie + "' no pertenece a su elemento " + source + ".");
                string key = source + ":" + String.Join(",", fn.OrderBy(n => n));
                if (unique.ContainsKey(key)) { duplicates++; continue; }
                var f = new Face { Key = key, Nodes = fn, Tetra = tetra, Min = new double[3], Max = new double[3], Center = new double[3] };
                for (int axis = 0; axis < 3; axis++)
                {
                    f.Min[axis] = fn.Min(n => Coordinate(allNodes[n], axis));
                    f.Max[axis] = fn.Max(n => Coordinate(allNodes[n], axis));
                    f.Center[axis] = (f.Min[axis] + f.Max[axis]) * 0.5;
                }
                unique.Add(key, f);
            }
            return unique.Values.OrderBy(f => f.Key, StringComparer.Ordinal).ToArray();
        }

        private static int[] ReadConnectivity(JArray ids, int count, Dictionary<string, Node> nodes, string label)
        {
            if (ids == null || ids.Count != count) throw Error("Conectividad inválida: " + label);
            var result = new int[count];
            for (int i = 0; i < count; i++)
            {
                Node node;
                if (!nodes.TryGetValue((string)ids[i], out node)) throw Error("Nodo inexistente en " + label + ": " + (string)ids[i]);
                result[i] = node.Index;
            }
            if (result.Distinct().Count() != count) throw Error("Nodos repetidos en " + label);
            return result;
        }

        private static Tetra MakeTetra(string id, int[] indices, Node[] nodes)
        {
            Node a = nodes[indices[0]], b = nodes[indices[1]], c = nodes[indices[2]], d = nodes[indices[3]];
            double bx = b.X - a.X, by = b.Y - a.Y, bz = b.Z - a.Z;
            double cx = c.X - a.X, cy = c.Y - a.Y, cz = c.Z - a.Z;
            double dx = d.X - a.X, dy = d.Y - a.Y, dz = d.Z - a.Z;
            double determinant = bx * (cy * dz - cz * dy) - cx * (by * dz - bz * dy) + dx * (by * cz - bz * cy);
            double scale = 0;
            for (int i = 0; i < 4; i++)
                for (int j = i + 1; j < 4; j++) scale = Math.Max(scale, Math.Sqrt(Distance2(nodes[indices[i]], nodes[indices[j]])));
            if (scale <= 0 || Math.Abs(determinant) <= 1.0e-12 * scale * scale * scale)
                throw Error("Tetraedro degenerado o demasiado plano para una unión soldada estable: " + id);
            return new Tetra
            {
                Id = id, Nodes = indices, Scale = scale,
                Inverse = new[] {
                    (cy * dz - cz * dy) / determinant, (cz * dx - cx * dz) / determinant, (cx * dy - cy * dx) / determinant,
                    (dy * bz - dz * by) / determinant, (dz * bx - dx * bz) / determinant, (dx * by - dy * bx) / determinant,
                    (by * cz - bz * cy) / determinant, (bz * cx - bx * cz) / determinant, (bx * cy - by * cx) / determinant }
            };
        }

        private static Binding MakeBinding(string tie, int slave, Tetra master, double gap, Node[] nodes)
        {
            Node p = nodes[slave], a = nodes[master.Nodes[0]];
            double x = p.X - a.X, y = p.Y - a.Y, z = p.Z - a.Z;
            double[] inv = master.Inverse;
            double w1 = inv[0] * x + inv[1] * y + inv[2] * z;
            double w2 = inv[3] * x + inv[4] * y + inv[5] * z;
            double w3 = inv[6] * x + inv[7] * y + inv[8] * z;
            double[] weights = { 1.0 - w1 - w2 - w3, w1, w2, w3 };
            double maxWeight = weights.Max(w => Math.Abs(w));
            if (weights.Any(w => Double.IsNaN(w) || Double.IsInfinity(w)) || maxWeight > MaximumAbsoluteWeight)
                throw Error("Extrapolación excesiva en unión '" + tie + "', nodo " + p.Id + ", elemento " + master.Id + ". Reduzca el hueco o mejore la malla (|peso| máximo permitido: " + MaximumAbsoluteWeight + ").");
            // Remove only geometric roundoff at tetra faces/edges. Rebuild one
            // coefficient to preserve partition of unity, then audit coordinates.
            int largest = 0;
            for (int i = 0; i < 4; i++)
            {
                if (Math.Abs(weights[i]) > Math.Abs(weights[largest])) largest = i;
                if (Math.Abs(weights[i]) <= 2.0e-13 * Math.Max(1.0, maxWeight)) weights[i] = 0.0;
            }
            double others = 0;
            for (int i = 0; i < 4; i++) if (i != largest) others += weights[i];
            weights[largest] = 1.0 - others;
            double rx = 0, ry = 0, rz = 0;
            var coefficients = new SortedDictionary<int, double>();
            coefficients.Add(slave, 1.0);
            for (int i = 0; i < 4; i++)
            {
                Node n = nodes[master.Nodes[i]];
                rx += weights[i] * (n.X - p.X); ry += weights[i] * (n.Y - p.Y); rz += weights[i] * (n.Z - p.Z);
                double previous;
                coefficients.TryGetValue(n.Index, out previous);
                coefficients[n.Index] = previous - weights[i];
            }
            double residual = Math.Sqrt(rx * rx + ry * ry + rz * rz);
            if (residual > 1.0e-9 * Math.Max(1.0, master.Scale))
                throw Error("La unión '" + tie + "' no reproduce el movimiento afín con precisión suficiente en " + p.Id + ".");
            int[] nonzero = coefficients.Where(c => c.Value != 0.0).Select(c => c.Key).ToArray();
            return new Binding { TieName = tie, Slave = slave, Master = master, Weights = weights, Gap = gap,
                AffineResidual = residual, RowNodes = nonzero, Coefficients = nonzero.Select(n => coefficients[n]).ToArray() };
        }

        private sealed class ReducedRow
        {
            internal int Order;
            internal Dictionary<int, double> Values;
            internal double Rhs, L1;
        }
        private sealed class RankBasis
        {
            private readonly Dictionary<int, double> fixedValues;
            private readonly Dictionary<int, ReducedRow> rows = new Dictionary<int, ReducedRow>();
            internal long TermCount;
            internal int MaximumRowTerms;
            internal RankBasis(Dictionary<int, double> prescribed) { fixedValues = prescribed; }

            // All accepted ORIGINAL equations are exported; echelon rows are
            // used only for rank/consistency. Thus sparse rank operations never
            // replace the physically audited coefficients in the solver deck.
            internal bool Add(int[] nodes, double[] coefficients, int preferredPivot, string label, out bool supportOnly)
            {
                var values = new Dictionary<int, double>();
                double scale = coefficients.Length == 0 ? 1.0 : coefficients.Max(c => Math.Abs(c));
                double rhs = 0.0, rhsScale = 0.0, growth = 1.0;
                for (int i = 0; i < nodes.Length; i++)
                {
                    double c = coefficients[i] / scale, prescribed;
                    if (fixedValues.TryGetValue(nodes[i], out prescribed)) { rhs -= c * prescribed; rhsScale += Math.Abs(c * prescribed); }
                    else values.Add(nodes[i], c);
                }
                supportOnly = values.Count == 0;
                int reductions = 0;
                while (true)
                {
                    int key = -1, order = Int32.MaxValue;
                    ReducedRow row = null;
                    foreach (KeyValuePair<int, double> term in values)
                    {
                        ReducedRow candidate;
                        if (rows.TryGetValue(term.Key, out candidate) && candidate.Order < order)
                        { key = term.Key; row = candidate; order = candidate.Order; }
                    }
                    if (row == null) break;
                    double factor = values[key]; values.Remove(key);
                    foreach (KeyValuePair<int, double> term in row.Values)
                    {
                        if (term.Key == key) continue;
                        double current; values.TryGetValue(term.Key, out current);
                        double updated = current - factor * term.Value;
                        if (updated == 0.0) values.Remove(term.Key); else values[term.Key] = updated;
                    }
                    rhs -= factor * row.Rhs;
                    rhsScale += Math.Abs(factor * row.Rhs);
                    growth += Math.Abs(factor) * row.L1;
                    if (Double.IsInfinity(growth) || growth > 1.0e8 || values.Count > MaximumReducedRowTerms || ++reductions > 100000)
                        throw Error("La red de uniones requiere una reducción numérica excesiva en " + label + ". Revise superficies repetidas, ciclos y calidad de malla; no se ha omitido ninguna unión.");
                }
                double tolerance = RankRelativeTolerance * growth;
                foreach (int zero in values.Where(v => Math.Abs(v.Value) <= tolerance).Select(v => v.Key).ToArray()) values.Remove(zero);
                double rhsTolerance = 1.0e-10 * Math.Max(1.0, rhsScale) * Math.Max(1.0, Math.Sqrt(growth));
                if (values.Count == 0)
                {
                    if (Math.Abs(rhs) > rhsTolerance)
                        throw Error("La unión soldada contradice los desplazamientos impuestos en " + label + ". Residuo: " + Number(rhs) + " mm.");
                    return false;
                }
                double maximum = values.Max(v => Math.Abs(v.Value));
                if (maximum <= 100.0 * tolerance)
                    throw Error("Rango numérico ambiguo en " + label + ". Revise malla y uniones superpuestas; no se eliminan ecuaciones de rango incierto.");
                int pivot = values.OrderByDescending(v => Math.Abs(v.Value)).ThenBy(v => v.Key).First().Key;
                double preferred;
                if (values.TryGetValue(preferredPivot, out preferred) && Math.Abs(preferred) >= 0.1 * maximum) pivot = preferredPivot;
                double diagonal = values[pivot];
                var normalized = new Dictionary<int, double>(values.Count);
                foreach (KeyValuePair<int, double> term in values) normalized.Add(term.Key, term.Value / diagonal);
                normalized[pivot] = 1.0;
                double l1 = normalized.Sum(v => Math.Abs(v.Value));
                TermCount += normalized.Count;
                MaximumRowTerms = Math.Max(MaximumRowTerms, normalized.Count);
                if (TermCount > MaximumBasisTerms) throw Error("La red de uniones excede el límite de reducción dispersa. Simplifique las superficies repetidas; no se ha generado un cálculo parcial.");
                rows.Add(pivot, new ReducedRow { Order = rows.Count, Values = normalized, Rhs = rhs / diagonal, L1 = l1 });
                return true;
            }
        }

        private static Tree BuildTree(Face[] faces, int start, int count)
        {
            var tree = new Tree { Min = new[] { Double.PositiveInfinity, Double.PositiveInfinity, Double.PositiveInfinity },
                Max = new[] { Double.NegativeInfinity, Double.NegativeInfinity, Double.NegativeInfinity } };
            for (int i = start; i < start + count; i++)
                for (int axis = 0; axis < 3; axis++) { tree.Min[axis] = Math.Min(tree.Min[axis], faces[i].Min[axis]); tree.Max[axis] = Math.Max(tree.Max[axis], faces[i].Max[axis]); }
            if (count <= 8) { tree.Faces = faces.Skip(start).Take(count).ToArray(); return tree; }
            int split = 0;
            for (int axis = 1; axis < 3; axis++) if (tree.Max[axis] - tree.Min[axis] > tree.Max[split] - tree.Min[split]) split = axis;
            Array.Sort(faces, start, count, Comparer<Face>.Create((a, b) => { int compare = a.Center[split].CompareTo(b.Center[split]); return compare != 0 ? compare : StringComparer.Ordinal.Compare(a.Key, b.Key); }));
            int half = count / 2;
            tree.Left = BuildTree(faces, start, half); tree.Right = BuildTree(faces, start + half, count - half);
            return tree;
        }
        private static void FindNearest(Tree tree, Node p, Node[] nodes, ref Face nearest, ref double best)
        {
            if (BoxDistance2(tree, p) > best + 1.0e-20) return;
            if (tree.Faces != null)
            {
                foreach (Face face in tree.Faces)
                {
                    double distance = TriangleDistance2(p, nodes[face.Nodes[0]], nodes[face.Nodes[1]], nodes[face.Nodes[2]]);
                    double tieEpsilon = 1.0e-20 * Math.Max(1.0, best);
                    if (distance < best - tieEpsilon || (Math.Abs(distance - best) <= tieEpsilon && (nearest == null || StringComparer.Ordinal.Compare(face.Key, nearest.Key) < 0)))
                    { best = distance; nearest = face; }
                }
                return;
            }
            Tree first = tree.Left, second = tree.Right;
            if (BoxDistance2(first, p) > BoxDistance2(second, p)) { first = tree.Right; second = tree.Left; }
            FindNearest(first, p, nodes, ref nearest, ref best); FindNearest(second, p, nodes, ref nearest, ref best);
        }
        private static double BoxDistance2(Tree tree, Node p)
        {
            double sum = 0;
            for (int axis = 0; axis < 3; axis++) { double v = Coordinate(p, axis); double d = v < tree.Min[axis] ? tree.Min[axis] - v : v > tree.Max[axis] ? v - tree.Max[axis] : 0; sum += d * d; }
            return sum;
        }
        // Closest-point region tests; evaluates face, edges and vertices, not
        // only vertex distances (nonmatching slave nodes may be inside a face).
        private static double TriangleDistance2(Node p, Node a, Node b, Node c)
        {
            double abx = b.X - a.X, aby = b.Y - a.Y, abz = b.Z - a.Z;
            double acx = c.X - a.X, acy = c.Y - a.Y, acz = c.Z - a.Z;
            double apx = p.X - a.X, apy = p.Y - a.Y, apz = p.Z - a.Z;
            double d1 = abx * apx + aby * apy + abz * apz, d2 = acx * apx + acy * apy + acz * apz;
            if (d1 <= 0 && d2 <= 0) return Distance2(p, a);
            double bpx = p.X - b.X, bpy = p.Y - b.Y, bpz = p.Z - b.Z;
            double d3 = abx * bpx + aby * bpy + abz * bpz, d4 = acx * bpx + acy * bpy + acz * bpz;
            if (d3 >= 0 && d4 <= d3) return Distance2(p, b);
            double vc = d1 * d4 - d3 * d2;
            if (vc <= 0 && d1 >= 0 && d3 <= 0) { double v = d1 / (d1 - d3); return Length2(apx - v * abx, apy - v * aby, apz - v * abz); }
            double cpx = p.X - c.X, cpy = p.Y - c.Y, cpz = p.Z - c.Z;
            double d5 = abx * cpx + aby * cpy + abz * cpz, d6 = acx * cpx + acy * cpy + acz * cpz;
            if (d6 >= 0 && d5 <= d6) return Distance2(p, c);
            double vb = d5 * d2 - d1 * d6;
            if (vb <= 0 && d2 >= 0 && d6 <= 0) { double w = d2 / (d2 - d6); return Length2(apx - w * acx, apy - w * acy, apz - w * acz); }
            double va = d3 * d6 - d5 * d4;
            if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) { double w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); return Length2(bpx - w * (c.X - b.X), bpy - w * (c.Y - b.Y), bpz - w * (c.Z - b.Z)); }
            double denominator = 1.0 / (va + vb + vc), u = vb * denominator, t = vc * denominator;
            return Length2(apx - u * abx - t * acx, apy - u * aby - t * acy, apz - u * abz - t * acz);
        }
        private static double Coordinate(Node n, int axis) { return axis == 0 ? n.X : axis == 1 ? n.Y : n.Z; }
        private static double Distance2(Node a, Node b) { return Length2(a.X - b.X, a.Y - b.Y, a.Z - b.Z); }
        private static double Length2(double x, double y, double z) { return x * x + y * y + z * z; }
        private static string Number(double value) { return value.ToString("G17", CultureInfo.InvariantCulture); }
        private static void Increment(JObject o, string name, int value) { o[name] = (int)o[name] + value; }
        private static void Maximum(JObject o, string name, double value) { if (value > (double)o[name]) o[name] = value; }
        private static InvalidDataException Error(string message) { return new InvalidDataException("C12.08 bonded: " + message); }
        private static double Finite(JToken token, string label)
        {
            if (token == null || (token.Type != JTokenType.Integer && token.Type != JTokenType.Float)) throw Error("Valor numérico requerido: " + label);
            double value = token.Value<double>();
            if (Double.IsNaN(value) || Double.IsInfinity(value)) throw Error("Valor no finito: " + label);
            return value;
        }
        private static string RequiredId(JToken token, string label)
        {
            string id = (string)token;
            if (String.IsNullOrWhiteSpace(id) || id.Length > 8 || id.Any(c => !(c >= 'A' && c <= 'Z') && !(c >= 'a' && c <= 'z') && !(c >= '0' && c <= '9') && c != '_'))
                throw Error("Identificador Code_Aster inválido de " + label + ": " + id);
            return id;
        }
    }
}
