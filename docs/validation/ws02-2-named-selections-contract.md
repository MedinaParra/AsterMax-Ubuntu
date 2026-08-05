# WS02.2 Named Selections — source/design acceptance contract

## Accepted workflow

A named selection has a stable identifier, unique name, declared entity type and either a manual scope or a worksheet definition. Manual selections contain exactly one entity class. Worksheet selections contain one or more finite criteria joined by explicit Boolean operators.

Evaluation records the resolved scope, active geometry signature and evaluation timestamp. Consumers resolve a named selection only when its recorded geometry signature matches the active model and its evaluated scope is non-empty.

## Required rejection behavior

The source model rejects empty identifiers or names, duplicate identifiers or names, empty manual scopes, mixed entity classes, worksheet selections without criteria, non-finite criterion values, invalid Between bounds, stale geometry signatures and empty evaluated scopes.

## Persistence and downstream use

Stable IDs are the contract for load, support, mesh-control, contact and result scoping. Geometry changes invalidate resolved scopes through signature mismatch rather than silently reusing obsolete entity IDs.

## Deferred runtime gate

Runtime validation remains deferred until aggregate roadmap progress reaches 50%. At that gate, acceptance must exercise manual and worksheet creation, stale-scope rejection, persistence round-trip and downstream scope resolution.
