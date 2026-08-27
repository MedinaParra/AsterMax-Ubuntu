# AsterMax Mechanical 2.0 beta

AsterMax is a GPL-3.0 finite-element pre/postprocessor and an evolving **evidence-native engineering analysis system**. Its development thesis is:

> **Can AsterMax demonstrate that the result being shown deserves confidence for the engineering decision being made?**

The solver is treated as a producer of evidence, not as the sole product boundary. AsterMax separates input provenance, code verification, solution verification, analytical corroboration, experimental validation, uncertainty and applicability to intended use.

No proprietary Ansys code, icons, screenshots or documentation are redistributed.

## Credibility-first development

The active development methodology and roadmap are:

- [`docs/DEVELOPMENT_METHODOLOGY.md`](docs/DEVELOPMENT_METHODOLOGY.md)
- [`docs/CREDIBILITY_ROADMAP.md`](docs/CREDIBILITY_ROADMAP.md)

Core rules:

- **No claim without evidence.**
- **Evidence before claim.**
- **AI may propose; deterministic checks must prove.**
- **Credibility is always evaluated for an intended use.**
- Missing, ambiguous or out-of-domain evidence fails closed.

AsterMax does not use a single opaque “trust score”; credibility is reported as separate evidence dimensions.

## Verified minimum Static Structural workflow

The current verified minimum workflow can complete a limited linear-static path with authentic numerical fields and explicit limitations:

```text
Geometry → Material → Scope → TET4/TET10 Mesh
→ Boundary Conditions / Loads → Sparse Solve
→ Displacement / Integration-Point Stress → Reactions
→ Equilibrium → Convergence / Verification Gates
→ Viewer → Evidence Package
```

The currently developed internal PMV scope includes:

- one 3-D solid in declared units;
- isotropic linear elasticity;
- small displacement;
- one load step;
- first- and second-order tetrahedral verification paths;
- sparse direct solution using SciPy;
- authentic displacement and stress evidence;
- force and moment equilibrium checks;
- convergence gates for declared benchmark quantities of interest;
- SHA-256 integrity/provenance evidence for selected analysis inputs and outputs;
- Windows executable packaging with packaged self-test.

Unsupported or unproven capabilities must be rejected explicitly rather than silently approximated.

## Claim boundary

A successful solve, green CI, mesh convergence, analytical agreement or cross-code agreement does **not** automatically mean that a model is physically validated, industrially validated, certified by an external authority, or equivalent to Ansys.

AsterMax uses the following distinctions:

- **code verification:** are the equations/algorithms implemented correctly?
- **solution verification:** is this numerical solution sufficiently resolved for the declared quantity of interest?
- **analytical/empirical corroboration:** does an independent witness support the result inside its applicability domain?
- **cross-code corroboration:** does another independent implementation agree?
- **validation:** does the model adequately represent physical reality for its intended use?
- **uncertainty:** how sensitive is the result to numerical, input, measurement and model-form uncertainty?

The term **certified** is reserved for cases where an identified authority, certification scope and acceptance basis justify it. Historical CLI/file names containing `certify` are implementation names and do not constitute an external certification claim.

## Analytical Evidence direction

AsterMax is adding independent mechanics witnesses to corroborate supported FEA regions. Planned first witnesses include:

- CAD-derived section area, centroid and second moments;
- axial and biaxial bending stress;
- circular-shaft torsion;
- combined bending/torsion von Mises reconstruction;
- versioned stress-concentration correlations for supported details only when source/provenance and applicability ranges are encoded.

Analytical witnesses do not replace FEA. They provide an independent evidence path. Empirical correlations are rejected when geometry/load assumptions lie outside their encoded applicability domain.

## Neighborhood Verification direction

Local FEA credibility will be assessed over a geometry-defined neighborhood rather than by trusting one maximum node/cell value. Controlled refinement will track finite-distance stress fields separately from point maxima so likely singularities can be distinguished from stable physical concentrations.

## Development discipline

Every engineering capability should follow:

```text
Engineering question
→ Intended use
→ Claim
→ Required evidence
→ Failure conditions
→ Independent benchmark/test
→ Implementation
→ Negative tests
→ Windows CI
→ Evidence package
→ Human review
→ Claim enabled
```

A feature is not considered complete merely because it executes.

## License

GNU GPL v3.
