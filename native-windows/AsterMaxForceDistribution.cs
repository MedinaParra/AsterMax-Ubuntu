using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    // Shared by the UI preview and the real exporter. No model mutation or I/O.
    public static class AsterMaxForceDistribution
    {
        public sealed class Plan
        {
            public string Group, Semantics;
            public int NodeCount;
            public double Fx, Fy, Fz, FxTotal, FyTotal, FzTotal;
            public JObject Report;
        }

        public static Plan Build(JObject contract)
        {
            if ((string)contract["unit_system"] != "MM_N_S_MPA")
                throw new InvalidDataException("La fuerza requiere unidades explícitas mm/N/MPa; no se convierten automáticamente.");
            var loads = contract["loads"] as JArray;
            if (loads == null || loads.Any(x => !(x is JObject))) throw new InvalidDataException("Falta la lista válida de cargas.");
            var forces = loads.Cast<JObject>().Where(x => IsType(x,"nodal_force_per_node") || IsType(x,"nodal_force_total")).ToArray();
            if (forces.Length != 1) throw new InvalidDataException("Se requiere exactamente una fuerza nodal y, opcionalmente, gravedad.");
            int gravityCount=loads.Cast<JObject>().Count(x=>IsType(x,"gravity_acceleration"));
            if(gravityCount>1 || loads.Count!=1+gravityCount)
                throw new InvalidDataException("Carga adicional no soportada; no se convierte presión u otra ley a fuerza nodal.");
            JObject force = forces[0];
            bool perNode = IsType(force,"nodal_force_per_node");
            string suffix = perNode ? "_per_node_n" : "_total_n";
            string forbidden = perNode ? "_total_n" : "_per_node_n";
            if (new[] { "fx", "fy", "fz" }.Any(x => force[x+forbidden] != null))
                throw new InvalidDataException("La carga mezcla fuerza por nodo y total, o contradice su tipo declarado. Revise su definición.");
            if (!new[] { "fx", "fy", "fz" }.Any(x => force[x+suffix] != null))
                throw new InvalidDataException("La carga no contiene componentes con la semántica declarada.");
            string distribution = (string)force["distribution"];
            if (distribution != null && (perNode || distribution != "UNIFORM_PER_SELECTED_NODE"))
                throw new InvalidDataException("Distribución de fuerza no soportada; sólo total uniforme por nodo seleccionado.");
            string group = (string)force["group"];
            JObject mesh = contract["mesh"] as JObject;
            JObject groups = mesh == null ? null : mesh["node_groups"] as JObject;
            JArray selection = groups == null || String.IsNullOrWhiteSpace(group) ? null : groups[group] as JArray;
            if (selection == null || selection.Count == 0) throw new InvalidDataException("Selección de fuerza vacía o ausente: " + group);
            JArray nodes = mesh["nodes"] as JArray;
            if (nodes == null) throw new InvalidDataException("Falta la malla actual para verificar la fuerza.");
            var ids = new HashSet<string>(StringComparer.Ordinal);
            foreach (JToken n in nodes)
            {
                var obj = n as JObject;
                string id = obj == null || obj["id"] == null || obj["id"].Type != JTokenType.String ? null : (string)obj["id"];
                if (String.IsNullOrWhiteSpace(id) || !ids.Add(id)) throw new InvalidDataException("Identidad de nodo vacía o duplicada en la malla actual.");
            }
            var selected = new HashSet<string>(StringComparer.Ordinal);
            foreach (JToken n in selection)
            {
                string id = n.Type == JTokenType.String ? (string)n : null;
                if (id == null || !ids.Contains(id)) throw new InvalidDataException("Nodo de carga inexistente en la malla actual: " + id);
                if (!selected.Add(id)) throw new InvalidDataException("Nodo duplicado en la selección de fuerza: " + id + ". Revise el conjunto; no se elimina automáticamente.");
            }
            double inputFx = Number(force,"fx"+suffix), inputFy = Number(force,"fy"+suffix), inputFz = Number(force,"fz"+suffix);
            int count = selected.Count;
            var plan = new Plan { Group=group, NodeCount=count,
                Semantics=perNode ? "PER_NODE_CLOAD" : distribution == null ? "LEGACY_TOTAL_DISTRIBUTED" : "TOTAL_UNIFORM_DISTRIBUTED",
                Fx=perNode ? inputFx : inputFx/count, Fy=perNode ? inputFy : inputFy/count, Fz=perNode ? inputFz : inputFz/count };
            plan.FxTotal=Finite(plan.Fx*count); plan.FyTotal=Finite(plan.Fy*count); plan.FzTotal=Finite(plan.Fz*count);
            if ((!perNode) && ((inputFx!=0 && plan.Fx==0) || (inputFy!=0 && plan.Fy==0) || (inputFz!=0 && plan.Fz==0)))
                throw new InvalidDataException("La fuerza por nodo queda fuera de la precisión numérica soportada.");
            plan.Report = new JObject {
                ["schema"]="astermax-force-distribution/v1", ["load_name"]=(string)force["name"],
                ["semantics"]=plan.Semantics, ["group"]=group, ["selected_unique_node_count"]=count,
                ["input_components_n"]=new JArray(inputFx,inputFy,inputFz), ["per_node_components_n"]=new JArray(plan.Fx,plan.Fy,plan.Fz),
                ["assembled_resultant_n"]=new JArray(plan.FxTotal,plan.FyTotal,plan.FzTotal),
                ["multi_node_per_node_warning"]=perNode && count>1,
                ["distribution_measure"]="NODE_COUNT_NOT_AREA", ["model_modified"]=false, ["solver_execution"]="NOT_RUN"
            };
            return plan;
        }

        public static string Describe(JObject contract, Plan plan)
        {
            int contacts=(contract["contacts"] as JArray ?? new JArray()).Count;
            int ties=(contract["bonded_ties"] as JArray ?? new JArray()).Count;
            string text="[Astermax] Modelo activo: " + ((string)contract["name"] ?? "<sin nombre>") +
                "\nDefinición real: " + contacts + " contactos CONTINUE y " + ties + " uniones bonded (Tie)." +
                "\nLa versión del ejecutable no convierte las conexiones guardadas." +
                "\n\nFuerza: " + (plan.Semantics=="PER_NODE_CLOAD" ? "POR NODO" : "RESULTANTE TOTAL, reparto uniforme por nodo") +
                "\nSelección actual: " + plan.Group + " — " + plan.NodeCount + " nodos únicos." +
                "\nPor nodo [N]: " + Vector(plan.Fx,plan.Fy,plan.Fz) +
                "\nResultante nodal [N]: " + Vector(plan.FxTotal,plan.FyTotal,plan.FzTotal) +
                "\nEl reparto uniforme por nodo no equivale a presión ni reparto por área.";
            if ((bool)plan.Report["multi_node_per_node_warning"])
                text+="\n\nATENCIÓN: cada nodo recibe la fuerza introducida. Si pretendía una fuerza total, cancele y cambie explícitamente el modo de la carga.";
            if (((JArray)contract["loads"]).OfType<JObject>().Any(x=>IsType(x,"gravity_acceleration")))
                text+="\nLa gravedad es adicional y no está incluida en esta resultante nodal.";
            return text;
        }
        private static string Vector(double x,double y,double z) { return String.Format(CultureInfo.InvariantCulture,"({0:R}, {1:R}, {2:R})",x,y,z); }
        private static bool IsType(JObject o,string t) { return String.Equals((string)o["type"],t,StringComparison.OrdinalIgnoreCase); }
        private static double Number(JObject o,string key) {
            JToken t=o[key]; if(t==null) return 0;
            if(t.Type!=JTokenType.Float && t.Type!=JTokenType.Integer) throw new InvalidDataException("Componente no numérica: "+key);
            return Finite((double)t);
        }
        private static double Finite(double v) { if(Double.IsNaN(v)||Double.IsInfinity(v)) throw new InvalidDataException("Fuerza o resultante no finita."); return v; }
    }
}
