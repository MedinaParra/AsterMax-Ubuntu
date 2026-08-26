# AsterMax Mechanical 2.0 beta

AsterMax is a GPL-3.0 finite-element pre/postprocessor for Ubuntu and Xubuntu. It uses an AsterMax-designed desktop CAE workspace with a command ribbon, model outline, graphics viewport, property/details editor and worksheet views while providing two solver paths:

1. **AsterMax Internal Linear Solver** for a verified minimum single-part static workflow.
2. **Code_Aster** for advanced and nonlinear analyses.

AsterMax is independently developed. No proprietary third-party code, icons, screenshots or documentation are redistributed. See `docs/CLEAN_ROOM_POLICY.md` for the project engineering boundary.

## Certified minimum Static Structural workflow

Version 2.0 can complete this path locally without Code_Aster:

```text
Geometry → Material → Named Selections → TET4 Mesh → Mesh Quality
→ Fixed/Displacement Support → Force/Pressure/Traction/Gravity
→ Solve → Displacement/Stress/Strain → Reactions
→ Stress Assessment → Traceable certification report
```

The internal solver supports:

- one 3-D solid;
- isotropic linear elasticity;
- small displacement;
- one load step;
- first-order tetrahedral elements;
- fixed or prescribed translational displacement;
- nodal force, pressure, surface traction and gravity;
- sparse direct solution using SciPy;
- authentic VTU displacement, stress, strain and reaction fields;
- force and moment equilibrium tables;
- von Mises, Tresca and brittle-material failure screening;
- SHA-256 traceability of solver inputs and outputs.

Unsupported advanced objects are rejected explicitly instead of being silently ignored. Contacts, remote couplings, joints, bolt pretension, nonlinear geometry, shells, beams, multiple materials and multistep analyses continue through Code_Aster.

## One-command certification

```bash
astermax-cli certify-static project.astermax.json \
  --backend internal --output certification
```

The command performs model validation, writes Code_Aster-compatible input, solves the model, reads authentic fields, checks mesh quality and reactions, then creates:

```text
static_structural_certification.html
static_structural_certification.json
static_workflow_acceptance.html
astermax_solver_run.json
certified_project.astermax.json
```

Run the built-in analytical reference:

```bash
astermax-cli run-static-reference reference
```

The reference is a solid TET4 cantilever. It checks displacement and stress against Euler–Bernoulli values and verifies force and moment equilibrium to numerical precision.

## CAE roadmap features

The application also includes:

- STEP/IGES/BREP import through Gmsh OCC;
- materials and assignments by volume;
- local/global mesh controls and quality contours;
- Code_Aster static, nonlinear, modal, thermal, buckling and submodel input;
- contacts, joints, remote points and constraint equations;
- deformation, stress, strain, reaction and contact-result processing;
- solution information, probes and Named Selection scoping;
- stress linearization through a Path;
- project mesh convergence;
- Design Points;
- multistep load histories;
- failure-theory stress assessment.

## Install

```bash
sudo apt install ./AsterMax-Ubuntu-2.0.0b1-amd64.deb
astermax-safe
```

The bootstrap package installs the GUI, VTK, SciPy, Gmsh and result-processing dependencies on first launch. The internal solver works without Code_Aster for the certified minimum workflow. Code_Aster can be configured separately through native, Docker, Podman, Apptainer or Singularity backends.

## Development

```bash
./scripts/install_ubuntu.sh
./scripts/run_dev.sh
pytest -q
```

## Engineering governance

Material implementation inputs and dependencies must be traceable before release:

- `docs/CLEAN_ROOM_POLICY.md` — independent-development and IP boundary;
- `docs/DEPENDENCY_REGISTER.md` — dependencies, integration modes and license review;
- `docs/SOURCE_PROVENANCE.md` — implementation-source and benchmark provenance.

## Validation boundary

“Certified” means the exact saved project passed the defined AsterMax certification scope and generated authentic numerical fields. It does not mean complete equivalence to any third-party CAE product, element formulation or design-code requirement. Advanced Code_Aster workflows require their own benchmark and target-system validation.

## License

GNU GPL v3.
