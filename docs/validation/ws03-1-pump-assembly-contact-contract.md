# WS03.1 Pump assembly with contact — source contract

## Accepted workflow

A pump assembly contact model declares stable contact-region identifiers and binds each region to distinct face-based named selections for source and target surfaces. Both selections must resolve against the active geometry signature before the region is accepted.

The source model supports frictionless, frictional, bonded and no-separation formulations; asymmetric or symmetric behavior; explicit detection methods; normal penalty scaling; optional pinball radius; and an explicit initial-penetration policy.

## Deterministic rejection rules

Source/design validation rejects:

- empty or duplicate contact identifiers and names;
- absent, identical, stale or unknown source/target selections;
- non-face selection types;
- overlapping source and target face scopes;
- non-finite or non-positive penalty and pinball values;
- negative friction coefficients;
- frictional contact without positive friction;
- friction values supplied to non-frictional formulations.

## Deferred runtime acceptance

Compilation, assembly execution and nonlinear contact convergence checks remain deferred until aggregate roadmap progress reaches the 50% build gate.
