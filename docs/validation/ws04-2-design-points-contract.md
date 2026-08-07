# WS04.2 Design Points acceptance contract

## Source workflow

1. Define stable input and output parameter identifiers, names and engineering units.
2. Create an ordered set of design points with deterministic identifiers and sequence values.
3. Require every design point to provide all input parameters.
4. Permit output values to be absent before evaluation and present after evaluation.
5. Reject unknown parameters, duplicate values, duplicate points and non-finite values.
6. Preserve the study-to-analysis relationship for project persistence and audit.

## Acceptance evidence

- Parameter roles are explicit and validated.
- Input and output parameter sets cannot be empty.
- Parameter identifiers and names are unique within a study.
- Point identifiers, names and sequences are unique within a study.
- Every point includes all required input parameters.
- Values reference only parameters owned by the study.
- Numeric values must be finite.

## Runtime gate

Compilation, persistence round-trip and parametric solve execution remain deferred until aggregate roadmap progress reaches 50%.
