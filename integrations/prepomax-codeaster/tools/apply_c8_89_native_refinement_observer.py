#!/usr/bin/env python3
from pathlib import Path
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    controller = repo / "PrePoMax" / "Controller.cs"
    text = controller.read_text(encoding="utf-8-sig")

    # C8.89a composes with C8.82f, which has already qualified the exact STEP/BREP
    # consumer boundary. Anchor to its unique marker instead of guessing from method text.
    c882f_marker = 'string c882fParametersCopy = Environment.GetEnvironmentVariable("ASTERMAX_NETGEN_PARAMETERS_COPY_PATH");'
    anchor = '            CreateMeshRefinementFile(part, meshRefinementFileName, null);'
    marker = "ASTERMAX_NATIVE_REFINEMENT_CONSUMER_COPY_PATH"

    if marker in text:
        raise RuntimeError("C8.89a observer already present; refusing duplicate instrumentation")
    if text.count(c882f_marker) != 1:
        raise RuntimeError("C8.89a expected exactly one qualified C8.82f BREP marker, found %d" % text.count(c882f_marker))

    marker_pos = text.index(c882f_marker)
    pos = text.find(anchor, marker_pos)
    if pos < 0:
        raise RuntimeError("C8.89a native refinement call not found after qualified BREP marker")
    if pos - marker_pos > 3000:
        raise RuntimeError("C8.89a native refinement call unexpectedly far from BREP marker: %d chars" % (pos-marker_pos))
    method_guard = text.find('        private ', marker_pos)
    if method_guard >= 0 and method_guard < pos:
        raise RuntimeError("C8.89a crossed a method boundary before native refinement consumer")

    injected = anchor + '''\n            // C8.89a read-only qualification observer at the C8.82f-qualified BREP seam.\n            // Copy the native-generated refinement contract before NetGen consumes it.\n            // Never rewrite or inject meshing input.\n            string asterMaxNativeRefinementCopy = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_CONSUMER_COPY_PATH");\n            if (!String.IsNullOrWhiteSpace(asterMaxNativeRefinementCopy) && System.IO.File.Exists(meshRefinementFileName))\n            {\n                string asterMaxNativeRefinementDir = System.IO.Path.GetDirectoryName(asterMaxNativeRefinementCopy);\n                if (!String.IsNullOrWhiteSpace(asterMaxNativeRefinementDir)) System.IO.Directory.CreateDirectory(asterMaxNativeRefinementDir);\n                System.IO.File.Copy(meshRefinementFileName, asterMaxNativeRefinementCopy, true);\n            }'''
    text = text[:pos] + text[pos:].replace(anchor, injected, 1)
    controller.write_text(text, encoding="utf-8")
    print("C8.89a C8.82f-anchored read-only BREP refinement observer applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
