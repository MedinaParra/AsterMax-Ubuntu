# Intellectual-property and clean-source policy

This policy is a mandatory development rule for AsterMax. Its purpose is to preserve a legally clean provenance trail while allowing AsterMax to provide efficient, familiar CAD/CAE workflows.

## 1. Independent implementation rule

AsterMax features must be implemented from one or more of the following permitted sources:

- the contributor's own engineering knowledge and experience;
- public standards, textbooks, scientific papers, and public-domain material;
- documentation that is lawfully available for reference;
- behavior observed while lawfully using software, where using that behavior as a functional requirement is lawful;
- source code and assets whose licenses are compatible with the intended AsterMax distribution;
- original specifications, tests, benchmark problems, and designs created for AsterMax.

A remembered workflow may be written down as a functional requirement. The implementation must still be independently designed and coded.

### Public internet references

Material found through Google, YouTube, forums, blogs, documentation sites, social networks, conference talks, or other publicly accessible sources may be used to learn facts, concepts, workflows, terminology, and observable behavior. **Public availability is not treated as a license to copy, adapt, redistribute, or embed the material.**

Before importing any third-party code, image, icon, model, drawing, text, dataset, binary, tutorial asset, transcript, audio, or video content, identify the original source and the actual license or permission that authorizes the intended use.

For publicly demonstrated product behavior, the preferred AsterMax workflow is:

`reference -> functional requirement -> independent design -> original/cleared implementation -> validation`

See `docs/PUBLIC_REFERENCE_PROVENANCE.md`.

## 2. Prohibited inputs

Do not add or use as implementation source material:

- proprietary source code obtained without an express right to reuse it;
- decompiled, disassembled, decoded, or otherwise extracted proprietary implementation code;
- copied proprietary icons, screenshots, graphics, manuals, help pages, tutorial media, templates, example files, databases, or UI resources;
- confidential customer, employer, partner, or vendor information without authorization;
- leaked, pirated, cracked, or access-controlled material;
- code or assets whose license or provenance cannot be established.

Reverse engineering of proprietary software must not be performed for AsterMax unless a separate, documented legal review first establishes that the proposed activity and use of the resulting information are permitted. AsterMax does not require reverse engineering of ANSYS or SOLIDWORKS to implement familiar engineering workflows.

## 3. User-interface independence

Familiar interaction patterns may be used when they are functional or conventional, but AsterMax must maintain its own visual identity. Do not deliberately reproduce another vendor's distinctive trade dress, including a pixel-identical layout, proprietary icon set, logos, distinctive color system, splash screens, or branded artwork.

UI requirements should be expressed functionally, for example:

- "feature history/tree remains visible while editing geometry";
- "a static structural analysis exposes materials, interactions, mesh, constraints, loads, solve status, and results in a predictable hierarchy";
- "common commands are reachable with minimal context switching".

Do not specify: "copy screen X exactly".

## 4. Third-party code and assets

Every imported dependency, source fragment, binary, model, icon set, font, mesh tool, solver, or data file must have:

1. a known source/provenance;
2. a known version or commit when practical;
3. a license or written permission compatible with the intended use;
4. required copyright/license notices preserved;
5. an entry in `THIRD_PARTY_NOTICES.md` when distributed with AsterMax.

If any of these is unknown, the item is **not cleared for redistribution**.

A URL found in Google or a video being publicly viewable on YouTube is not, by itself, evidence of reuse permission.

## 5. Copyleft boundary

AsterMax is historically a native derivative of the GPLv3 PrePoMax codebase. Code that forms part of that derivative must remain compliant with the GNU GPL version 3 when conveyed. Do not represent derivative PrePoMax code as proprietary or closed-source.

Future modules that are intended to have a different licensing model must be designed as genuinely separate works with a documented process/API boundary and must receive a license review before distribution. Merely placing code in another folder does not create a licensing boundary.

## 6. Solver boundary

Where practical, solver integrations should use documented files, command-line/process boundaries, or documented APIs. This makes technical provenance clearer and allows each solver/runtime to retain its own license terms. Bundling a solver does not automatically make every bundled component legally cleared; exact package licenses must still be reviewed.

## 7. Patent and standards review

Common engineering workflows are not assumed to be patent-free. Before commercializing a distinctive algorithm, proprietary file-format implementation, optimization method, specialized solver technique, or other nontrivial technical feature, perform a targeted patent/licensing review. Prefer published standards and independently implemented open specifications when available.

## 8. Trademarks and product names

Use third-party product names only when reasonably necessary to identify interoperability, compatibility, testing, migration, or comparison. Do not imply affiliation or endorsement. Do not use third-party logos in AsterMax branding.

Marketing should describe AsterMax capabilities in AsterMax terms rather than presenting the product as an "ANSYS clone" or "SOLIDWORKS clone".

## 9. AI-assisted contributions

AI-assisted code is subject to exactly the same provenance rules. Do not provide proprietary source code, confidential material, or restricted assets to an AI system for the purpose of recreating a protected implementation. Generated output must be reviewed for license, provenance, security, and technical correctness before merge.

Public tutorials, videos, screenshots, or snippets supplied to an AI system remain subject to their original rights and licenses. AI assistance does not convert restricted third-party material into cleared AsterMax material.

## 10. Contributor declaration

By submitting a contribution, a contributor confirms that they have the right to submit it, that known third-party material is identified, and that the contribution is intentionally offered under the repository's applicable license. Employer or client ownership obligations must be resolved by the contributor before submission.

## 11. Release gate

A public or commercial binary release must not be promoted until the release owner has completed `docs/COMMERCIAL_RELEASE_CHECKLIST.md` and any unresolved third-party item is either cleared, removed, or replaced.
