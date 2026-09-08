import json, re, sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.')
resu = root / 'axial-bar.resu'
mess = root / 'axial-bar.mess'
rmed = root / 'axial-bar.rmed'

checks = []
def gate(name, passed, evidence):
    checks.append({'name': name, 'pass': bool(passed), 'evidence': str(evidence)})

for p in (resu, mess, rmed):
    gate(f'{p.suffix[1:]}_exists', p.exists(), p)
    if p.exists():
        gate(f'{p.suffix[1:]}_nonempty', p.stat().st_size > 32, p.stat().st_size)

resu_text = resu.read_text(errors='ignore') if resu.exists() else ''
mess_text = mess.read_text(errors='ignore') if mess.exists() else ''

# Parse the explicit POST_RELEVE_T LOAD-face displacement table. The final three
# numeric fields on each LOAD_FACE_DISPLA row are DX, DY and DZ.
dx_values = []
for line in resu_text.splitlines():
    if not line.startswith('LOAD_FACE_DISPLA'):
        continue
    nums = re.findall(r'[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?', line)
    if len(nums) >= 3:
        dx_values.append(float(nums[-3]))

reference_dx = 10000.0 * 100.0 / (100.0 * 210000.0)  # analytical 1D reference, mm
solver_dx = sum(dx_values) / len(dx_values) if dx_values else None
rel_error = abs(solver_dx-reference_dx)/reference_dx if solver_dx is not None else None
spread = (max(dx_values)-min(dx_values)) if dx_values else None

gate('solver_displacement_extracted', solver_dx is not None,
     f'count={len(dx_values)}; mean_dx_mm={solver_dx}; values={dx_values}')
gate('load_face_dx_uniform_0p1pct', spread is not None and spread <= max(abs(solver_dx),1e-12)*0.001,
     f'spread_mm={spread}')
gate('displacement_matches_analytical_reference_5pct', rel_error is not None and rel_error <= 0.05,
     f'solver_dx={solver_dx}; analytical_reference={reference_dx}; rel_error={rel_error}')

gate('solver_log_present', bool(mess_text.strip()), 'axial-bar.mess')
nonzero_exit = re.search(r'EXECUTION_CODE_ASTER_EXIT_\d+=([1-9]\d*)', mess_text)
fatal_marker = re.search(r'(^|\n)\s*!?\s*<F(?:>|_)', mess_text)
gate('solver_no_fatal_marker', not nonzero_exit and not fatal_marker,
     f'nonzero_exit={bool(nonzero_exit)}; fatal_marker={bool(fatal_marker)}')
gate('solver_normal_stop', 'ARRET NORMAL' in mess_text and 'TOTAL_JOB' in mess_text,
     'ARRET NORMAL + TOTAL_JOB')

manifest = {
    'release': 'C9.62',
    'title': 'Real Code_Aster End-to-End Solver Gate',
    'solver_execution': 'RUN',
    'reference_kind': 'ANALYTICAL_1D_AXIAL_BAR_REFERENCE_NOT_FEA_OUTPUT',
    'analytical_reference': {
        'force_N': 10000.0,
        'length_mm': 100.0,
        'area_mm2': 100.0,
        'youngs_modulus_MPa': 210000.0,
        'sigma_MPa': 100.0,
        'ux_mm': reference_dx,
    },
    'solver_observation': {
        'load_face_dx_values_mm': dx_values,
        'mean_ux_mm': solver_dx,
        'ux_relative_error': rel_error,
        'rmed_bytes': rmed.stat().st_size if rmed.exists() else 0,
    },
    'checks_total': len(checks),
    'checks_passed': sum(1 for c in checks if c['pass']),
    'all_checks_pass': all(c['pass'] for c in checks),
    'checks': checks,
}
(root / 'C9.62_SOLVER_VALIDATION.json').write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
if not manifest['all_checks_pass']:
    sys.exit(2)
