#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'AsterMaxAI' / 'AsterMaxStepMeshHarness.cs'
text = path.read_text(encoding='utf-8-sig')

# Controller.AddMeshingParameters replays CreationData and regenerates CreationIds.
# Therefore the Selection payload must carry the encoded geometry-part ID too;
# changing CreationIds alone (C8.82c) is not authoritative.
old_selection = '''                    geometrySelection.Add(new CaeGlobals.SelectionNodeIds(CaeGlobals.vtkSelectOperation.Add, false, new int[] { targetPartId }, true));'''
new_selection = '''                    // C8.82d: CreationData is authoritative during AddMeshingParameters; keep it in the
                    // same encoded geometry-ID space as CreationIds so Controller replay cannot erase the binding.
                    geometrySelection.Add(new CaeGlobals.SelectionNodeIds(CaeGlobals.vtkSelectOperation.Add, false, new int[] { targetGeometryPartId }, true));'''
if old_selection not in text:
    raise SystemExit('C8.82d CreationData selection anchor not found; refusing non-deterministic patch')
text = text.replace(old_selection, new_selection, 1)

old_admitted = '''                    MeshingParameters admitted = _controller.GetMeshingParameters(p.Name);
                    bool admittedIsNull = admitted == null;'''
new_admitted = '''                    MeshingParameters admitted = _controller.GetMeshingParameters(p.Name);
                    int[] admittedPartIds = admitted == null || admitted.CreationIds == null
                        ? new int[0]
                        : CaeMesh.FeMesh.GetPartIdsFromGeometryIds(admitted.CreationIds);
                    bool admittedTargetsPart = admittedPartIds.Contains(targetPartId);
                    bool admittedIsNull = admitted == null;'''
if old_admitted not in text:
    raise SystemExit('C8.82d admitted-selection anchor not found; refusing non-deterministic patch')
text = text.replace(old_admitted, new_admitted, 1)

old_json = '''                            "  \\\"encoded_geometry_part_id\\\": " + targetGeometryPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"effective_get_part_maxh_mm\\\": " +'''
new_json = '''                            "  \\\"encoded_geometry_part_id\\\": " + targetGeometryPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"admitted_creation_ids_decode_target_part\\\": " + (admittedTargetsPart ? "true" : "false") + ",\\n" +
                            "  \\\"effective_get_part_maxh_mm\\\": " +'''
if old_json not in text:
    raise SystemExit('C8.82d selection-evidence anchor not found; refusing non-deterministic patch')
text = text.replace(old_json, new_json, 1)

old_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize || !effectiveMaxHMatch)
                        throw new InvalidOperationException("C8.82c effective GetPartMeshingParameters admission failed; see NETGEN_CONFIG.json.");'''
new_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize || !admittedTargetsPart || !effectiveMaxHMatch)
                        throw new InvalidOperationException("C8.82d authoritative CreationData/GetPartMeshingParameters admission failed; see NETGEN_CONFIG.json.");'''
if old_gate not in text:
    raise SystemExit('C8.82d admission gate anchor not found; refusing non-deterministic patch')
text = text.replace(old_gate, new_gate, 1)

path.write_text(text, encoding='utf-8')
print(f'C8.82d authoritative Selection replay seam applied: {path}')
