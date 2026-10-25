#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

anchor = '''                if (demoCase.ExpectedDispMax.HasValue && Math.Abs(dispMax - demoCase.ExpectedDispMax.Value) > 1e-9)\n                    throw new InvalidDataException("DISP/ALL maximum failed the pinned displacement oracle. Observed=" + dispMax);\n\n                controller.AllResults.Add(results.FileName, results);\n'''
insert = '''                if (demoCase.ExpectedDispMax.HasValue && Math.Abs(dispMax - demoCase.ExpectedDispMax.Value) > 1e-9)\n                    throw new InvalidDataException("DISP/ALL maximum failed the pinned displacement oracle. Observed=" + dispMax);\n\n                // C8.70: qualify a product-native nodal probe through FeResults.GetValues().\n                // The nodes are solver-admitted extrema provenance from C8.65; no values are fabricated.\n                int verifiedMisesNode = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_MISES_NODE") ?? "-1", CultureInfo.InvariantCulture);\n                int verifiedDispNode = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_DISP_NODE") ?? "-1", CultureInfo.InvariantCulture);\n                if (verifiedMisesNode <= 0 || verifiedDispNode <= 0)\n                    throw new InvalidOperationException("C8.70 native probe requires solver-verified extrema node provenance.");\n                float[] probeMisesValues = results.GetValues(stressData, new int[] { verifiedMisesNode });\n                float[] probeDispValues = results.GetValues(dispData, new int[] { verifiedDispNode });\n                if (probeMisesValues == null || probeMisesValues.Length != 1 ||\n                    probeDispValues == null || probeDispValues.Length != 1 ||\n                    Single.IsNaN(probeMisesValues[0]) || Single.IsInfinity(probeMisesValues[0]) ||\n                    Single.IsNaN(probeDispValues[0]) || Single.IsInfinity(probeDispValues[0]))\n                    throw new InvalidDataException("C8.70 FeResults.GetValues nodal probe returned invalid data.");\n                double expectedProbeMises = Double.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_MISES_MAX") ?? "NaN", CultureInfo.InvariantCulture);\n                double expectedProbeDisp = Double.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_DISP_MAX") ?? "NaN", CultureInfo.InvariantCulture);\n                if (Double.IsNaN(expectedProbeMises) || Double.IsNaN(expectedProbeDisp))\n                    throw new InvalidOperationException("C8.70 expected probe values are unavailable.");\n                if (Math.Abs(probeMisesValues[0] - expectedProbeMises) > 1e-5)\n                    throw new InvalidDataException("C8.70 Mises node probe disagrees with solver-admitted extrema. Observed=" + probeMisesValues[0]);\n                if (Math.Abs(probeDispValues[0] - expectedProbeDisp) > 1e-8)\n                    throw new InvalidDataException("C8.70 displacement node probe disagrees with solver-admitted extrema. Observed=" + probeDispValues[0]);\n\n                controller.AllResults.Add(results.FileName, results);\n'''
if anchor not in text:
    raise SystemExit('C8.70 displacement oracle anchor not found; refusing partial patch.')
text = text.replace(anchor, insert, 1)

old = '''            provenance.Text = "SOLVER VERIFIED  |  STRESS/MISES  |  undeformed contour  |  mm-N-MPa";\n'''
new = '''            provenance.Text = "SOLVER VERIFIED  |  native node probe  |  undeformed contour  |  mm-N-MPa";\n'''
if old not in text:
    raise SystemExit('C8.69 provenance anchor not found; refusing partial C8.70 patch.')
text = text.replace(old, new, 1)

payload_anchor = '''                    "  \\\"deformation_state\\\": \\\"undeformed-contour\\\",\\n" +\n                    "  \\\"deformation_scale_semantics_verified\\\": false\\n" +'''
payload_new = '''                    "  \\\"deformation_state\\\": \\\"undeformed-contour\\\",\\n" +\n                    "  \\\"deformation_scale_semantics_verified\\\": false,\\n" +\n                    "  \\\"native_node_probe_verified\\\": true,\\n" +\n                    "  \\\"native_node_probe_source\\\": \\\"FeResults.GetValues(FieldData,int[])\\\",\\n" +\n                    "  \\\"probe_mises_node\\\": " + verifiedMisesNode.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"probe_mises_mpa\\\": " + probeMisesValues[0].ToString("R", CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"probe_disp_node\\\": " + verifiedDispNode.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"probe_disp_mm\\\": " + probeDispValues[0].ToString("R", CultureInfo.InvariantCulture) + "\\n" +'''
if payload_anchor not in text:
    raise SystemExit('C8.69 READY deformation anchor not found; refusing partial C8.70 patch.')
text = text.replace(payload_anchor, payload_new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.70 native node-probe qualification')
