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

    method_tokens = ["CreateMeshFromBrep(", "CreateMeshFromBrep ("]
    starts = [text.find(t) for t in method_tokens if text.find(t) >= 0]
    if not starts:
        raise RuntimeError("C8.89 observer: CreateMeshFromBrep method anchor not found")
    start = min(starts)
    anchor = "CreateMeshRefinementFile(part, meshRefinementFileName, null);"
    pos = text.find(anchor, start)
    if pos < 0 or pos - start > 20000:
        raise RuntimeError("C8.89 observer: BREP CreateMeshRefinementFile anchor not found in guarded window")
    next_pos = text.find(anchor, pos + len(anchor))
    if next_pos >= 0 and next_pos - start < 20000:
        raise RuntimeError("C8.89 observer: ambiguous BREP refinement consumer anchors")

    marker = "ASTERMAX_NATIVE_REFINEMENT_CONSUMER_COPY_PATH"
    if marker in text:
        print("C8.89 observer already present")
        return 0

    injected = anchor + '''\n            // C8.89 read-only qualification observer. Copy the native-generated refinement contract\n            // before NetGen consumes it. Never rewrite or inject meshing input.\n            string asterMaxNativeRefinementCopy = Environment.GetEnvironmentVariable("ASTERMAX_NATIVE_REFINEMENT_CONSUMER_COPY_PATH");\n            if (!String.IsNullOrWhiteSpace(asterMaxNativeRefinementCopy) && System.IO.File.Exists(meshRefinementFileName))\n            {\n                string asterMaxNativeRefinementDir = System.IO.Path.GetDirectoryName(asterMaxNativeRefinementCopy);\n                if (!String.IsNullOrWhiteSpace(asterMaxNativeRefinementDir)) System.IO.Directory.CreateDirectory(asterMaxNativeRefinementDir);\n                System.IO.File.Copy(meshRefinementFileName, asterMaxNativeRefinementCopy, true);\n            }'''
    text = text[:pos] + text[pos:].replace(anchor, injected, 1)
    controller.write_text(text, encoding="utf-8")
    print("C8.89 read-only BREP refinement observer applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
