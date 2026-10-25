#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

old = '''                    "  \\\"deformation_state\\\": \\\"undeformed-contour\\\",\\n" +\n'''
new = '''                    "  \\\"deformation_state\\\": \\\"user-defined-x10-contour\\\",\\n" +\n'''
if old not in text:
    raise SystemExit('Inherited C8.69 deformation_state anchor not found; refusing inconsistent C8.73 evidence.')
text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path}: deformation_state now matches the verified final UserDefined x10 UI state')
