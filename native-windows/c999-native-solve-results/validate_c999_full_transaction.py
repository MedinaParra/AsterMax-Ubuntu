#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, sys


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path: pathlib.Path):
    with path.open('r', encoding='utf-8-sig') as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate C9.99 full native solve-to-results transaction')
    ap.add_argument('--transaction', required=True)
    ap.add_argument('--bundle', required=True)
    ap.add_argument('--med', required=True)
    ap.add_argument('--vtu', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    tx_path = pathlib.Path(a.transaction)
    bundle_path = pathlib.Path(a.bundle)
    med_path = pathlib.Path(a.med)
    vtu_path = pathlib.Path(a.vtu)
    out_path = pathlib.Path(a.out)

    tx = load(tx_path)
    bundle = load(bundle_path)
    fp = str(tx.get('model_fingerprint') or '').lower()
    integrity = bundle.get('integrity') or {}
    result_fp = str(integrity.get('model_fingerprint_sha256') or '').lower()
    tx_outputs = tx.get('output_sha256') or {}

    checks = {
        'c989_transaction_passed': tx.get('passed') is True and tx.get('solver_execution') == 'COMPLETED_VERIFIED',
        'c989_result_state_current': tx.get('result_state') == 'CURRENT',
        'fingerprint_present': len(fp) == 64 and all(c in '0123456789abcdef' for c in fp),
        'bundle_schema_supported': bundle.get('schema') == 'astermax-results-bundle/v0',
        'bundle_non_synthetic': integrity.get('fea_values_invented') is False,
        'binding_did_not_modify_fea': integrity.get('result_values_modified_by_binding') is False,
        'bundle_matches_solve_fingerprint': result_fp == fp,
        'med_exists_nonempty': med_path.is_file() and med_path.stat().st_size > 0,
        'med_hash_matches_c989': med_path.is_file() and tx_outputs.get(med_path.name) == sha256(med_path),
        'vtu_exists_nonempty': vtu_path.is_file() and vtu_path.stat().st_size > 0,
    }

    mesh = bundle.get('mesh') or {}
    checks['result_mesh_nonempty'] = int(mesh.get('node_count') or 0) > 0 and int(mesh.get('element_count') or 0) > 0
    units = bundle.get('units') or {}
    checks['mm_n_mpa_contract'] = units.get('length') == 'mm' and units.get('force') == 'N' and units.get('stress') == 'MPa'

    passed = all(checks.values())
    manifest = {
        'schema': 'astermax-native-solve-results-transaction/v1',
        'release': 'C9.99',
        'passed': passed,
        'checks': checks,
        'model_fingerprint_sha256': fp,
        'med_sha256': sha256(med_path) if med_path.is_file() else None,
        'bundle_sha256': sha256(bundle_path) if bundle_path.is_file() else None,
        'vtu_sha256': sha256(vtu_path) if vtu_path.is_file() else None,
        'solution_state': 'SOLUTION_CURRENT' if passed else 'SOLUTION_UNTRUSTED',
        'solver_backend': 'Code_Aster',
        'fea_values_invented': False,
        'ansys_equivalence': 'NOT_PROVEN',
        'truth_boundary': 'C9.99 proves continuity from a verified real Code_Aster transaction into the bound post-processing bundle; it does not claim ANSYS numerical equivalence.'
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    sys.exit(main())
