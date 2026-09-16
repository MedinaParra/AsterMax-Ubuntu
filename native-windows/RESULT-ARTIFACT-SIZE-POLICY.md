# C10.20 result-artifact size policy

## Decision for P1 #5 / Phase 0.3

C10.20 deliberately retains `astermax-results-bundle/v0`, the streaming ASCII VTU writer at `%.15g`, and the complete coordinates/connectivity arrays in the JSON bundle. This branch does **not** reduce persisted floating-point precision to `.9g` and does **not** introduce a new v1 bundle/VTU reader path.

The decision is scope- and integrity-driven, not a claim that the current disk representation is optimal:

1. `.9g` would alter persisted geometry and result values. The existing numerical/regression evidence was produced with the current precision contract; changing it while the historical Windows GUI workflow remains unexercised would mix a storage-format change into the higher-priority conformance investigation.
2. VTK appended data encoded as base64 reduces numeric text expansion but adds base64's 4/3 encoding overhead and, by itself, does not remove the duplicate coordinates/connectivity still required by the v0 C# bundle reader.
3. Moving coordinates/connectivity out of JSON is the structurally cleaner long-term option, but it requires `astermax-results-bundle/v1` plus a tested C# VTU reader. That is a cross-format reader migration and is intentionally deferred until after the Windows end-to-end workflow gate is established.

## Explicit production envelope for the retained v0 format

For C10.20 the supported operational envelope is bounded to:

- at most **1,000,000 nodes**;
- at most **500,000 TETRA10 elements** (or another supported mix whose total connectivity is at most **5,000,000 element-node references**);
- at most approximately **1.5 GiB combined** for the generated JSON bundle plus VTU.

The disk estimate is intentionally conservative. Both artifacts currently persist roughly 14 nodal floating-point values per node (3 coordinates, 3 displacement components, total deformation, von Mises and 6 stress components) plus connectivity. With textual values bounded near the width of a 15-significant-digit scientific representation and delimiters, one million nodes plus five million connectivity entries remains below the stated combined envelope with margin for XML/JSON structure.

This is an **operational support boundary, not an automatically enforced hard limit** in the bridge. Exceeding it is unsupported for this release and must not be described as tested. A future v1 migration should remove geometry/connectivity duplication and establish new disk-size and reader-memory gates before increasing this envelope.

## Why this is acceptable in this branch

The Python bridge already writes JSON and VTU incrementally, so the previously demonstrated producer-side giant-string/tree memory failure is addressed. The remaining P1 #5 concern is disk duplication/size. C10.20 constrains that concern explicitly rather than changing two persisted formats immediately before the first native-Windows workflow-conformance run.
