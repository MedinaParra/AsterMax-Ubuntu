# AsterMax Future Simulation PMV

## Objective

Build one technically credible, visually striking vertical slice that demonstrates a future workflow for mechanical simulation:

**Engineering intent -> auditable model setup -> real FEA -> automated verification -> parametric exploration -> AI surrogate -> explainable engineering decision.**

The PMV is not a claim that AsterMax replaces Ansys Mechanical. It is a demonstration of an autonomous, solver-agnostic engineering reasoning layer that can eventually integrate with multiple solvers, including Ansys through a future adapter.

## Product thesis

AsterMax should not compete by reproducing menus. The differentiated product is the reasoning and orchestration layer around simulation.

The system must be able to:

1. Understand the engineering question.
2. Convert that question into an explicit simulation plan.
3. Show every assumption before solving.
4. Build the model using versioned, machine-readable contracts.
5. Execute a real solver.
6. Verify equilibrium, convergence, mesh quality and scope.
7. Detect likely numerical or modelling failure modes.
8. Explore a parameter space automatically.
9. Train a surrogate only from validated simulation cases.
10. Explain the final engineering conclusion and link it to evidence.

## Killer demo: hub-sprocket excessive-gap RCA

The flagship PMV shall use a hub/sprocket mechanical assembly with an excessive gap capable of changing contact/load transfer and generating local stress concentration.

The purpose is not to predetermine a crack location. The PMV must calculate the response and report only what the numerical evidence supports.

### Engineering question

> How does increasing gap alter contact/load transfer, local stress, deformation and failure risk in the hub-sprocket load path?

### Minimum parameter set

- gap
- applied torque or equivalent tangential load
- material definition
- contact/friction assumptions
- local mesh size near the gap/contact transition
- relevant geometric dimensions

### Required outputs

- total deformation
- von Mises stress
- maximum principal stress
- contact pressure when supported by the selected solver model
- reaction force/moment balance
- mesh-quality metrics
- hotspot coordinates and scoped region
- convergence evidence
- parameter-response curves
- solver provenance and hashes

## User experience

### 1. Intent

The engineer enters the problem in natural language or selects the industrial case.

Example:

> Evaluate whether excessive gap in this hub-sprocket assembly causes abnormal load transfer and a local stress concentration. Sweep gap and identify the region where the response changes most strongly.

AsterMax generates a Simulation Intent object containing:

- physics
- requested outputs
- candidate loads and supports
- contact assumptions
- uncertain inputs
- validation checks
- required solver capability

Nothing is silently accepted.

### 2. Model Plan

The UI presents a compact engineering plan:

- geometry bodies
- materials
- connections/contacts
- boundary conditions
- mesh strategy
- analysis type
- requested results
- verification tests

Every item has one state: Confirmed, Inferred, Missing, or Rejected.

### 3. Solve

The PMV shall execute a real finite-element backend.

Preferred initial backend:

- Code_Aster for contact/nonlinear capability when required

Existing certified linear AsterMax workflow may be used for benchmark/reference cases, but no synthetic field may be presented as a solved industrial result.

### 4. Verification Gate

A result cannot enter the AI dataset until it passes the verification gate.

Minimum gate:

- solver completed normally
- no unsupported object was silently ignored
- force equilibrium within configured tolerance
- moment equilibrium within configured tolerance
- mesh metrics recorded
- displacement/stress fields exist and are non-empty
- hotspot is not only a known singular boundary unless explicitly identified as such
- model/input/output hashes saved
- convergence status recorded

Cases that fail remain visible but are labelled Rejected for learning.

### 5. Parametric Explorer

Run a controlled design-of-experiments sweep over gap and load.

The PMV should show:

- a timeline of completed simulations
- validated vs rejected cases
- response curves
- hotspot migration
- field thumbnails
- sensitivity ranking

The first objective is not large-scale optimisation. It is to make the relationship between geometry/operating condition and mechanical response obvious.

### 6. AI Surrogate

Only after enough validated runs exist, AsterMax can train a lightweight surrogate model.

The surrogate must provide:

- near-instant prediction for scalar responses
- optional predicted field representation if technically validated
- uncertainty/confidence indicator
- nearest validated simulations
- out-of-domain warning
- one-click escalation to real FEA

The PMV must visually distinguish:

- FEA truth
- surrogate prediction
- extrapolation

### 7. Mechanical Reasoning Report

The final view should answer:

- What changed?
- Where did it change?
- Why does the model indicate that?
- Which assumptions materially affect the conclusion?
- Is the result converged and balanced?
- What should be simulated next?

Each claim links to the underlying result, parameter, mesh or solver run.

## Solver-agnostic architecture

Create a stable orchestration contract so the product is not coupled to one backend.

```text
SimulationIntent
    |
    v
ModelPlan
    |
    v
SolverModelV1
    |--------------------------|
    v                          v
CodeAsterAdapter          InternalAdapter
    |                          |
    +------------+-------------+
                 v
          SolverResultV1
                 |
                 v
          VerificationV1
                 |
        +--------+--------+
        |                 |
      REJECT            ACCEPT
                          |
                          v
                    DatasetCaseV1
                          |
                          v
                  SurrogateModelV1
```

Future adapters may include Ansys/PyAnsys without changing the upper product workflow.

## Versioned contracts

### SimulationIntentV1

Must include:

- problem statement
- target physics
- geometry source
- parameters
- requested outputs
- known constraints
- uncertain assumptions
- verification policy

### SolverRunManifestV1

Must include:

- solver name/version
- backend configuration
- model hash
- mesh hash
- input hash
- start/end timestamps
- termination status
- log location

### VerificationV1

Must include machine-readable pass/fail values for:

- equilibrium
- mesh
- convergence
- result-field presence
- unsupported-feature detection
- domain/singularity warnings

### DatasetCaseV1

Only generated from accepted solver runs.

Must preserve linkage back to the exact solver result and input hashes.

## Visual design for the PMV

The PMV should open directly on the engineering problem, not on a generic empty CAD screen.

Recommended layout:

- Left: Simulation Graph / Outline
- Center: 3D model and fields
- Right: Engineering Reasoning panel
- Bottom: Evidence timeline

### Engineering Reasoning panel

Show short, testable statements such as:

- Gap increased from X to Y.
- Contact/load-transfer region moved toward Z.
- Peak principal stress changed by N%.
- Current hotspot is/is not mesh converged.
- Current prediction lies inside/outside the validated surrogate domain.

Never generate a number in this panel unless it exists in the result data.

## Demo sequence

The target live demo should be understandable without explanation:

1. Open hub-sprocket case.
2. Display the engineering question.
3. Show detected model assumptions.
4. Confirm/adjust the uncertain ones.
5. Solve one real baseline case.
6. Display stress/deformation/contact fields.
7. Open Verification Gate and show equilibrium/convergence evidence.
8. Launch gap sweep.
9. Show response curves and hotspot migration.
10. Train/update surrogate from accepted cases.
11. Move the gap slider and obtain an immediate prediction.
12. Click Verify with FEA for that prediction.
13. Compare surrogate vs real result.
14. Generate an evidence-linked RCA summary.

## What makes this strategically interesting

The PMV is deliberately complementary to high-end solvers.

The valuable asset is not another linear solver. It is the layer that can turn engineering intent into a traceable simulation workflow and turn verified solver runs into reusable engineering intelligence.

A future Ansys adapter should make the same AsterMax workflow capable of dispatching a case to Ansys Mechanical/PyAnsys and ingesting the returned fields and metadata.

## Non-negotiable credibility rules

- No fabricated FEA fields.
- No deterministic colour-map mock presented as physics.
- No hidden assumptions.
- No surrogate prediction labelled as an FEA result.
- No accepted AI-training case without verification evidence.
- No claim of solver equivalence without benchmark data.
- No silent fallback from unsupported advanced physics to a simpler model.

## PMV acceptance criteria

The PMV is considered successful only when all of the following are demonstrable on one machine:

- [ ] industrial geometry loads correctly
- [ ] model assumptions are serialised
- [ ] real solver is executed
- [ ] authentic fields are visualised
- [ ] run provenance is stored
- [ ] equilibrium check is visible
- [ ] at least one mesh/convergence check is visible
- [ ] gap parameter can be changed reproducibly
- [ ] multiple validated FEA cases can be compared
- [ ] rejected cases cannot train the surrogate
- [ ] surrogate can predict at least one engineering response
- [ ] uncertainty/domain status is shown
- [ ] prediction can be verified by launching a new real FEA case
- [ ] final explanation cites exact numerical evidence from the run

## First implementation increment

Do not begin with the full autonomous agent.

Implement the following thin slice first:

1. `SimulationIntentV1` JSON schema.
2. `SolverRunManifestV1` JSON schema.
3. `VerificationV1` JSON schema.
4. One hub-sprocket PMV project template.
5. One real baseline solve.
6. Parameter runner for gap.
7. Result extractor for peak stress, displacement and equilibrium.
8. Dataset table containing only verified cases.
9. Simple scalar surrogate for gap -> selected response.
10. PMV dashboard showing FEA truth vs surrogate prediction.

Once that loop works end-to-end, extend contact sophistication, adaptive meshing, field surrogates and autonomous model planning.

## North-star message

**AsterMax turns simulation from a sequence of software operations into an auditable engineering reasoning loop.**
