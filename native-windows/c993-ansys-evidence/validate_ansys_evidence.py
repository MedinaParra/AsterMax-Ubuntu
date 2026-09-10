#!/usr/bin/env python3
import argparse, hashlib, json, math, pathlib, sys

SCHEMA = "astermax-ansys-reference/v1"
ALLOWED_BENCHMARKS = {"B01", "B02", "B03", "B04", "B05"}

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def finite_number(v):
    return isinstance(v, (int, float)) and math.isfinite(float(v))

def fail(msg):
    raise ValueError(msg)

def validate_reference(doc, evidence_path=None):
    if doc.get("schema") != SCHEMA:
        fail("unsupported schema")
    if doc.get("benchmark_id") not in ALLOWED_BENCHMARKS:
        fail("unknown benchmark_id")
    if doc.get("solver", {}).get("product") != "ANSYS Mechanical":
        fail("solver.product must be ANSYS Mechanical")
    if not str(doc.get("solver", {}).get("version", "")).strip():
        fail("solver.version is required")
    prov = doc.get("provenance", {})
    if prov.get("independent") is not True:
        fail("ANSYS reference must be independently obtained")
    if prov.get("synthetic") is not False:
        fail("synthetic ANSYS values are forbidden")
    if prov.get("fea_values_invented") is not False:
        fail("fea_values_invented must be false")
    if prov.get("source_kind") not in {"ANSYS_EXPORT", "ANSYS_REPORT"}:
        fail("source_kind must be ANSYS_EXPORT or ANSYS_REPORT")
    source_sha = str(prov.get("source_sha256", "")).lower()
    if len(source_sha) != 64 or any(c not in "0123456789abcdef" for c in source_sha):
        fail("valid source_sha256 required")
    if evidence_path:
        actual = sha256_file(evidence_path)
        if actual != source_sha:
            fail("ANSYS evidence file hash mismatch")
    contract = doc.get("model_contract", {})
    if contract.get("units") != {"length":"mm","force":"N","stress":"MPa"}:
        fail("unit contract must be mm/N/MPa")
    if not str(contract.get("contract_sha256", "")).strip():
        fail("model contract hash required")
    mesh = contract.get("mesh", {})
    if not isinstance(mesh.get("nodes"), int) or mesh.get("nodes") <= 0:
        fail("positive mesh.nodes required")
    if not isinstance(mesh.get("elements"), int) or mesh.get("elements") <= 0:
        fail("positive mesh.elements required")
    results = doc.get("results", {})
    if not results:
        fail("at least one result quantity required")
    for name, item in results.items():
        if not finite_number(item.get("value")):
            fail(f"non-finite result: {name}")
        if not str(item.get("unit", "")).strip():
            fail(f"unit required: {name}")
    return True

def compare(ansys_doc, code_aster_doc, tolerances):
    out = {"schema":"astermax-ansys-comparison/v1", "benchmark_id":ansys_doc["benchmark_id"], "quantities":{}, "passed":True}
    if code_aster_doc.get("benchmark_id") != ansys_doc.get("benchmark_id"):
        fail("benchmark mismatch")
    if code_aster_doc.get("model_contract", {}).get("contract_sha256") != ansys_doc.get("model_contract", {}).get("contract_sha256"):
        fail("model contract hash mismatch")
    for q, tol in tolerances.items():
        if q not in ansys_doc.get("results", {}) or q not in code_aster_doc.get("results", {}):
            fail(f"missing comparison quantity: {q}")
        a=float(ansys_doc["results"][q]["value"]); c=float(code_aster_doc["results"][q]["value"])
        denom=max(abs(a), abs(c), 1e-30)
        rel=abs(a-c)/denom*100.0
        passed=rel <= float(tol)
        out["quantities"][q]={"ansys":a,"code_aster":c,"relative_difference_percent":rel,"tolerance_percent":float(tol),"passed":passed}
        out["passed"] = out["passed"] and passed
    out["ansys_equivalence"] = "PROVEN_FOR_THIS_BENCHMARK" if out["passed"] else "FAILED_FOR_THIS_BENCHMARK"
    return out

def self_test():
    # Mathematical comparator test only. These are NOT FEA results and can never pass validate_reference().
    a={"benchmark_id":"B01","model_contract":{"contract_sha256":"x"},"results":{"Q":{"value":100.0,"unit":"u"}}}
    c={"benchmark_id":"B01","model_contract":{"contract_sha256":"x"},"results":{"Q":{"value":101.0,"unit":"u"}}}
    r=compare(a,c,{"Q":2.0})
    assert r["passed"] is True
    c["results"]["Q"]["value"]=104.0
    r=compare(a,c,{"Q":2.0})
    assert r["passed"] is False
    print("C9.93 comparator self-test PASS (non-FEA arithmetic fixture)")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ansys")
    ap.add_argument("--evidence-file")
    ap.add_argument("--code-aster")
    ap.add_argument("--tolerances")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test(); return 0
    if not args.ansys:
        ap.error("--ansys required")
    ansys=json.load(open(args.ansys, encoding="utf-8"))
    validate_reference(ansys, args.evidence_file)
    print("ANSYS_REFERENCE_PROVENANCE=VERIFIED")
    if args.code_aster:
        ca=json.load(open(args.code_aster, encoding="utf-8"))
        tol=json.loads(args.tolerances or "{}")
        result=compare(ansys, ca, tol)
        text=json.dumps(result, indent=2, sort_keys=True)
        if args.out: pathlib.Path(args.out).write_text(text+"\n", encoding="utf-8")
        print(text)
        return 0 if result["passed"] else 2
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as e:
        print(f"C9.93 REJECTED: {e}", file=sys.stderr)
        sys.exit(3)
