# AsterMax Mechanical engineering material library

This file documents the scope and engineering basis of the `materials.lib`
packaged with AsterMax Mechanical.

## Scope

The current library contains **70 common engineering materials in 8 groups**:

- Structural and wear steels
- Carbon, alloy and tool steels
- Stainless and duplex steels
- Cast irons
- Aluminum alloys
- Copper, brass and bronze
- Titanium and nickel alloys
- Engineering polymers

The library intentionally stores only properties currently consumed safely by
the AsterMax Mechanical linear Code_Aster adapter:

- isotropic Young's modulus
- Poisson's ratio
- density

Values are nominal room-temperature engineering references. They are suitable
for model setup, comparison studies and preliminary linear FEA, but are **not**
certified design allowables and are not a substitute for the material
specification, MTR, product form/thickness or heat-treatment condition.

The native library unit system is `MM_TON_S_C`:

- Young's modulus: MPa
- density: tonne/mm^3

## Particularly relevant SKM / heavy-mechanical entries

The packaged library includes, among others:

- ASTM A36
- ASTM A572 Grade 50
- ASTM A514
- ASTM A516 Grade 70
- EN S235 / S275 / S355
- Generic 400 HB and 500 HB wear plate elastic seeds
- AISI/SAE 1018, 1020, 1040, 1045, 1060
- SAE 4130, 4140, 4340, 8620
- SAE 4340 HB 270-320 elastic seed
- AISI 52100 bearing steel
- AISI 304/304L, 316/316L, 321, 410, 420
- 17-4PH H900, Duplex 2205 and Super Duplex 2507
- Gray and ductile cast irons
- Aluminum 2024-T3, 5052-H32, 5083-H116, 6061-T6, 6082-T6, 7075-T6
- C110 copper, cartridge/free-cutting brass, bearing and aluminum bronze
- Titanium Grade 2, Ti-6Al-4V, Inconel 625/718 and Monel 400
- HDPE, UHMWPE, PA6, POM, PTFE, PVC-U, ABS and polycarbonate

## Important limitations

A material name does **not** generate a plastic law. For example:

- `SAE_4340_HB_270_320` uses the nominal elastic modulus and density for
  4340; the hardness range is descriptive. Yield stress and hardening must come
  from the actual heat-treatment/MTR or an approved constitutive dataset.
- The generic 400 HB/500 HB wear-plate entries do not imply a particular brand
  or certified strength.
- Polymer values are small-strain references. Creep, viscoelasticity,
  temperature, moisture and large-strain effects can dominate.
- Gray cast iron is not ideally isotropic-linear over all stress states.
- No fatigue, fracture, creep, thermal expansion, conductivity, orthotropy,
  hyperelasticity or temperature-dependent law is inferred.

## Reference basis

The seed values were selected as representative room-temperature values and
cross-checked against commonly used public/industry engineering references,
including manufacturer/producer data sheets, ASTM/EN grade documentation,
MatWeb, AZoM, Atlas Steels, NIST aluminum data and common engineering handbooks.

Representative public references used in earlier validation of the library:

- ASTM A36 overview: https://www.azom.com/article.aspx?ArticleID=6117
- ASTM A572 Grade 50: https://www.matweb.com/search/datasheet_print.aspx?matguid=9ced5dc901c54bd1aef19403d0385d7f
- AISI 1020: https://www.azom.com/article.aspx?ArticleID=9145
- AISI 1045: https://www.azom.com/article.aspx?ArticleID=9153
- AISI 4140: https://www.azom.com/article.aspx?ArticleID=6769
- AISI 4340: https://www.azom.com/article.aspx?ArticleID=6772
- Stainless 304: https://atlassteels.com.au/documents/Atlas_Grade_datasheet_304_rev_Jan_2011.pdf
- Stainless 316/316L: https://atlassteels.com.au/documents/Atlas316-316L.pdf
- NIST Aluminum 6061-T6: https://www.nist.gov/mml/acmd/aluminum-6061-t6-uns-aa96061
- Aluminum 6061: https://www.azom.com/article.aspx?ArticleID=6636

For released engineering, the governing project specification and certified
material documentation always take precedence over this seed library.
