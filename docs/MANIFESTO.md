# AsterMax Engineering Manifesto

## Engineering first. Intelligence on top of evidence.

AsterMax is not intended to become merely another finite-element interface with an AI chat box attached to it.

The long-term objective is to build an engineering environment in which numerical mechanics, an explicit editable model, standards, solver evidence and artificial intelligence work together without hiding engineering decisions from the user.

The order matters:

> **AI proposes → the model is explicit → the engineer decides → the solver executes → benchmarks verify → AI interprets.**

AsterMax must earn physical trust before it earns autonomy.

---

## 1. The numerical core comes first

AsterMax must first become a dependable and testable mechanics platform.

Geometry, materials, meshing, constraints, loads, contacts, joints, remote conditions, solver formulations, reactions and result recovery must be implemented as deterministic engineering capabilities with known validation boundaries.

Compilation is not certification.

A feature is not considered physically functional because a dialog exists, because a model can be saved, or because a solver returns a number. A capability becomes trusted only when it survives analytical checks, numerical benchmarks, regression tests and adversarial review appropriate to its scope.

The AI layer must never be used to compensate for an incomplete or unverified physical formulation.

---

## 2. The analysis tree is the source of truth

The engineering model must always remain visible and manually editable.

A future AI agent may navigate the tree, create objects, configure boundary conditions, modify mesh controls, define load cases and inspect results, but it must operate through the same explicit model that the engineer can inspect and change.

The user must always be able to move between two equivalent modes of working:

- direct manual configuration through the analysis tree;
- natural-language engineering interaction through the AI agent.

Neither mode should create hidden physics.

AsterMax should preserve an auditable tree such as:

```text
Project
├─ Geometry
├─ Materials
├─ Connections
├─ Mesh
├─ Analysis
│  ├─ Supports
│  ├─ Loads
│  ├─ Remote Conditions
│  ├─ Contacts
│  └─ Load Cases
└─ Results
```

The AI may help construct that tree, but the tree remains inspectable, editable and authoritative.

---

## 3. Natural language must become an engineering specification, not a direct solver command

AsterMax should never use the unsafe path:

```text
Natural language → solver
```

The intended architecture is:

```text
Natural language
→ physical interpretation
→ explicit Model Specification
→ validation
→ visible analysis tree
→ engineer review or approval
→ solver execution
→ numerical verification
→ result interpretation
```

The intermediate Model Specification is essential. It converts a human engineering intention into structured mechanics before any numerical solve begins.

For example:

```text
AnalysisType: StaticStructural
Objective: Evaluate stress caused by excessive assembly gap

Materials:
  Hub: AISI 4340
  Segment: ASTM A572 Gr50

Connections:
  HubSegment: FrictionalContact
  BoltSet: Pretension

BoundaryConditions:
  BearingA: CylindricalSupport
  BearingB: RadialSupport

LoadCases:
  LC1: Nominal gap
  LC2: Measured gap
  LC3: Maximum plausible gap
```

If the AI misunderstood the user's sentence, the error must be visible here before it becomes a solver error.

---

## 4. The AI should reason about the physical phenomenon

The future AsterMax agent should not merely translate phrases into GUI clicks.

It should help the engineer decide what physical model is appropriate.

When the user describes a mechanical problem, the agent should be able to identify the objective, inspect the available geometry and model state, detect missing information, propose competing modelling assumptions and explain which decisions materially affect the answer.

Instead of silently creating a model, it should be able to say, in substance:

> The requested objective appears to be determining whether an assembly gap can produce a local stress concentration and crack initiation risk. A nonlinear contact model with bolt preload and several gap cases is more representative than a single bonded static solve. Two assumptions remain decisive: the hub-to-shaft interface and the actual preload state.

The agent should guide. The engineer should decide.

---

## 5. Boundary conditions are engineering hypotheses

Boundary conditions are among the most consequential choices in finite-element modelling.

AsterMax should treat them as explicit hypotheses rather than routine interface inputs.

The AI should help the user identify whether a support, remote condition, contact, joint, symmetry condition, preload, distributed load or other representation actually corresponds to the real load path.

It should also warn when a proposed boundary condition may artificially stiffen the model, suppress a relevant mode of deformation, create a singular system or generate a non-physical stress concentration.

The system must never hide these assumptions simply because it can automatically create them.

---

## 6. Fidelity should adapt to the engineer's available time

Engineering analysis is performed under real constraints.

AsterMax should eventually treat available time as an explicit modelling input.

A user who needs a screening answer in five minutes should not receive the same workflow as a user preparing a certification-quality analysis over several hours.

The future agent should be able to adapt:

```text
available time
→ required fidelity
→ computational cost
→ modelling strategy
→ verification depth
```

For a rapid screening case it may recommend a linearized model, a medium mesh and one conservative load case, while clearly labelling the limitations.

For a higher-confidence study it may propose mesh convergence, contact nonlinearity, material sensitivity, multiple load cases, parameter sweeps and stronger verification.

The AI must explain what accuracy is being traded for time.

---

## 7. The purpose of the analysis matters

AsterMax should distinguish between different engineering intents, including:

- preliminary design;
- troubleshooting;
- root-cause analysis;
- comparison of alternatives;
- optimization;
- verification;
- certification support.

The same geometry may require very different assumptions and evidence depending on the purpose of the study.

The agent should therefore reason not only about *what is being modelled*, but also *why it is being modelled*.

---

## 8. Standards must remain traceable to their source

A future standards-aware agent should be capable of reading an applicable engineering standard, identifying relevant clauses and translating them into explicit model requirements, load cases, combinations or result checks.

The chain must remain auditable:

```text
standard
→ applicable clause
→ engineering requirement
→ modelling assumption
→ load case or verification
→ numerical result
→ conclusion
```

AsterMax must clearly distinguish between:

- requirements directly derived from a cited standard;
- engineering assumptions needed to apply that requirement;
- additional cases recommended by the AI.

The AI must never present its own recommendation as if it were a normative requirement.

---

## 9. AI result interpretation must remain physics-aware

Post-processing should evolve beyond displaying contour plots and extrema.

The future agent should help the engineer interpret:

- load paths;
- deformation modes;
- stress concentrations;
- contact state;
- reaction balance;
- mesh sensitivity;
- convergence behaviour;
- singularities and numerical artefacts;
- suspicious boundary-condition effects;
- whether the requested result actually answers the engineering question.

It should be able to recommend the next useful analysis rather than merely restating the maximum von Mises stress.

Interpretation must always be grounded in solver data and explicit model information. The AI must not invent numerical evidence.

---

## 10. Manual control and AI control must coexist permanently

AI assistance must not remove the engineer's ability to directly configure the model.

Every AI action affecting the engineering model should be representable as an explicit change to the tree or Model Specification.

The ideal interaction is collaborative:

- the AI can build or modify the model;
- the user can inspect and change anything manually;
- the AI can explain the consequence of those changes;
- the solver remains deterministic;
- the final model remains reproducible.

AsterMax should not become a black box whose intelligence is inversely proportional to its transparency.

---

## 11. Multiphysics is a future extension of the same architecture

Structural mechanics is the first domain, not the final boundary.

A long-term AsterMax architecture may extend toward:

- advanced thermal analysis;
- nonlinear structural mechanics;
- dynamics and rotordynamics;
- computational fluid dynamics;
- conjugate heat transfer;
- fluid-structure interaction;
- additional coupled multiphysics workflows.

These disciplines should not require abandoning the core philosophy. They should extend the same explicit tree, semantic model, validation model and engineering-agent architecture.

A future project may therefore evolve toward:

```text
Project
├─ Geometry
├─ Materials
├─ Structural
│  ├─ Static
│  ├─ Modal
│  └─ Nonlinear
├─ Thermal
├─ CFD
│  ├─ Fluid Domain
│  ├─ Inlet
│  ├─ Outlet
│  └─ Turbulence Model
└─ Fluid-Structure Interaction
   ├─ CFD Solution
   ├─ Structural Solution
   └─ Coupling Interface
```

The solver technologies may evolve. The engineering contract should remain stable.

---

## 12. The agent must know the limits of the software

An intelligent engineering system must be able to say **no**, **not yet**, **insufficient information**, or **this assumption is not validated**.

AsterMax should maintain an explicit capability ledger separating:

- implemented;
- numerically validated;
- experimentally or externally validated where applicable;
- experimental;
- planned;
- unsupported.

The AI must consult that boundary before proposing or executing an analysis.

A capability should never become "supported" merely because an LLM knows how such a feature works in another FEA package.

---

## 13. Numerical evidence outranks agent confidence

AsterMax development follows a simple rule:

> **The agent that implements a capability does not certify it. Numerical evidence certifies it.**

The development loop should continue to emphasize:

```text
OBSERVE
→ SELECT BOTTLENECK
→ SPECIFY
→ IMPLEMENT
→ BUILD
→ REGRESSION
→ NUMERICAL VALIDATION
→ ADVERSARIAL TEST
→ REVIEW
→ MERGE
→ UPDATE CAPABILITY LEDGER
→ NEXT BOTTLENECK
```

The same principle applies to the future user-facing AI. Confidence, eloquence and automation are never substitutes for equilibrium, convergence, validation and physical consistency.

---

## 14. The engineer remains responsible for engineering judgement

AsterMax should make engineering reasoning more accessible, faster and more systematic, but it should not pretend to eliminate professional judgement.

The system should expose assumptions, uncertainty, limitations and alternatives so that the engineer can make a better decision.

The objective is not to remove the engineer from the process.

The objective is to give the engineer a computational partner capable of carrying more of the mechanical reasoning, repetitive configuration, verification and documentation burden while keeping the decisive assumptions visible.

---

# North Star

AsterMax aims to become an engineering environment where an AI agent understands the intended physical phenomenon, constructs and explains an explicit model, proposes appropriate boundary conditions and load cases, interprets standards with traceability, adapts modelling fidelity to the time available, operates a fully editable analysis tree and interprets authentic solver results.

But its governing principle remains unchanged:

> **No hidden physics. No invented evidence. No autonomy without validation.**

AsterMax should become more intelligent without becoming less auditable.
