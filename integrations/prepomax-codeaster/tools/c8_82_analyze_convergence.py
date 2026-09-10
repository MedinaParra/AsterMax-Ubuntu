#!/usr/bin/env python3
import csv
import hashlib
import json
import math
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'artifact/c8-82')
family = json.loads((root / 'C8.82_NATIVE_MESH_FAMILY.json').read_text(encoding='utf-8-sig'))
by_name = {x['name']: x for x in family['levels']}
levels = ['coarse', 'medium', 'fine']


def sha(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def table(text, marker, header):
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit('missing ' + marker)
    lines = text[pos:].splitlines()
    key = ';'.join(header)
    hi = next((i for i, line in enumerate(lines) if line.strip() == key), None)
    if hi is None:
        raise SystemExit('missing header for ' + marker)
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
            raise SystemExit(f'non-finite {marker} row at node {node}')
        rows[node] = vals
    if not rows:
        raise SystemExit('empty ' + marker)
    return rows


def parse_mail_quality(path):
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    nodes, tets, mode = {}, [], None
    for raw in lines:
        s = raw.strip()
        if s == 'COOR_3D':
            mode = 'nodes'
            continue
        if s == 'TETRA10':
            mode = 'tets'
            continue
        if s in ('FINSF', 'FIN'):
            mode = None
            continue
        if not s or s.startswith('%'):
            continue
        parts = s.split()
        if mode == 'nodes' and len(parts) >= 4:
            try:
                nodes[parts[0]] = tuple(float(x.replace('D', 'E')) for x in parts[1:4])
            except ValueError:
                pass
        elif mode == 'tets' and len(parts) >= 11:
            tets.append(parts[1:11])
    if not nodes or not tets:
        raise SystemExit(f'could not parse COOR_3D/TETRA10 from {path}')

    qualities, volumes = [], []
    for ids in tets:
        a, b, c, d = (nodes[x] for x in ids[:4])
        def sub(x, y):
            return tuple(x[i] - y[i] for i in range(3))
        ab, ac, ad = sub(b, a), sub(c, a), sub(d, a)
        cross = (ac[1] * ad[2] - ac[2] * ad[1],
                 ac[2] * ad[0] - ac[0] * ad[2],
                 ac[0] * ad[1] - ac[1] * ad[0])
        volume = abs(sum(ab[i] * cross[i] for i in range(3))) / 6.0
        pts = (a, b, c, d)
        edge_sq_sum = 0.0
        for i in range(4):
            for j in range(i + 1, 4):
                edge_sq_sum += sum((pts[i][k] - pts[j][k]) ** 2 for k in range(3))
        # Corner-node tetra mean-ratio proxy. A regular linear tetrahedron gives 1.0.
        q = 12.0 * (3.0 * volume) ** (2.0 / 3.0) / edge_sq_sum if volume > 0 and edge_sq_sum > 0 else 0.0
        qualities.append(q if math.isfinite(q) else 0.0)
        volumes.append(volume)
    qualities.sort()
    def pct(p):
        return qualities[min(len(qualities) - 1, max(0, int(round((len(qualities) - 1) * p))))]
    return {
        'tetra10_count': len(tets),
        'corner_tet_volume_min_mm3': min(volumes),
        'mean_ratio_proxy_min': qualities[0],
        'mean_ratio_proxy_p05': pct(0.05),
        'mean_ratio_proxy_median': pct(0.50),
        'degenerate_corner_tets': sum(1 for v in volumes if v <= 1e-12),
    }


results = []
for name in levels:
    study = root / name / 'study'
    resu = study / 'astermax_c862_static.resu'
    comm = study / 'astermax_c862_static.comm'
    mail = study / 'astermax_c862_static.mail'
    mess = study / 'astermax_c862_static.mess'
    for p in (resu, comm, mail, mess, study / 'astermax_c862_static.rmed', study / 'AsterMax_C862_Structural.pmx'):
        if not p.is_file() or p.stat().st_size == 0:
            raise SystemExit(f'{name}: missing/empty {p.name}')
    mess_text = mess.read_text(encoding='utf-8', errors='replace')
    if re.search(r'<F>|ERREUR FATALE|FATAL_ERROR', mess_text, re.I):
        raise SystemExit(name + ': solver fatal marker')
    text = resu.read_text(encoding='utf-8', errors='replace')
    depl = table(text, 'PPM_DEPL', ['NOEUD', 'DX', 'DY', 'DZ'])
    sn = table(text, 'PPM_STRESS_N', ['NOEUD', 'SIXX', 'SIYY', 'SIZZ'])
    ss = table(text, 'PPM_STRESS_S', ['NOEUD', 'SIXY', 'SIYZ', 'SIXZ'])
    reac = table(text, 'PPM_REACTION', ['NOEUD', 'DX', 'DY', 'DZ'])
    disp = {n: math.sqrt(sum(v * v for v in xyz)) for n, xyz in depl.items()}
    umax_node = max(disp, key=disp.get)
    umax = disp[umax_node]
    def vm(n):
        sx, sy, sz = sn[n]
        xy, yz, xz = ss[n]
        return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                         + 3.0 * (xy * xy + yz * yz + xz * xz))
    mises = {n: vm(n) for n in sn}
    vm_node = max(mises, key=mises.get)
    vm_max = mises[vm_node]
    reaction = [sum(v[i] for v in reac.values()) for i in range(3)]
    comm_text = comm.read_text(encoding='utf-8', errors='replace')
    load_match = re.search(r"GROUP_NO=['\"]N_LOAD_XMAX_NODE['\"],\s*FX=([+\-0-9.eEdD]+)", comm_text)
    if not load_match:
        raise SystemExit(name + ': applied FX parse failed')
    fx = float(load_match.group(1).replace('D', 'E'))
    residual = [reaction[0] + fx, reaction[1], reaction[2]]
    residual_norm = math.sqrt(sum(x * x for x in residual))
    if residual_norm > 1e-3:
        raise SystemExit(f'{name}: reaction equilibrium residual {residual_norm} N')
    quality = parse_mail_quality(mail)
    if quality['degenerate_corner_tets'] or quality['mean_ratio_proxy_min'] <= 0:
        raise SystemExit(name + ': degenerate TETRA10 corner geometry')
    f = by_name[name]
    if sha(mail) != f['mail_sha256']:
        raise SystemExit(name + ': MAIL provenance mismatch')
    results.append({
        'name': name,
        'requested_maxh_mm': f['requested_maxh_mm'],
        'nodes': len(depl),
        'elements': quality['tetra10_count'],
        'mises_max_mpa': vm_max,
        'mises_max_node': vm_node,
        'disp_max_mm': umax,
        'disp_max_node': umax_node,
        'reaction_sum_n': reaction,
        'equilibrium_residual_norm_n': residual_norm,
        'reaction_equilibrium_verified': True,
        'mesh_quality_proxy': quality,
        'pmx_sha256': sha(study / 'AsterMax_C862_Structural.pmx'),
        'rmed_sha256': sha(study / 'astermax_c862_static.rmed'),
        'resu_sha256': sha(resu),
    })

if not (results[0]['nodes'] < results[1]['nodes'] < results[2]['nodes'] and
        results[0]['elements'] < results[1]['elements'] < results[2]['elements']):
    raise SystemExit('solved mesh family is not monotonically refined')


def rel(old, new):
    return abs(new - old) / max(abs(new), 1e-30)


du = rel(results[1]['disp_max_mm'], results[2]['disp_max_mm'])
ds = rel(results[1]['mises_max_mpa'], results[2]['mises_max_mpa'])
u_tol = 0.05
stress_tol = 0.05
u_ok = du <= u_tol
stress_ok = ds <= stress_tol

evidence = {
    'schema': 'astermax.c8.82.native-netgen-convergence.v1',
    'solver': 'Code_Aster 17.4.0',
    'unit_system': 'mm-N-MPa',
    'levels': results,
    'fine_pair_displacement_relative_change': du,
    'fine_pair_mises_relative_change': ds,
    'displacement_convergence_tolerance': u_tol,
    'mises_convergence_tolerance': stress_tol,
    'displacement_convergence_admitted': u_ok,
    'peak_mises_convergence_admitted': stress_ok,
    'solution_convergence_admitted': u_ok and stress_ok,
    'mesh_quality_metric': 'corner-node tetrahedral mean-ratio proxy; not a NetGen Jacobian metric',
    'all_reaction_balances_verified': True,
    'point_load_singularity_caveat': 'Fixture uses a concentrated nodal CLoad; peak stress is not assumed mesh-convergent.',
    'industrial_validation': False,
    'ansys_equivalence': False,
}
(root / 'C8.82_CONVERGENCE_QUALIFICATION.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
with (root / 'C8.82_CONVERGENCE.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['level', 'maxh_mm', 'nodes', 'tetra10', 'umax_mm', 'vmmax_mpa',
                'quality_min', 'quality_p05', 'quality_median', 'reaction_residual_n'])
    for x in results:
        q = x['mesh_quality_proxy']
        w.writerow([x['name'], x['requested_maxh_mm'], x['nodes'], x['elements'],
                    x['disp_max_mm'], x['mises_max_mpa'], q['mean_ratio_proxy_min'],
                    q['mean_ratio_proxy_p05'], q['mean_ratio_proxy_median'],
                    x['equilibrium_residual_norm_n']])
print(json.dumps(evidence, indent=2))
