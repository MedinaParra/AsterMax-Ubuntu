#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

old_sig = 'private static DemoCase CreateCase(string resuFile)\n        {\n'
new_sig = '''private static DemoCase CreateCase(Controller controller, string resuFile)\n        {\n            string fullModelPmx = Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_FULL_MODEL_PMX");\n            if (!String.IsNullOrWhiteSpace(fullModelPmx))\n            {\n                fullModelPmx = Path.GetFullPath(fullModelPmx);\n                if (!File.Exists(fullModelPmx))\n                    throw new FileNotFoundException("C8.66 full-model PMX does not exist.", fullModelPmx);\n                controller.Open(fullModelPmx);\n                if (controller.Model == null || controller.Model.Mesh == null)\n                    throw new InvalidDataException("C8.66 native PMX open produced no FE mesh.");\n                FeMesh fullMesh = controller.Model.Mesh;\n                int expectedNodes = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_NODES") ?? "5158", CultureInfo.InvariantCulture);\n                int expectedElements = Int32.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_ELEMENTS") ?? "2474", CultureInfo.InvariantCulture);\n                if (fullMesh.Nodes.Count != expectedNodes || fullMesh.Elements.Count != expectedElements)\n                    throw new InvalidDataException("C8.66 PMX topology mismatch. Nodes=" + fullMesh.Nodes.Count + " Elements=" + fullMesh.Elements.Count);\n                double expectedMises = Double.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_MISES_MAX") ?? "25.2160918", CultureInfo.InvariantCulture);\n                double expectedDisp = Double.Parse(Environment.GetEnvironmentVariable("ASTERMAX_RESULTS_EXPECTED_DISP_MAX") ?? "0.0182068655", CultureInfo.InvariantCulture);\n                return new DemoCase\n                {\n                    Name = "C8.66-full-model-pmx",\n                    Mesh = fullMesh,\n                    ExpectedNodeCount = expectedNodes,\n                    RequireNondegenerateMises = true,\n                    ExpectedMisesMax = expectedMises,\n                    ExpectedDispMax = expectedDisp\n                };\n            }\n'''
if old_sig not in text:
    raise SystemExit('CreateCase signature anchor not found; refusing partial patch.')
text = text.replace(old_sig, new_sig, 1)

old_call = 'DemoCase demoCase = CreateCase(resuFile);'
new_call = 'DemoCase demoCase = CreateCase(controller, resuFile);'
if old_call not in text:
    raise SystemExit('CreateCase call anchor not found; refusing partial patch.')
text = text.replace(old_call, new_call, 1)

old_payload = '"  \\"mesh_nodes\\": " + demoCase.ExpectedNodeCount.ToString(CultureInfo.InvariantCulture) + ",\\n" +'
new_payload = '"  \\"mesh_nodes\\": " + demoCase.ExpectedNodeCount.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\"full_model_pmx_loaded\\": " + (String.Equals(demoCase.Name, "C8.66-full-model-pmx", StringComparison.Ordinal) ? "true" : "false") + ",\\n" +'
if old_payload not in text:
    raise SystemExit('READY payload mesh_nodes anchor not found; refusing partial patch.')
text = text.replace(old_payload, new_payload, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path}')
