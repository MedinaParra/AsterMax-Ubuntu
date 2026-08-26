# AsterMax Source & Implementation Provenance

This register records the origin of material technical inputs used to design, implement, validate, or document AsterMax.

## Entry template

Copy this block for every material algorithm, numerical formulation, benchmark, dataset, file-format implementation, UI asset set, or externally informed subsystem.

### PROV-XXXX — Short title

- **Subsystem:**
- **Change / module:**
- **Author / agent:**
- **Date:**
- **Implementation status:** proposed / implemented / validated / released
- **Source type:** original derivation / public literature / open-source reference / public standard / analytical benchmark / project-created data
- **Public references:**
  - title, author/organization, edition/version, stable URL/DOI if applicable
- **Open-source references inspected:**
  - repository, exact commit/tag, file paths inspected, license
- **What was learned from the source:**
- **What was independently implemented:**
- **Code copied verbatim:** none / identify permitted licensed excerpt and justification
- **Proprietary software inspected for implementation details:** no
- **Validation evidence:**
- **Related tests:**
- **Related ADR / issue / PR:**
- **Reviewer:**
- **Review outcome:** pending / accepted / quarantined

---

## Initial provenance boundaries

### PROV-0001 — Minimum linear static solver scope

- **Subsystem:** internal solver
- **Change / module:** TET4 linear-elastic static workflow described by the current project README
- **Author / agent:** AsterMax project
- **Date:** 2026-08-25
- **Implementation status:** provenance review pending
- **Source type:** project implementation requiring reconstruction of explicit public references
- **Public references:** TBD before release
- **Open-source references inspected:** TBD
- **What was learned from the source:** TBD
- **What was independently implemented:** sparse linear solution workflow, element assembly, loads, supports, result fields, equilibrium checks as applicable to actual code
- **Code copied verbatim:** none claimed; must be verified against repository contents when code is added
- **Proprietary software inspected for implementation details:** no permitted source under project policy
- **Validation evidence:** analytical cantilever/reference evidence to be attached when implementation is present
- **Related tests:** TBD
- **Related ADR / issue / PR:** clean-room governance bootstrap
- **Reviewer:** pending
- **Review outcome:** pending

### PROV-0002 — Product workflow and user experience

- **Subsystem:** desktop UI / workflow
- **Change / module:** model tree, properties, graphics viewport, setup and results workflow
- **Author / agent:** AsterMax project
- **Date:** 2026-08-25
- **Implementation status:** design boundary established
- **Source type:** original product design informed by generic CAE/FEM workflows
- **Public references:** TBD as concrete design decisions are made
- **Open-source references inspected:** TBD
- **What was learned from the source:** generic CAE concepts only
- **What was independently implemented:** AsterMax-specific information architecture, terminology, visual system, icons and interaction patterns
- **Code copied verbatim:** none
- **Proprietary software inspected for implementation details:** no
- **Validation evidence:** usability and workflow acceptance tests to be added
- **Related tests:** TBD
- **Related ADR / issue / PR:** clean-room governance bootstrap
- **Reviewer:** pending
- **Review outcome:** pending

## Rules

- A URL alone is not sufficient provenance: record what was used and how it influenced the implementation.
- Never paste proprietary manual text, screenshots, decompiled output, confidential files, or private implementation notes into this register.
- Where an open-source implementation is studied, pin the exact commit/tag and license.
- Analytical and numerical validation must be separated from provenance: a result can be numerically correct and still have unacceptable provenance.
- Any entry with unresolved provenance remains `quarantined` and cannot enter a production release.
