#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'Controller.cs'
text = path.read_text(encoding='utf-8-sig')

# C8.86d: anchor to the seam installed immediately beforehand by C8.82f instead of
# matching a brittle multiline snapshot of upstream Controller.cs. C8.82f already
# identifies the qualified CreateMeshFromBrep consumer boundary used by the STEP path.
# We therefore locate its unique parameter-copy marker, then instrument only the first
# CreateMeshRefinementFile call that follows it within a bounded window. Any ambiguity
# remains fail-closed.
c882f_marker = 'string c882fParametersCopy = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_PARAMETERS_COPY_PATH");'
refinement_call = '            CreateMeshRefinementFile(part, meshRefinementFileName, null);'
c886_sentinel = 'string c886Points = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_REFINEMENT_POINTS");'

if c886_sentinel in text:
    raise SystemExit('C8.86d refinement seam already present; refusing duplicate instrumentation')
if text.count(c882f_marker) != 1:
    raise SystemExit(f'C8.86d expected exactly one C8.82f consumer marker, found {text.count(c882f_marker)}')

marker_pos = text.index(c882f_marker)
call_pos = text.find(refinement_call, marker_pos)
if call_pos < 0:
    raise SystemExit('C8.86d refinement call not found after C8.82f consumer marker')
if call_pos - marker_pos > 3000:
    raise SystemExit(f'C8.86d refinement call is unexpectedly far from C8.82f marker ({call_pos - marker_pos} chars)')

# Guard against accidentally crossing into another method if upstream changes.
method_guard = text.find('        private ', marker_pos)
if method_guard >= 0 and method_guard < call_pos:
    raise SystemExit('C8.86d crossed a method boundary before refinement call; refusing patch')

seam = '''            CreateMeshRefinementFile(part, meshRefinementFileName, null);\n\n            // C8.86d harness-only multi-ROI qualification seam at the effective BREP_MESH\n            // consumer boundary established by C8.82f. This writes the exact NetGen point\n            // refinement contract. It does NOT claim native FeMeshRefinement / GUI / PMX binding.\n            string c886Points = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_REFINEMENT_POINTS");\n            if (!String.IsNullOrWhiteSpace(c886Points))\n            {\n                string[] c886Specs = c886Points.Split(new char[] { ';' }, StringSplitOptions.RemoveEmptyEntries);\n                if (c886Specs.Length == 0) throw new InvalidOperationException("C8.86 refinement point contract is empty.");\n                using (System.IO.StreamWriter c886Writer = new System.IO.StreamWriter(meshRefinementFileName, false))\n                {\n                    c886Writer.WriteLine(c886Specs.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));\n                    foreach (string c886Spec in c886Specs)\n                    {\n                        string[] c886Vals = c886Spec.Split(',');\n                        if (c886Vals.Length != 4) throw new InvalidOperationException("C8.86 point must be x,y,z,h.");\n                        double[] c886Num = new double[4];\n                        for (int c886I = 0; c886I < 4; c886I++)\n                        {\n                            if (!Double.TryParse(c886Vals[c886I], System.Globalization.NumberStyles.Float,\n                                                 System.Globalization.CultureInfo.InvariantCulture, out c886Num[c886I]) ||\n                                Double.IsNaN(c886Num[c886I]) || Double.IsInfinity(c886Num[c886I]))\n                                throw new InvalidOperationException("C8.86 point contains a non-finite value.");\n                        }\n                        if (c886Num[3] <= 0) throw new InvalidOperationException("C8.86 local h must be > 0 mm.");\n                        c886Writer.WriteLine(String.Format(System.Globalization.CultureInfo.InvariantCulture,\n                            "{0:R} {1:R} {2:R} {3:R}", c886Num[0], c886Num[1], c886Num[2], c886Num[3]));\n                    }\n                    c886Writer.WriteLine("0"); // zero refined segments; point refinements only\n                }\n\n                // Capture before launching NetGen. A missing evidence file therefore means the\n                // effective BREP consumer seam was not reached, not a later mesher/solver timeout.\n                string c886Copy = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_REFINEMENT_COPY_PATH");\n                if (!String.IsNullOrWhiteSpace(c886Copy))\n                {\n                    string c886Dir = Path.GetDirectoryName(c886Copy);\n                    if (!String.IsNullOrWhiteSpace(c886Dir)) Directory.CreateDirectory(c886Dir);\n                    File.Copy(meshRefinementFileName, c886Copy, true);\n                }\n            }'''

text = text[:call_pos] + seam + text[call_pos + len(refinement_call):]
path.write_text(text, encoding='utf-8')
print(f'C8.86d C8.82f-anchored BREP multi-ROI NetGen refinement seam applied: {path}')
