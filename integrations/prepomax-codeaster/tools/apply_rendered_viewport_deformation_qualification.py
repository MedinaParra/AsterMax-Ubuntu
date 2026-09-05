#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()

# Expose a read-only qualification seam on vtkControl. It does not mutate geometry:
# it inspects the actual visible color-contour vtkActor bounds after DrawResults().
vtk = root / 'vtkControl' / 'vtkControl.cs'
text = vtk.read_text(encoding='utf-8-sig')
anchor = '''        // Callbacks                                                                                                                \n'''
helper = '''        // AsterMax C8.74 qualification seam: inspect the geometry actually handed to VTK rendering.\n        // Only visible ColorContours actors are included, so diagnostics/selection overlays cannot\n        // make a false PASS. The method is intentionally read-only.\n        public double[] AsterMaxGetVisibleContourActorBoundsForQualification(out int actorCount)\n        {\n            actorCount = 0;\n            double[] combined = new double[]\n            {\n                Double.PositiveInfinity, Double.NegativeInfinity,\n                Double.PositiveInfinity, Double.NegativeInfinity,\n                Double.PositiveInfinity, Double.NegativeInfinity\n            };\n\n            foreach (vtkMaxActor actor in _actors.Values)\n            {\n                if (actor == null || !actor.ColorContours || actor.Geometry == null) continue;\n                if (actor.Geometry.GetVisibility() != 1) continue;\n                double[] b = actor.Geometry.GetBounds();\n                if (b == null || b.Length != 6) continue;\n                bool finite = true;\n                for (int i = 0; i < 6; i++)\n                    if (Double.IsNaN(b[i]) || Double.IsInfinity(b[i])) finite = false;\n                if (!finite) continue;\n\n                actorCount++;\n                combined[0] = Math.Min(combined[0], b[0]); combined[1] = Math.Max(combined[1], b[1]);\n                combined[2] = Math.Min(combined[2], b[2]); combined[3] = Math.Max(combined[3], b[3]);\n                combined[4] = Math.Min(combined[4], b[4]); combined[5] = Math.Max(combined[5], b[5]);\n            }\n\n            if (actorCount == 0)\n                throw new InvalidOperationException("No visible VTK ColorContours actor found for C8.74 qualification.");\n            return combined;\n        }\n\n'''
if helper not in text:
    if anchor not in text:
        raise SystemExit('vtkControl callbacks anchor not found; refusing partial C8.74 patch.')
    text = text.replace(anchor, helper + anchor, 1)
vtk.write_text(text, encoding='utf-8')

# Route the read-only VTK inspection through FrmMain, which owns the live vtkControl instance.
frm = root / 'PrePoMax' / 'Forms' / 'FrmMain.cs'
f = frm.read_text(encoding='utf-8-sig')
frm_anchor = '''        public string GetDeformationVariable()\n        {\n'''
frm_helper = '''        // AsterMax C8.74: read-only access to the live rendered contour actor bounds.\n        public double[] AsterMaxGetRenderedContourBoundsForQualification(out int actorCount)\n        {\n            if (_vtk == null) throw new InvalidOperationException("VTK control is not initialized.");\n            return _vtk.AsterMaxGetVisibleContourActorBoundsForQualification(out actorCount);\n        }\n\n'''
if frm_helper not in f:
    if frm_anchor not in f:
        raise SystemExit('FrmMain deformation getter anchor not found; refusing partial C8.74 patch.')
    f = f.replace(frm_anchor, frm_helper + frm_anchor, 1)
frm.write_text(f, encoding='utf-8')

# After C8.73 has retained UserDefined x10, compare the live VTK actor bounds against the
# x10-deformed FeResults mesh bounds. This qualifies the last handoff into the viewport.
demo = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
d = demo.read_text(encoding='utf-8')
old = '''                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n'''
new = '''                // C8.74: qualify the final handoff to VTK. At this point C8.73 has retained\n                // UserDefined x10 and DrawResults() has populated the live rendered actors.\n                double[] meshBounds = new double[]\n                {\n                    Double.PositiveInfinity, Double.NegativeInfinity,\n                    Double.PositiveInfinity, Double.NegativeInfinity,\n                    Double.PositiveInfinity, Double.NegativeInfinity\n                };\n                foreach (FeNode meshNode in results.Mesh.Nodes.Values)\n                {\n                    meshBounds[0] = Math.Min(meshBounds[0], meshNode.Coor[0]);\n                    meshBounds[1] = Math.Max(meshBounds[1], meshNode.Coor[0]);\n                    meshBounds[2] = Math.Min(meshBounds[2], meshNode.Coor[1]);\n                    meshBounds[3] = Math.Max(meshBounds[3], meshNode.Coor[1]);\n                    meshBounds[4] = Math.Min(meshBounds[4], meshNode.Coor[2]);\n                    meshBounds[5] = Math.Max(meshBounds[5], meshNode.Coor[2]);\n                }\n\n                int renderedContourActorCount;\n                double[] renderedBounds = controller.Form.AsterMaxGetRenderedContourBoundsForQualification(out renderedContourActorCount);\n                double renderedBoundsMaxError = 0;\n                for (int bi = 0; bi < 6; bi++)\n                    renderedBoundsMaxError = Math.Max(renderedBoundsMaxError, Math.Abs(renderedBounds[bi] - meshBounds[bi]));\n                const double renderedBoundsTolerance = 1e-6;\n                if (renderedContourActorCount < 1)\n                    throw new InvalidDataException("C8.74 no rendered contour actors found.");\n                if (renderedBoundsMaxError > renderedBoundsTolerance)\n                    throw new InvalidDataException("C8.74 VTK actor bounds do not match the verified x10 Results mesh. max_error=" + renderedBoundsMaxError);\n\n                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n'''
if old not in d:
    raise SystemExit('NativeScalarBarGate anchor not found; refusing partial C8.74 patch.')
d = d.replace(old, new, 1)

payload_old = '''                    "  \\\"deformation_ui_scale_selector_verified\\\": true,\\n" +\n                    "  \\\"render_mesh_deformation_source\\\": \\\"FeResults.SetMeshDeformation(scale,step,increment)\\\",\\n" +'''
payload_new = '''                    "  \\\"deformation_ui_scale_selector_verified\\\": true,\\n" +\n                    "  \\\"rendered_viewport_deformation_source\\\": \\\"vtkControl visible ColorContours vtkActor.Geometry.GetBounds()\\\",\\n" +\n                    "  \\\"rendered_viewport_contour_actor_count\\\": " + renderedContourActorCount.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"rendered_viewport_bounds_max_error_mm\\\": " + renderedBoundsMaxError.ToString("R", CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"rendered_viewport_deformation_verified\\\": true,\\n" +\n                    "  \\\"render_mesh_deformation_source\\\": \\\"FeResults.SetMeshDeformation(scale,step,increment)\\\",\\n" +'''
if payload_old not in d:
    raise SystemExit('C8.73 READY payload anchor not found; refusing partial C8.74 patch.')
d = d.replace(payload_old, payload_new, 1)

old_provenance = '''            provenance.Text = "SOLVER VERIFIED  |  native deformation UI x10 verified  |  mm-N-MPa";\n'''
new_provenance = '''            provenance.Text = "SOLVER VERIFIED  |  rendered deformation x10 verified  |  mm-N-MPa";\n'''
if old_provenance not in d:
    raise SystemExit('C8.73 provenance anchor not found; refusing partial C8.74 patch.')
d = d.replace(old_provenance, new_provenance, 1)

demo.write_text(d, encoding='utf-8')
print(f'Patched {vtk} with read-only rendered contour actor bounds qualification')
print(f'Patched {frm} with live VTK qualification bridge')
print(f'Patched {demo} with C8.74 VTK viewport deformation gate')
