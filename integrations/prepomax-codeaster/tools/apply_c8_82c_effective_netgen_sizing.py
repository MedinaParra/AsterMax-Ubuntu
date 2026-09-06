#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'AsterMaxAI' / 'AsterMaxStepMeshHarness.cs'
text = path.read_text(encoding='utf-8-sig')

old_ids = '''                    p.CreationIds = new int[] { targetPartId };'''
new_ids = '''                    // C8.82c: CreationIds are geometry IDs, not raw BasePart.PartId values.
                    // Controller.GetPartMeshingParameters decodes them through FeMesh.GetPartIdsFromGeometryIds.
                    int targetGeometryPartId = CaeMesh.FeMesh.GetGeometryId(0, (int)CaeMesh.GeometryType.Part, targetPartId);
                    p.CreationIds = new int[] { targetGeometryPartId };'''
if old_ids not in text:
    raise SystemExit('C8.82c CreationIds anchor not found; refusing non-deterministic patch')
text = text.replace(old_ids, new_ids, 1)

old_effective = '''                    bool maxHMatch = admitted != null && Finite(admittedMaxH) && Math.Abs(admittedMaxH - requestedMaxH) <= 1e-12;

                    if (!String.IsNullOrWhiteSpace(c882CfgPath))'''
new_effective = '''                    bool maxHMatch = admitted != null && Finite(admittedMaxH) && Math.Abs(admittedMaxH - requestedMaxH) <= 1e-12;
                    MeshingParameters effective = _controller.GetPartMeshingParameters(meshedPartName);
                    double effectiveMaxH = effective == null ? Double.NaN : effective.MaxH;
                    bool effectiveMaxHMatch = effective != null && Finite(effectiveMaxH) && Math.Abs(effectiveMaxH - requestedMaxH) <= 1e-12;

                    if (!String.IsNullOrWhiteSpace(c882CfgPath))'''
if old_effective not in text:
    raise SystemExit('C8.82c effective-parameter anchor not found; refusing non-deterministic patch')
text = text.replace(old_effective, new_effective, 1)

old_json = '''                            "  \\\"target_geometry_part_id_before_command\\\": " + targetPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"admitted_is_null\\\": " + (admittedIsNull ? "true" : "false") + ",\\n" +'''
new_json = '''                            "  \\\"target_geometry_part_id_before_command\\\": " + targetPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"encoded_geometry_part_id\\\": " + targetGeometryPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"effective_get_part_maxh_mm\\\": " + (Finite(effectiveMaxH) ? effectiveMaxH.ToString("R", CultureInfo.InvariantCulture) : "null") + ",\\n" +
                            "  \\\"effective_get_part_maxh_match\\\": " + (effectiveMaxHMatch ? "true" : "false") + ",\\n" +
                            "  \\\"admitted_is_null\\\": " + (admittedIsNull ? "true" : "false") + ",\\n" +'''
if old_json not in text:
    raise SystemExit('C8.82c evidence anchor not found; refusing non-deterministic patch')
text = text.replace(old_json, new_json, 1)

old_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize)
                        throw new InvalidOperationException("C8.82 canonical MeshingParameters admission failed; see NETGEN_CONFIG.json.");'''
new_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize || !effectiveMaxHMatch)
                        throw new InvalidOperationException("C8.82c effective GetPartMeshingParameters admission failed; see NETGEN_CONFIG.json.");'''
if old_gate not in text:
    raise SystemExit('C8.82c admission gate anchor not found; refusing non-deterministic patch')
text = text.replace(old_gate, new_gate, 1)

path.write_text(text, encoding='utf-8')
print(f'C8.82c encoded geometry-ID + effective NetGen sizing seam applied: {path}')
