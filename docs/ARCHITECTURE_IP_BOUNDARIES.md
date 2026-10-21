# Architecture and intellectual-property boundaries

This document records the intended product architecture so that technical convenience does not accidentally erase licensing boundaries.

## Product direction

AsterMax is intended to become an integrated mechanical engineering environment with two user-facing workflows:

### Design workflow

A familiar parametric mechanical-CAD experience built around original AsterMax interaction design:

`Part / Sketch -> Features -> Assemblies -> Drawings / Exchange`

The objective is workflow efficiency familiar to experienced mechanical designers, not reproduction of another vendor's source code, assets, or trade dress.

### Analysis workflow

An integrated structural-analysis experience:

`Geometry -> Materials -> Interactions -> Mesh -> Constraints / Loads -> Solve -> Results -> Verification`

The objective is a predictable engineering hierarchy familiar to experienced FEA users, implemented using AsterMax code and lawfully licensed components.

## Current copyleft foundation

The existing AsterMax Mechanical application is historically a native derivative of PrePoMax. Treat its integrated derivative code as GPLv3-covered when conveyed unless a file-specific analysis establishes otherwise.

## Future CAD module

A future CAD kernel/UI may be developed from original code and compatible open-source components. If there is a business reason to give it a different license, it must be designed from the outset as a genuinely separable component with a documented IPC/file/API interface and reviewed before code is combined with the GPL-covered application.

Do not assume that a DLL boundary, namespace change, repository subfolder, or branding change alone avoids GPL obligations.

## Solver adapters

Prefer explicit adapters that exchange documented files/data and launch independently distributed solver processes. Record for each solver:

- executable/package provenance;
- integration method;
- license;
- whether it is bundled or user-installed;
- source/notice obligations;
- supported versions.

## Validation boundary

Commercial comparison products may be used as external engineering references where lawful, but expected numerical results should be stored as AsterMax-owned benchmark data wherever possible. Prefer analytical solutions, published benchmarks, standards, and independently constructed reference models over redistributing proprietary tutorial content.
