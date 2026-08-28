from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from astermax.fea.credibility_visualization import render_from_json


def main() -> int:
    source = Path("c3_2_cad_derived_axial_benchmark.json")
    if not source.is_file():
        raise RuntimeError("C4 requires c3_2_cad_derived_axial_benchmark.json from the real C3.2 benchmark")
    output = Path("astermax_c4_credibility_chain.html")
    manifest = render_from_json(source, output)
    Path("astermax_c4_credibility_chain.manifest.json").write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(asdict(manifest), indent=2, sort_keys=True, allow_nan=False))
    if manifest.arbitrary_model_convergence or manifest.industrial_validation or manifest.ansys_equivalence:
        raise RuntimeError("C4 visualization upgraded a prohibited claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
