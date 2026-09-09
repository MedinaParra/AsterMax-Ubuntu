import json, math, sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
solver_manifest_path = root / 'C9.62_SOLVER_VALIDATION.json'
ansys_reference_path = root / 'B01_ANSYS_REFERENCE.json'

checks = []
def gate(name, passed, evidence, required=True):
    checks.append({
        'name': name,
        'pass': bool(passed),
        'required': bool(required),
        'evidence': str(evidence),
    })

# Benchmark contract is declared before inspecting any numerical result.
contract = {
    'benchmark_id': 'B01',
    'name': 'Axial HEXA8 bar',
    'unit_system': 'mm-N-MPa',
    'geometry': {'length_mm': 100.0, 'width_mm': 10.0, 'height_mm': 10.0},
    'material': {'youngs_modulus_MPa': 210000.0, 'poisson_ratio': 0.30},
    'load': {'total_force_N': 10000.0, 'direction': '+X'},
    'bc': {'x0_face': 'DX=DY=DZ=0'},
    'mesh': {'element_type': 'HEXA8', 'elements': 10},
    'tolerances': {
        'code_aster_vs_analytical_ux_relative': 0.05,
        'ansys_vs_code_aster_ux_relative': 0.02,
        'ansys_vs_analytical_ux_relative': 0.05,
    },
}

L = contract['geometry']['length_mm']
A = contract['geometry']['width_mm'] * contract['geometry']['height_mm']
E = contract['material']['youngs_modulus_MPa']
F = contract['load']['total_force_N']
analytical_ux = F * L / (A * E)
analytical_sigma = F / A

gate('solver_manifest_exists', solver_manifest_path.exists(), solver_manifest_path)
solver_manifest = {}
if solver_manifest_path.exists():
    solver_manifest = json.loads(solver_manifest_path.read_text())

gate('real_code_aster_execution', solver_manifest.get('solver_execution') == 'RUN', solver_manifest.get('solver_execution'))
gate('code_aster_internal_validation_pass', solver_manifest.get('all_checks_pass') is True, solver_manifest.get('all_checks_pass'))
solver_ux = solver_manifest.get('solver_observation', {}).get('mean_ux_mm')
solver_err = None
if solver_ux is not None:
    solver_err = abs(float(solver_ux) - analytical_ux) / abs(analytical_ux)
gate('code_aster_ux_extracted', solver_ux is not None, solver_ux)
gate('code_aster_vs_analytical_ux_within_predeclared_tolerance',
     solver_err is not None and solver_err <= contract['tolerances']['code_aster_vs_analytical_ux_relative'],
     f'solver_ux_mm={solver_ux}; analytical_ux_mm={analytical_ux}; rel_error={solver_err}; tol={contract["tolerances"]["code_aster_vs_analytical_ux_relative"]}')

gate('analytical_reference_ux', math.isclose(analytical_ux, 0.047619047619047616, rel_tol=0, abs_tol=1e-15), analytical_ux)
gate('analytical_reference_sigma', math.isclose(analytical_sigma, 100.0, rel_tol=0, abs_tol=1e-12), analytical_sigma)

# ANSYS evidence is intentionally independent and optional at this stage.
# Absence must never be converted into a fabricated number or a passing equivalence claim.
ansys = None
ansys_ux = None
ansys_source_valid = False
if ansys_reference_path.exists():
    ansys = json.loads(ansys_reference_path.read_text())
    ansys_ux = ansys.get('observations', {}).get('mean_load_face_ux_mm')
    ansys_source_valid = (
        ansys.get('benchmark_id') == 'B01'
        and ansys.get('solver_family') == 'ANSYS Mechanical'
        and ansys.get('source_kind') in ('EXPORTED_RESULT', 'SIGNED_REPORT', 'USER_SUPPLIED_VERIFIED')
        and isinstance(ansys.get('source_sha256'), str)
        and len(ansys.get('source_sha256')) == 64
        and ansys_ux is not None
    )

gate('ansys_reference_present', ansys_reference_path.exists(), ansys_reference_path, required=False)
gate('ansys_reference_provenance_valid', ansys_source_valid,
     'valid independent ANSYS provenance required before numerical equivalence can be evaluated', required=False)

ansys_vs_ca = None
ansys_vs_analytical = None
if ansys_source_valid and solver_ux is not None:
    ansys_vs_ca = abs(float(ansys_ux) - float(solver_ux)) / max(abs(float(solver_ux)), 1e-30)
    ansys_vs_analytical = abs(float(ansys_ux) - analytical_ux) / abs(analytical_ux)

gate('ansys_vs_code_aster_ux_within_tolerance',
     ansys_vs_ca is not None and ansys_vs_ca <= contract['tolerances']['ansys_vs_code_aster_ux_relative'],
     f'ansys_ux_mm={ansys_ux}; code_aster_ux_mm={solver_ux}; rel_error={ansys_vs_ca}; tol={contract["tolerances"]["ansys_vs_code_aster_ux_relative"]}', required=False)
gate('ansys_vs_analytical_ux_within_tolerance',
     ansys_vs_analytical is not None and ansys_vs_analytical <= contract['tolerances']['ansys_vs_analytical_ux_relative'],
     f'ansys_ux_mm={ansys_ux}; analytical_ux_mm={analytical_ux}; rel_error={ansys_vs_analytical}; tol={contract["tolerances"]["ansys_vs_analytical_ux_relative"]}', required=False)

required_pass = all(c['pass'] for c in checks if c['required'])
ansys_equivalence_proven = bool(
    required_pass and ansys_source_valid and ansys_vs_ca is not None and ansys_vs_analytical is not None
    and ansys_vs_ca <= contract['tolerances']['ansys_vs_code_aster_ux_relative']
    and ansys_vs_analytical <= contract['tolerances']['ansys_vs_analytical_ux_relative']
)

report = {
    'release': 'C9.80',
    'title': 'B01 Axial HEXA8 Triple-Validation Harness',
    'contract': contract,
    'scientific_integrity': {
        'fea_values_invented': False,
        'ansys_values_invented': False,
        'analytical_values_are_fea_output': False,
    },
    'observations': {
        'analytical_ux_mm': analytical_ux,
        'analytical_sigma_MPa': analytical_sigma,
        'code_aster_mean_ux_mm': solver_ux,
        'code_aster_vs_analytical_ux_relative_error': solver_err,
        'ansys_mean_ux_mm': ansys_ux,
        'ansys_vs_code_aster_ux_relative_error': ansys_vs_ca,
        'ansys_vs_analytical_ux_relative_error': ansys_vs_analytical,
    },
    'required_harness_pass': required_pass,
    'ansys_reference_state': 'VERIFIED' if ansys_source_valid else 'MISSING_OR_UNVERIFIED',
    'ansys_equivalence': 'PROVEN_FOR_B01_UX' if ansys_equivalence_proven else 'NOT_PROVEN',
    'checks_total': len(checks),
    'checks_required': sum(1 for c in checks if c['required']),
    'checks_required_passed': sum(1 for c in checks if c['required'] and c['pass']),
    'checks': checks,
}

out = root / 'C9.80_B01_EQUIVALENCE.json'
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

# CI validates AsterMax/Code_Aster + analytical evidence and the integrity rule.
# Missing ANSYS evidence is a scientifically correct NOT_PROVEN state, not a CI failure.
if not required_pass:
    sys.exit(2)
if not ansys_source_valid and report['ansys_equivalence'] != 'NOT_PROVEN':
    sys.exit(3)
