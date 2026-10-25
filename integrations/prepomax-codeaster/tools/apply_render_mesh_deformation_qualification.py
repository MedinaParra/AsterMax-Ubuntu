#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

anchor = '''                if (userScaleMaxError > deformationCoordinateTolerance)\n                    throw new InvalidDataException("C8.71 user-scale geometry failed Xd=X0+scale*U. max_error=" + userScaleMaxError);\n\n                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n'''
insert = '''                if (userScaleMaxError > deformationCoordinateTolerance)\n                    throw new InvalidDataException("C8.71 user-scale geometry failed Xd=X0+scale*U. max_error=" + userScaleMaxError);\n\n                // C8.72: qualify the FeResults mesh-deformation pipeline that feeds Results drawing.\n                // Do not infer success from GetScaledNode alone: mutate the live result mesh with the\n                // native SetMeshDeformation path and compare the actual render-source node coordinates.\n                int[] renderControlNodes = new int[] { verifiedDispNode, verifiedMisesNode };\n                float[] qualifiedRenderScales = new float[] { 0f, 1f, qualifiedUserScale };\n                double renderMeshMaxError = 0;\n                foreach (float renderScale in qualifiedRenderScales)\n                {\n                    results.SetMeshDeformation(renderScale, 1, 1);\n                    foreach (int controlNodeId in renderControlNodes)\n                    {\n                        FeNode expectedRenderNode = controller.GetScaledNode(renderScale, controlNodeId);\n                        FeNode actualRenderNode = results.Mesh.Nodes[controlNodeId];\n                        for (int i = 0; i < 3; i++)\n                            renderMeshMaxError = Math.Max(renderMeshMaxError,\n                                Math.Abs(actualRenderNode.Coor[i] - expectedRenderNode.Coor[i]));\n                    }\n                }\n                if (renderMeshMaxError > deformationCoordinateTolerance)\n                    throw new InvalidDataException("C8.72 render-source mesh deformation failed. max_error=" + renderMeshMaxError);\n\n                // Restore the demonstrator to undeformed contour after qualification; no visual overclaim.\n                results.SetMeshDeformation(0f, 1, 1);\n                controller.DrawResults(false);\n                Application.DoEvents();\n\n                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n'''
if anchor not in text:
    raise SystemExit('C8.71 deformation anchor not found; refusing partial C8.72 patch.')
text = text.replace(anchor, insert, 1)

payload_anchor = '''                    "  \\\"deformation_ui_scale_selector_verified\\\": false,\\n" +\n                    "  \\\"native_node_probe_verified\\\": true,\\n" +'''
payload_new = '''                    "  \\\"deformation_ui_scale_selector_verified\\\": false,\\n" +\n                    "  \\\"render_mesh_deformation_source\\\": \\\"FeResults.SetMeshDeformation(scale,step,increment)\\\",\\n" +\n                    "  \\\"render_mesh_control_nodes\\\": [" + verifiedDispNode.ToString(CultureInfo.InvariantCulture) + "," + verifiedMisesNode.ToString(CultureInfo.InvariantCulture) + "],\\n" +\n                    "  \\\"render_mesh_scales_verified\\\": [0.0,1.0,10.0],\\n" +\n                    "  \\\"render_mesh_max_coordinate_error_mm\\\": " + renderMeshMaxError.ToString("R", CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"render_mesh_deformation_verified\\\": true,\\n" +\n                    "  \\\"native_node_probe_verified\\\": true,\\n" +'''
if payload_anchor not in text:
    raise SystemExit('C8.71 READY payload anchor not found; refusing partial C8.72 patch.')
text = text.replace(payload_anchor, payload_new, 1)

old_provenance = '''            provenance.Text = "SOLVER VERIFIED  |  probe + deformation geometry  |  mm-N-MPa";\n'''
new_provenance = '''            provenance.Text = "SOLVER VERIFIED  |  render-mesh deformation qualified  |  mm-N-MPa";\n'''
if old_provenance not in text:
    raise SystemExit('C8.71 provenance anchor not found; refusing partial C8.72 patch.')
text = text.replace(old_provenance, new_provenance, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.72 render-mesh deformation qualification')
