# WS02.3 Object Generator source contract

## Accepted workflow

The object generator represents a deterministic table-to-object transformation for supported Mechanical objects. Each definition has a stable identifier, object kind, typed columns and stable rows. Every generated object retains its source row identifier.

## Source-level acceptance

- `name` and `scopeId` are mandatory columns.
- Column keys and row identifiers are unique.
- Unknown row columns are rejected.
- Required values cannot be empty.
- Numeric values must parse as finite invariant-culture numbers.
- Boolean and identifier values are validated by declared type.
- Generated IDs are deterministic from generator and row IDs.
- Generated properties exclude identity and scope fields while preserving all other typed inputs.
- Invalid definitions fail explicitly rather than creating partial objects.

## Deferred runtime gate

Compilation, UI exercise, persistence round-trip and generated-object execution remain deferred until aggregate roadmap progress reaches 50%.
