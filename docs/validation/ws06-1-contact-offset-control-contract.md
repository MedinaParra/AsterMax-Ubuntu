# WS06.1 Contact Offset Control source/design contract

## Accepted capabilities

- Contact regions retain stable source and target face selections and explicit contact formulation, detection method and symmetry behavior.
- Initial-gap treatment is explicit: preserve the imported gap, apply a signed user-defined offset, or automatically adjust the interface to touch.
- User-defined offsets must be finite and non-zero and cannot be combined with automatic adjustment.
- Adjust-to-touch requires a finite positive maximum initial adjustment and cannot be combined with a user-defined offset.
- Optional penetration tolerance must be finite and positive.
- When a pinball radius is defined, user offset magnitude and maximum automatic adjustment must remain inside that search radius.
- Friction, penalty factor, pinball radius, source/target scoping and overlap rules remain deterministic and validated before solver translation.
- Unsupported enum values and null offset-control definitions are rejected before persistence or solver handoff.

## Deterministic rejection fixtures

1. Unsupported contact formulation, detection, symmetry or initial-gap treatment.
2. Preserve-gap mode combined with offset or automatic adjustment.
3. Missing, non-finite or zero user-defined offset.
4. User-defined offset combined with maximum automatic adjustment.
5. Missing, non-finite or non-positive AdjustToTouch maximum adjustment.
6. AdjustToTouch combined with a user-defined offset.
7. Non-positive or non-finite penetration tolerance.
8. Offset magnitude greater than the configured pinball radius.
9. Maximum automatic adjustment greater than the configured pinball radius.
10. Existing contact-domain failures: invalid friction, penalty, pinball, source/target scope or overlapping faces.

## Source evidence

`windows/AsterMax.MechanicalGui/ContactDomain.cs`

## Runtime boundary

This increment certifies the contact-offset model and validation contract only. It does **not** claim nonlinear contact solution support. Solver translation and benchmark validation remain required before contact offset can be marked runtime-complete.
