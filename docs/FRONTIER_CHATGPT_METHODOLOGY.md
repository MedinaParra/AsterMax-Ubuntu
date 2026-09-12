# AsterMax Frontier Methodology for ChatGPT

## Purpose

AsterMax is developed with an evidence-driven autonomous engineering method. ChatGPT or any coding agent may reason, propose, implement and critique, but it does not get to declare its own work correct.

The system under test is the full agentic system:

`model + instructions + tools + repository context + harness + compute + evaluation budget + safeguards`.

## Four nested loops

### 1. Build Loop

Specification -> Architect -> Implementation -> Test Engineer -> Critic.

### 2. Evidence Loop

Every release-relevant claim must be connected to machine-checkable evidence: test output, benchmark output, static analysis, solver provenance, hash, or explicit human approval.

### 3. Validity Loop

A frozen evaluation suite probes failure modes that can make an apparently successful run misleading:

- reward hacking / test weakening
- scope escape
- evidence fabrication
- provenance loss
- evaluation contamination
- unsupported numerical claims
- silent fallback

The suite itself is hashed and treated as protected evidence.

### 4. Meta-Improvement Loop

The harness may propose improvements to itself, but a candidate harness is retained only if:

1. no mandatory evaluation regresses,
2. no protected policy/eval is weakened,
3. aggregate score improves by the configured minimum,
4. resource use stays inside the configured budget ratio,
5. a human still approves the merge.

Otherwise the candidate is rolled back.

## Frontier operating principle

> Agents generate hypotheses and artifacts. Deterministic systems generate measurements. Evidence gates decide admissibility. Humans retain authority over irreversible release decisions.

## Evidence graph

AsterMax records relationships between:

`Requirement -> WorkPackage -> Agent Task -> Change -> Test/Benchmark -> Artifact -> Claim -> Release Decision`.

A numerical or engineering claim without a path to machine evidence is an orphan claim and cannot support release.

## Evaluation budgets

Every significant WorkPackage can constrain:

- maximum agent turns,
- maximum tool calls,
- maximum retries,
- maximum wall-clock budget,
- optional cost budget.

This prevents a candidate from appearing better only because it consumed an unbounded amount of inference or retries.

## W2 policy

The Solver Bridge is the first frontier work package. It must prove both software correctness and numerical admissibility. A green unit-test suite alone is insufficient. A real numerical benchmark is mandatory before PASS.

## Non-negotiable rules

- Do not fabricate FEA fields.
- Do not relabel mocks or surrogate output as solver truth.
- Do not weaken a test, threshold, benchmark or eval to make a candidate pass.
- Do not allow the implementation agent to approve its own release.
- Do not modify frozen evals inside a feature WorkPackage.
- Do not retain a self-improved harness without baseline-vs-candidate evidence.
- Do not treat an LLM explanation as machine evidence.
