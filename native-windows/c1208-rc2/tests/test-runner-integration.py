"""Run the actual adapter with an explicitly synthetic native backend.

This verifies adapter orchestration and file ownership, not Code_Aster, MED
validity, the application GUI, or any engineering result. On Windows it uses a
real CMD launcher; on Linux it uses an executable Python fixture.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid


FIXTURE = r'''#!/usr/bin/env python3
import os, pathlib, sys, time
p = pathlib.Path.cwd()
mode = os.environ['ASTERMAX_TEST_MODE']
for name in ['CODE_ASTER_RUNNER_STDOUT.log', 'CODE_ASTER_RUNNER_STDERR.log', 'ASTERMAX_SOLVE_STATE.json']:
    if (p/name).exists():
        print('test-error: live caller file leaked into stage', file=sys.stderr)
        sys.exit(93)
print('fixture-out-start', flush=True)
print('fixture-err-start', file=sys.stderr, flush=True)
if mode == 'large':
    print('x' * 150000, flush=True)
    print('y' * 150000, file=sys.stderr, flush=True)
if mode == 'fatal':
    (p/'study.mess').write_text('<F> <TEST_42>\nSYNTHETIC TEST FATAL\nEXIT_CODE=0\n')
else:
    (p/'study.mess').write_text('SYNTHETIC TEST ONLY\nCODE_ASTER\nARRET NORMAL\nEXIT_CODE=0\n')
if mode != 'missing':
    (p/'study.rmed').write_bytes(b'SYNTHETIC TEST, NOT A MED FILE')
for name in ['CODE_ASTER_RUNNER_STDOUT.log', 'CODE_ASTER_RUNNER_STDERR.log', 'ASTERMAX_SOLVE_STATE.json', 'ASTERMAX_SOLVE_STATE.json.stale.tmp']:
    (p/name).write_text('stale-stage-content')
print('fixture-out-end', flush=True)
print('fixture-err-end', file=sys.stderr, flush=True)
sys.exit(17 if mode == 'nonzero' else 0)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runner', required=True, type=Path)
    ap.add_argument('--pwsh', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    root = args.out.resolve() / ('integration-' + uuid.uuid4().hex)
    root.mkdir()
    if os.name == 'nt':
        backend_script = root / 'synthetic-native-backend.py'
        backend_script.write_text(FIXTURE)
        backend = root / 'synthetic-native-backend.cmd'
        backend.write_text('@echo off\n"' + sys.executable + '" "' + str(backend_script) + '" %*\nexit /b %errorlevel%\n')
    else:
        backend = root / 'synthetic-native-backend.exe'
        backend.write_text(FIXTURE)
        backend.chmod(0o700)
    checks = []

    def check(condition, label):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print('PASS:', label, flush=True)

    for mode, code, marker in [('success', 0, None), ('large', 0, None), ('fatal', 31, 'TEST_42'), ('nonzero', 17, 'NATIVE_PROCESS_EXIT'), ('missing', 30, 'MISSING_OUTPUT')]:
        workspace = root / ('workspace ñ [literal] ' + mode)
        workspace.mkdir()
        (workspace / 'study.export').write_text('P version stable\nP time_limit 60\nP memory_limit 512\nF comm ./study.comm D 1\nF mess ./study.mess R 6\nF rmed ./study.rmed R 80\n')
        (workspace / 'study.comm').write_text('# SYNTHETIC TEST, NOT A REAL SOLVE\n')
        (workspace / 'ASTERMAX_SOLVE_STATE.json').write_text('CANCELLING:revision=5')
        (workspace / 'ASTERMAX_SOLVE_STATE.json.stale.tmp').write_text('live-state-temporary')
        (workspace / 'ASTERMAX_SOLVE_TRANSACTION.json').write_text('{"synthetic_test_only":true}')
        env = os.environ.copy()
        env.update(ASTERMAX_WINDOWS_CODE_ASTER_COMMAND=str(backend), ASTERMAX_TEST_MODE=mode, PUBLIC=str(root), LOCALAPPDATA=str(root))
        outpath = workspace / 'CODE_ASTER_RUNNER_STDOUT.log'
        errpath = workspace / 'CODE_ASTER_RUNNER_STDERR.log'
        with outpath.open('wb', buffering=0) as out, errpath.open('wb', buffering=0) as err:
            out.write(b'caller-out-before|')
            err.write(b'caller-err-before|')
            proc = subprocess.Popen([str(args.pwsh.resolve()), '-NoLogo', '-NoProfile', '-File', str(args.runner.resolve()), str(workspace / 'study.export'), str(workspace)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

            def drain(pipe, log):
                while True:
                    chunk = pipe.read(2048)
                    if not chunk:
                        break
                    log.write(chunk)

            threads = [threading.Thread(target=drain, args=(proc.stdout, out)), threading.Thread(target=drain, args=(proc.stderr, err))]
            for thread in threads:
                thread.start()
            try:
                actual_code = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise
            finally:
                for thread in threads:
                    thread.join(timeout=5)
            check(all(not t.is_alive() for t in threads), mode + ': console drains finished')
            out.write(b'|caller-out-after')
            err.write(b'|caller-err-after')
        stdout, stderr = outpath.read_bytes(), errpath.read_bytes()
        check(actual_code == code, f'{mode}: exit {code}, got {actual_code}')
        check(stdout.startswith(b'caller-out-before|') and stdout.endswith(b'|caller-out-after'), mode + ': caller stdout preserved')
        check(stderr.startswith(b'caller-err-before|') and stderr.endswith(b'|caller-err-after'), mode + ': caller stderr preserved')
        check(b'stale-stage-content' not in stdout + stderr, mode + ': stale stage never promoted into caller logs')
        check((workspace / 'ASTERMAX_SOLVE_STATE.json').read_text() == 'CANCELLING:revision=5', mode + ': cancellation state preserved')
        check((workspace / 'ASTERMAX_SOLVE_STATE.json.stale.tmp').read_text() == 'live-state-temporary', mode + ': temporary state preserved')
        check(stdout.count(b'fixture-out-start') == 1 and stdout.count(b'fixture-out-end') == 1, mode + ': stdout streamed once')
        check(stderr.count(b'fixture-err-start') == 1 and stderr.count(b'fixture-err-end') == 1, mode + ': stderr streamed once')
        if code == 0:
            check(b'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS' in stdout, mode + ': success marker present')
            check((workspace / 'study.rmed').read_bytes() == b'SYNTHETIC TEST, NOT A MED FILE', mode + ': synthetic output copied')
            check((workspace / 'astermax-native.stdout.log').read_bytes().count(b'fixture-out-end') == 1, mode + ': native log retained')
            if mode == 'large':
                check((workspace / 'astermax-native.stdout.log').stat().st_size > 150000, 'large: complete stdout, not bounded tail')
                check((workspace / 'astermax-native.stderr.log').stat().st_size > 150000, 'large: complete stderr, not bounded tail')
            check(not list(workspace.glob('failed-*')), mode + ': no failed diagnostic directory')
        else:
            check(b'ASTERMAX_CODE_ASTER_RUNNER=SUCCESS' not in stdout, mode + ': no false success marker')
            check(not (workspace / 'study.rmed').exists(), mode + ': failed output not promoted')
            failures = list(workspace.glob('failed-*/astermax-runner-diagnostic.json'))
            check(len(failures) == 1, mode + ': structured failure retained')
            diagnostic = json.loads(failures[0].read_text())
            check(diagnostic['marker'] == marker, mode + ': correct diagnostic marker')
    version = subprocess.check_output([str(args.pwsh.resolve()), '-NoLogo', '-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], text=True).strip()
    report = {'passed': len(checks), 'checks': checks, 'platform': os.name, 'powershell_version': version, 'synthetic_native_backend': True, 'windows_powershell_5_1': ('PASS' if os.name == 'nt' and version.startswith('5.1') else 'NOT_RUN'), 'real_code_aster': 'NOT_RUN', 'engineering_result': False, 'root': str(root)}
    (args.out / 'integration-summary.json').write_text(json.dumps(report, indent=2))
    print('TOTAL PASS:', len(checks))
    print('PLATFORM:', os.name, 'POWERSHELL:', version)
    print('GUI, REAL CODE_ASTER, MED VALIDITY: NOT_RUN')


if __name__ == '__main__':
    main()
