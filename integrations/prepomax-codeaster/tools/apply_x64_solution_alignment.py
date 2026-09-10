#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
sln = root / 'PrePoMax.sln'
csproj = root / 'UserControls' / 'UserControls.csproj'

sln_text = sln.read_text(encoding='utf-8-sig')
csproj_text = csproj.read_text(encoding='utf-8-sig')

required_csproj = [
    "Condition=\"'$(Configuration)|$(Platform)' == 'Release|x64'\"",
    '<PlatformTarget>x64</PlatformTarget>',
    '<OutputPath>bin\\x64\\Release\\</OutputPath>',
]
for token in required_csproj:
    if token not in csproj_text:
        raise SystemExit(f'C8.76 UserControls x64 project contract missing: {token}')

project = '{74EA83FB-2743-49EE-85A8-5B42CBCE19B3}'
replacements = {
    f'{project}.Debug|x64.ActiveCfg = Debug|Any CPU': f'{project}.Debug|x64.ActiveCfg = Debug|x64',
    f'{project}.Debug|x64.Build.0 = Debug|Any CPU': f'{project}.Debug|x64.Build.0 = Debug|x64',
    f'{project}.Release|x64.ActiveCfg = Release|Any CPU': f'{project}.Release|x64.ActiveCfg = Release|x64',
    f'{project}.Release|x64.Build.0 = Release|Any CPU': f'{project}.Release|x64.Build.0 = Release|x64',
}
for old, new in replacements.items():
    count = sln_text.count(old)
    if count != 1:
        raise SystemExit(f'C8.76 expected exactly one solution mapping anchor, found {count}: {old}')
    sln_text = sln_text.replace(old, new, 1)

if f'{project}.Release|x64.ActiveCfg = Release|Any CPU' in sln_text:
    raise SystemExit('C8.76 UserControls Release x64 solution mapping remained Any CPU')

sln.write_text(sln_text, encoding='utf-8-sig')
print('C8.76 aligned UserControls solution mapping to native x64 for Debug/Release')
