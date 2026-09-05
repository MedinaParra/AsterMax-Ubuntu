#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

# C8.75 presentation-only increment. Physics/results stay untouched. Replace the developer-style
# fixed tool window with a compact, borderless verified-results badge that occupies substantially
# less viewport area. The harness independently inspects native window style and geometry.
old = '''            overlay.FormBorderStyle = FormBorderStyle.FixedToolWindow;\n            overlay.ShowInTaskbar = false;\n            overlay.StartPosition = FormStartPosition.Manual;\n            overlay.Width = 440;\n            overlay.Height = 150;\n'''
new = '''            overlay.FormBorderStyle = FormBorderStyle.None;\n            overlay.ShowInTaskbar = false;\n            overlay.StartPosition = FormStartPosition.Manual;\n            overlay.Width = 560;\n            overlay.Height = 82;\n            overlay.BackColor = Color.FromArgb(24, 28, 34);\n            overlay.ForeColor = Color.WhiteSmoke;\n            overlay.Opacity = 0.94;\n'''
if old not in text:
    raise SystemExit('C8.75 overlay frame anchor not found; refusing partial patch.')
text = text.replace(old, new, 1)

# Make the badge concise. Full numerical semantics remain available in the scalar bar and READY JSON.
text = text.replace('''            title.Left = 14;\n            title.Top = 14;\n            title.Text = "VERIFIED FIELD  STRESS / MISES";\n''', '''            title.Left = 14;\n            title.Top = 9;\n            title.ForeColor = Color.WhiteSmoke;\n            title.Text = "SOLVER VERIFIED  ·  STRESS / MISES  ·  deformation ×10";\n''', 1)

for label_name in ('source', 'range', 'deformation'):
    marker = '            ' + label_name + '.AutoSize = true;\n'
    if marker not in text:
        raise SystemExit('C8.75 label anchor not found: ' + label_name)
    text = text.replace(marker, marker + '            ' + label_name + '.Visible = false;\n', 1)

# C8.69 inserts a MAX/Umax line, while the historical benchmark assignment can still appear later.
# Force one professional data line after all prior presentation patches.
legacy_benchmark = '            benchmark.Text = "Benchmark: " + demoCase.Name;\n'
if legacy_benchmark in text:
    text = text.replace(legacy_benchmark, '', 1)
text = text.replace('            benchmark.Top = 82;\n', '            benchmark.Top = 34;\n', 1)
text = text.replace('            benchmark.Left = 12;\n', '            benchmark.Left = 14;\n', 1)
text = text.replace('            benchmark.Width = 306;\n', '            benchmark.Width = 535;\n', 1)
text = text.replace('            benchmark.Height = 34;\n', '            benchmark.Height = 20;\n', 1)
text = text.replace('            provenance.Top = 116;\n', '            provenance.Top = 57;\n', 1)
text = text.replace('            provenance.Left = 14;\n', '            provenance.Left = 14;\n            provenance.ForeColor = Color.Gainsboro;\n', 1)
text = text.replace('            provenance.Text = "SOLVER VERIFIED  |  STRESS/MISES  |  undeformed contour  |  mm-N-MPa";\n',
                    '            provenance.Text = "Code_Aster 17.4.0  ·  mm-N-MPa  ·  fail-closed provenance";\n', 1)

# Keep it away from the scalar bar and make the compact footprint deterministic.
old_pos = '''            overlay.Left = Math.Max(controller.Form.Right - overlay.Width - 28, 0);\n            overlay.Top = Math.Max(controller.Form.Top + 76, 0);\n'''
new_pos = '''            overlay.Left = Math.Max(controller.Form.Right - overlay.Width - 36, 0);\n            overlay.Top = Math.Max(controller.Form.Top + 78, 0);\n'''
if old_pos not in text:
    raise SystemExit('C8.75 overlay position anchor not found; refusing partial patch.')
text = text.replace(old_pos, new_pos, 1)

# Presentation mode should not leave the large extrema arrow callout covering the model.
# The values remain visible in the verified badge and in the READY evidence. This hides only the
# annotation widgets after all extrema/probe/render gates have already admitted the result.
show_anchor = '''            overlay.Show(controller.Form);\n            overlay.BringToFront();\n'''
show_new = '''            controller.Form.AsterMaxHideVerifiedResultArrowWidgets();\n            overlay.Show(controller.Form);\n            overlay.BringToFront();\n'''
if show_anchor not in text:
    raise SystemExit('C8.75 overlay show anchor not found; refusing lifecycle patch.')
text = text.replace(show_anchor, show_new, 1)

# Qualify normal shutdown by explicitly detaching VTK arrow widgets from their interactor while
# the WinForms/VTK stack is still alive. Upstream vtkControl.RemoveAllArrowWidgets() performs the
# required RemoveInteractor() for each widget before clearing the collection.
finally_anchor = '''            finally\n            {\n                if (verificationOverlay != null && !verificationOverlay.IsDisposed)\n                    verificationOverlay.Close();\n            }\n'''
finally_new = '''            finally\n            {\n                if (verificationOverlay != null && !verificationOverlay.IsDisposed)\n                    verificationOverlay.Close();\n            }\n'''
if finally_anchor not in text:
    raise SystemExit('C8.75 finally anchor not found; refusing partial lifecycle patch.')
# No semantic change in finally itself; shutdown hook is attached to the owner form below.

path.write_text(text, encoding='utf-8')

frm = root / 'PrePoMax' / 'Forms' / 'FrmMain.cs'
ftext = frm.read_text(encoding='utf-8-sig')
frm_anchor = '''        public string GetDeformationVariable()\n        {\n'''
frm_helper = '''        // AsterMax C8.75: presentation/lifecycle seam for the verified Results demo.\n        // It only manages VTK annotation widgets; it cannot alter result values, scale, mesh or actors.\n        public void AsterMaxHideVerifiedResultArrowWidgets()\n        {\n            if (InvokeRequired)\n            {\n                Invoke(new Action(AsterMaxHideVerifiedResultArrowWidgets));\n                return;\n            }\n            if (_vtk != null) _vtk.HideAllArrowWidgets();\n        }\n\n        public void AsterMaxPrepareVerifiedResultsShutdown()\n        {\n            if (InvokeRequired)\n            {\n                Invoke(new Action(AsterMaxPrepareVerifiedResultsShutdown));\n                return;\n            }\n            if (_vtk != null)\n            {\n                _vtk.RenderingOn = false;\n                _vtk.HideAllArrowWidgets();\n                _vtk.RemoveAllArrowWidgets();\n            }\n        }\n\n'''
if frm_helper not in ftext:
    if frm_anchor not in ftext:
        raise SystemExit('C8.75 FrmMain lifecycle seam anchor not found; refusing partial patch.')
    ftext = ftext.replace(frm_anchor, frm_helper + frm_anchor, 1)
frm.write_text(ftext, encoding='utf-8')

# Register the lifecycle cleanup on the real owner form. This is intentionally a FormClosing hook,
# so the interactor exists when RemoveInteractor() is invoked and the normal WinForms close path continues.
text = path.read_text(encoding='utf-8')
run_anchor = '''                verificationOverlay = CreateVerificationOverlay(controller, demoCase, min, max, dispMax);\n                if (verificationOverlay == null || verificationOverlay.IsDisposed || !verificationOverlay.Visible)\n'''
run_new = '''                verificationOverlay = CreateVerificationOverlay(controller, demoCase, min, max, dispMax);\n                controller.Form.FormClosing += delegate(object sender, FormClosingEventArgs e)\n                {\n                    controller.Form.AsterMaxPrepareVerifiedResultsShutdown();\n                    if (verificationOverlay != null && !verificationOverlay.IsDisposed)\n                        verificationOverlay.Hide();\n                };\n                if (verificationOverlay == null || verificationOverlay.IsDisposed || !verificationOverlay.Visible)\n'''
if run_anchor not in text:
    raise SystemExit('C8.75 verification overlay assignment anchor not found; refusing lifecycle patch.')
text = text.replace(run_anchor, run_new, 1)
path.write_text(text, encoding='utf-8')

print(f'Patched {path} with C8.75 compact borderless verified-results badge and normal-close lifecycle hook')
print(f'Patched {frm} with C8.75 safe VTK annotation cleanup seams')
