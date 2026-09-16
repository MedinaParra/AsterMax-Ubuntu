# Code_Aster Windows provider MSI fingerprint

This file records the provider artifact used by the AsterMax native-Windows CI gate. The cryptographic blocking criterion is SHA-256; MD5 is not used for acceptance.

- Origin: `https://simulease.com/wp-content/uploads/2026/03/code-aster_v2025_std.msi`
- Product observed after installation: `Code_Aster v2025`, product version `0.0.2025.3`, manufacturer `Simulease`
- Observation date: 2026-09-16
- Observed size: `398012592` bytes
- SHA-256: `B789FEFFC12E0FECBCFBABE6D386FA15C1AB74797C8C9D27A5733F8D2B5D092D`
- Evidence source: GitHub Actions run `35155333405`, job `104993327077`, step `Download genuine Code_Aster 2025 MSI`

The same run installed the MSI successfully (`MSI_EXIT_CODE=0`). The overall historical smoke job did **not** pass: it subsequently failed because that version of the discovery step searched for `as_run.bat` and did not find it. Therefore this record is evidence of the downloaded artifact fingerprint and successful MSI installation only, not evidence that the native solver integration was operational end-to-end.
