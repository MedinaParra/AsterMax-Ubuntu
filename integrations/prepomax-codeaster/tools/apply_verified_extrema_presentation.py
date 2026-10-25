#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

old = '''            benchmark.Visible = false;\n            benchmark.Top = 130;\n'''
new = '''            int verifiedMisesNode = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_MISES_NODE") ?? "-1", CultureInfo.InvariantCulture);\n            int verifiedDispNode = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_DISP_NODE") ?? "-1", CultureInfo.InvariantCulture);\n            if (verifiedMisesNode <= 0 || verifiedDispNode <= 0)\n                throw new InvalidOperationException("Verified extrema node provenance is unavailable.");\n            benchmark.Visible = true;\n            benchmark.Top = 82;\n            benchmark.Left = 12;\n            benchmark.Width = 306;\n            benchmark.Height = 34;\n            benchmark.AutoSize = false;\n            benchmark.Text = "MAX  " + max.ToString("0.000", CultureInfo.InvariantCulture) + " MPa  ·  Node " +\n                verifiedMisesNode.ToString(CultureInfo.InvariantCulture) + "     Umax  " +\n                dispMax.ToString("0.0000000", CultureInfo.InvariantCulture) + " mm  ·  Node " +\n                verifiedDispNode.ToString(CultureInfo.InvariantCulture);\n'''
if old not in text:
    raise SystemExit('C8.68 benchmark-hidden anchor not found; refusing partial C8.69 patch.')
text = text.replace(old, new, 1)

old = '''            provenance.Top = 120;\n            provenance.Text = "SOLVER VERIFIED | mm-N-MPa";\n'''
new = '''            provenance.Top = 116;\n            provenance.Text = "SOLVER VERIFIED  |  STRESS/MISES  |  undeformed contour  |  mm-N-MPa";\n'''
if old not in text:
    raise SystemExit('C8.68 provenance anchor not found; refusing partial C8.69 patch.')
text = text.replace(old, new, 1)

old = '''            overlay.Width = 330;\n            overlay.Height = 150;\n'''
new = '''            overlay.Width = 440;\n            overlay.Height = 150;\n'''
if old not in text:
    raise SystemExit('C8.68 overlay size anchor not found; refusing partial C8.69 patch.')
text = text.replace(old, new, 1)

payload_anchor = '''                    "  \\\"hidden_diagnostic_tokens\\\": \\\"" + presentation.HiddenDiagnosticTokens + "\\\"\\n" +'''
payload_new = '''                    "  \\\"hidden_diagnostic_tokens\\\": \\\"" + presentation.HiddenDiagnosticTokens + "\\\",\\n" +\n                    "  \\\"verified_extrema_labels\\\": true,\\n" +\n                    "  \\\"mises_max_node\\\": " + Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_MISES_NODE") ?? "-1", CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"disp_max_node\\\": " + Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_DISP_NODE") ?? "-1", CultureInfo.InvariantCulture).ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"deformation_state\\\": \\\"undeformed-contour\\\",\\n" +\n                    "  \\\"deformation_scale_semantics_verified\\\": false\\n" +'''
if payload_anchor not in text:
    raise SystemExit('C8.68 READY payload anchor not found; refusing partial C8.69 patch.')
text = text.replace(payload_anchor, payload_new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.69 verified extrema presentation')
