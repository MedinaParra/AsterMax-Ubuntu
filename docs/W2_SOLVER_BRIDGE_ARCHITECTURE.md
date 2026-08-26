# W2 Solver Bridge — Architecture Boundary

Status: first H1/H2 thin slice. No Code_Aster execution is implemented by this document or commit.

## Purpose

W2 creates a deterministic evidence boundary between AsterMax and any external solver. Agents may prepare a request or interpret validated results, but only a solver adapter may execute backend work and only the bridge may promote returned files to solver evidence.

## Contracts

- `SolverModelV1` — versioned description of the prepared model package and the capabilities it requires.
- `SolverRequestV1` — binds one model to one backend, run id and requested result fields.
- `SolverRunManifestV1` — records backend identity/version, worker identity, timestamps, termination, logs and SHA-256/size for inputs and outputs.
- `SolverResultV1` — references field/reaction artifacts and is cryptographically linked to the validated manifest.
- `SolverCapabilityV1` — advertises the analysis capabilities and result fields a backend can actually supply.

The JSON Schemas under `contracts/Solver*.schema.json` are generated from the same Pydantic shapes used at runtime.

## Fail-closed rules

1. Backend mismatch rejects before execution.
2. Missing required capability rejects before execution.
3. Unsupported requested field rejects before execution.
4. A `SUCCEEDED` manifest without output artifacts is invalid.
5. Request, manifest and result identities must match.
6. Returned paths cannot escape the run directory.
7. Every accepted artifact must exist and match declared SHA-256 and byte size.
8. Every result field must reference an artifact declared by the solver manifest.
9. A result must contain the hash of the exact validated manifest.
10. Failed/cancelled solver termination is never promoted to valid solver evidence.

## Deliberate boundary

The tests in this slice use `StubAdapter` only to test contracts and fail-closed behavior. The stub cannot execute a solver and its test bytes are not FEA results. No numerical result is claimed by this slice.

## Next slice

Implement `CodeAsterWSL2Adapter` as a process worker that:

1. materializes the exact request package into an isolated run directory;
2. invokes a pinned Code_Aster environment through the Windows/WSL2 bridge;
3. captures stdout/stderr and solver version;
4. hashes all inputs and outputs;
5. emits `SolverRunManifestV1`;
6. parses only authentic returned field artifacts into `SolverResultV1`;
7. fails closed on missing, malformed or unsupported output;
8. proves the implemented path with a reference numerical benchmark before W2 can receive PASS.

The numerical benchmark gate intentionally remains unsatisfied after this architecture slice.
