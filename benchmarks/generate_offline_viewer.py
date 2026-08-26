from pathlib import Path

from astermax.fea.connected_scaling import build_structured_bar
from astermax.fea.postprocess import write_linear_static_vtu
from astermax.fea.solver import solve_linear_static
from astermax.fea.tet4 import IsotropicMaterial
from astermax.fea.viewer import write_offline_viewer_html


if __name__ == "__main__":
    nodes, elements, loads, fixed = build_structured_bar(8, ny=2, nz=1)
    result = solve_linear_static(
        nodes,
        elements,
        IsotropicMaterial(210000.0, 0.3),
        loads,
        fixed,
    )
    out_dir = Path("astermax_demo")
    out_dir.mkdir(exist_ok=True)
    vtu = out_dir / "astermax_verification.vtu"
    html = out_dir / "astermax_viewer.html"
    vtu_manifest = write_linear_static_vtu(vtu, nodes, elements, result)
    viewer_manifest = write_offline_viewer_html(html, nodes, elements, result)
    print(f"VTU: {vtu.resolve()}")
    print(f"Viewer: {html.resolve()}")
    print(f"VTU SHA-256: {vtu_manifest.vtu_sha256}")
    print(f"Viewer SHA-256: {viewer_manifest.html_sha256}")
