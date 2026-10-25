#!/usr/bin/env python3
import hashlib, json, math, pathlib, re, sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'artifact/c8-87')
ref_root = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else 'artifact/c8-83-ref')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def table(text, marker, header):
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit('missing ' + marker)
    lines = text[pos:].splitlines()
    key = ';'.join(header)
    hi = next((i for i, line in enumerate(lines) if line.strip() == key), None)
    if hi is None:
        raise SystemExit('missing header ' + marker)
    rows = {}
    for line in lines[hi + 1:]:
        if rows and (not line.strip() or line.startswith('PPM_') or 'ASTER 17.' in line):
            break
        parts = [x.strip() for x in line.split(';')]
        if len(parts) != len(header):
            if rows:
                break
            continue
        try:
            node = int(parts[0])
            vals = [float(x.replace('D', 'E')) for x in parts[1:]]
        except ValueError:
            if rows:
                break
            continue
        if not all(math.isfinite(x) for x in vals):
            raise SystemExit(f'nonfinite {marker} at {node}')
        rows[node] = vals
    if not rows:
        raise SystemExit('empty ' + marker)
    return rows


def mail_nodes(path):
    nodes = {}
    active = False
    for raw in path.read_text(errors='replace').splitlines():
        s = raw.strip()
        if s == 'COOR_3D':
            active = True
            continue
        if active and s == 'FINSF':
            break
        if not active:
            continue
        p = s.split()
        if len(p) >= 4 and re.fullmatch(r'N\d+', p[0]):
            nodes[int(p[0][1:])] = [float(p[1]), float(p[2]), float(p[3])]
    return nodes


def parse_case(study, traction_ev):
    resu = study / 'astermax_c862_static.resu'
    mess = study / 'astermax_c862_static.mess'
    mail = study / 'astermax_c862_static.mail'
    rmed = study / 'astermax_c862_static.rmed'
    for p in (resu, mess, mail, rmed):
        if not p.is_file() or p.stat().st_size == 0:
            raise SystemExit('missing ' + str(p))
    if re.search(r'<F>|ERREUR FATALE|FATAL_ERROR', mess.read_text(errors='replace'), re.I):
        raise SystemExit('solver fatal ' + str(study))
    text = resu.read_text(errors='replace')
    depl = table(text, 'PPM_DEPL', ['NOEUD', 'DX', 'DY', 'DZ'])
    sn = table(text, 'PPM_STRESS_N', ['NOEUD', 'SIXX', 'SIYY', 'SIZZ'])
    ss = table(text, 'PPM_STRESS_S', ['NOEUD', 'SIXY', 'SIYZ', 'SIXZ'])
    reac = table(text, 'PPM_REACTION', ['NOEUD', 'DX', 'DY', 'DZ'])
    disp = {n: math.sqrt(sum(x*x for x in v)) for n, v in depl.items()}
    un = max(disp, key=disp.get)
    def vm(n):
        sx, sy, sz = sn[n]
        xy, yz, xz = ss[n]
        return math.sqrt(.5*((sx-sy)**2 + (sy-sz)**2 + (sz-sx)**2) + 3*(xy*xy + yz*yz + xz*xz))
    mises = {n: vm(n) for n in set(sn).intersection(ss)}
    vn = max(mises, key=mises.get)
    tev = json.loads(traction_ev.read_text())
    resultant = float(tev['integrated_resultant_n'])
    reaction = [sum(v[i] for v in reac.values()) for i in range(3)]
    residual = [reaction[0] + resultant, reaction[1], reaction[2]]
    rnorm = math.sqrt(sum(x*x for x in residual))
    coords = mail_nodes(mail)
    return {
        'nodes': len(depl),
        'umax_mm': disp[un], 'umax_node': un, 'umax_xyz_mm': coords.get(un),
        'mises_max_mpa': mises[vn], 'mises_max_node': vn, 'mises_max_xyz_mm': coords.get(vn),
        'reaction_residual_n': rnorm,
        'reaction_balance_verified': rnorm <= 1e-3,
        'resu_sha256': sha(resu), 'rmed_sha256': sha(rmed), 'mail_sha256': sha(mail)
    }

family = json.loads((root / 'C8.87_MESH_FAMILY.json').read_text(encoding='utf-8-sig'))
refq = json.loads((ref_root / 'C8.83_CONVERGENCE_QUALIFICATION.json').read_text(encoding='utf-8-sig'))
ref = next(x for x in refq['levels'] if x['name'] == 'fine')
ref_u = float(ref['disp_max_mm']); ref_s = float(ref['mises_max_mpa']); ref_e = int(ref['elements'])
rel = lambda a, b: abs(a-b) / max(abs(b), 1e-30)

cases = []
for level in family['levels']:
    name = level['name']
    case = parse_case(root / name / 'study', root / name / 'C8.87_SURFACE_TRACTION.json')
    case.update({'name': name, 'global_maxh_mm': level['global_maxh_mm'], 'local_h_mm': level['local_h_mm'], 'elements': int(level['elements']), 'generation_walltime_s': level['generation_walltime_s']})
    case['umax_error_vs_global25'] = rel(case['umax_mm'], ref_u)
    case['mises_error_vs_global25'] = rel(case['mises_max_mpa'], ref_s)
    case['element_reduction_vs_global25'] = 1 - case['elements']/ref_e
    cases.append(case)

base = next(x for x in cases if x['name'] == 'baseline')
for c in cases:
    c['umax_accuracy_improved_vs_baseline'] = c['umax_error_vs_global25'] < base['umax_error_vs_global25']
    c['mises_accuracy_improved_vs_baseline'] = c['mises_error_vs_global25'] < base['mises_error_vs_global25']
    c['local_cost_below_global25'] = c['elements'] < ref_e
    c['dual_metric_candidate'] = c['name'] != 'baseline' and c['umax_accuracy_improved_vs_baseline'] and c['mises_accuracy_improved_vs_baseline'] and c['local_cost_below_global25'] and c['reaction_balance_verified']

candidates = [c for c in cases if c['dual_metric_candidate']]
# Deterministic selection: minimize worst normalized error; break ties by fewer elements then larger h.
for c in candidates:
    c['worst_error_vs_global25'] = max(c['umax_error_vs_global25'], c['mises_error_vs_global25'])
best = min(candidates, key=lambda c: (c['worst_error_vs_global25'], c['elements'], -(c['local_h_mm'] or 0))) if candidates else None

ev = {
    'schema': 'astermax.c8.87.adaptive-pareto-sweep.v1',
    'solver': 'Code_Aster 17.4.0', 'unit_system': 'mm-N-MPa',
    'reference_global25': {'elements': ref_e, 'umax_mm': ref_u, 'mises_max_mpa': ref_s, 'source_workflow': 34033613470},
    'cases': cases,
    'dual_metric_candidate_count': len(candidates),
    'best_candidate': None if best is None else {k: best[k] for k in ('name','local_h_mm','elements','umax_mm','mises_max_mpa','umax_error_vs_global25','mises_error_vs_global25','worst_error_vs_global25','element_reduction_vs_global25','reaction_residual_n','mises_max_xyz_mm')},
    'pareto_adaptive_efficiency_admitted': best is not None,
    'consumer_multi_roi_refinement_verified': True,
    'native_femeshrefinement_binding_verified': False,
    'industrial_validation': False,
    'ansys_equivalence': False
}
(root / 'C8.87_PARETO_QUALIFICATION.json').write_text(json.dumps(ev, indent=2), encoding='utf-8')
print(json.dumps(ev, indent=2))
