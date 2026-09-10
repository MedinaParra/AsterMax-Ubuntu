#!/usr/bin/env python3
import argparse, hashlib, json, math, pathlib, sys

SCHEMA="astermax-cad-model-fidelity/v1"

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=True).encode("utf-8")

def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def finite3(v):
    return isinstance(v,list) and len(v)==3 and all(isinstance(x,(int,float)) and math.isfinite(float(x)) for x in v)

def fail(msg): raise ValueError(msg)

def build(doc):
    unit=doc.get("step_unit",{})
    state=unit.get("state")
    factor=unit.get("scale_to_mm")
    if state not in {"MM_NATIVE","RESCALE_REQUIRED"}: fail("STEP unit state must be resolved before model preparation")
    if not isinstance(factor,(int,float)) or not math.isfinite(float(factor)) or float(factor)<=0: fail("positive finite scale_to_mm required")
    if state=="MM_NATIVE" and abs(float(factor)-1.0)>1e-12: fail("MM_NATIVE requires scale_to_mm=1")
    geom=doc.get("geometry",{})
    if not finite3(geom.get("bbox_min_mm")) or not finite3(geom.get("bbox_max_mm")): fail("finite geometry bounding box required")
    dims=[float(b)-float(a) for a,b in zip(geom["bbox_min_mm"],geom["bbox_max_mm"])]
    if any(d<=0 for d in dims): fail("non-positive geometry extent")
    for k in ("solids","faces","edges"):
        if not isinstance(geom.get(k),int) or geom[k]<=0: fail(f"positive geometry.{k} required")
    mesh=doc.get("mesh",{})
    for k in ("nodes","elements"):
        if not isinstance(mesh.get(k),int) or mesh[k]<=0: fail(f"positive mesh.{k} required")
    if not str(mesh.get("element_family","")).strip(): fail("mesh.element_family required")
    model=doc.get("model",{})
    mats=model.get("materials",[]); bcs=model.get("boundary_conditions",[]); loads=model.get("loads",[])
    if not mats: fail("at least one material assignment required")
    if not bcs: fail("at least one boundary condition required")
    if not loads: fail("at least one load required")
    core={
      "schema":SCHEMA,
      "source_step_sha256":str(doc.get("source_step_sha256","")).lower(),
      "step_unit":{"state":state,"scale_to_mm":float(factor)},
      "geometry":{"bbox_min_mm":[float(x) for x in geom["bbox_min_mm"]],"bbox_max_mm":[float(x) for x in geom["bbox_max_mm"]],"solids":geom["solids"],"faces":geom["faces"],"edges":geom["edges"]},
      "mesh":{"nodes":mesh["nodes"],"elements":mesh["elements"],"element_family":mesh["element_family"]},
      "model":{"materials":mats,"boundary_conditions":bcs,"loads":loads}
    }
    s=core["source_step_sha256"]
    if len(s)!=64 or any(c not in "0123456789abcdef" for c in s): fail("valid source STEP sha256 required")
    return {"schema":SCHEMA,"fingerprint_sha256":sha(core),"contract":core,"status":"MODEL_FIDELITY_LOCKED"}

def verify(lock, downstream):
    if lock.get("schema")!=SCHEMA: fail("wrong lock schema")
    expected=lock.get("fingerprint_sha256")
    rebuilt=build(downstream)
    actual=rebuilt["fingerprint_sha256"]
    if expected!=actual: fail(f"stale/model drift detected: expected {expected}, got {actual}")
    return {"status":"PASS","fingerprint_sha256":actual,"stale_model":False}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--build"); ap.add_argument("--verify"); ap.add_argument("--lock"); ap.add_argument("--out")
    a=ap.parse_args()
    if a.build:
        r=build(json.load(open(a.build,encoding="utf-8")))
    elif a.verify and a.lock:
        r=verify(json.load(open(a.lock,encoding="utf-8")),json.load(open(a.verify,encoding="utf-8")))
    else: ap.error("use --build INPUT or --verify INPUT --lock LOCK")
    text=json.dumps(r,indent=2,sort_keys=True)
    if a.out: pathlib.Path(a.out).write_text(text+"\n",encoding="utf-8")
    print(text); return 0

if __name__=="__main__":
    try: sys.exit(main())
    except Exception as e:
        print("C9.96 REJECTED: "+str(e),file=sys.stderr); sys.exit(3)
