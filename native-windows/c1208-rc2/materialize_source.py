"""Reconstruct and verify the exact shipped RC1 source on native Windows.

The four duplicate case aliases in the Linux cross-build are normalized to the
upstream filename. Their contents were verified identical before normalization.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    here = Path(__file__).resolve().parent
    manifest = json.loads((here / 'source-manifest.json').read_text())
    archive = here / 'source-overlay.zip'
    if digest(archive) != manifest['overlay_sha256']:
        raise SystemExit('Source overlay checksum mismatch')
    root = args.root.resolve()
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != manifest['upstream_commit']:
        raise SystemExit('Unexpected upstream checkout: ' + head)
    # Windows Git may convert LF to CRLF. Restore the exact committed bytes
    # before applying the snapshot, instead of weakening the checksum gate.
    raw = subprocess.check_output(['git', '-C', str(root), 'archive', '--format=tar', head])
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as upstream:
        for member in upstream:
            if not member.isfile():
                continue
            target = (root / member.name).resolve()
            if root not in target.parents:
                raise SystemExit('Unsafe upstream archive path')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(upstream.extractfile(member).read())
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            target = (root / member.filename).resolve()
            if root not in target.parents:
                raise SystemExit('Unsafe source overlay path')
        z.extractall(root)
    mismatches = []
    for name, expected in manifest['source_files'].items():
        file = root / name
        if not file.is_file() or digest(file) != expected:
            mismatches.append(name)
    extras = [str(p.relative_to(root)) for p in root.rglob('*')
              if p.is_file() and '.git' not in p.relative_to(root).parts
              and p.relative_to(root).as_posix() not in manifest['source_files']]
    report = {'source_files_verified': len(manifest['source_files']),
              'upstream_commit': manifest['upstream_commit'],
              'overlay_sha256': manifest['overlay_sha256'],
              'case_aliases_normalized': manifest['case_aliases_normalized'],
              'mismatches': mismatches, 'extra_files': extras}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    if mismatches or extras:
        raise SystemExit('Source reconstruction mismatch: ' + json.dumps(report))
    print('Verified exact source snapshot:', len(manifest['source_files']), 'files')


if __name__ == '__main__':
    main()
