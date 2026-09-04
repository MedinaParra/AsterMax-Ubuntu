#!/usr/bin/env python3
"""Generate the native AsterMax Mechanical materials.lib library.

The library uses PrePoMax's native JSON .lib format and MM_TON_S_C units:
  Young's modulus -> MPa
  density         -> tonne/mm^3

Scope:
- nominal room-temperature isotropic elastic properties + density
- intended for model setup and preliminary linear FEA
- no plastic, fatigue, fracture, creep, hyperelastic or orthotropic law is
  inferred from a material name

For released engineering, replace/verify the seed values against the governing
specification, product form/thickness, heat treatment and actual MTR/data sheet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def m(name, e_mpa, nu, rho_kg_m3, note=""):
    return (name, float(e_mpa), float(nu), float(rho_kg_m3) * 1.0e-12, note)


MATERIALS = [
    ("Structural_And_Wear_Steels", [
        m("Steel_Generic", 200000, 0.30, 7850, "Generic structural-steel reference."),
        m("ASTM_A36", 200000, 0.30, 7850, "Structural carbon steel; strength depends on product/thickness."),
        m("ASTM_A572_Gr50", 200000, 0.29, 7800, "HSLA structural steel Grade 50."),
        m("ASTM_A992", 200000, 0.30, 7850, "Structural-shape steel reference."),
        m("ASTM_A588", 200000, 0.30, 7850, "Weathering structural steel reference."),
        m("ASTM_A516_Gr70", 200000, 0.30, 7850, "Pressure-vessel plate Grade 70 reference."),
        m("ASTM_A514", 205000, 0.29, 7850, "Quenched-and-tempered high-strength plate reference."),
        m("EN_S235JR", 210000, 0.30, 7850, "EN structural steel S235 reference."),
        m("EN_S275JR", 210000, 0.30, 7850, "EN structural steel S275 reference."),
        m("EN_S355JR", 210000, 0.30, 7850, "EN structural steel S355 reference."),
        m("EN_S355J2", 210000, 0.30, 7850, "EN structural steel S355J2 reference."),
        m("ASTM_A500_GrB", 200000, 0.30, 7850, "Cold-formed structural tubing Grade B reference."),
        m("ASTM_A500_GrC", 200000, 0.30, 7850, "Cold-formed structural tubing Grade C reference."),
        m("Wear_Plate_400HB", 205000, 0.29, 7850, "Generic ~400 HB wear-plate elastic reference; hardness/strength are not encoded."),
        m("Wear_Plate_500HB", 205000, 0.29, 7850, "Generic ~500 HB wear-plate elastic reference; hardness/strength are not encoded."),
    ]),
    ("Carbon_Alloy_And_Tool_Steels", [
        m("AISI_1018", 205000, 0.29, 7870, "Low-carbon steel reference."),
        m("AISI_1020", 205000, 0.29, 7870, "Low-carbon steel reference."),
        m("AISI_1040", 200000, 0.29, 7870, "Medium-carbon steel reference."),
        m("AISI_1045", 200000, 0.29, 7870, "Medium-carbon steel; strength is condition-dependent."),
        m("AISI_1060", 200000, 0.29, 7850, "Higher-carbon steel reference."),
        m("SAE_4130", 205000, 0.29, 7850, "Cr-Mo alloy steel; strength is heat-treatment dependent."),
        m("SAE_4140", 205000, 0.29, 7850, "Cr-Mo alloy steel; strength is heat-treatment dependent."),
        m("SAE_4340", 200000, 0.29, 7850, "Ni-Cr-Mo alloy steel; strength is heat-treatment dependent."),
        m("SAE_4340_HB_270_320", 200000, 0.29, 7850, "4340 elastic seed for HB 270-320 condition; hardness is descriptive only, not a plastic law."),
        m("SAE_8620", 205000, 0.29, 7850, "Case-hardening Ni-Cr-Mo steel reference."),
        m("AISI_52100", 210000, 0.30, 7810, "High-carbon chromium bearing steel reference."),
        m("AISI_12L14", 200000, 0.29, 7870, "Free-machining carbon steel reference."),
        m("Tool_Steel_D2", 210000, 0.28, 7700, "Cold-work tool steel reference; heat-treatment dependent."),
    ]),
    ("Stainless_And_Duplex_Steels", [
        m("AISI_304", 193000, 0.29, 7900, "Austenitic stainless reference."),
        m("AISI_304L", 193000, 0.29, 7900, "Low-carbon 304 stainless reference."),
        m("AISI_316", 193000, 0.30, 8000, "Austenitic stainless reference."),
        m("AISI_316L", 193000, 0.30, 8000, "Low-carbon 316 stainless reference."),
        m("AISI_321", 193000, 0.29, 8000, "Titanium-stabilized austenitic stainless reference."),
        m("AISI_410", 200000, 0.27, 7750, "Martensitic stainless reference."),
        m("AISI_420", 200000, 0.27, 7740, "Martensitic stainless reference."),
        m("17_4PH_H900", 197000, 0.27, 7750, "Precipitation-hardening stainless H900 reference."),
        m("Duplex_2205", 200000, 0.30, 7800, "Duplex stainless 2205 reference."),
        m("SuperDuplex_2507", 200000, 0.30, 7800, "Super-duplex stainless 2507 reference."),
    ]),
    ("Cast_Irons", [
        m("Gray_Iron_A48_Class20", 100000, 0.26, 7150, "Gray cast iron; elastic modulus varies substantially with grade/microstructure."),
        m("Gray_Iron_A48_Class30", 110000, 0.26, 7150, "Gray cast iron; elastic modulus varies substantially with grade/microstructure."),
        m("Gray_Iron_A48_Class40", 130000, 0.26, 7150, "Gray cast iron reference."),
        m("Ductile_Iron_60_40_18", 169000, 0.29, 7100, "Ductile iron grade reference."),
        m("Ductile_Iron_65_45_12", 169000, 0.29, 7100, "Ductile iron grade reference."),
        m("Ductile_Iron_80_55_06", 169000, 0.29, 7100, "Ductile iron grade reference."),
    ]),
    ("Aluminum_Alloys", [
        m("AA_1100_H14", 69000, 0.33, 2710, "Commercially pure aluminum reference."),
        m("AA_2024_T3", 73100, 0.33, 2780, "High-strength Al-Cu alloy T3 reference."),
        m("AA_3003_H14", 69000, 0.33, 2730, "Al-Mn alloy H14 reference."),
        m("AA_5052_H32", 70300, 0.33, 2680, "Al-Mg alloy H32 reference."),
        m("AA_5083_H116", 71700, 0.33, 2660, "Marine Al-Mg alloy H116 reference."),
        m("AA_6061_T6", 68900, 0.33, 2700, "Al-Mg-Si alloy T6 reference."),
        m("AA_6082_T6", 70000, 0.33, 2700, "Al-Mg-Si alloy T6 reference."),
        m("AA_7075_T6", 71700, 0.33, 2810, "High-strength Al-Zn-Mg-Cu alloy T6 reference."),
    ]),
    ("Copper_Brass_And_Bronze", [
        m("Copper_C110", 117000, 0.34, 8940, "ETP copper reference."),
        m("Brass_C260", 110000, 0.34, 8530, "Cartridge brass reference."),
        m("Brass_C360", 97000, 0.31, 8500, "Free-cutting brass reference."),
        m("Bearing_Bronze_C932", 103000, 0.34, 8930, "Tin bearing bronze reference."),
        m("Aluminum_Bronze_C954", 110000, 0.34, 7450, "Aluminum bronze reference."),
    ]),
    ("Titanium_And_Nickel_Alloys", [
        m("Titanium_Grade2", 105000, 0.34, 4510, "Commercially pure titanium Grade 2 reference."),
        m("Ti_6Al_4V_Grade5", 114000, 0.34, 4430, "Titanium Grade 5 reference."),
        m("Inconel_625", 207000, 0.28, 8440, "Nickel alloy 625 reference."),
        m("Inconel_718", 200000, 0.29, 8190, "Nickel alloy 718 reference."),
        m("Monel_400", 179000, 0.32, 8800, "Nickel-copper alloy reference."),
    ]),
    ("Engineering_Polymers", [
        m("HDPE", 1000, 0.42, 950, "Small-strain isotropic seed only; polymer response is rate/temperature dependent."),
        m("UHMWPE", 800, 0.46, 930, "Small-strain isotropic seed only; strongly nonlinear for many applications."),
        m("PA6_Nylon", 2800, 0.39, 1130, "Dry nominal small-strain seed; moisture and temperature strongly affect properties."),
        m("POM_Acetal", 3000, 0.35, 1410, "Nominal small-strain engineering-plastic seed."),
        m("PTFE", 500, 0.46, 2200, "Small-strain reference only; creep/nonlinearity are important."),
        m("PVC_U", 3000, 0.38, 1400, "Rigid PVC nominal small-strain seed."),
        m("ABS", 2200, 0.35, 1040, "Nominal small-strain engineering-plastic seed."),
        m("Polycarbonate", 2400, 0.37, 1200, "Nominal small-strain engineering-plastic seed."),
    ]),
]


def _named(name: str) -> dict:
    return {
        "Name": name,
        "Active": True,
        "Visible": True,
        "Valid": True,
        "Internal": False,
    }


def _description(name: str, youngs_mpa: float, poisson: float,
                 density_tonne_per_mm3: float, note: str) -> str:
    density_kg_m3 = density_tonne_per_mm3 * 1.0e12
    prefix = (
        f"{name}: nominal room-temperature isotropic linear-elastic seed. "
        f"E={youngs_mpa:g} MPa, nu={poisson:g}, rho={density_kg_m3:g} kg/m3. "
    )
    suffix = (
        "No plastic/fatigue/fracture/creep law is included. Verify the governing "
        "specification, product form, condition and certified data before design release."
    )
    return prefix + (note.strip() + " " if note else "") + suffix


def _material_item(name: str, youngs_mpa: float, poisson: float,
                   density_tonne_per_mm3: float, note: str) -> dict:
    material = {
        "Description": _description(name, youngs_mpa, poisson, density_tonne_per_mm3, note),
        "TemperatureDependent": False,
        "Properties": [
            {
                "$type": "CaeModel.ElasticWithDensity, CaeModel",
                "YoungsModulus": youngs_mpa,
                "PoissonsRatio": poisson,
                "Density": density_tonne_per_mm3,
            }
        ],
        **_named(name),
    }
    return {
        "Expanded": False,
        "Items": [],
        "Tag": material,
        **_named(name),
    }


def build_library() -> dict:
    root = {
        "Expanded": True,
        "Items": [],
        "Tag": None,
        **_named("Materials"),
    }
    for category_name, materials in MATERIALS:
        root["Items"].append({
            "Expanded": True,
            "Items": [_material_item(*material) for material in materials],
            "Tag": None,
            **_named(category_name),
        })
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, help="Destination materials.lib path")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    library = build_library()
    output.write_text(json.dumps(library, indent=2) + "\n", encoding="utf-8")
    count = sum(len(items) for _, items in MATERIALS)
    print(
        f"Generated AsterMax Mechanical material library: "
        f"{count} materials in {len(MATERIALS)} categories -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
