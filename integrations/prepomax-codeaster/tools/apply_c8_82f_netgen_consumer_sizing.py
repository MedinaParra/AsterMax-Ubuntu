#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'Controller.cs'
text = path.read_text(encoding='utf-8-sig')

anchor = '''            MeshingParameters meshingParameters = GetPartMeshingParameters(part.Name);
            meshingParameters.WriteToFile(meshParametersFileName, part.BoundingBox.GetDiagonal());
            CreateMeshRefinementFile(part, meshRefinementFileName, null);'''
replacement = '''            MeshingParameters meshingParameters = GetPartMeshingParameters(part.Name);

            // C8.82f harness-only qualification seam. The product-level geometry-selection binding is
            // still under investigation; do not claim it is fixed. This override is intentionally placed
            // at the exact consumer boundary used by CreateMeshFromBrep, immediately before the parameters
            // are serialized for NetGen. It lets CI distinguish a PrePoMax binding defect from a NetGen
            // sizing defect while preserving a fail-closed evidence trail.
            string c882fRequestedMaxH = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_CONSUMER_MAXH_MM");
            if (!String.IsNullOrWhiteSpace(c882fRequestedMaxH))
            {
                double c882fMaxH;
                if (!Double.TryParse(c882fRequestedMaxH, System.Globalization.NumberStyles.Float,
                                     System.Globalization.CultureInfo.InvariantCulture, out c882fMaxH) ||
                    Double.IsNaN(c882fMaxH) || Double.IsInfinity(c882fMaxH) || c882fMaxH <= 0)
                    throw new InvalidOperationException("ASTERMAX_NETGEN_CONSUMER_MAXH_MM must be finite and > 0 mm.");
                meshingParameters.RelativeSize = false;
                meshingParameters.MaxH = c882fMaxH;
                if (meshingParameters.MinH > c882fMaxH) meshingParameters.MinH = 0;
            }

            meshingParameters.WriteToFile(meshParametersFileName, part.BoundingBox.GetDiagonal());

            string c882fParametersCopy = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_PARAMETERS_COPY_PATH");
            if (!String.IsNullOrWhiteSpace(c882fParametersCopy))
            {
                string c882fDir = Path.GetDirectoryName(c882fParametersCopy);
                if (!String.IsNullOrWhiteSpace(c882fDir)) Directory.CreateDirectory(c882fDir);
                File.Copy(meshParametersFileName, c882fParametersCopy, true);
            }
            CreateMeshRefinementFile(part, meshRefinementFileName, null);'''

if anchor not in text:
    raise SystemExit('C8.82f CreateMeshFromBrep consumer anchor not found; refusing non-deterministic patch')
text = text.replace(anchor, replacement, 1)
path.write_text(text, encoding='utf-8')
print(f'C8.82f effective NetGen consumer sizing + parameter capture applied: {path}')
