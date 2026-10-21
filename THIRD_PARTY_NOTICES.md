# Third-party notices and provenance register

This file is a release-oriented provenance register, not a substitute for the license text shipped with each component. Entries marked **VERIFY BEFORE REDISTRIBUTION** are not cleared for bundling merely because they have been used during development.

| Component / reference | Role in AsterMax | Known licensing/provenance status | Redistribution status |
|---|---|---|---|
| PrePoMax | Native pre/post-processing foundation and historical upstream | Upstream repository is GNU GPL version 3. Preserve upstream copyrights, notices, and corresponding-source obligations for derivative distributions. | **Required attribution / GPL compliance** |
| Code_Aster | Finite-element solver integration | EDF open-source solver distributed under GNU GPL. Exact distributed runtime and transitive packages must be inventoried per release. | **Clear only after package-level review** |
| Netgen / NetGenMesher runtime | Meshing runtime used by the inherited workflow | AsterMax development has used a NetGen runtime obtained from an official PrePoMax distribution. Exact version, source package, license text, and binary redistribution terms must be recorded before release. | **VERIFY BEFORE REDISTRIBUTION** |
| VTK / ActiViz | 3D visualization infrastructure inherited through the PrePoMax ecosystem | Exact VTK/ActiViz build and license corresponding to the distributed binaries must be recorded. Do not assume that a historical binary has the same terms as a current upstream package. | **VERIFY BEFORE REDISTRIBUTION** |
| Newtonsoft.Json and other .NET packages | Supporting libraries where present | Review exact package versions and NuGet license metadata/SBOM for each release. | **VERIFY PER RELEASE** |
| STEP/CAD import libraries and converters | Geometry interoperability where present | Record exact implementation and license. Proprietary SDKs may not be redistributed without explicit rights. | **VERIFY PER RELEASE** |

## Proprietary applications used only as references

ANSYS/Ansys Mechanical and SOLIDWORKS are not AsterMax dependencies and must not be bundled. They may be used externally for lawful engineering comparison, migration tests, or benchmark validation. Their trademarks, software, documentation, assets, and license terms remain the property of their respective owners.

## Required release inventory

Before every binary release, generate or update an SBOM that includes, at minimum:

- component name;
- exact version/commit;
- source URL or provenance record;
- license identifier and bundled license text when required;
- whether the component is linked, embedded, invoked as a process, or merely used at build time;
- whether source/corresponding-source delivery is required;
- any attribution, notice, patent, trademark, or redistribution condition.

Unknown provenance means **do not distribute** until resolved.
