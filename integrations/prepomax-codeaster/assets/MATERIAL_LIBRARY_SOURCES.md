# AsterMax Mechanical starter material library

This file documents the basis of the seed values packaged into `materials.lib`.

## Scope and engineering use

The packaged library is intentionally limited to **linear-elastic properties plus density** for the first AsterMax Mechanical/Code_Aster integration. Values are nominal room-temperature references suitable for model setup and preliminary linear FEA. They are **not** design allowables, certified MTR values, fatigue data, fracture data, or constitutive plastic curves.

For released engineering, nonlinear analysis, acceptance criteria, or safety-critical calculations, replace/confirm the seed data using the governing material specification, product thickness/form, heat treatment and the actual material certificate.

The native PrePoMax material library uses `MM_TON_S_C`: Young's modulus is stored in MPa and density in tonne/mm^3.

| Material | E (MPa) | nu | density (tonne/mm^3) | Basis |
|---|---:|---:|---:|---|
| Steel_Generic | 200000 | 0.30 | 7.85e-9 | General structural steel reference |
| ASTM_A36 | 200000 | 0.30 | 7.85e-9 | Typical structural-steel elastic data; Fy reference 250 MPa |
| ASTM_A572_Gr50 | 200000 | 0.29 | 7.80e-9 | Grade 50 reference; Fy 345 MPa, Fu 450 MPa |
| AISI_1020 | 205000 | 0.29 | 7.87e-9 | Cold-rolled reference data |
| AISI_1045 | 200000 | 0.29 | 7.87e-9 | Carbon-steel reference data; strength condition-dependent |
| SAE_4140 | 205000 | 0.29 | 7.85e-9 | Alloy-steel elastic reference; strength heat-treatment dependent |
| SAE_4340 | 200000 | 0.29 | 7.85e-9 | Midpoint/nominal within published 190-210 GPa range |
| AISI_304 | 193000 | 0.29 | 7.90e-9 | Annealed room-temperature reference |
| AISI_316 | 193000 | 0.30 | 8.00e-9 | Annealed room-temperature reference |
| AA_6061_T6 | 68900 | 0.33 | 2.70e-9 | T6 room-temperature reference |
| AA_7075_T6 | 70000 | 0.33 | 2.80e-9 | T6 room-temperature reference |

## Public references consulted

- ASTM A36 overview and typical physical/mechanical properties: AZoM, `https://www.azom.com/article.aspx?ArticleID=6117`
- ASTM A572 Grade 50: MatWeb, `https://www.matweb.com/search/datasheet_print.aspx?matguid=9ced5dc901c54bd1aef19403d0385d7f`
- ASTM A572 Grade 50 standard elastic reference: BeamDimensions, `https://www.beamdimensions.com/materials/Steel/ASTM/ASTM_A572/`
- AISI 1020: AZoM, `https://www.azom.com/article.aspx?ArticleID=9145`
- AISI 1045: AZoM, `https://www.azom.com/article.aspx?ArticleID=9153`
- AISI 4140: AZoM, `https://www.azom.com/article.aspx?ArticleID=6769`
- AISI 4340: AZoM, `https://www.azom.com/article.aspx?ArticleID=6772`
- Stainless 304: Atlas Steels grade data sheet, `https://atlassteels.com.au/documents/Atlas_Grade_datasheet_304_rev_Jan_2011.pdf`
- Stainless 316/316L: Atlas Steels grade data sheet, `https://atlassteels.com.au/documents/Atlas316-316L.pdf`
- Aluminum 6061-T6 Young's modulus temperature data: NIST, `https://www.nist.gov/mml/acmd/aluminum-6061-t6-uns-aa96061`
- Aluminum 6061 alloy room-temperature nominal data: AZoM, `https://www.azom.com/article.aspx?ArticleID=6636`
- Aluminum 7075-T6 reference data: Metals 2020, 10(8), 1033, `https://www.mdpi.com/2075-4701/10/8/1033`

The sources above contain values for particular product states/conditions and should be read with their own limitations. The AsterMax seed intentionally does not extrapolate them into a plastic law.
