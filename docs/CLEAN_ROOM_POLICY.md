# AsterMax Clean-Room Engineering Policy

## Purpose
AsterMax is developed independently. The project must not contain proprietary third-party code, assets, documentation, confidential information, or implementation details obtained through reverse engineering.

This policy is an engineering-control document, not legal advice.

## Mandatory rules

1. **Independent implementation**
   - Implement functionality from public scientific literature, standards that may lawfully be used, open-source projects under compatible licenses, and original engineering work.
   - Similar end-user capability does not justify copying a third party's implementation, source code, binary behavior obtained through disassembly, or protected expressive assets.

2. **No reverse engineering of proprietary software for implementation extraction**
   - Do not decompile, disassemble, patch, instrument, scrape, or otherwise inspect proprietary binaries to recover algorithms, source structure, private file formats, hidden APIs, or implementation details unless a separate documented legal review explicitly authorizes a narrow activity.

3. **No proprietary assets**
   - Do not copy third-party icons, screenshots, manuals, tutorial text, sample projects, UI artwork, branding, or documentation into the repository.

4. **Neutral product design**
   - Describe AsterMax features in functional engineering terms.
   - Do not imitate another product's distinctive visual identity, branding, or presentation more closely than required for ordinary engineering usability.

5. **Provenance required for every material implementation input**
   - New modules, algorithms, numerical formulations, datasets, examples, icons, and generated code must have a traceable origin recorded in `docs/SOURCE_PROVENANCE.md` or an equivalent machine-readable record.

6. **Dependency licensing required**
   - Every direct runtime, build, solver, and packaging dependency must be listed in `docs/DEPENDENCY_REGISTER.md` with version, license, source URL, linking/integration mode, redistribution status, and review state.

7. **AI-generated code is not provenance-free**
   - AI-assisted contributions must be reviewed by a human or project agent against this policy.
   - Prompts must not request reconstruction of proprietary source code or confidential implementation details.
   - The contribution record should state the public references and project requirements used to validate the implementation.

8. **Benchmarks must be clean**
   - Prefer analytical solutions, published benchmark problems, standards-compliant public cases, or project-created models.
   - Comparative tests against commercial tools may report independently obtained outputs, but must not redistribute proprietary project files, screenshots, assets, or confidential material.

9. **Reject uncertain inputs**
   - If provenance or license status is unclear, the contribution remains quarantined and must not be merged into a release branch.

## Required pull-request checklist

Every PR that changes solver behavior, UI assets, dependencies, numerical formulations, import/export behavior, or benchmark data must answer:

- [ ] Is the implementation independently authored?
- [ ] Are all external technical sources recorded?
- [ ] Are all dependency licenses recorded and compatible with the intended distribution?
- [ ] Does the change avoid proprietary code, binaries, assets, manuals, screenshots, and confidential information?
- [ ] Does the UI use AsterMax-original naming, layout decisions, icons, and visual assets?
- [ ] Are numerical claims covered by reproducible tests or benchmarks?
- [ ] Are unsupported cases rejected explicitly rather than silently approximated?

## Release gate

A release is blocked when any of the following is true:

- dependency license is unknown;
- source provenance is missing for a material implementation;
- proprietary third-party material is present;
- a benchmark cannot be reproduced;
- solver output is represented as validated outside its documented scope;
- trademark or affiliation language could imply third-party sponsorship or endorsement.

## Escalation

When a contributor is uncertain whether an implementation source, license, benchmark, file format, visual element, or comparative claim is acceptable, stop the merge and open an `IP-review` issue describing only non-confidential facts and the proposed technical alternative.
