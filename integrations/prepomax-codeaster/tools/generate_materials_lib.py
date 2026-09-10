#!/usr/bin/env python3
"""Generate the native PrePoMax/AsterMax Mechanical materials.lib seed library.

The library is stored in PrePoMax's native JSON .lib format and uses the
MM_TON_S_C library unit system expected by FrmMaterialLibrary:
  stress / Young's modulus -> MPa (N/mm^2)
  density                 -> tonne/mm^3

Only linear-elastic + density properties are solver-active in this seed.
Strength values mentioned in descriptions are references, not plastic laws.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


MATERIALS = [
    ("Reference_Steels", [
        ("Steel_Generic", 200000.0, 0.30, 7.85e-9,
         "Linear-elastic reference steel for preliminary FEA near room temperature. "
         "E=200 GPa, nu=0.30, rho=7850 kg/m3. Replace with project-specific certified "
         "data for design release or nonlinear analysis."),
        ("ASTM_A36", 200000.0, 0.30, 7.85e-9,
         "ASTM A36 nominal linear-elastic seed. Typical room-temperature density 7850 "
         "kg/m3 and E about 200 GPa. Typical minimum yield strength is about 250 MPa, "
         "but strength requirements vary with product/thickness. No plastic curve is "
         "included; verify the governing specification and MTR."),
        ("ASTM_A572_Gr50", 200000.0, 0.29, 7.80e-9,
         "ASTM A572 Grade 50 nominal linear-elastic seed. Typical E=200 GPa, nu=0.29, "
         "rho=7800 kg/m3. Grade 50 nominal yield strength 345 MPa and tensile strength "
         "450 MPa. No plastic curve is included; verify thickness/product requirements "
         "and MTR."),
    ]),
    ("Carbon_Alloy_Steels", [
        ("AISI_1020", 205000.0, 0.29, 7.87e-9,
         "AISI 1020 nominal room-temperature elastic data. E=205 GPa, nu=0.29, "
         "rho=7870 kg/m3. Strength depends on product condition; no plastic curve is included."),
        ("AISI_1045", 200000.0, 0.29, 7.87e-9,
         "AISI 1045 nominal room-temperature elastic data. E=200 GPa, nu=0.29, "
         "rho=7870 kg/m3. Yield/ultimate properties vary with hot-rolled, cold-rolled "
         "and heat-treated condition; no plastic curve is included."),
        ("SAE_4140", 205000.0, 0.29, 7.85e-9,
         "SAE/AISI 4140 nominal linear-elastic seed. E=205 GPa, nu=0.29, rho=7850 kg/m3. "
         "Strength and hardness are strongly heat-treatment dependent; use the actual "
         "heat-treatment/MTR data for nonlinear or acceptance calculations."),
        ("SAE_4340", 200000.0, 0.29, 7.85e-9,
         "SAE/AISI 4340 nominal linear-elastic seed. Typical elastic modulus is in the "
         "190-210 GPa range, nu about 0.27-0.30, rho about 7850 kg/m3. Strength is "
         "heat-treatment dependent; no plastic curve is included."),
    ]),
    ("Stainless_Steels", [
        ("AISI_304", 193000.0, 0.29, 7.90e-9,
         "AISI 304 annealed reference, room-temperature linear-elastic seed. E=193 GPa, "
         "nu=0.29, rho=7900 kg/m3. Verify product condition and temperature-dependent "
         "data when required."),
        ("AISI_316", 193000.0, 0.30, 8.00e-9,
         "AISI 316/316L annealed reference, room-temperature linear-elastic seed. "
         "E=193 GPa, nu=0.30, rho=8000 kg/m3. Verify exact grade/product condition for "
         "design release."),
    ]),
    ("Aluminum_Alloys", [
        ("AA_6061_T6", 68900.0, 0.33, 2.70e-9,
         "Aluminum 6061-T6 nominal room-temperature linear-elastic seed. E=68.9 GPa, "
         "nu=0.33, rho=2700 kg/m3. Typical yield strength is about 276 MPa for common "
         "T6 data; verify product form/specification before release."),
        ("AA_7075_T6", 70000.0, 0.33, 2.80e-9,
         "Aluminum 7075-T6 nominal room-temperature linear-elastic seed. E about 70 GPa, "
         "nu=0.33, rho about 2800 kg/m3. Strength is product/temper dependent; no plastic "
         "curve is included."),
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


def _material_item(name: str, youngs_mpa: float, poisson: float,
                   density_tonne_per_mm3: float, description: str) -> dict:
    material = {
        "Description": description,
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
    print(f"Generated AsterMax Mechanical material library: {count} materials -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
