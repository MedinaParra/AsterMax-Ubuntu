# WS02.4 Object Generator with Named Selections — source contract

## Accepted source workflow

1. Every object-generator row has exactly one stable named-selection binding.
2. Bindings cannot reference unknown rows and rows cannot remain unbound.
3. The named-selection catalog resolves each binding against the active geometry signature.
4. Stale or empty named selections fail before generated objects are returned.
5. Generated scope identifiers retain the named-selection UUID.
6. Generated properties retain the resolved entity count and geometry signature for deterministic audit.
7. Duplicate bindings and empty identifiers fail explicitly.

## Deferred runtime gate

Compilation, UI execution, serialization and end-to-end tutorial validation remain deferred until aggregate roadmap progress reaches 50%.
