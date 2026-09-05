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

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.75 compact borderless verified-results badge')
