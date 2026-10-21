# Commercial/public release legal checklist

Complete this checklist before publishing or commercially deploying a binary distribution. Keep the completed record with the release evidence.

## A. Source and license

- [ ] Release commit/tag identified.
- [ ] Root `LICENSE` included in source and binary distribution where required.
- [ ] Corresponding source for GPL-covered binaries is available by a compliant delivery method.
- [ ] Modified upstream files retain required notices and modification history.
- [ ] No source file has an unexplained or incompatible license header.

## B. Third-party inventory

- [ ] SBOM generated for source packages, binaries, NuGet/native libraries, solvers, meshers, CAD importers, and runtime assets.
- [ ] Every distributed component has exact version/provenance recorded.
- [ ] Every distributed component has license text/notices packaged as required.
- [ ] Items marked `VERIFY BEFORE REDISTRIBUTION` in `THIRD_PARTY_NOTICES.md` are resolved.
- [ ] No proprietary SDK/runtime is bundled without written redistribution rights.

## C. Copyright / clean source

- [ ] No proprietary source code, decompiled code, leaked code, copied icons, manuals, screenshots, tutorial media, or restricted sample files are present.
- [ ] Significant externally inspired features have a documented functional requirement and independent implementation history.
- [ ] Public references discovered through Google, YouTube, forums, blogs, documentation, or product demonstrations were treated as knowledge/behavior references unless an actual reuse license or permission is recorded.
- [ ] Any code/assets copied or adapted from public internet sources have original-source provenance and a license/permission compatible with the release.
- [ ] No file is treated as reusable merely because it was publicly accessible or indexed by a search engine.
- [ ] Contributor rights/sign-offs are present for material contributions.
- [ ] Employer/client ownership issues are resolved for contributors whose agreements may claim the work.

## D. Trademark / UI identity

- [ ] Product name and logo do not include third-party marks.
- [ ] UI uses AsterMax-owned/licensed icons, colors, graphics, and layout decisions.
- [ ] Comparative references are factual and do not imply endorsement.
- [ ] Major commercial launch has received a trademark clearance search for the AsterMax name/logo.

## E. Patent / interoperability

- [ ] Distinctive new algorithms and nontrivial proprietary-file-format work have been reviewed for patent/license risk when commercially material.
- [ ] Interoperability claims have reproducible tests and do not require unauthorized proprietary components.
- [ ] Any reverse-engineering activity, if ever proposed, has a documented legal approval before work begins.

## F. Engineering claims

- [ ] Release notes distinguish software test PASS from engineering validation/certification.
- [ ] Numerical benchmarks, mesh/convergence evidence, solver versions, and model assumptions are traceable.
- [ ] Marketing does not claim universal equivalence to, certification by, or affiliation with a proprietary vendor.

## G. Security and distribution

- [ ] Distributed binaries are built from the tagged source using a traceable build process.
- [ ] Release artifacts are checksummed/signed where available.
- [ ] Known critical dependency vulnerabilities have been reviewed.
- [ ] License/notice files remain accessible from the distribution.

A release with an unresolved red item is not legally cleared merely because it builds or passes numerical tests.
