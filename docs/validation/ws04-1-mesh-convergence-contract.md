# WS04.1 Mesh Convergence source/design contract

## Accepted workflow

1. Create a study with stable study and analysis identifiers.
2. Select total deformation, equivalent stress, maximum principal stress, strain energy or reaction force as the monitored quantity.
3. Select global element-size, scoped element-size or adaptive refinement.
4. Resolve scoped refinement through a current edge-, face- or body-based named selection when the mode is not global.
5. Record at least two ordered refinement points containing characteristic size, node count, element count and result value.
6. Require strictly decreasing characteristic size and strictly increasing node and element counts.
7. Evaluate convergence from consecutive relative result changes against an explicit tolerance and pass count.

## Rejected states

The source contract rejects empty or duplicate identifiers and names, unknown modes, invalid tolerances, missing scoped selections, stale geometry signatures, vertex-only refinement scopes, duplicate refinement sequences, non-finite results, non-decreasing element size, non-increasing mesh population and insufficient convergence points.

## Runtime gate

Compilation, solver execution and numerical benchmark comparison remain deferred until aggregate roadmap progress reaches 50%.
