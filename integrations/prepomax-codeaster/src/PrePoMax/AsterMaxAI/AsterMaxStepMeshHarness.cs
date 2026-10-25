using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using CaeMesh;

namespace PrePoMax.AsterMaxAI
{
    // CI-only qualification harness. It imports a real STEP model through Controller.ImportFile,
    // meshes that imported CAD through Controller.CreateMesh (native NetGen path), and then
    // checks FE topology and dimensional scale. It never executes or verifies an FEA solver.
    internal sealed class AsterMaxStepMeshHarness
    {
        private readonly Controller _controller;

        public AsterMaxStepMeshHarness(Controller controller)
        {
            _controller = controller;
        }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_STEP_MESH_FIXTURE"), "1", StringComparison.Ordinal)) return;

            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_STEP_MESH_EVIDENCE_PATH");
            string stepPath = Environment.GetEnvironmentVariable("ASTERMAX_STEP_MESH_PATH");
            bool sourceExists = false, sourceDeclaresMm = false, imported = false, cadScaleOk = false;
            bool createMeshReturned = false, meshGenerated = false, meshScaleOk = false;
            bool nodeCoordinatesFinite = false, elementConnectivityValid = false, noCoincidentElementNodes = false;
            int geometryPartCount = 0, geometryNodeCount = 0, meshPartCount = 0, meshNodeCount = 0, meshElementCount = 0;
            double cadDx = Double.NaN, cadDy = Double.NaN, cadDz = Double.NaN;
            double meshDx = Double.NaN, meshDy = Double.NaN, meshDz = Double.NaN;
            double minElementNodeDistance = Double.NaN;
            string meshedPartName = "", elementTypes = "", sha256 = "", error = "";

            try
            {
                if (String.IsNullOrWhiteSpace(stepPath) || !File.Exists(stepPath))
                    throw new FileNotFoundException("C8.60 STEP fixture is missing.", stepPath);

                sourceExists = true;
                string source = File.ReadAllText(stepPath);
                sourceDeclaresMm = source.IndexOf(".MILLI., .METRE.", StringComparison.OrdinalIgnoreCase) >= 0;
                if (!sourceDeclaresMm) throw new InvalidOperationException("STEP fixture does not explicitly declare SI millimetres.");
                sha256 = HashFile(stepPath);

                if (_controller.Model == null || _controller.Model.Geometry == null || _controller.Model.Mesh == null ||
                    _controller.Model.Geometry.Parts.Count != 0 || _controller.Model.Mesh.Parts.Count != 0 ||
                    _controller.Model.Mesh.Nodes.Count != 0 || _controller.Model.Mesh.Elements.Count != 0)
                    throw new InvalidOperationException("C8.60 requires a clean startup model; refusing to overwrite user/model data.");

                _controller.ImportFile(stepPath, false);
                FeMesh geometry = _controller.Model.Geometry;
                imported = geometry != null && geometry.Parts != null && geometry.Parts.Count > 0;
                if (!imported) throw new InvalidOperationException("Native STEP import produced no geometry parts.");

                geometryPartCount = geometry.Parts.Count;
                geometryNodeCount = geometry.Nodes == null ? 0 : geometry.Nodes.Count;
                BoundingBox cadBox = geometry.BoundingBox;
                if (cadBox == null) throw new InvalidOperationException("Imported CAD has no bounding box.");
                cadDx = cadBox.MaxX - cadBox.MinX;
                cadDy = cadBox.MaxY - cadBox.MinY;
                cadDz = cadBox.MaxZ - cadBox.MinZ;
                cadScaleOk = ExpectedScale(cadDx, cadDy, cadDz, 0.25);
                if (!cadScaleOk) throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                    "Pre-mesh STEP/mm gate failed: {0:R} x {1:R} x {2:R} mm.", cadDx, cadDy, cadDz));

                meshedPartName = geometry.Parts.First().Key;
                // Pinned native path: Controller.CreateMesh -> CreateMeshFromBrep -> NetGenMesher -> ImportGeneratedMesh.
                createMeshReturned = _controller.CreateMesh(meshedPartName);
                if (!createMeshReturned) throw new InvalidOperationException("Controller.CreateMesh returned false for the imported STEP part.");

                FeMesh mesh = _controller.Model.Mesh;
                meshPartCount = mesh.Parts == null ? 0 : mesh.Parts.Count;
                meshNodeCount = mesh.Nodes == null ? 0 : mesh.Nodes.Count;
                meshElementCount = mesh.Elements == null ? 0 : mesh.Elements.Count;
                meshGenerated = meshPartCount > 0 && meshNodeCount > 0 && meshElementCount > 0;
                if (!meshGenerated) throw new InvalidOperationException("Native NetGen path returned success but produced no FE mesh entities.");

                double minX = Double.PositiveInfinity, minY = Double.PositiveInfinity, minZ = Double.PositiveInfinity;
                double maxX = Double.NegativeInfinity, maxY = Double.NegativeInfinity, maxZ = Double.NegativeInfinity;
                nodeCoordinatesFinite = true;
                foreach (FeNode node in mesh.Nodes.Values)
                {
                    if (!Finite(node.X) || !Finite(node.Y) || !Finite(node.Z)) { nodeCoordinatesFinite = false; break; }
                    if (node.X < minX) minX = node.X; if (node.X > maxX) maxX = node.X;
                    if (node.Y < minY) minY = node.Y; if (node.Y > maxY) maxY = node.Y;
                    if (node.Z < minZ) minZ = node.Z; if (node.Z > maxZ) maxZ = node.Z;
                }
                if (!nodeCoordinatesFinite) throw new InvalidOperationException("Generated FE mesh contains non-finite node coordinates.");

                meshDx = maxX - minX; meshDy = maxY - minY; meshDz = maxZ - minZ;
                meshScaleOk = ExpectedScale(meshDx, meshDy, meshDz, 0.50);
                if (!meshScaleOk) throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                    "Post-mesh dimensional gate failed: {0:R} x {1:R} x {2:R} mm.", meshDx, meshDy, meshDz));

                elementConnectivityValid = true;
                noCoincidentElementNodes = true;
                minElementNodeDistance = Double.PositiveInfinity;
                HashSet<string> types = new HashSet<string>(StringComparer.Ordinal);
                foreach (FeElement element in mesh.Elements.Values)
                {
                    types.Add(element.GetType().Name);
                    int[] ids = element.NodeIds;
                    if (ids == null || ids.Length < 2) { elementConnectivityValid = false; break; }
                    for (int i = 0; i < ids.Length; i++)
                    {
                        if (!mesh.Nodes.ContainsKey(ids[i])) { elementConnectivityValid = false; break; }
                        FeNode a = mesh.Nodes[ids[i]];
                        for (int j = i + 1; j < ids.Length; j++)
                        {
                            if (!mesh.Nodes.ContainsKey(ids[j])) { elementConnectivityValid = false; break; }
                            FeNode b = mesh.Nodes[ids[j]];
                            double ddx = a.X - b.X, ddy = a.Y - b.Y, ddz = a.Z - b.Z;
                            double d = Math.Sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
                            if (d < minElementNodeDistance) minElementNodeDistance = d;
                            if (!(d > 1E-10)) noCoincidentElementNodes = false;
                        }
                        if (!elementConnectivityValid) break;
                    }
                    if (!elementConnectivityValid) break;
                }
                elementTypes = String.Join(",", types.OrderBy(x => x).ToArray());
                if (!elementConnectivityValid) throw new InvalidOperationException("Generated FE mesh has invalid element-to-node connectivity.");
                if (!noCoincidentElementNodes) throw new InvalidOperationException("Generated FE mesh contains coincident nodes inside at least one element.");

                // Make the native GUI proof useful: show the generated model mesh, not only CAD geometry.
                _controller.CurrentView = ViewGeometryModelResults.Model;
            }
            catch (Exception ex)
            {
                error = ex.GetType().Name + ": " + ex.Message;
            }

            WriteEvidence(evidencePath, stepPath, sourceExists, sourceDeclaresMm, imported, cadScaleOk,
                          createMeshReturned, meshGenerated, meshScaleOk, nodeCoordinatesFinite,
                          elementConnectivityValid, noCoincidentElementNodes, geometryPartCount, geometryNodeCount,
                          meshPartCount, meshNodeCount, meshElementCount, cadDx, cadDy, cadDz,
                          meshDx, meshDy, meshDz, minElementNodeDistance, meshedPartName, elementTypes, sha256, error);
        }

        private static bool Finite(double v) { return !Double.IsNaN(v) && !Double.IsInfinity(v); }
        private static bool ExpectedScale(double dx, double dy, double dz, double tol)
        {
            return Math.Abs(dx - 537.0) <= tol && Math.Abs(dy - 162.0) <= tol && Math.Abs(dz - 254.0) <= tol;
        }
        private static string HashFile(string path)
        {
            using (SHA256 sha = SHA256.Create())
            using (FileStream fs = File.OpenRead(path))
            {
                byte[] h = sha.ComputeHash(fs); StringBuilder sb = new StringBuilder();
                foreach (byte b in h) sb.Append(b.ToString("x2", CultureInfo.InvariantCulture));
                return sb.ToString();
            }
        }
        private static string Json(string s) { return "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", " ").Replace("\n", " ") + "\""; }
        private static string Num(double v) { return (!Finite(v)) ? "null" : v.ToString("R", CultureInfo.InvariantCulture); }

        private static void WriteEvidence(string path, string stepPath, bool sourceExists, bool sourceDeclaresMm,
            bool imported, bool cadScaleOk, bool createMeshReturned, bool meshGenerated, bool meshScaleOk,
            bool finiteNodes, bool connectivity, bool noCoincident, int geometryParts, int geometryNodes,
            int meshParts, int meshNodes, int meshElements, double cadDx, double cadDy, double cadDz,
            double meshDx, double meshDy, double meshDz, double minDistance, string partName,
            string elementTypes, string sha, string error)
        {
            if (String.IsNullOrWhiteSpace(path)) return;
            string dir = Path.GetDirectoryName(path); if (!String.IsNullOrWhiteSpace(dir)) Directory.CreateDirectory(dir);
            bool qualified = sourceExists && sourceDeclaresMm && imported && cadScaleOk && createMeshReturned &&
                             meshGenerated && meshScaleOk && finiteNodes && connectivity && noCoincident &&
                             String.IsNullOrEmpty(error);
            string json = "{\n" +
                "  \"schema\": \"astermax.native-step-netgen-mesh-qualification.v1\",\n" +
                "  \"source_step_exists\": " + (sourceExists ? "true" : "false") + ",\n" +
                "  \"source_step_declares_si_millimetres\": " + (sourceDeclaresMm ? "true" : "false") + ",\n" +
                "  \"source_step_sha256\": " + Json(sha) + ",\n" +
                "  \"native_step_imported\": " + (imported ? "true" : "false") + ",\n" +
                "  \"geometry_part_count\": " + geometryParts.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"geometry_node_count\": " + geometryNodes.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"cad_extents_mm\": [" + Num(cadDx) + "," + Num(cadDy) + "," + Num(cadDz) + "],\n" +
                "  \"cad_mm_scale_qualified\": " + (cadScaleOk ? "true" : "false") + ",\n" +
                "  \"meshed_part_name\": " + Json(partName) + ",\n" +
                "  \"controller_create_mesh_returned\": " + (createMeshReturned ? "true" : "false") + ",\n" +
                "  \"native_netgen_mesh_generated\": " + (meshGenerated ? "true" : "false") + ",\n" +
                "  \"mesh_part_count\": " + meshParts.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"mesh_node_count\": " + meshNodes.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"mesh_element_count\": " + meshElements.ToString(CultureInfo.InvariantCulture) + ",\n" +
                "  \"mesh_element_types\": " + Json(elementTypes) + ",\n" +
                "  \"mesh_extents_mm\": [" + Num(meshDx) + "," + Num(meshDy) + "," + Num(meshDz) + "],\n" +
                "  \"post_mesh_mm_scale_qualified\": " + (meshScaleOk ? "true" : "false") + ",\n" +
                "  \"mesh_node_coordinates_finite\": " + (finiteNodes ? "true" : "false") + ",\n" +
                "  \"element_connectivity_valid\": " + (connectivity ? "true" : "false") + ",\n" +
                "  \"no_coincident_element_nodes\": " + (noCoincident ? "true" : "false") + ",\n" +
                "  \"minimum_element_node_distance_mm\": " + Num(minDistance) + ",\n" +
                "  \"step_to_netgen_mesh_qualified\": " + (qualified ? "true" : "false") + ",\n" +
                "  \"solver_executed\": false,\n  \"solver_verified\": false,\n  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n" +
                "  \"step_path\": " + Json(stepPath) + ",\n  \"error\": " + Json(error) + "\n}";
            File.WriteAllText(path, json, Encoding.UTF8);
        }
    }
}
