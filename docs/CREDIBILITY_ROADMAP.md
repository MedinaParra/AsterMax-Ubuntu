# AsterMax Credibility-First Roadmap

## Product thesis

AsterMax exists to answer one engineering question:

> Can the software demonstrate that the result being shown deserves confidence for the engineering decision being made?

The solver is a producer of evidence. It is not the product boundary. The product boundary is the credibility of an engineering claim for an explicitly declared intended use.

## Non-negotiable rules

1. **No claim without evidence.**
2. **Evidence before claim.**
3. **AI may propose; deterministic checks must prove.**
4. **Credibility is always evaluated for an intended use.**
5. **No single opaque trust score.** Credibility is a vector of independently reported dimensions.
6. **Fail closed.** Missing, ambiguous, out-of-domain or non-reproducible evidence blocks the claim.
7. **One active capability gate at a time.** New physics, UX polish and agent autonomy wait behind the current credibility gate.
8. **No automatic industrial-validation claim.** Numerical agreement, analytical corroboration and cross-code agreement are not physical validation.
9. **No use of “certified” unless an identified authority, certification scope and acceptance basis justify the term.**
10. **Every empirical/handbook correlation carries an applicability contract and source metadata.** Out-of-domain use is rejected.

## Credibility dimensions

AsterMax must keep these dimensions separate:

- input provenance and integrity;
- code verification;
- solution verification;
- equilibrium and conservation checks;
- analytical/semi-analytical corroboration;
- empirical-correlation corroboration;
- cross-code corroboration;
- experimental validation;
- uncertainty quantification;
- applicability to intended use;
- industrial validation status.

## Development order

### C0 — Credibility Core

**Claim:** AsterMax can represent what is known, assumed, unknown and proven without conflating those states.

Deliverables:
- `ContextOfUse` schema: engineering question, decision, quantities of interest, consequence/criticality, acceptance criteria.
- `ClaimEngine` schema with deterministic state transitions.
- `EvidenceGraph` schema linking CAD, geometry scopes, material, loads, mesh, solver, results and checks.
- provenance classes: `VERIFIED`, `USER_CONFIRMED`, `ASSUMED`, `DERIVED`, `UNKNOWN`, `NOT_APPLICABLE`.
- applicability contracts for every witness/correlation.
- Analysis Passport v1 with a credibility vector, never a single trust score.

Exit gate:
- tests prove that an absent prerequisite cannot accidentally enable a higher claim.

### C1 — Persistent geometry and section evidence

**Claim:** The same physical region is identifiable after remeshing and section properties are derived from the actual CAD geometry.

Deliverables:
- persistent geometric selections independent of mesh node ids;
- topology/geometry fingerprints and ambiguity detection;
- section-cut extraction;
- numerical CAD integrals for area, centroid, `Iy`, `Iz`, `Iyz` and principal axes;
- unit and tolerance evidence;
- remesh persistence benchmark across TET4/TET10 and multiple target sizes.

Exit gate:
- support/load and analytical section witnesses recover the same intended geometry after remeshing, or fail closed.

### C2 — Analytical Evidence Engine v0.1

**Claim:** For supported geometries/load states, AsterMax can independently reconstruct classical-mechanics stresses and compare them with FEA without using the FEA stress field as the reference.

Initial analytical witnesses:
1. axial stress on general sections;
2. biaxial bending from section integrals;
3. circular-shaft torsion;
4. combined bending + torsion with von Mises reconstruction;
5. stepped-shaft stress-concentration witness only when a licensed/public correlation and its applicability domain are encoded.

Each witness stores:
- source and equation/correlation identifier;
- assumptions;
- valid geometry/load domain;
- input provenance;
- numerical method/tolerances where integrals are used;
- result and discrepancy metric;
- `APPLICABLE`, `NOT_APPLICABLE`, `INSUFFICIENT_EVIDENCE` or `PASS/FAIL` state.

Exit gate:
- witnesses reproduce independent closed-form/reference fixtures and reject out-of-domain geometries.

### C3 — Neighborhood Verification Engine

**Claim:** AsterMax can distinguish a stable physical stress field from a mesh-sensitive local maximum or likely singularity.

Deliverables:
- integration-point sampling in declared neighborhoods;
- section/path sampling at controlled distances from geometric features;
- FEA-vs-witness discrepancy profiles;
- local h-refinement series;
- singularity diagnostic: local maximum non-convergent while finite-distance neighborhood stabilizes;
- no hidden nodal stress smoothing in credibility checks.

Exit gate:
- synthetic finite-concentration and singular fixtures are classified correctly under refinement.

### C4 — Physics-guided local mesh refinement

**Claim:** AsterMax can refine a region because independent evidence shows insufficient numerical resolution, not merely because stress is high.

Deliverables:
- refinement trigger based on discrepancy/convergence/quality criteria;
- before/after mesh fingerprints;
- bounded refinement policy;
- evidence showing whether discrepancy decreases and stabilizes;
- termination/failure criteria.

Exit gate:
- refinement improves a declared verification metric reproducibly without relaxing acceptance thresholds.

### C5 — Code Verification Program

**Claim:** The implemented equations are solved correctly within declared formulation scopes.

Deliverables:
- patch tests and rigid-body tests;
- method of manufactured solutions where appropriate;
- analytical benchmark suite;
- NAFEMS-style benchmark set where licensing/public data permits;
- element formulation verification manual;
- regression tests tied to exact solver versions.

Exit gate:
- versioned AsterMax Verification Manual generated from CI evidence.

### C6 — General Solution Verification

**Claim:** A user model can carry a defensible numerical-resolution assessment even when no exact analytical solution exists.

Deliverables:
- h/p convergence framework;
- quantity-of-interest convergence rather than global “mesh converged” labels;
- Richardson/asymptotic estimators where assumptions apply;
- iterative/linear-solver residual evidence;
- mesh-quality and conditioning diagnostics;
- explicit singularity-aware handling of maxima.

### C7 — Validation and Uncertainty

**Claim:** AsterMax can distinguish numerical correctness from agreement with physical reality and can record relevant uncertainty.

Deliverables:
- experimental validation dataset schema;
- measurement uncertainty and model discrepancy metadata;
- validation metrics for declared quantities of interest;
- input-parameter sensitivity and uncertainty propagation framework;
- `CROSS_CODE_CORROBORATED` kept separate from `EXPERIMENTALLY_VALIDATED`.

### C8 — Verifiable Engineering Agent

Only after C0–C7 foundations exist for the targeted workflow.

The agent may:
- inspect;
- propose;
- request evidence;
- call deterministic tools;
- explain blocked claims;
- suggest refinement/alternative models.

The agent may not:
- set `converged`, `verified`, `validated` or `industrial_validation` directly;
- fabricate missing material/load/geometry provenance;
- override applicability contracts;
- silently change acceptance criteria;
- convert cross-code agreement into physical validation.

Required execution chain:

`AI proposal -> deterministic tool -> evidence -> ClaimEngine -> permitted/blocked claim`

### C9 — Productization

After the credibility architecture is stable:
- graphical persistent face selection;
- integrated viewer;
- project persistence;
- report generation;
- installer/signing;
- UX and performance work;
- additional physics only through new claim/evidence gates.

## Explicitly deferred until their credibility gates exist

- nonlinear contact;
- plasticity;
- fatigue;
- shells/beams beyond verified scopes;
- GPU acceleration as a product headline;
- autonomous “one-click solve” agent;
- universal material inference;
- automatic design-code compliance;
- a single numeric “trust score”.

## Definition of Done for every increment

Every increment follows this order:

`Engineering question -> Intended use -> Claim -> Required evidence -> Failure conditions -> Independent test/benchmark -> Implementation -> Windows CI -> Evidence package -> Human review -> Claim enabled`

A feature is not done because it runs. It is done when the declared claim can be enabled by evidence and disabled by its negative tests.

## Anti-drift checkpoint

Before opening any PR, answer:

1. What engineering claim becomes possible if this PR passes?
2. What independent evidence is required?
3. What is the negative test that must block the claim?
4. Does this change improve credibility for a declared intended use?
5. Is it the single highest-priority active gate?

If questions 1–4 cannot be answered, do not implement the feature. If question 5 is no, backlog it.
