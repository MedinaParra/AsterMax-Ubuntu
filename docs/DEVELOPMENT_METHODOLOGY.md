# AsterMax Development Methodology

## Purpose

AsterMax is developed as a credibility-oriented engineering system. The development unit is not a feature; it is a **claim with an evidence contract**.

The methodology is informed by the separation of verification, validation, uncertainty and credibility used in computational mechanics and modeling/simulation practice, including ASME V&V 10, NAFEMS verification practice and NASA-STD-7009B / NASA-HDBK-7009B concepts. AsterMax does not claim compliance or certification to those standards unless a formal conformity activity is performed; they are used as methodological references.

## Required vocabulary

### Code verification
Question: **Are the implemented equations and algorithms solved correctly?**

Evidence examples:
- patch tests;
- rigid body modes;
- manufactured/exact solutions;
- independent benchmark problems;
- element formulation/unit tests;
- regression evidence.

### Solution verification
Question: **Is this particular numerical solution sufficiently resolved for the declared quantities of interest?**

Evidence examples:
- mesh/refinement studies;
- iterative residuals;
- discretization estimates;
- equilibrium/conservation;
- mesh quality;
- singularity diagnostics.

### Analytical corroboration
Question: **Does an independent classical/analytical/semi-analytical witness support the local or global numerical result within its applicability domain?**

This is not physical validation.

### Empirical corroboration
Question: **Does a documented empirical correlation support the result inside its encoded domain of applicability?**

Every empirical witness must carry source metadata, dimensional inputs, assumptions and domain limits. AsterMax must reject extrapolation outside that domain unless an explicitly separate research mode is used; research-mode extrapolation can never enable a production credibility claim.

### Cross-code corroboration
Question: **Does another independent implementation produce a compatible result?**

Cross-code agreement is useful evidence but is not automatically physical validation.

### Validation
Question: **Does the model represent physical reality adequately for the intended use?**

Validation evidence should be tied to experiments, measurements or other defensible physical observations, with their uncertainties and applicability documented.

### Uncertainty quantification
Question: **How sensitive is the quantity of interest to uncertain inputs, numerical error, measurement uncertainty and model-form assumptions?**

### Credibility for intended use
Question: **Is the accumulated evidence sufficient for the declared engineering decision and consequence level?**

AsterMax must not claim universal model credibility independent of intended use.

## Mandatory development pipeline

For every engineering capability:

1. **Engineering question** — state the decision the user is trying to make.
2. **Context of use** — define quantity/quantities of interest, consequence/criticality and acceptance criteria.
3. **Claim** — write the exact statement the software may eventually be allowed to make.
4. **Evidence contract** — list all prerequisites that must exist for that claim.
5. **Applicability contract** — define geometry, material, load, formulation and numerical domains in which the claim is meaningful.
6. **Failure conditions** — define missing/ambiguous/out-of-domain states that must block the claim.
7. **Independent oracle/test** — establish a reference that does not depend on the implementation under test wherever practical.
8. **Implementation** — write the minimum code required to satisfy the claim contract.
9. **Negative tests** — deliberately violate prerequisites and prove the claim remains blocked.
10. **Regression suite** — protect prior evidence and previously enabled claims.
11. **Exact Windows CI** — run deterministic tests on the target Windows environment.
12. **Evidence package** — persist source identity, inputs, solver identity, checks, outputs and hashes.
13. **Human review** — inspect assumptions, applicability and claim wording.
14. **Enable claim** — only deterministic ClaimEngine logic may change claim state.

## Architecture rule for AI

The AI is outside the trusted claim kernel.

```text
AI proposal
    |
    v
Deterministic engineering tool
    |
    v
Evidence record
    |
    v
ClaimEngine
    |
    +--> permitted claim
    |
    +--> blocked claim + reason
```

An agent may propose a material, surface, load, mesh refinement or analytical witness. It may not create the evidence state that proves its own proposal.

## Analytical Evidence methodology

Analytical witnesses are independent corroborators.

### Section-property path

For a CAD-derived section, compute numerically from the actual section geometry:
- area;
- centroid;
- second moments of area;
- product of inertia;
- principal axes.

Where torsion is involved, use only a torsion relation appropriate to the section and assumptions. Do not substitute polar second moment for the Saint-Venant torsion constant on arbitrary sections.

### Internal-resultant path

AsterMax should recover or independently define section resultants such as:
- axial force `N`;
- shear forces `Vy`, `Vz`;
- bending moments `My`, `Mz`;
- torque `T`.

The analytical witness reconstructs nominal/classical stress from those quantities and CAD section properties. Von Mises is then computed from the reconstructed stress tensor/components, rather than used as an independent primary equation.

### Empirical concentration path

Stress concentration correlations for shoulders, fillets, holes, keyways or similar details must be modeled as versioned witness definitions. Each definition includes:
- source/license status;
- equation/table/correlation identifier;
- interpolation method if applicable;
- dimensional ratios;
- valid range;
- nominal stress definition;
- load mode;
- uncertainty/fit metadata when available.

Do not copy proprietary handbook tables/charts into the codebase without appropriate rights. Prefer public/licensed sources or independently encoded correlations with documented provenance.

## Neighborhood Verification methodology

A point maximum is never sufficient evidence for local stress credibility.

For a selected feature/region:
1. define a geometric neighborhood independent of the mesh;
2. sample genuine integration-point or explicitly declared recovered fields;
3. compare several distances/sections against analytical witnesses where applicable;
4. repeat under controlled local refinement;
5. track maximum stress and finite-distance neighborhood quantities separately;
6. classify behavior such as `STABLE_FIELD`, `INSUFFICIENT_RESOLUTION`, `LIKELY_SINGULAR`, `OUTSIDE_WITNESS_DOMAIN`.

A diverging point maximum with a stabilizing finite-distance field must not be reported as a converged physical maximum.

## Evidence states

Use explicit states instead of ambiguous green/red labels:

- `VERIFIED`
- `USER_CONFIRMED`
- `DERIVED`
- `ASSUMED`
- `UNKNOWN`
- `NOT_APPLICABLE`
- `PASS`
- `FAIL`
- `BLOCKED`
- `NOT_ASSESSED`

Claim transitions must be deterministic and inspectable.

## Prohibited shortcuts

- no enabling claims from an LLM confidence score;
- no “validated” because two solvers agree;
- no “certified” because CI is green;
- no silent relaxation of tolerances after seeing a result;
- no cherry-picking mesh levels or comparison pairs based on favorable error;
- no nodal stress fabrication hidden behind visualization;
- no empirical correlation outside its applicability range;
- no automatic reuse of a prior material/load as verified evidence for a new model;
- no development branch that simultaneously adds new physics, new credibility logic and major UI changes unless required by the same claim gate.

## Branch/PR discipline

Prefer stacked, narrow PRs. Each PR body must state:
- claim unlocked;
- evidence contract;
- negative/fail-closed tests;
- exact head SHA;
- target-environment CI result;
- measured evidence only;
- limitations and explicitly blocked claims;
- next gate.

Never merge a draft automatically. The default for a new physics or credibility capability is `Draft` until exact target-platform evidence is green and reviewed.

## Periodic anti-drift audit

At each milestone, ask:
- Are we adding capability or adding credible decision support?
- Can every visible claim be traced backward to evidence?
- Is an assumption being displayed as if it were verified?
- Do we have an independent oracle for the core equations?
- Are validation and numerical verification still separated?
- Has the intended use changed?
- Are we expanding physics faster than verification coverage?

If the answer to the last question is yes, freeze new physics and increase verification coverage.
