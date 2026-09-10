# C9.96 — CAD→Model Fidelity Lock

C9.96 closes a professional CAE integrity gap between STEP import and solve preparation: silent model drift.

The lock binds, in one deterministic SHA-256 fingerprint:
- source STEP SHA-256;
- resolved STEP unit state and scale-to-mm;
- geometry bounding box in mm and topology counts;
- mesh node/element counts and element family;
- material assignments;
- boundary conditions;
- loads.

A downstream mesh/solve contract must reproduce the same fingerprint. Any unit, geometry, mesh, material, BC or load change invalidates the lock and is rejected as `stale/model drift detected`.

## What this proves
It proves deterministic provenance continuity for supplied model metadata and blocks known classes of silent scale/model drift. It does not prove that the CAD kernel imported the B-Rep correctly, that topology counts came from a real importer, or that Code_Aster solved the model. Those remain separate evidence gates.

## Professional-demo significance
AsterMax should expose this as a visible `Model Integrity: VERIFIED` state and mark Solution stale immediately after any model mutation. This is a differentiator only if connected to native model events; C9.96 establishes the contract and automated rejection behavior first.

## Next priority
C9.97 should bind this lock into the native Windows GUI/import pipeline and generate geometry metadata from a real known-dimension STEP after import. Acceptance evidence must include bounding box, solids/faces/edges, selectable geometry, viewport fit, and a lock transition to stale when the model is edited.
