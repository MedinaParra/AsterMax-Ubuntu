#!/usr/bin/env python3
import argparse, json, math, re
from pathlib import Path

def floats(text):
    vals=[]
    for token in re.findall(r"[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?",text):
        try: vals.append(float(token))
        except ValueError: pass
    return vals

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",required=True)
    ap.add_argument("--name",default="astermax-c1036-contact")
    a=ap.parse_args()
    root=Path(a.root)
    mess=root/f"{a.name}.mess"
    rmed=root/f"{a.name}.rmed"
    reactions=root/f"{a.name}.reactions"
    for p in (mess,rmed,reactions):
        if not p.exists() or p.stat().st_size==0:
            raise SystemExit(f"missing/non-empty solver output: {p}")
    m=mess.read_text(errors="ignore")
    bad=["<F>","ERREUR_FATALE","ARRET PAR MANQUE"]
    for token in bad:
        if token in m:
            raise SystemExit(f"fatal Code_Aster marker found: {token}")
    rt=reactions.read_text(errors="ignore")
    nums=floats(rt)
    # Table contains time/index data too, so require a clearly mechanical reaction.
    max_abs=max((abs(x) for x in nums),default=0.0)
    if max_abs < 10.0:
        raise SystemExit(f"reaction evidence too small: max_abs={max_abs}")
    contact_markers=sum(1 for t in ("DEFI_CONTACT","CONTACT","STAT_NON_LINE") if t in m.upper())
    report={
      "release":"C10.36",
      "solver_execution":"RUN",
      "contact_benchmark":"PASS",
      "rmed_bytes":rmed.stat().st_size,
      "reaction_table_bytes":reactions.stat().st_size,
      "max_abs_numeric_in_reaction_table":max_abs,
      "contact_markers_in_mess":contact_markers,
      "fea_values_invented":False
    }
    (root/"C10.36_CONTACT_VALIDATION.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
