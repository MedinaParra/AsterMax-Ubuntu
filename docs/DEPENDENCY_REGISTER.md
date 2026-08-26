# AsterMax Dependency & License Register

All direct runtime, solver, build, packaging, visualization, geometry, and test dependencies must be registered before release.

| Component | Purpose | Version / Pin | License | Source | Integration mode | Redistributed? | Review state | Notes |
|---|---|---|---|---|---|---|---|---|
| Python | Runtime | TBD | TBD | official upstream | runtime | TBD | pending | Pin exact supported versions |
| SciPy | Sparse numerical routines | TBD | TBD | official upstream | Python dependency | TBD | pending | Used by internal linear solver per project README |
| Gmsh | Geometry / meshing | TBD | TBD | official upstream | process/library TBD | TBD | pending | Confirm exact integration and redistribution model |
| VTK | Result visualization / fields | TBD | TBD | official upstream | library | TBD | pending | Confirm packaged modules |
| Code_Aster | Advanced solver backend | TBD | TBD | official upstream | external solver backend | TBD | pending | Keep boundary and distribution model explicit |

## Required fields

Every dependency entry must include:

- exact package/component name;
- exact version or reproducible version range;
- SPDX license identifier where possible;
- canonical upstream source;
- whether it is linked, imported, executed as an external process, accessed over an API, or used only at build/test time;
- whether AsterMax redistributes it;
- license obligations relevant to distribution;
- reviewer and review date before a production release.

## Policy

1. No dependency with an unknown license enters a production release.
2. No vendored source is accepted without provenance and license files.
3. Transitive dependencies used in packaged binaries must be captured through an automated SBOM before release.
4. Solver backends must expose a documented boundary so the distribution model can be reviewed independently from the AsterMax application layer.
5. License notices required by dependencies must be generated into the release package.

## Planned automation

Release CI should eventually generate:

- SPDX or CycloneDX SBOM;
- dependency version lock snapshot;
- license inventory;
- third-party notices;
- hash manifest for distributed artifacts.
