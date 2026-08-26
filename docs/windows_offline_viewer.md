# AsterMax PMV — Offline Result Viewer

## Purpose

The offline viewer is a portable visualization surface for AsterMax verification results. It is intentionally separated from numerical validation: the viewer displays solver fields but cannot promote them to converged or industrially validated evidence.

## Generate the verification demo

From a Windows PowerShell terminal in the repository:

```powershell
python -m pip install -e .[test]
python benchmarks/generate_offline_viewer.py
```

The command creates `astermax_demo/` containing:

- `astermax_verification.vtu` — solver fields for external CAE/post-processing tools;
- `astermax_verification.vtu.manifest.json` — VTU evidence metadata and SHA-256;
- `astermax_viewer.html` — self-contained offline viewer;
- `astermax_viewer.html.manifest.json` — viewer payload and HTML SHA-256 evidence.

Open `astermax_viewer.html` directly in a current Windows browser. No web server, CDN or Internet connection is required.

## Viewer controls

- drag the model to orbit;
- use the mouse wheel to zoom;
- switch between displacement magnitude and von Mises stress;
- change deformation display scale or use the automatic display scale;
- toggle the undeformed wireframe;
- inspect min/max values, units, topology counts and evidence status.

## Evidence rules

The verification demo is classified `VERIFICATION_BENCHMARK_NOT_INDUSTRIAL_RESULT`.

`converged_claim = false` means no mesh-convergence acceptance has been granted to the displayed result.

`industrial_validation_claim = false` means the result must not be used as an accepted industrial design result.

The deformation display scale changes visualization coordinates only. It does not modify displacement, stress, reaction or equilibrium values produced by the solver.

Cell von Mises values remain cell-located. The viewer colors each external surface triangle from its owning TET4 value rather than silently manufacturing a nodal stress field.

## Reproducibility

The viewer payload is serialized canonically and hashed with SHA-256. The generated HTML is independently hashed. CI publishes the complete `astermax_demo` folder so the result fields and the visualization can be tied back to the exact Windows workflow run that generated them.
