# WS03.2 Beam Connections — source/design acceptance contract

## Accepted workflow

1. Define two stable named selections for the reference and mobile beam ends.
2. Scope each end to vertices or edges evaluated against the active geometry signature.
3. Choose fixed, pinned, translational, rotational or generalized connection semantics.
4. Declare released translational/rotational degrees of freedom and, for generalized connections, optional non-negative elastic stiffness per degree of freedom.
5. Apply a finite connection offset when the connection point is eccentric to the scoped beam end.
6. Register the connection through the catalog, which enforces stable identifiers and unique names.

## Source/design rejection gates

- Empty IDs, names or end-selection IDs are rejected.
- The same named selection cannot be used at both ends.
- Stale, empty, face/body/node-based or overlapping end scopes are rejected.
- Unknown release flags, non-finite offsets, negative/non-finite stiffness and duplicate catalog entries are rejected.
- Fixed connections cannot release degrees of freedom.
- Pinned connections must release all rotations and no translations.
- Translational and rotational connections must release at least one matching degree of freedom.
- Only generalized connections may define elastic stiffness, and a degree of freedom cannot be both released and elastically restrained.

## Deferred runtime gate

Compilation and beam-element runtime validation remain provisional until aggregate roadmap progress reaches 50%. At that gate, representative fixed, pinned and generalized connection cases must be compiled and exercised before promotion to runtime-validated status.
