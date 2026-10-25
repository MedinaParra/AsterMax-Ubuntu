using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using CaeGlobals;
using CaeMesh;
using CaeResults;

namespace PrePoMax.CodeAster
{
    /// <summary>
    /// Emits compact ASCII tables in the standard Code_Aster .resu file and reads
    /// them back into PrePoMax FeResults. RMED remains the complete solver result;
    /// the table file is a deterministic interoperability bridge for the existing GUI.
    /// </summary>
    public static class CodeAsterResultBridge
    {
        public const string DeplTitle = "PPM_DEPL";
        public const string StressNormalTitle = "PPM_STRESS_N";
        public const string StressShearTitle = "PPM_STRESS_S";
        public const string StrainNormalTitle = "PPM_STRAIN_N";
        public const string StrainShearTitle = "PPM_STRAIN_S";

        public static void AppendResultTables(StringBuilder sb)
        {
            if (sb == null) throw new ArgumentNullException("sb");

            AppendTable(sb, "tab_depl", DeplTitle, "DEPL",
                        new string[] { "NOEUD", "DX", "DY", "DZ" },
                        new string[] { "DX", "DY", "DZ" });
            AppendTable(sb, "tab_sig_n", StressNormalTitle, "SIGM_NOEU",
                        new string[] { "NOEUD", "SIXX", "SIYY", "SIZZ" },
                        new string[] { "SIXX", "SIYY", "SIZZ" });
            AppendTable(sb, "tab_sig_s", StressShearTitle, "SIGM_NOEU",
                        new string[] { "NOEUD", "SIXY", "SIYZ", "SIXZ" },
                        new string[] { "SIXY", "SIYZ", "SIXZ" });
            AppendTable(sb, "tab_eps_n", StrainNormalTitle, "EPSI_NOEU",
                        new string[] { "NOEUD", "EPXX", "EPYY", "EPZZ" },
                        new string[] { "EPXX", "EPYY", "EPZZ" });
            AppendTable(sb, "tab_eps_s", StrainShearTitle, "EPSI_NOEU",
                        new string[] { "NOEUD", "EPXY", "EPYZ", "EPXZ" },
                        new string[] { "EPXY", "EPYZ", "EPXZ" });
        }

        private static void AppendTable(StringBuilder sb, string variable, string title,
                                        string fieldName, string[] printedColumns, string[] components)
        {
            sb.Append(variable).AppendLine(" = CREA_TABLE(RESU=_F(");
            sb.AppendLine("    RESULTAT=result,");
            sb.AppendLine("    TOUT='OUI',");
            sb.Append("    NOM_CHAM='").Append(fieldName).AppendLine("',");
            sb.Append("    NOM_CMP=(").Append(String.Join(", ", components.Select(x => "'" + x + "'"))).AppendLine(")))");
            sb.AppendLine("IMPR_TABLE(");
            sb.Append("    TABLE=").Append(variable).AppendLine(",");
            sb.Append("    TITRE='").Append(title).AppendLine("',");
            sb.AppendLine("    UNITE=8,");
            sb.AppendLine("    FORMAT='TABLEAU',");
            sb.AppendLine("    SEPARATEUR=';',");
            sb.AppendLine("    FORMAT_R='1PE15.8',");
            sb.Append("    NOM_PARA=(").Append(String.Join(", ", printedColumns.Select(x => "'" + x + "'"))).AppendLine("))");
            sb.AppendLine();
        }

        public static FeResults Read(string rmedFileName, string resuFileName, FeMesh mesh, UnitSystemType unitSystemType)
        {
            if (mesh == null) throw new ArgumentNullException("mesh");
            if (mesh.Nodes == null || mesh.Nodes.Count == 0)
                throw new InvalidDataException("Cannot admit Code_Aster results for an empty mesh.");
            if (String.IsNullOrWhiteSpace(resuFileName) || !File.Exists(resuFileName))
                throw new FileNotFoundException("The Code_Aster interoperability .resu file was not found.", resuFileName);

            Dictionary<int, int> nodeLookup = new Dictionary<int, int>();
            int position = 0;
            foreach (var entry in mesh.Nodes.OrderBy(x => x.Key)) nodeLookup[entry.Key] = position++;

            string[] lines = File.ReadAllLines(resuFileName);
            Dictionary<string, float[]> depl = ReadTable(lines, DeplTitle,
                new string[] { "DX", "DY", "DZ" }, nodeLookup);
            Dictionary<string, float[]> sigN = ReadTable(lines, StressNormalTitle,
                new string[] { "SIXX", "SIYY", "SIZZ" }, nodeLookup);
            Dictionary<string, float[]> sigS = ReadTable(lines, StressShearTitle,
                new string[] { "SIXY", "SIYZ", "SIXZ" }, nodeLookup);
            Dictionary<string, float[]> epsN = ReadTable(lines, StrainNormalTitle,
                new string[] { "EPXX", "EPYY", "EPZZ" }, nodeLookup);
            Dictionary<string, float[]> epsS = ReadTable(lines, StrainShearTitle,
                new string[] { "EPXY", "EPYZ", "EPXZ" }, nodeLookup);

            FeResults results = new FeResults(rmedFileName);
            results.SetMesh(mesh, nodeLookup);
            results.UnitSystem = new UnitSystem(unitSystemType);

            Field displacement = new Field(FOFieldNames.Disp);
            displacement.AddComponent(FOComponentNames.U1, depl["DX"]);
            displacement.AddComponent(FOComponentNames.U2, depl["DY"]);
            displacement.AddComponent(FOComponentNames.U3, depl["DZ"]);
            displacement.ComputeInvariants();
            results.AddField(NewStaticFieldData(FOFieldNames.Disp), displacement);

            Field stress = new Field(FOFieldNames.Stress);
            stress.AddComponent(FOComponentNames.S11, sigN["SIXX"]);
            stress.AddComponent(FOComponentNames.S22, sigN["SIYY"]);
            stress.AddComponent(FOComponentNames.S33, sigN["SIZZ"]);
            stress.AddComponent(FOComponentNames.S12, sigS["SIXY"]);
            stress.AddComponent(FOComponentNames.S23, sigS["SIYZ"]);
            stress.AddComponent(FOComponentNames.S13, sigS["SIXZ"]);
            stress.ComputeInvariants();
            results.AddField(NewStaticFieldData(FOFieldNames.Stress), stress);

            Field strain = new Field(FOFieldNames.ToStrain);
            strain.AddComponent(FOComponentNames.E11, epsN["EPXX"]);
            strain.AddComponent(FOComponentNames.E22, epsN["EPYY"]);
            strain.AddComponent(FOComponentNames.E33, epsN["EPZZ"]);
            strain.AddComponent(FOComponentNames.E12, epsS["EPXY"]);
            strain.AddComponent(FOComponentNames.E23, epsS["EPYZ"]);
            strain.AddComponent(FOComponentNames.E13, epsS["EPXZ"]);
            strain.ComputeInvariants();
            results.AddField(NewStaticFieldData(FOFieldNames.ToStrain), strain);

            return results;
        }

        private static FieldData NewStaticFieldData(string name)
        {
            FieldData data = new FieldData(name);
            data.GlobalIncrementId = 1;
            data.StepType = StepTypeEnum.Static;
            data.Time = 1;
            data.MethodId = 1;
            data.StepId = 1;
            data.StepIncrementId = 1;
            return data;
        }

        private static Dictionary<string, float[]> ReadTable(string[] lines, string title, string[] components,
                                                             Dictionary<int, int> nodeLookup)
        {
            int titleLine = FindLine(lines, 0, title);
            if (titleLine < 0) throw new InvalidDataException("Code_Aster result section not found: " + title + ".");

            int headerLine = -1;
            string[] header = null;
            for (int i = titleLine + 1; i < lines.Length; i++)
            {
                if (i > titleLine + 80) break;
                string candidate = NormalizeComment(lines[i]);
                if (candidate.IndexOf(';') < 0) continue;
                string[] tokens = Split(candidate);
                if (IndexOf(tokens, "NOEUD") >= 0 && components.All(c => IndexOf(tokens, c) >= 0))
                {
                    headerLine = i;
                    header = tokens;
                    break;
                }
            }
            if (headerLine < 0) throw new InvalidDataException("Header for Code_Aster result section not found: " + title + ".");

            int nodeColumn = IndexOf(header, "NOEUD");
            Dictionary<string, int> componentColumns = components.ToDictionary(c => c, c => IndexOf(header, c), StringComparer.OrdinalIgnoreCase);
            Dictionary<string, float[]> values = new Dictionary<string, float[]>(StringComparer.OrdinalIgnoreCase);
            foreach (string component in components)
            {
                float[] data = Enumerable.Repeat(float.NaN, nodeLookup.Count).ToArray();
                values.Add(component, data);
            }

            HashSet<int> seenNodes = new HashSet<int>();
            int rows = 0;
            for (int i = headerLine + 1; i < lines.Length; i++)
            {
                string raw = lines[i].Trim();
                if (raw.Length == 0)
                {
                    if (rows > 0) break;
                    continue;
                }
                if (raw.Contains("PPM_") && rows > 0) break;
                string[] tokens = Split(NormalizeComment(raw));
                if (tokens.Length <= nodeColumn) continue;

                int nodeId;
                if (!TryParseNode(tokens[nodeColumn], out nodeId))
                {
                    if (rows > 0 && raw.StartsWith("#")) break;
                    continue;
                }

                int index;
                if (!nodeLookup.TryGetValue(nodeId, out index))
                    throw new InvalidDataException("Code_Aster result section " + title + " contains node " + nodeId + " which is not present in the admitted mesh.");
                if (!seenNodes.Add(nodeId))
                    throw new InvalidDataException("Code_Aster result section " + title + " contains duplicate node " + nodeId + ".");

                Dictionary<string, float> rowValues = new Dictionary<string, float>(StringComparer.OrdinalIgnoreCase);
                foreach (string component in components)
                {
                    int column = componentColumns[component];
                    float value;
                    if (column < 0 || column >= tokens.Length || !TryParseFloat(tokens[column], out value) ||
                        Single.IsNaN(value) || Single.IsInfinity(value))
                        throw new InvalidDataException("Code_Aster result section " + title + " contains a missing or non-finite " + component + " value for node " + nodeId + ".");
                    rowValues.Add(component, value);
                }

                foreach (string component in components) values[component][index] = rowValues[component];
                rows++;
            }

            if (rows == 0)
                throw new InvalidDataException("No nodal values were read from Code_Aster result section: " + title + ".");
            if (seenNodes.Count != nodeLookup.Count)
            {
                int[] missing = nodeLookup.Keys.Where(id => !seenNodes.Contains(id)).OrderBy(id => id).Take(12).ToArray();
                string suffix = nodeLookup.Count - seenNodes.Count > missing.Length ? ", ..." : String.Empty;
                throw new InvalidDataException("Code_Aster result section " + title + " does not cover the admitted mesh. Missing node(s): " +
                                               String.Join(", ", missing) + suffix + ".");
            }

            foreach (string component in components)
                if (values[component].Any(value => Single.IsNaN(value) || Single.IsInfinity(value)))
                    throw new InvalidDataException("Code_Aster result section " + title + " left non-finite values in component " + component + ".");

            return values;
        }

        private static int FindLine(string[] lines, int start, string value)
        {
            for (int i = Math.Max(0, start); i < lines.Length; i++)
                if (lines[i].IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0) return i;
            return -1;
        }

        private static string NormalizeComment(string value)
        {
            string s = (value ?? String.Empty).Trim();
            while (s.StartsWith("#")) s = s.Substring(1).TrimStart();
            return s;
        }

        private static string[] Split(string value)
        {
            return (value ?? String.Empty).Split(new char[] { ';' }, StringSplitOptions.None)
                .Select(x => x.Trim()).ToArray();
        }

        private static int IndexOf(string[] values, string target)
        {
            for (int i = 0; i < values.Length; i++)
                if (String.Equals(values[i], target, StringComparison.OrdinalIgnoreCase)) return i;
            return -1;
        }

        private static bool TryParseNode(string token, out int nodeId)
        {
            nodeId = -1;
            string value = (token ?? String.Empty).Trim();
            if (value.Length > 1 && (value[0] == 'N' || value[0] == 'n')) value = value.Substring(1);
            return Int32.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out nodeId);
        }

        private static bool TryParseFloat(string token, out float value)
        {
            string normalized = (token ?? String.Empty).Trim().Replace('D', 'E').Replace('d', 'e');
            return Single.TryParse(normalized, NumberStyles.Float | NumberStyles.AllowLeadingSign,
                                   CultureInfo.InvariantCulture, out value);
        }
    }
}
