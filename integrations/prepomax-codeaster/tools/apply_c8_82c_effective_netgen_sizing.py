#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'build/PrePoMax-CodeAster')
path = root / 'PrePoMax' / 'AsterMaxAI' / 'AsterMaxStepMeshHarness.cs'
text = path.read_text(encoding='utf-8-sig')

# Exact GUI replay: FrmMeshingParameters does not synthesize CreationData. It puts the
# controller in Part-selection mode, receives controller-generated IDs, and deep-clones
# Controller.Selection. AddMeshingParameters then replays that same Selection internally.
old_selection_block = '''                    p.CreationIds = new int[] { targetPartId };
                    CaeGlobals.Selection geometrySelection = new CaeGlobals.Selection();
                    geometrySelection.SelectItem = CaeGlobals.vtkSelectItem.Part;
                    geometrySelection.Add(new CaeGlobals.SelectionNodeIds(CaeGlobals.vtkSelectOperation.Add, false, new int[] { targetPartId }, true));
                    p.CreationData = geometrySelection;
                    _controller.AddMeshingParametersCommand(p);'''
new_selection_block = '''                    // C8.82e: reproduce FrmMeshingParameters selection semantics through Controller.
                    _controller.SetSelectItemToPart();
                    _controller.Selection.Clear();
                    CaeGlobals.SelectionNodeIds nativePartSelection = new CaeGlobals.SelectionNodeIds(
                        CaeGlobals.vtkSelectOperation.Add, false, new int[] { targetPartId });
                    _controller.AddSelectionNode(nativePartSelection, true, true);
                    int[] nativeSelectionIds = _controller.GetSelectionIds();
                    if (nativeSelectionIds == null || nativeSelectionIds.Length == 0)
                        throw new InvalidOperationException("C8.82e native Controller part selection produced no IDs.");
                    p.CreationIds = nativeSelectionIds;
                    p.CreationData = _controller.Selection.DeepClone();
                    _controller.AddMeshingParametersCommand(p);'''
if old_selection_block not in text:
    raise SystemExit('C8.82e native GUI-selection anchor not found; refusing non-deterministic patch')
text = text.replace(old_selection_block, new_selection_block, 1)

old_admitted = '''                    MeshingParameters admitted = _controller.GetMeshingParameters(p.Name);
                    bool admittedIsNull = admitted == null;'''
new_admitted = '''                    MeshingParameters admitted = _controller.GetMeshingParameters(p.Name);
                    int[] admittedPartIds = admitted == null || admitted.CreationIds == null
                        ? new int[0]
                        : CaeMesh.FeMesh.GetPartIdsFromGeometryIds(admitted.CreationIds);
                    bool admittedTargetsPart = admittedPartIds.Contains(targetPartId);
                    bool admittedIsNull = admitted == null;'''
if old_admitted not in text:
    raise SystemExit('C8.82e admitted-selection anchor not found; refusing non-deterministic patch')
text = text.replace(old_admitted, new_admitted, 1)

old_effective = '''                    bool maxHMatch = admitted != null && Finite(admittedMaxH) && Math.Abs(admittedMaxH - requestedMaxH) <= 1e-12;

                    if (!String.IsNullOrWhiteSpace(c882CfgPath))'''
new_effective = '''                    bool maxHMatch = admitted != null && Finite(admittedMaxH) && Math.Abs(admittedMaxH - requestedMaxH) <= 1e-12;
                    MeshingParameters effective = _controller.GetPartMeshingParameters(meshedPartName);
                    double effectiveMaxH = effective == null ? Double.NaN : effective.MaxH;
                    bool effectiveMaxHMatch = effective != null && Finite(effectiveMaxH) && Math.Abs(effectiveMaxH - requestedMaxH) <= 1e-12;

                    if (!String.IsNullOrWhiteSpace(c882CfgPath))'''
if old_effective not in text:
    raise SystemExit('C8.82e effective-parameter anchor not found; refusing non-deterministic patch')
text = text.replace(old_effective, new_effective, 1)

old_json = '''                            "  \\\"target_geometry_part_id_before_command\\\": " + targetPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"admitted_is_null\\\": " + (admittedIsNull ? "true" : "false") + ",\\n" +'''
new_json = '''                            "  \\\"target_geometry_part_id_before_command\\\": " + targetPartId.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"native_controller_selection_id_count\\\": " + nativeSelectionIds.Length.ToString(CultureInfo.InvariantCulture) + ",\\n" +
                            "  \\\"admitted_creation_ids_decode_target_part\\\": " + (admittedTargetsPart ? "true" : "false") + ",\\n" +
                            "  \\\"effective_get_part_maxh_mm\\\": " + (Finite(effectiveMaxH) ? effectiveMaxH.ToString("R", CultureInfo.InvariantCulture) : "null") + ",\\n" +
                            "  \\\"effective_get_part_maxh_match\\\": " + (effectiveMaxHMatch ? "true" : "false") + ",\\n" +
                            "  \\\"admitted_is_null\\\": " + (admittedIsNull ? "true" : "false") + ",\\n" +'''
if old_json not in text:
    raise SystemExit('C8.82e evidence anchor not found; refusing non-deterministic patch')
text = text.replace(old_json, new_json, 1)

old_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize)
                        throw new InvalidOperationException("C8.82 canonical MeshingParameters admission failed; see NETGEN_CONFIG.json.");'''
new_gate = '''                    if (admittedIsNull || !maxHMatch || admittedRelativeSize || !admittedTargetsPart || !effectiveMaxHMatch)
                    {
                        string admittedMaxHText = Finite(admittedMaxH) ? admittedMaxH.ToString("R", CultureInfo.InvariantCulture) : "null";
                        string effectiveMaxHText = Finite(effectiveMaxH) ? effectiveMaxH.ToString("R", CultureInfo.InvariantCulture) : "null";
                        throw new InvalidOperationException("C8.82e native GUI-selection meshing admission failed: admittedNull=" + admittedIsNull +
                            ", maxHMatch=" + maxHMatch + ", relativeSize=" + admittedRelativeSize +
                            ", decodedTargetPart=" + admittedTargetsPart + ", effectiveMaxHMatch=" + effectiveMaxHMatch +
                            ", nativeSelectionIdCount=" + nativeSelectionIds.Length.ToString(CultureInfo.InvariantCulture) +
                            ", requestedMaxH=" + requestedMaxH.ToString("R", CultureInfo.InvariantCulture) +
                            ", admittedMaxH=" + admittedMaxHText + ", effectiveMaxH=" + effectiveMaxHText + ".");
                    }'''
if old_gate not in text:
    raise SystemExit('C8.82e admission gate anchor not found; refusing non-deterministic patch')
text = text.replace(old_gate, new_gate, 1)

path.write_text(text, encoding='utf-8')
print(f'C8.82e native FrmMeshingParameters selection replay + effective NetGen sizing seam applied: {path}')
