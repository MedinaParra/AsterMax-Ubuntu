#!/usr/bin/env python3
import argparse, json, pathlib, re, sys

# Conservative STEP unit preflight. It does not parse geometry and does not claim successful CAD import.
# It only proves whether the STEP text declares millimetre-compatible SI length units or a known conversion.

SI_PREFIX_TO_MM = {
    None: 1000.0,
    'MILLI': 1.0,
    'CENTI': 10.0,
    'DECI': 100.0,
    'MICRO': 0.001,
    'KILO': 1_000_000.0,
}

KNOWN_CONVERSION_MM = {
    'INCH': 25.4,
    'FOOT': 304.8,
}

def inspect_step(text: str):
    upper = text.upper()
    evidence = []
    scale_to_mm = None
    declared = None

    # Common ISO-10303 SI unit form, e.g. SI_UNIT(.MILLI.,.METRE.)
    m = re.search(r"SI_UNIT\s*\(\s*(\$|\.[A-Z]+\.)\s*,\s*\.METRE\.\s*\)", upper)
    if m:
        token = m.group(1)
        prefix = None if token == '$' else token.strip('.')
        if prefix in SI_PREFIX_TO_MM:
            scale_to_mm = SI_PREFIX_TO_MM[prefix]
            declared = ('metre' if prefix is None else prefix.lower() + 'metre')
            evidence.append(m.group(0))

    # Explicit conversion names frequently emitted by CAD exporters.
    if scale_to_mm is None:
        for name, factor in KNOWN_CONVERSION_MM.items():
            if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'" + name + r"'", upper):
                scale_to_mm = factor
                declared = name.lower()
                evidence.append(name)
                break

    status = 'UNKNOWN'
    if scale_to_mm is not None:
        status = 'MM_NATIVE' if abs(scale_to_mm - 1.0) < 1e-12 else 'RESCALE_REQUIRED'

    return {
        'schema': 'astermax-step-unit-preflight/v1',
        'declared_length_unit': declared,
        'scale_to_mm': scale_to_mm,
        'status': status,
        'evidence': evidence,
        'safe_for_direct_mm_import': status == 'MM_NATIVE',
        'geometry_import_proven': False,
        'fea_values_invented': False,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('step_file')
    ap.add_argument('--json-out')
    ap.add_argument('--require-mm-native', action='store_true')
    args = ap.parse_args()
    p = pathlib.Path(args.step_file)
    if not p.is_file():
        print('STEP_UNIT_GUARD=FILE_NOT_FOUND', file=sys.stderr); return 4
    text = p.read_text(encoding='utf-8', errors='ignore')
    result = inspect_step(text)
    out = json.dumps(result, indent=2, sort_keys=True)
    print(out)
    if args.json_out:
        pathlib.Path(args.json_out).write_text(out + '\n', encoding='utf-8')
    if args.require_mm_native and result['status'] != 'MM_NATIVE':
        return 2
    return 0 if result['status'] != 'UNKNOWN' else 3

if __name__ == '__main__':
    sys.exit(main())
