from __future__ import annotations

import base64
import hashlib
import lzma
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FIX = ROOT / "payload_fix"
OUT_XZ = ROOT / "MAX_CIM_structure_base.brep.xz"
OUT_BREP = ROOT / "MAX_CIM_structure_base.brep"

# The original upload attempt mixed two chunking schemes and duplicated brep_08.
# This manifest is deliberate and hash-gated: only chunks proven to match the
# locally regenerated CadQuery BREP stream are used, with four repaired gaps.
PARTS = [
    PAYLOAD / "brep_00.b64",  # 0..7999
    PAYLOAD / "brep_01.b64",  # 8000..19999
    PAYLOAD / "brep_02.b64",  # 20000..31999
    FIX / "seg_03.b64",       # 32000..43999
    PAYLOAD / "brep_03.b64",  # 44000..55999
    PAYLOAD / "brep_04.b64",
    PAYLOAD / "brep_05.b64",
    PAYLOAD / "brep_06.b64",
    PAYLOAD / "brep_07.b64",
    PAYLOAD / "brep_09.b64",  # brep_08 is a duplicate and intentionally skipped
    PAYLOAD / "brep_10.b64",
    PAYLOAD / "brep_11.b64",
    PAYLOAD / "brep_12.b64",
    FIX / "seg_13.b64",
    PAYLOAD / "brep_14.b64",
    PAYLOAD / "brep_15.b64",
    FIX / "seg_16.b64",
    FIX / "seg_17.b64",
]

EXPECTED_B64_LENGTH = 208_856
EXPECTED_XZ_SHA256 = "27b6caa728e4d98aa9c0e66991630c5e0cb694fcd255ebe32d72c48d86d22aba"
EXPECTED_BREP_SHA256 = "8c5ac5b58343ef63b82094fb0ec59ce4a75336a2a86d26c9c105de408ac4b960"
EXPECTED_BREP_BYTES = 1_809_786


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    missing = [str(p.relative_to(ROOT)) for p in PARTS if not p.is_file()]
    if missing:
        raise SystemExit("MISSING_PAYLOAD_PARTS: " + ", ".join(missing))

    encoded = "".join(p.read_text(encoding="ascii").strip() for p in PARTS)
    if len(encoded) != EXPECTED_B64_LENGTH:
        raise SystemExit(f"B64_LENGTH_MISMATCH: {len(encoded)} != {EXPECTED_B64_LENGTH}")

    compressed = base64.b64decode(encoded, validate=True)
    xz_hash = sha256(compressed)
    if xz_hash != EXPECTED_XZ_SHA256:
        raise SystemExit(f"XZ_SHA256_MISMATCH: {xz_hash}")

    brep = lzma.decompress(compressed)
    brep_hash = sha256(brep)
    if len(brep) != EXPECTED_BREP_BYTES:
        raise SystemExit(f"BREP_SIZE_MISMATCH: {len(brep)} != {EXPECTED_BREP_BYTES}")
    if brep_hash != EXPECTED_BREP_SHA256:
        raise SystemExit(f"BREP_SHA256_MISMATCH: {brep_hash}")

    OUT_XZ.write_bytes(compressed)
    OUT_BREP.write_bytes(brep)
    print(f"PASS payload_b64_chars={len(encoded)}")
    print(f"PASS xz_bytes={len(compressed)} sha256={xz_hash}")
    print(f"PASS brep_bytes={len(brep)} sha256={brep_hash}")
    print(OUT_BREP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
