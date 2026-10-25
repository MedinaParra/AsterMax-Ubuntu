using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using CaeMesh;

namespace PrePoMax.CodeAster
{
    public sealed class CodeAsterMeshMap
    {
        public string VolumeGroup { get; internal set; }
        public Dictionary<string, string> NodeGroups { get; private set; }
        public Dictionary<string, string> ElementGroups { get; private set; }
        public Dictionary<string, string> SurfaceGroups { get; private set; }

        public CodeAsterMeshMap()
        {
            NodeGroups = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            ElementGroups = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            SurfaceGroups = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        }

        public string ResolveNodeGroup(string name)
        {
            string value;
            return name != null && NodeGroups.TryGetValue(name, out value) ? value : null;
        }

        public string ResolveElementGroup(string name)
        {
            string value;
            return name != null && ElementGroups.TryGetValue(name, out value) ? value : null;
        }

        public string ResolveSurfaceGroup(string name)
        {
            string value;
            return name != null && SurfaceGroups.TryGetValue(name, out value) ? value : null;
        }
    }

    public sealed class CodeAsterMeshWriteResult
    {
        public string FileName { get; internal set; }
        public CodeAsterMeshMap Map { get; internal set; }
        public List<string> Warnings { get; private set; }

        public CodeAsterMeshWriteResult()
        {
            Warnings = new List<string>();
        }
    }

    /// <summary>
    /// Writes the active PrePoMax FE mesh to Code_Aster's native text (ASTER/.mail) format.
    /// The first integration intentionally targets 3-D solid elements; boundary faces are emitted
    /// as unmodelled skin elements so PRES_REP/contact-oriented groups can reference real faces.
    /// </summary>
    public static class CodeAsterMeshWriter
    {
        private const string VolumeGroup = "VOLUME_ALL";

        public static CodeAsterMeshWriteResult Write(string fileName, FeMesh mesh)
        {
            if (mesh == null || mesh.Nodes == null || mesh.Elements == null || mesh.Nodes.Count == 0 || mesh.Elements.Count == 0)
                throw new InvalidOperationException("The PrePoMax model does not contain a finite-element mesh.");

            CodeAsterMeshWriteResult result = new CodeAsterMeshWriteResult();
            result.FileName = fileName;
            result.Map = new CodeAsterMeshMap();
            result.Map.VolumeGroup = VolumeGroup;

            Dictionary<string, List<string>> elementsByType = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);
            List<string> volumeElementNames = new List<string>();

            foreach (var entry in mesh.Elements.OrderBy(e => e.Key))
            {
                FeElement element = entry.Value;
                string type = GetAsterVolumeType(element.GetVtkCellType());
                if (type == null)
                {
                    throw new NotSupportedException("Code_Aster integration currently supports 3-D tetrahedral, hexahedral and wedge elements. " +
                                                    "Unsupported PrePoMax VTK cell type: " + element.GetVtkCellType() + ".");
                }

                List<string> lines;
                if (!elementsByType.TryGetValue(type, out lines))
                {
                    lines = new List<string>();
                    elementsByType.Add(type, lines);
                }

                string elementName = ElementName(element.Id);
                lines.Add(" " + elementName + " " + String.Join(" ", element.NodeIds.Select(NodeName)));
                volumeElementNames.Add(elementName);
            }

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("TITRE");
            sb.AppendLine(" PrePoMax -> Code_Aster");
            sb.AppendLine("FINSF");
            sb.AppendLine("COOR_3D");
            foreach (var entry in mesh.Nodes.OrderBy(n => n.Key))
            {
                FeNode n = entry.Value;
                sb.Append(" ").Append(NodeName(n.Id)).Append(" ")
                  .Append(Format(n.X)).Append(" ").Append(Format(n.Y)).Append(" ").Append(Format(n.Z)).AppendLine();
            }
            sb.AppendLine("FINSF");

            foreach (var typeEntry in elementsByType)
            {
                sb.AppendLine(typeEntry.Key);
                foreach (string line in typeEntry.Value) sb.AppendLine(line);
                sb.AppendLine("FINSF");
            }

            WriteGroupMa(sb, VolumeGroup, volumeElementNames);

            // Native node sets.
            foreach (var entry in mesh.NodeSets)
            {
                if (entry.Value == null || entry.Value.Labels == null || entry.Value.Labels.Length == 0) continue;
                string group = UniqueGroupName(entry.Key, "N", result.Map.NodeGroups.Values);
                result.Map.NodeGroups[entry.Key] = group;
                WriteGroupNo(sb, group, entry.Value.Labels.Select(NodeName));
            }

            // Parts are useful material/section regions in PrePoMax.
            foreach (var entry in mesh.Parts)
            {
                if (entry.Value == null || entry.Value.Labels == null || entry.Value.Labels.Length == 0) continue;
                string group = UniqueGroupName(entry.Key, "P", result.Map.ElementGroups.Values);
                result.Map.ElementGroups[entry.Key] = group;
                WriteGroupMa(sb, group, entry.Value.Labels.Select(ElementName));
            }

            // Explicit element sets.
            foreach (var entry in mesh.ElementSets)
            {
                if (entry.Value == null || entry.Value.Labels == null || entry.Value.Labels.Length == 0) continue;
                string group = UniqueGroupName(entry.Key, "E", result.Map.ElementGroups.Values);
                result.Map.ElementGroups[entry.Key] = group;
                WriteGroupMa(sb, group, entry.Value.Labels.Select(ElementName));
            }

            // Surface node aliases: FixedBC/DisplacementRotation may target a surface.
            foreach (var entry in mesh.Surfaces)
            {
                FeSurface surface = entry.Value;
                if (surface == null) continue;
                string nodeGroup = result.Map.ResolveNodeGroup(surface.NodeSetName);
                if (nodeGroup != null) result.Map.NodeGroups[entry.Key] = nodeGroup;
            }

            // Create real skin elements for element-based solid surfaces. They remain outside VOLUME_ALL
            // and therefore are not assigned the 3-D mechanical model by AFFE_MODELE.
            int skinId = 1;
            foreach (var entry in mesh.Surfaces)
            {
                FeSurface surface = entry.Value;
                if (surface == null || surface.ElementFaces == null || surface.ElementFaces.Count == 0) continue;

                if (surface.SurfaceFaceTypes != FeSurfaceFaceTypes.SolidFaces &&
                    surface.SurfaceFaceTypes != FeSurfaceFaceTypes.Unknown)
                {
                    result.Warnings.Add("Surface '" + entry.Key + "' is not a solid-face surface and was not exported as a pressure group.");
                    continue;
                }

                List<Tuple<string, string>> skinElements = new List<Tuple<string, string>>();
                foreach (var faceEntry in surface.ElementFaces)
                {
                    FeElementSet set;
                    if (!mesh.ElementSets.TryGetValue(faceEntry.Value, out set) || set == null || set.Labels == null) continue;
                    foreach (int elementId in set.Labels)
                    {
                        FeElement parent;
                        if (!mesh.Elements.TryGetValue(elementId, out parent)) continue;
                        int[] faceNodes = parent.GetVtkCellFromFaceName(faceEntry.Key);
                        string faceType = GetAsterFaceType(faceNodes.Length);
                        if (faceType == null)
                        {
                            result.Warnings.Add("Surface '" + entry.Key + "' contains an unsupported face with " + faceNodes.Length + " nodes.");
                            continue;
                        }
                        string skinName = "S" + skinId.ToString(CultureInfo.InvariantCulture);
                        skinId++;
                        skinElements.Add(Tuple.Create(faceType,
                            " " + skinName + " " + String.Join(" ", faceNodes.Select(NodeName))));
                    }
                }

                if (skinElements.Count == 0) continue;
                foreach (var typeGroup in skinElements.GroupBy(x => x.Item1))
                {
                    sb.AppendLine(typeGroup.Key);
                    foreach (var item in typeGroup) sb.AppendLine(item.Item2);
                    sb.AppendLine("FINSF");
                }

                string surfaceGroup = UniqueGroupName(entry.Key, "S", result.Map.SurfaceGroups.Values);
                result.Map.SurfaceGroups[entry.Key] = surfaceGroup;
                WriteGroupMa(sb, surfaceGroup, skinElements.Select(x => x.Item2.Trim().Split(' ')[0]));
            }

            sb.AppendLine("FIN");
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(fileName)));
            File.WriteAllText(fileName, sb.ToString(), new UTF8Encoding(false));
            return result;
        }

        private static string GetAsterVolumeType(int vtkType)
        {
            switch (vtkType)
            {
                case 10: return "TETRA4";
                case 12: return "HEXA8";
                case 13: return "PENTA6";
                case 24: return "TETRA10";
                case 25: return "HEXA20";
                case 26: return "PENTA15";
                default: return null;
            }
        }

        private static string GetAsterFaceType(int nodeCount)
        {
            switch (nodeCount)
            {
                case 3: return "TRIA3";
                case 4: return "QUAD4";
                case 6: return "TRIA6";
                case 8: return "QUAD8";
                default: return null;
            }
        }

        private static string NodeName(int id) { return "N" + id.ToString(CultureInfo.InvariantCulture); }
        private static string ElementName(int id) { return "M" + id.ToString(CultureInfo.InvariantCulture); }
        private static string Format(double value) { return value.ToString("R", CultureInfo.InvariantCulture); }

        private static void WriteGroupNo(StringBuilder sb, string name, IEnumerable<string> nodeNames)
        {
            string[] names = nodeNames.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            if (names.Length == 0) return;
            sb.Append("GROUP_NO NOM=").Append(name).Append(" NBOBJ=").Append(names.Length).AppendLine();
            WriteTokens(sb, names);
            sb.AppendLine("FINSF");
        }

        private static void WriteGroupMa(StringBuilder sb, string name, IEnumerable<string> elementNames)
        {
            string[] names = elementNames.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            if (names.Length == 0) return;
            sb.Append("GROUP_MA NOM=").Append(name).Append(" NBOBJ=").Append(names.Length).AppendLine();
            WriteTokens(sb, names);
            sb.AppendLine("FINSF");
        }

        private static void WriteTokens(StringBuilder sb, string[] tokens)
        {
            const int perLine = 8;
            for (int i = 0; i < tokens.Length; i += perLine)
                sb.Append(" ").AppendLine(String.Join(" ", tokens.Skip(i).Take(perLine)));
        }

        private static string UniqueGroupName(string original, string prefix, IEnumerable<string> existing)
        {
            HashSet<string> used = new HashSet<string>(existing, StringComparer.OrdinalIgnoreCase);
            string clean = Sanitize(original);
            string candidate = prefix + "_" + clean;
            if (candidate.Length > 24) candidate = candidate.Substring(0, 24);
            if (!used.Contains(candidate)) return candidate;

            string suffix = "_" + StableHash(original).ToString("X8", CultureInfo.InvariantCulture);
            int keep = Math.Max(1, 24 - suffix.Length);
            candidate = candidate.Substring(0, Math.Min(candidate.Length, keep)) + suffix;
            return candidate;
        }

        private static string Sanitize(string value)
        {
            if (String.IsNullOrWhiteSpace(value)) return "GROUP";
            StringBuilder sb = new StringBuilder();
            foreach (char c in value)
            {
                if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')
                    sb.Append(Char.ToUpperInvariant(c));
                else sb.Append('_');
            }
            if (sb.Length == 0) sb.Append("GROUP");
            if (Char.IsDigit(sb[0])) sb.Insert(0, 'G');
            return sb.ToString();
        }

        private static uint StableHash(string value)
        {
            unchecked
            {
                uint hash = 2166136261;
                foreach (char c in value ?? String.Empty)
                {
                    hash ^= c;
                    hash *= 16777619;
                }
                return hash;
            }
        }
    }
}
