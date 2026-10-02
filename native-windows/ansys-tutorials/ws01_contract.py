"""Evidence checks for the corrected WS01 case; no solver results are embedded."""
import math

CAD_SHA256 = "4b98de09f4ff958974ebf92e298dde2210b6e2a5bbdddb82a22634ac1e8883c8"
SCOPES = {
    "pressure_faces": [39,11,176,174,6,2,7,12,175,170,10,8,172,9,169,171,173],
    "counterbore_support": [22,66,68,70],
    "inner_recess_support": [41,76,74,78,35,43,75,77],
    "lip_support": [13],
}


def finite_number(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be finite and {'positive' if positive else 'nonnegative'}")
    return float(value)


def matches_faces(actual, expected):
    return (isinstance(actual, list) and all(type(x) is int for x in actual)
            and len(actual) == len(expected) and sorted(actual) == sorted(expected))


def check_contract(bundle, analysis, reference):
    binding = analysis.get("scope_binding", {})
    scope = analysis.get("scope", {})
    material = analysis.get("material", {})
    mesh = bundle.get("mesh", {})
    input_mesh = analysis.get("mesh", {})
    checks = {
        "real_solver_metadata": bundle.get("source", {}).get("kind") == "REAL_CODE_ASTER_MED"
            and bundle.get("integrity", {}).get("fea_values_invented") is False,
        "units": bundle.get("units") == {"length": "mm", "force": "N", "stress": "MPa"},
        "component_first_stress": bundle.get("integrity", {}).get("von_mises_component_first_ansys_parity") is True,
        "exact_cad": binding.get("cad_sha256") == CAD_SHA256,
        "scope_binding": binding.get("mode") == "exact_cad_sha256_plus_face_manifest"
            and binding.get("verified") is True and binding.get("selected_face_count") == 30,
        "pressure_scope": matches_faces(scope.get("pressure_faces"), SCOPES["pressure_faces"])
            and scope.get("pressure_face_count") == 17,
        "support_scope": all(matches_faces(scope.get(key), SCOPES[key]) for key in SCOPES if key != "pressure_faces"),
        "pressure": analysis.get("load") == {"type": "pressure", "magnitude_mpa": 1.1},
        "supports": analysis.get("supports", {}).get("type") == "frictionless-normal"
            and analysis.get("supports", {}).get("code_aster") == "FACE_IMPO/DNOR=0",
        "material": material.get("E_mpa") == 71000.0 and material.get("nu") == 0.33
            and material.get("yield_mpa_for_safety_factor") == 280.0,
        "quadratic_mesh": input_mesh.get("order") == 2 and mesh.get("element_type") == "TETRA10",
        "mesh_counts": all(type(mesh.get(a)) is int and mesh[a] > 0 and mesh[a] == input_mesh.get(b)
                           for a, b in (("node_count", "nodes"), ("element_count", "volume_elements"))),
    }
    if reference is not None:
        checks["reference_cad_units"] = reference.get("cad_sha256") == CAD_SHA256 and reference.get("units") == "mm-N-MPa"
    return checks
