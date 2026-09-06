#!/usr/bin/env python3
import csv, json, math, pathlib, sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'artifact/c8-85')
LEVELS = ('coarse', 'medium', 'fine')
TOP_K = 20
CLUSTER_RADIUS_MM = 35.0


def parse_nodes(mail_path):
    nodes = {}
    mode = None
    for raw in mail_path.read_text(encoding='utf-8', errors='replace').splitlines():
        s = raw.strip()
        if s == 'COOR_3D':
            mode = 'nodes'; continue
        if s in ('FINSF', 'FIN'):
            mode = None; continue
        p = s.split()
        if mode == 'nodes' and len(p) >= 4:
            try:
                nodes[int(p[0].lstrip('N'))] = tuple(float(x.replace('D', 'E')) for x in p[1:4])
            except ValueError:
                pass
    if not nodes:
        raise SystemExit(f'No nodes parsed from {mail_path}')
    return nodes


def parse_table(text, marker, header):
    pos = text.find(marker)
    if pos < 0:
        raise SystemExit('Missing marker ' + marker)
    lines = text[pos:].splitlines()
    key = ';'.join(header)
    hi = next((i for i, line in enumerate(lines) if line.strip() == key), None)
    if hi is None:
        raise SystemExit('Missing header for ' + marker)
    rows = {}
    for line in lines[hi + 1:]:
        if rows and (not line.strip() or line.startswith('PPM_') or 'ASTER 17.' in line):
            break
        p = [x.strip() for x in line.split(';')]
        if len(p) != len(header):
            if rows: break
            continue
        try:
            node = int(p[0]); vals = [float(x.replace('D', 'E')) for x in p[1:]]
        except ValueError:
            if rows: break
            continue
        if not all(math.isfinite(x) for x in vals):
            raise SystemExit(f'Non-finite value in {marker} at node {node}')
        rows[node] = vals
    if not rows:
        raise SystemExit('Empty table ' + marker)
    return rows


def distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def von_mises(sn, ss, node):
    sx, sy, sz = sn[node]
    xy, yz, xz = ss[node]
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2) + 3 * (xy * xy + yz * yz + xz * xz))


points = []
level_summary = []
for level in LEVELS:
    study = ROOT / level / 'study'
    mail = study / 'astermax_c862_static.mail'
    resu = study / 'astermax_c862_static.resu'
    if not mail.is_file() or not resu.is_file():
        raise SystemExit(f'{level}: missing admitted C8.83 MAIL/RESU')
    nodes = parse_nodes(mail)
    text = resu.read_text(encoding='utf-8', errors='replace')
    sn = parse_table(text, 'PPM_STRESS_N', ['NOEUD', 'SIXX', 'SIYY', 'SIZZ'])
    ss = parse_table(text, 'PPM_STRESS_S', ['NOEUD', 'SIXY', 'SIYZ', 'SIXZ'])
    common = sorted(set(sn).intersection(ss).intersection(nodes))
    ranked = sorted(((von_mises(sn, ss, n), n, nodes[n]) for n in common), reverse=True)
    top = ranked[:TOP_K]
    if len(top) < TOP_K:
        raise SystemExit(f'{level}: fewer than {TOP_K} stress nodes')
    for rank, (vm, node, xyz) in enumerate(top, 1):
        points.append({'level': level, 'rank': rank, 'node': node, 'mises_mpa': vm, 'xyz_mm': xyz})
    level_summary.append({'level': level, 'peak_node': top[0][1], 'peak_mises_mpa': top[0][0], 'peak_xyz_mm': top[0][2]})

# Global-max migration is explicitly measured; a single-hotspot adaptation is only safe if maxima stay local.
peak_distances = {}
for a, b in (('coarse', 'medium'), ('medium', 'fine'), ('coarse', 'fine')):
    pa = next(x for x in level_summary if x['level'] == a)['peak_xyz_mm']
    pb = next(x for x in level_summary if x['level'] == b)['peak_xyz_mm']
    peak_distances[f'{a}_to_{b}_mm'] = distance(pa, pb)

global_peak_stationary = max(peak_distances.values()) <= CLUSTER_RADIUS_MM

# Build connected physical hotspot components from top-K stress nodes across all meshes.
adj = [set() for _ in points]
for i in range(len(points)):
    for j in range(i + 1, len(points)):
        if distance(points[i]['xyz_mm'], points[j]['xyz_mm']) <= CLUSTER_RADIUS_MM:
            adj[i].add(j); adj[j].add(i)

seen = set(); components = []
for i in range(len(points)):
    if i in seen: continue
    stack = [i]; seen.add(i); comp = []
    while stack:
        k = stack.pop(); comp.append(k)
        for j in adj[k]:
            if j not in seen:
                seen.add(j); stack.append(j)
    components.append(comp)

rois = []
for comp in components:
    members = [points[i] for i in comp]
    present = sorted(set(x['level'] for x in members))
    if present != sorted(LEVELS):
        continue
    if min(x['rank'] for x in members) > 5:
        continue
    xs = [x['xyz_mm'][0] for x in members]; ys = [x['xyz_mm'][1] for x in members]; zs = [x['xyz_mm'][2] for x in members]
    centroid = (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))
    radius = max(distance(x['xyz_mm'], centroid) for x in members)
    by_level = {}
    for level in LEVELS:
        lm = sorted((x for x in members if x['level'] == level), key=lambda x: x['rank'])
        by_level[level] = {'best_rank': lm[0]['rank'], 'best_node': lm[0]['node'], 'best_mises_mpa': lm[0]['mises_mpa'], 'best_xyz_mm': lm[0]['xyz_mm']}
    rois.append({
        'centroid_mm': centroid,
        'envelope_min_mm': (min(xs), min(ys), min(zs)),
        'envelope_max_mm': (max(xs), max(ys), max(zs)),
        'component_radius_mm': radius,
        'member_count': len(members),
        'levels': by_level,
        'max_mises_mpa': max(x['mises_mpa'] for x in members),
        'best_rank_any_level': min(x['rank'] for x in members),
    })

rois.sort(key=lambda r: (-r['max_mises_mpa'], r['best_rank_any_level']))
for i, roi in enumerate(rois, 1): roi['roi_id'] = f'ROI-{i:02d}'

multi_roi_ready = len(rois) >= 2
single_hotspot_refinement_admitted = global_peak_stationary
adaptive_strategy = 'multi_roi' if multi_roi_ready and not single_hotspot_refinement_admitted else ('single_roi' if single_hotspot_refinement_admitted else 'not_admitted')

evidence = {
    'schema': 'astermax.c8.85.hotspot-roi-qualification.v1',
    'source': {
        'workflow_run': 34033613470,
        'head_sha': '86302f91a4974eb1ae8b5a813d144c845589707c',
        'artifact_digest': 'sha256:6ab45a9ab22d4a7535d580705be36999ac8586576f39ce807fcbf79e801c221e',
        'solver': 'Code_Aster 17.4.0',
        'unit_system': 'mm-N-MPa'
    },
    'analysis_contract': {
        'top_k_per_mesh': TOP_K,
        'physical_cluster_radius_mm': CLUSTER_RADIUS_MM,
        'persistent_roi_requires_all_levels': True,
        'persistent_roi_requires_top5_member': True,
    },
    'level_peaks': level_summary,
    'global_peak_migration': peak_distances,
    'global_peak_stationary': global_peak_stationary,
    'persistent_rois': rois,
    'persistent_roi_count': len(rois),
    'single_hotspot_refinement_admitted': single_hotspot_refinement_admitted,
    'multi_roi_refinement_ready': multi_roi_ready,
    'recommended_adaptive_strategy': adaptive_strategy,
    'new_solver_results_generated': False,
    'source_solver_results_reused_without_modification': True,
    'mesh_adaptation_verified': False,
    'industrial_validation': False,
    'ansys_equivalence': False,
}

(ROOT / 'C8.85_HOTSPOT_ROI.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
with (ROOT / 'C8.85_TOPK_HOTSPOTS.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['level','rank','node','mises_mpa','x_mm','y_mm','z_mm'])
    for p in sorted(points, key=lambda x: (LEVELS.index(x['level']), x['rank'])):
        w.writerow([p['level'], p['rank'], p['node'], p['mises_mpa'], *p['xyz_mm']])

print(json.dumps(evidence, indent=2))
if not rois:
    raise SystemExit('No persistent multi-mesh stress ROI found; local refinement target not admitted')
