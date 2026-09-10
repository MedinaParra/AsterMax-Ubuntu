#!/usr/bin/env python3
import argparse, hashlib, json, re, sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path):
    with path.open('r', encoding='utf-8-sig') as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate AsterMax C9.89 native solve transaction')
    ap.add_argument('--workdir', required=True)
    ap.add_argument('--expected-input-hashes', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    wd = Path(args.workdir)
    expected = load_json(Path(args.expected_input_hashes))
    out = Path(args.out)

    required = {
        'model': wd / 'c988.model.json',
        'mail': wd / 'c988.mail',
        'comm': wd / 'c988.comm',
        'adapter': wd / 'c988.adapter.json',
        'semantic_gate': wd / 'C9.88_SEMANTIC_GATE.json',
        'validation': wd / 'C9.88_VALIDATION.json',
        'native_evidence': wd / 'native-serializer-evidence.json',
        'mess': wd / 'c988.mess',
        'resu': wd / 'c988.resu',
        'rmed': wd / 'c988.rmed',
    }

    checks = {}
    missing = [k for k,p in required.items() if not p.exists()]
    checks['required_files_present'] = not missing

    current_inputs = {}
    for key in ('model','mail','comm','adapter','semantic_gate','validation','native_evidence'):
        p = required[key]
        if p.exists(): current_inputs[p.name] = sha256(p)
    checks['input_hash_lock_preserved'] = current_inputs == expected

    semantic = load_json(required['semantic_gate']) if required['semantic_gate'].exists() else {}
    validation = load_json(required['validation']) if required['validation'].exists() else {}
    native = load_json(required['native_evidence']) if required['native_evidence'].exists() else {}

    checks['semantic_gate_passed'] = bool(semantic.get('passed', False))
    checks['solve_was_authorized'] = validation.get('solve_authorization') == 'READY'
    checks['pre_solve_claim_was_not_run'] = validation.get('solver_execution') == 'NOT_RUN'
    checks['native_serializer_non_mutating'] = bool(native.get('serializer_non_mutating', False))
    checks['native_fingerprint_stable'] = bool(native.get('fingerprint_before')) and native.get('fingerprint_before') == native.get('fingerprint_after')

    mess_text = required['mess'].read_text(encoding='utf-8', errors='ignore') if required['mess'].exists() else ''
    checks['code_aster_normal_stop'] = re.search(r'ARRET\s+NORMAL', mess_text, re.IGNORECASE) is not None
    checks['med_nonempty'] = required['rmed'].exists() and required['rmed'].stat().st_size > 0
    checks['resu_nonempty'] = required['resu'].exists() and required['resu'].stat().st_size > 0

    output_hashes = {}
    for key in ('mess','resu','rmed'):
        p = required[key]
        if p.exists() and p.stat().st_size > 0:
            output_hashes[p.name] = sha256(p)

    passed = all(checks.values())
    manifest = {
        'schema': 'astermax-solve-transaction/v1',
        'release': 'C9.89',
        'passed': passed,
        'checks': checks,
        'missing': missing,
        'model_fingerprint': native.get('fingerprint_before'),
        'input_sha256': current_inputs,
        'output_sha256': output_hashes,
        'solver_execution': 'COMPLETED_VERIFIED' if passed else 'REJECTED',
        'result_state': 'CURRENT' if passed else 'UNTRUSTED',
        'fea_values_invented': False,
        'ansys_equivalence': 'NOT_PROVEN',
        'truth_boundary': 'C9.89 verifies transaction integrity and Code_Aster completion; it does not establish ANSYS numerical equivalence.'
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    sys.exit(main())
