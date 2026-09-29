# AsterMax Mechanical Qualification — lessons captured from WS01.1

## Purpose

WS01.1 exposed several failure modes that can produce a numerically completed solve while still
giving a misleading engineering comparison. These lessons are now product rules, not tutorial-only
exceptions.

## 1. Solver success is not engineering qualification

A Code_Aster job that ends successfully proves execution, not model correctness. AsterMax must keep
separate states:

1. **SOLVED_AUTHENTIC** — genuine solver evidence exists.
2. **SOLVED_WITH_ENGINEERING_WARNINGS** — the solve is real but one or more qualification gates
   remain incomplete.
3. **ENGINEERING_QUALIFIED** — solver evidence plus mesh, scope, post-processing and equilibrium
   gates are satisfied.
4. **BENCHMARK_EQUIVALENT** — optional, separate comparison to an external reference.

A benchmark mismatch must never be "fixed" by tuning the model until the number matches.

## 2. CAD face numbers are not persistent identity

The first WS01 reproduction used the wrong four counterbore faces while still producing a stable
solution. Raw STEP/Gmsh/NetGen surface numbers may change when geometry is regenerated.

Production rule:

- Persist a CAD SHA-256 and geometric/topological fingerprint for every scoped face.
- Resolve the fingerprint against the current geometry before meshing/solving.
- Fail closed on missing, ambiguous or colliding matches.
- Raw face indices may remain in evidence as audit hints only.

For frozen benchmark fixtures, an exact CAD SHA-256 plus an attested face manifest is acceptable.

## 3. Structural solid element order matters

WS01 with linear tetrahedra was substantially too stiff. Moving from TETRA4 to TETRA10 materially
changed displacement and stress.

Production rule:

- Static structural 3-D solids should default to second-order elements where the mesher/solver route
  supports them.
- Linear TETRA4/HEXA8 remain valid capabilities, but AsterMax should warn before using them for
  stress equivalence or bending-sensitive work.
- Record the actual emitted element family; do not trust only the requested mesh setting.

## 4. High-order mesh quality is a solve gate

Generating a nominal TETRA10 mesh is insufficient. Curved midside-node placement can create inverted
or badly distorted high-order elements.

Production rule:

- Inspect the actual high-order Jacobian/quality evidence before accepting a mesh.
- Treat negative/inverted Jacobian evidence as a block.
- Meshing algorithms may be changed to obtain a valid mesh, but every algorithm choice is recorded.
- AsterMax must never silently downgrade to TETRA4 to make a case solve.

## 5. Frictionless support semantics must be normal-only

Mechanical frictionless support means zero normal displacement with tangential motion allowed.
For the Code_Aster route this maps to face-normal displacement constraint semantics
(`FACE_IMPO / DNOR=0`) rather than a fully fixed support.

The selected geometry is as important as the command syntax; both must be evidenced.

## 6. Equivalent stress must use component-first nodal averaging

Averaging already-computed von Mises scalars is not equivalent to averaging the tensor and then
computing the invariant.

AsterMax rule for Mechanical-style nodal Equivalent Stress:

1. Read real element-node stress tensor components.
2. Average SIXX, SIYY, SIZZ, SIXY, SIXZ and SIYZ independently at each node.
3. Compute von Mises from the averaged tensor.
4. Retain raw ELNO von Mises only as diagnostic evidence.

This rule is implemented in the MED bridge and tagged in result integrity metadata.

## 7. Reaction equilibrium is first-class evidence

Code_Aster `REAC_NODA` is now admitted by the result bridge. AsterMax records the global reaction
resultant from the real solver field.

Production rule:

- Assemble the applied-load resultant independently from the model/exporter.
- Compare applied load + support reaction.
- <= 1% residual: pass.
- > 1% and <= 5%: warning.
- > 5%: block engineering qualification.
- Absence of an independently assembled load resultant leaves an engineering warning.

## 8. Convergence is about observables, not chasing one peak

Local support-edge stresses can be mesh-sensitive and may behave differently from global
displacement.

Production rule:

- Track at least displacement and equivalent stress separately.
- Report changes between mesh levels.
- Default guidance: <=5% change in displacement and <=10% in stress is a useful qualification
  target, not a universal physical law.
- Flag likely singular/local peaks instead of forcing them to match another solver's maximum.

## 9. External benchmark values retain provenance

The ANSYS WS01 values 235.96 MPa / 0.064809 mm / 1.1866 are a tutorial snapshot before a later
1 mm refinement exercise. They are not treated as a demonstrated mesh-converged truth.

AsterMax stores benchmark classification and compares numerically, but benchmark error does not
decide whether the solve is physically valid.

## 10. Result rendering must not control solve validity

CI previously failed after a valid solve because the Windows runner had no OpenGL context.

Production rule:

- Solver/result admission and screenshot generation are separate gates.
- Headless evidence rendering uses a non-OpenGL path when appropriate.
- A rendering failure cannot invalidate an already authenticated FEA solve; it is a presentation
  failure with its own status.

## 11. Evidence is immutable and hashable

For every production solve, retain lightweight evidence:

- model/CAD fingerprint;
- mesh family/order/counts and quality status;
- solver message file hash;
- result MED/VTU hash;
- qualification report;
- post-processing method;
- selected scope fingerprints;
- reaction/equilibrium summary;
- convergence summary when present.

No result is promoted if its provenance cannot be tied to the current model.

## Current implementation

- Component-first Equivalent Stress: implemented in `bridge-c964-med-results.py`.
- Real `REAC_NODA` resultant: implemented in the MED bridge.
- Native static exporter requests `REAC_NODA` and persists an independently assembled nodal-load resultant.
- Mechanical qualification policy: `mechanical-qualification-policy.json`.
- Reusable qualification gate: `qualify-mechanical-analysis.py`.
- The qualification gate consumes the real Code_Aster `.mess` file and blocks recognized
  inverted/distorted-element or Jacobian alarm evidence.
- In-app summary: `AsterMaxMechanicalQualification.cs` via C10.21.
- Native Solve executes the qualification gate before promoting the result to Solution Current.
- C10.22 extends the frozen FeModel SHA-256 identity with NodeSet, ElementSet and Surface membership,
  so a scope-membership change invalidates old results even when the group name is unchanged.
- Qualification regression tests include an explicit distorted-mesh blocking case.
- Fast qualification CI passes independently of the long solver workflow.
- C10.21 and C10.22 both compile successfully on the pinned PrePoMax Windows x64 Release build.
- WS01 exact-CAD + face-manifest scope evidence: implemented.
- WS01 TETRA10 convergence workflow remains an evidence benchmark, not product logic.
- PrePoMax already requests second-order meshing by default; AsterMax therefore verifies the actual
  emitted element family rather than duplicating or overriding that default.

## Next product-level items

1. Persist geometric/topological CAD face fingerprints in the native project model for arbitrary
   geometry-scoped loads/supports; current C10.22 scope identity is strongest after mesh groups exist.
2. Add independent high-order Jacobian/quality metrics to the native mesh model and pre-solve
   readiness. The current `.mess` alarm gate is authoritative post-solve evidence but not a
   substitute for a pre-solve high-order metric.
3. Generalize independent load-resultant assembly beyond the current native nodal-force route to
   pressure, gravity, centrifugal and distributed loads.
4. Surface qualification state as a dedicated Solution-tree/status badge in addition to
   Solution Information.
5. Generalize convergence service/UI so each result observable can carry its own convergence history
   and local-peak/singularity warning.
6. Extend the same qualification contract to contact, shells, beams, thermal and nonlinear cases with
   formulation-specific gates.
