# AsterMax C12.07 — native contact export repair

## Incident and scope

C12.06 can start the native Windows Code_Aster engine, but a model with multiple
contact zones can stop with `CONTACT2_16`: two zones use common real finite-element
nodes on their slave surfaces. The reported incident involved twelve common
nodes. The absence of a valid RMED file is a consequence of that solver failure.

This repair continues `agent/c1199-codeaster-contract-fix`. The engine remains
native Windows Code_Aster. Existing licenses, source notices, STEP import fixes,
and the installer downloaded directly from its original publisher are retained.

## Contact export

Before writing a solver deck, `AsterMaxContactTopology` checks the actual surface
connectivity against the exported mesh. It builds the restrictions on which side
of each pair may be the slave. A deterministic 2-SAT solution prefers original
roles in zone order and changes roles only when needed for a compatible global
assignment. Existing explicit orientation locks in a JSON contract are respected.

The export preserves every active pair, its two surfaces, all face and node IDs,
contact initialization, friction law and coefficient, loads, and supports. It
does not exclude shared nodes, delete active contacts, replace friction with a
bonded relation, or fabricate results. Inactive contacts are omitted and invalid
active contacts are rejected.

If no compatible assignment exists, or the two surfaces within one pair share
nodes, export stops before solver execution and identifies the relevant pairs
and nodes. The source model and original contract are not mutated.

The manifest records the original and exported roles in
`contact_orientation_report`, including names, one-based zone indices, changed
roles, original conflicts, and shared-node samples. Reversing master/slave roles
changes the numerical discretization of contact; preserving the physical law is
not a claim of identical numerical answers. Convergence and result validation
remain necessary.

Solution Information also names the reoriented pairs and explains this numerical
change so the audit is visible without opening a manifest file.

For static calculations with contacts, all solver increments remain active and
the result bridge receives the explicitly selected final state, `INST=1.0`.

## Failure handling

The packaged runner checks solver fatal markers before publishing any output.
A fatal `.mess` or process diagnostic is rejected even when the Windows launcher
returns zero or prints `DIAGNOSTIC JOB: OK`. Fatal solver evidence uses adapter
exit code 31; missing required files retain code 30. Failed output is kept in a
diagnostic subdirectory and cannot replace accepted results.

The adapter writes complete UTF-8 process logs and
`astermax-runner-diagnostic.json`. The application shows a concise Spanish
explanation with the contact names and a path to those records. Python's encoding
settings are limited to child processes; persistent user environment variables
are not changed.

## Validation gates

The Windows build requires:

- Compilation of the complete patch chain and the x64 application.
- Tests of the production C# topology planner and diagnostic methods.
- Native runner process regressions, including stale output and fatal evidence
  accompanied by a nonempty partial result file.
- The existing real TETRA4 solve and strict MED field validation.
- A new three-body contact benchmark whose original two slave surfaces share
  exactly twelve nodes. The original roles must reproduce `CONTACT2_16`; the
  corrected deck produced by the compiled application's exporter must solve with
  native Windows Code_Aster and pass independent MED and equilibrium checks.
- Integrity checks of the final ZIP and its packaged tools.

The workflow's audit and build manifest record the outcome. Unit-test fixtures
are never described as solver results. Interactive GUI use and the user's exact
project are separate from these automated checks and are not claimed as tested.

## References

- [Code_Aster U2.04.04, contact zones and master/slave selection, sections 2.1–2.2](https://code-aster.org/doc/v16/man_u/u2/u2.04.04.pdf).
- [Code_Aster U4.44.11, DEFI_CONTACT](https://code-aster.org/doc/v16/man_u/u4/u4.44.11.pdf).
- [Code_Aster 16.9.0, CONTACT2 message definitions](https://gitlab.com/codeaster/src/-/blob/16.9.0/code_aster/Messages/contact2.py).

The topology planner and diagnostic integration are project code. These
references establish solver requirements; no third-party implementation was
copied into the planner.
