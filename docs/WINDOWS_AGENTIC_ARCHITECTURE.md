# AsterMax Windows — Agentic Architecture

## Goal

Build AsterMax for Windows as an engineering-orchestration product, not as a chatbot wrapped around an FEA solver.

The system must transform an engineering question into an auditable simulation workflow, execute real physics, verify the evidence, learn only from accepted runs, and explain the result without fabricating data.

## Windows product architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ AsterMax Windows Desktop                                  │
│ PySide6/Qt + VTK                                          │
│ Ribbon | Outline | 3D View | Reasoning | Evidence Timeline│
└───────────────────────┬─────────────────────────────────────┘
                        │ typed commands/events
                        v
┌─────────────────────────────────────────────────────────────┐
│ Agentic Orchestrator                                      │
│ Python asyncio + deterministic state machine              │
│ Job Store + Evidence Store + Policy Engine                │
└─────────────┬───────────────┬───────────────┬───────────────┘
              │               │               │
              v               v               v
     Engineering Agents   Deterministic     Solver Router
                          Services
              │               │               │
              │               │        ┌──────┴──────────────┐
              │               │        │                     │
              │               │        v                     v
              │               │  Native Windows        WSL2/Docker
              │               │  Internal Solver       Code_Aster
              │               │        │                     │
              │               │        └─────────┬───────────┘
              │               │                  │
              │               │                  v
              │               │          SolverResultV1
              │               │                  │
              └───────────────┴──────────────────┘
                                 │
                                 v
                         Verification Gate
                                 │
                          REJECT / ACCEPT
                                 │
                                 v
                         Validated Dataset
                                 │
                                 v
                          Surrogate Layer

Future adapter: PyAnsys / Ansys Mechanical
```

## Platform decision

### Native Windows layer

Run natively on Windows:

- Desktop UI
- project management
- STEP/IGES/BREP import and visualization
- VTK postprocessing
- agent orchestrator
- local database
- deterministic validators
- internal linear solver
- surrogate inference/training when practical
- future PyAnsys adapter

### Linux solver worker

Run Code_Aster in a reproducible Linux environment through WSL2/Docker.

The Windows app must treat this as a worker, never as part of the UI. Communication is through explicit job directories/manifests and result contracts.

This gives AsterMax a clean Windows experience while preserving a Linux-native path for advanced Code_Aster physics.

## Fundamental rule: agents propose, deterministic services prove

An LLM/agent may:

- interpret intent
- propose a model plan
- identify missing information
- rank candidate assumptions
- propose mesh strategies
- choose among declared solver capabilities
- explain verified numerical evidence
- plan the next experiment

An LLM/agent may not:

- fabricate a field
- create a numerical result without a solver
- declare equilibrium passed
- declare mesh convergence passed
- silently simplify unsupported physics
- silently invent material properties
- silently invent loads, contacts or supports
- promote a surrogate result to FEA truth

Pass/fail decisions are made by deterministic validators operating on artifacts.

# Agent topology

## A0 — Supervisor / Engineering Conductor

Purpose: control workflow state and delegate bounded tasks.

Inputs:
- SimulationIntentV1
- current project state
- agent capability registry
- verification status

Outputs:
- AgentTaskV1 jobs
- ordered execution plan
- explicit stop/escalation conditions

Rules:
- cannot bypass a required gate
- cannot accept its own result
- every delegated task has bounded inputs/outputs
- each plan step references a capability and acceptance criterion

## A1 — Intent Agent

Purpose: turn natural-language engineering intent into structured requirements.

Produces:
- problem statement
- target physics
- requested outputs
- known parameters
- unknowns
- assumptions requiring confirmation
- target evidence

The output is never a solver file. It is a typed intent contract.

## A2 — Geometry Agent

Purpose: inspect and classify geometry for simulation.

Produces:
- body inventory
- candidate interfaces
- geometric parameters
- named regions
- gap/clearance candidates
- geometry health findings

Uses deterministic geometry services for dimensions, topology and healing.

## A3 — Physics Agent

Purpose: propose the physical model.

Produces candidates for:
- materials
- contact definitions
- friction assumptions
- supports
- loads
- symmetry
- analysis type
- nonlinear requirements

Each property has provenance and confidence/state: Confirmed, Inferred, Missing, Rejected.

## A4 — Mesh Agent

Purpose: create a meshing plan, not to invent convergence.

Produces:
- global element size
- local refinements
- contact-zone refinement
- element family
- quality targets
- convergence plan

Actual mesh metrics are created by the mesher and checked deterministically.

## A5 — Solver Router Agent

Purpose: map required physics to an available backend.

Candidate backends:
- AsterMax Internal Solver
- Code_Aster Worker
- future Ansys/PyAnsys Worker

It must reject a route when capabilities do not cover required physics.

## A6 — Solver Execution Worker

Not an LLM.

Purpose:
- execute exact generated solver input
- capture stdout/stderr
- collect fields
- preserve solver version
- calculate hashes
- produce SolverRunManifestV1 + SolverResultV1

## A7 — Verification Agent

Purpose: interpret deterministic verification findings and decide next actions.

It does not calculate pass/fail values itself.

Deterministic Verification Gate checks:
- solver termination
- unsupported feature detection
- force balance
- moment balance
- mesh-quality thresholds
- field presence
- convergence evidence
- suspicious singularity/hotspot conditions
- hash/provenance completeness

Outputs:
- ACCEPT
- REJECT
- RETRY_WITH_REFINEMENT
- REQUEST_ENGINEER_INPUT

## A8 — Results Agent

Purpose: turn accepted result data into engineering observations.

Can report:
- hotspot location
- peak/min values
- scoped statistics
- deformation behavior
- contact redistribution
- comparisons between runs

Every statement must cite a result artifact or deterministic calculation.

## A9 — Experiment Agent

Purpose: design and run parametric exploration.

For the hub-sprocket PMV:
- gap sweep
- torque/load sweep
- optional friction sweep
- adaptive refinement around transitions

It schedules independent SolverRun jobs and only sends ACCEPT cases to the dataset.

## A10 — Surrogate Agent

Purpose: train/select a surrogate from validated cases.

Responsibilities:
- dataset eligibility check
- train/validation split
- model selection
- error metrics
- uncertainty/domain assessment
- model provenance

Outputs are always labelled AI Prediction, never FEA Result.

## A11 — RCA / Mechanical Reasoning Agent

Purpose: synthesize causal evidence.

For each conclusion it must distinguish:
- observation
- numerical evidence
- engineering inference
- hypothesis
- unresolved uncertainty

It can build:
- 5 Why chain
- Ishikawa candidate structure
- sensitivity-based cause ranking
- next-test recommendation

It cannot claim physical causality solely from correlation in a parameter sweep.

## A12 — Report / Evidence Agent

Purpose: generate a traceable engineering package.

Includes:
- model assumptions
- geometry/configuration
- solver provenance
- mesh evidence
- verification evidence
- accepted/rejected cases
- response plots
- surrogate metrics
- RCA conclusion
- unresolved assumptions

# Orchestration model

## State machine

```text
NEW
 -> INTENT_STRUCTURED
 -> GEOMETRY_READY
 -> PHYSICS_PROPOSED
 -> MODEL_REVIEW
 -> MESH_READY
 -> SOLVER_READY
 -> SOLVING
 -> VERIFYING
 -> REJECTED | ACCEPTED

ACCEPTED
 -> EXPERIMENTING
 -> DATASET_READY
 -> SURROGATE_READY
 -> RCA_READY
 -> REPORT_READY
```

No agent may jump states.

## Agent execution pattern

Every agent follows:

```text
1. Read bounded input artifacts
2. Produce structured proposal
3. Run deterministic checks where applicable
4. Attach evidence/provenance
5. Return status
6. Supervisor decides next transition
```

## Human-in-the-loop checkpoints

Required confirmation for the PMV when:

- a material value is inferred rather than supplied
- a contact/friction model materially affects the result
- a load/support is inferred
- geometry healing changes topology
- the solver router proposes a physics simplification
- verification identifies a likely singularity
- the surrogate is asked to extrapolate outside its validated domain

The user can approve, edit or reject the proposal.

# Data and evidence architecture

## Local project layout

```text
project.astermax/
  project.json
  geometry/
  intent/
  model/
  mesh/
  runs/
    run_<uuid>/
      input/
      output/
      manifest.json
      verification.json
      logs/
  dataset/
  surrogate/
  reports/
  audit/
```

## Local database

Use SQLite initially.

Tables:
- projects
- artifacts
- agent_runs
- solver_runs
- verification_checks
- dataset_cases
- surrogate_models
- decisions

Large mesh/result files remain file artifacts; SQLite stores metadata, hashes, status and links.

# Agent runtime

## Recommended PMV implementation

- Python 3.12+
- PySide6 / Qt for Windows desktop
- VTK for 3D visualization
- asyncio for orchestration
- Pydantic for contracts
- SQLite for state/audit
- Gmsh for meshing
- NumPy/SciPy for deterministic calculations and internal solver
- scikit-learn initially for scalar surrogate
- optional PyTorch later for field surrogates
- WSL2/Docker worker for Code_Aster
- future PyAnsys adapter on Windows

Avoid introducing Kubernetes, message brokers or distributed microservices in the PMV.

# Windows process boundaries

```text
AsterMax.exe
  ├─ UI Process
  ├─ Orchestrator Process
  ├─ Geometry/Mesh Worker
  ├─ Internal Solver Worker
  ├─ Surrogate Worker
  └─ Solver Bridge
       ├─ WSL2/Docker -> Code_Aster
       └─ Future native Windows -> PyAnsys
```

Long-running solver or surrogate tasks must never freeze the UI.

# IPC strategy

PMV:
- local subprocesses
- JSON task/result envelopes
- temporary/job directories
- stdout/stderr capture

Later:
- localhost gRPC or named pipes if stronger process isolation is required

Do not expose an internet-facing local API by default.

# AgentTaskV1

Every task must contain:

- task_id
- project_id
- agent_id
- objective
- allowed_inputs
- expected_output_contract
- acceptance_criteria
- prohibited_actions
- created_at
- parent_task_id

Every result must contain:

- task_id
- status
- output_artifacts
- evidence_refs
- assumptions
- warnings
- deterministic_checks
- model/provider metadata when an AI model was used

# Trust model

AsterMax should visibly separate four classes of information:

1. USER INPUT
2. AGENT PROPOSAL
3. DETERMINISTIC CALCULATION
4. SOLVER RESULT
5. SURROGATE PREDICTION

The UI must use badges/icons/status to prevent these categories from being confused.

# Hub-sprocket PMV agent flow

```text
User question
  -> A1 Intent
  -> A2 Geometry
  -> A3 Physics
  -> Human review of uncertain assumptions
  -> A4 Mesh
  -> A5 Solver Router
  -> A6 Code_Aster solve
  -> deterministic Verification Gate
  -> A7 verification reasoning
  -> ACCEPT baseline
  -> A9 gap DOE
  -> verification per run
  -> validated dataset
  -> A10 surrogate
  -> slider prediction
  -> Verify with FEA
  -> compare prediction vs truth
  -> A11 RCA
  -> A12 evidence report
```

# Build phases

## Phase W0 — Windows shell

Deliver:
- app launches on Windows
- project open/save
- VTK viewport
- Outline / Details / Reasoning / Evidence panels
- background-task execution

Exit criterion: UI remains responsive while a dummy worker runs.

## Phase W1 — Agent contracts and state engine

Deliver:
- Pydantic contracts
- SQLite audit store
- state-machine orchestrator
- agent registry
- task/result envelopes

Exit criterion: a mocked project can traverse states with full audit history.

## Phase W2 — Real baseline FEA

Deliver:
- geometry import
- material/BC scoping
- mesh
- solver bridge
- Code_Aster baseline solve
- result ingestion

Exit criterion: authentic fields render on Windows.

## Phase W3 — Verification Gate

Deliver:
- equilibrium
- mesh quality
- provenance/hash checks
- convergence workflow
- reject/accept states

Exit criterion: a bad case is rejected automatically and cannot become dataset evidence.

## Phase W4 — Gap experiment engine

Deliver:
- gap parameter
- design points
- queued solver runs
- run comparison
- hotspot tracking

Exit criterion: multiple verified gap cases can be compared reproducibly.

## Phase W5 — Surrogate loop

Deliver:
- validated dataset only
- scalar surrogate
- uncertainty/domain indicator
- Verify with FEA action

Exit criterion: predicted response can be checked against a fresh physical solve.

## Phase W6 — Mechanical RCA

Deliver:
- evidence-linked observations
- sensitivity ranking
- 5 Why / Ishikawa hypothesis structure
- unresolved-uncertainty list

Exit criterion: no numerical statement exists without a source artifact.

## Phase W7 — Future Ansys adapter

Deliver interface only first:
- backend capability descriptor
- SolverModelV1 mapping
- SolverResultV1 mapping

Then implement PyAnsys adapter in a separate integration increment.

# Coding-agent development process

The software itself should also be built agentically.

For every feature:

```text
SPEC AGENT
  -> writes/updates acceptance contract

IMPLEMENTATION AGENT
  -> changes only scoped modules

TEST AGENT
  -> unit + contract + regression tests

SIMULATION VALIDATION AGENT
  -> runs analytical benchmark where physics changed

REVIEW AGENT
  -> checks architecture, numerical credibility and scope

HUMAN MERGE GATE
  -> merge only when evidence is present
```

No coding agent may both implement and self-approve a numerical feature.

# Definition of Done for any simulation feature

A feature is not done because the UI works.

It is done only if:

- contract/schema exists
- unit tests pass
- unsupported paths fail explicitly
- numerical benchmark exists when physics changes
- artifact provenance is recorded
- deterministic verification is implemented
- UI labels evidence class correctly
- regression case is saved
- documentation states validation boundary

# North-star architecture

The product is not a chain of autonomous LLMs improvising an FEA model.

It is a controlled engineering state machine in which specialized agents propose bounded actions, deterministic services perform measurable work, physical solvers generate truth, and verification gates decide what evidence is trustworthy.
