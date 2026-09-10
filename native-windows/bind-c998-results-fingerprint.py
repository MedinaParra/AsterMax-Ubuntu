#!/usr/bin/env python3
"""C9.98 metadata-only binder for real AsterMax result bundles.

Adds the SHA-256 fingerprint of the FeModel that produced the result bundle.
It never creates, interpolates, scales, or modifies FEA result arrays.
"""
import argparse
import copy
import hashlib
import json
import pathlib
import re
import sys

HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def bind(bundle, fingerprint):
    if bundle.get("schema") != "astermax-results-bundle/v0":
        raise ValueError("unsupported results bundle schema")
    integrity = bundle.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("fea_values_invented") is not False:
        raise ValueError("only non-synthetic verified result bundles can be bound")
    fp = str(fingerprint).strip().lower()
    if not HEX64.fullmatch(fp):
        raise ValueError("model fingerprint must be a 64-character lowercase SHA-256")

    before_arrays = digest(bundle.get("arrays"))
    out = copy.deepcopy(bundle)
    out.setdefault("integrity", {})["model_fingerprint_sha256"] = fp
    out["integrity"]["model_binding"] = "ASTERMAX_FE_MODEL_FINGERPRINT_C9_76"
    out["integrity"]["result_values_modified_by_binding"] = False
    after_arrays = digest(out.get("arrays"))
    if before_arrays != after_arrays:
        raise RuntimeError("FEA arrays changed during metadata binding")
    return out, before_arrays


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("fingerprint")
    ap.add_argument("out")
    a = ap.parse_args()
    source = json.loads(pathlib.Path(a.bundle).read_text(encoding="utf-8"))
    out, arrays_sha = bind(source, a.fingerprint)
    pathlib.Path(a.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "release": "C9.98",
        "status": "PASS",
        "model_fingerprint_sha256": out["integrity"]["model_fingerprint_sha256"],
        "fea_arrays_sha256_before_after": arrays_sha,
        "fea_values_modified": False
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("C9.98 REJECTED: " + str(exc), file=sys.stderr)
        sys.exit(3)
