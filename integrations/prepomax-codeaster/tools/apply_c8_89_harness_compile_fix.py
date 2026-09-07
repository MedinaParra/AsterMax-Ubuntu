#!/usr/bin/env python3
from pathlib import Path
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    args = ap.parse_args()
    path = Path(args.repo).resolve() / "PrePoMax" / "AsterMaxAI" / "AsterMaxNativeRoiConsumerHarness.cs"
    text = path.read_text(encoding="utf-8-sig")
    old = "if(!geometry.Nodes.TryGetValue(id,out node) || node==null) continue;"
    new = "if(!geometry.Nodes.TryGetValue(id,out node)) continue;"
    if text.count(old) != 1:
        if new in text:
            raise RuntimeError("C8.89b compile fix already present; refusing duplicate patch")
        raise RuntimeError("C8.89b expected exactly one FeNode value-type guard, found %d" % text.count(old))
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("C8.89b FeNode value-type compile contract applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
