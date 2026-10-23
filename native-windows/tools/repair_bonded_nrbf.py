"""Append named bonded Tie constraints to trusted NRBF metadata as plain data.

This program does not deserialize .NET objects or run serialization callbacks.
It accepts a raw NRBF stream plus explicit facet selections and coordinates.
The original stream is retained, with just holder._model redirected to an
appended model/mesh metadata copy. Geometry, mesh and analysis object references
remain intact. A separate caller may wrap this stream in a PMX container.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from nrbf_append import Scanner, Schema, Writer, Inline, reference, validate_references


def sha(data):
    return hashlib.sha256(data).hexdigest()


def named_overrides(template, name, internal):
    replacements = {}
    for key in template:
        member = key.split("+")[-1]
        if member == "_name":
            replacements[key] = name
        elif member in ["_active", "_visible", "_valid", "_checkName"]:
            replacements[key] = True
        elif member == "_internal":
            replacements[key] = internal
    return replacements


def find_library(scanner, simple_name):
    return next(i for i, name in scanner.libraries.items() if name.split(",")[0] == simple_name)


def repair(data, selections, coordinates, reset_history=False):
    scanner = Scanner(data)
    scanner.parse()
    initial_validation = validate_references(scanner)
    writer = Writer(scanner)
    candidates = []
    for oid, value in scanner.objects.items():
        if isinstance(value, dict) and "_model" in value:
            model = scanner.raw(value["_model"])
            if isinstance(model, dict) and model.get("__class__") == "CaeModel.FeModel":
                candidates.append(oid)
    if len(candidates) != 1:
        raise ValueError(("Expected one model holder", candidates))
    holder_id = candidates[0]
    model_id = scanner.objects[holder_id]["_model"]["__ref__"]
    original_model = scanner.objects[model_id]
    mesh_id = original_model["_mesh"]["__ref__"]
    original_mesh = scanner.objects[mesh_id]
    # No implicit removal of constraints in an existing constrained project.
    if scanner.ordered(original_model["_constraints"]["__ref__"]):
        raise ValueError("The seed model must have an empty constraint collection")
    node_template_id = scanner.find("CaeMesh.FeNodeSet")
    element_template_id = scanner.find("CaeMesh.FeElementSet")
    surface_template_id = scanner.find("CaeMesh.FeSurface")
    contact_template_id = scanner.find("CaeModel.ContactPair")
    surface_template = scanner.objects[surface_template_id]
    contact_template = scanner.objects[contact_template_id]
    element_faces_template_id = surface_template["_elementFaces"]["__ref__"]
    face_enum_id = scanner.find("CaeMesh.FeFaceName")
    node_pairs = scanner.ordered(original_mesh["_nodeSets"]["__ref__"])
    element_pairs = scanner.ordered(original_mesh["_elementSets"]["__ref__"])
    surface_pairs = scanner.ordered(original_mesh["_surfaces"]["__ref__"])
    existing_names = {"nodes": {key for key, _ in node_pairs},
                      "elements": {key for key, _ in element_pairs},
                      "surfaces": {key for key, _ in surface_pairs}}
    tie_pairs = []
    tie_schema_id = None
    model_lib = find_library(scanner, "CaeModel")
    globals_lib = find_library(scanner, "CaeGlobals")
    color_lib = next(i for i, name in scanner.libraries.items()
                     if name.split(",")[0] in ["System.Drawing", "System.Drawing.Primitives"])
    tie_schema = Schema(
        "CaeModel.Tie",
        ["_name", "_active", "_visible", "_valid", "_internal", "_checkName",
         "_masterRegionName", "_masterRegionType", "_slaveRegionName", "_slaveRegionType",
         "_masterCreationIds", "_masterCreationData", "_slaveCreationIds", "_slaveCreationData",
         "_masterColor", "_slaveColor", "_twoD", "_positionTolerance", "_adjust"],
        [1, 0, 0, 0, 0, 0, 1, 4, 1, 4, 7, 4, 7, 4, 4, 4, 0, 0, 0],
        [None, 1, 1, 1, 1, 1, None, ("CaeGlobals.RegionTypeEnum", globals_lib),
         None, ("CaeGlobals.RegionTypeEnum", globals_lib), 8, ("CaeGlobals.Selection", globals_lib),
         8, ("CaeGlobals.Selection", globals_lib), ("System.Drawing.Color", color_lib),
         ("System.Drawing.Color", color_lib), 1, 6, 1], model_lib)
    audit_ties = []
    for number, selection in enumerate(selections, 1):
        if selection.get("adjust") is not False:
            raise ValueError("Every tie must explicitly preserve coordinates with adjust=false")
        tolerance = float(selection["position_tolerance_mm"])
        if not 0 < tolerance < float("inf"):
            raise ValueError("Every tie requires a finite positive position tolerance")
        surface_names = {}
        for role, tag in [("master", "M"), ("slave", "S")]:
            skin = selection[role]
            name = f"Bonded_{number:02d}_{tag}"
            node_name = name + "_Nodes"
            surface_names[role] = name
            if name in existing_names["surfaces"] or node_name in existing_names["nodes"]:
                raise ValueError("Generated surface name already exists")
            node_ids = sorted({int(n) for facet in skin["facets"] for n in facet["nodes"]})
            if node_ids != sorted(skin["node_ids"]):
                raise ValueError("Declared node set does not match surface facets")
            xyz = [coordinates[str(n)] for n in node_ids]
            center = [sum(p[d] for p in xyz) / len(xyz) for d in range(3)]
            bounds = [[min(p[d] for p in xyz), max(p[d] for p in xyz)] for d in range(3)]
            labels = writer.primitive_array(8, node_ids)
            center_ref = writer.primitive_array(6, center)
            bounds_ref = writer.array(7, 6, [writer.primitive_array(6, x) for x in bounds], jagged=True)
            overrides = named_overrides(scanner.objects[node_template_id], node_name, True)
            overrides.update({"_creationData": None, "_creationIds": None,
                              "_centerOfGravity": center_ref, "_boundingBox": bounds_ref})
            for key in scanner.objects[node_template_id]:
                if key.split("+")[-1] == "_labels":
                    overrides[key] = labels
            node_pairs.append((node_name, writer.clone(node_template_id, overrides)))
            face_groups = collections.defaultdict(set)
            face_ids = set()
            for facet in skin["facets"]:
                eid = int(facet["source_element_id"])
                face = int(facet["source_face"])
                if face not in [1, 2, 3, 4] or len(facet["nodes"]) != 3:
                    raise ValueError("Only explicit TETRA4/TRIA3 surface facets are supported")
                vtk_id = 10 * eid + face - 1
                if vtk_id != int(facet["vtk_face_id"]):
                    raise ValueError("Surface VTK face ID mismatch")
                face_groups[face].add(eid)
                face_ids.add(vtk_id)
            element_face_pairs = []
            for face, ids in sorted(face_groups.items()):
                element_name = f"{name}_S{face}"
                if element_name in existing_names["elements"]:
                    raise ValueError("Generated element-set name already exists")
                labels = writer.primitive_array(8, sorted(ids))
                overrides = named_overrides(scanner.objects[element_template_id], element_name, True)
                overrides.update({"_creationData": None, "_creationIds": None, "_createdFromParts": False})
                for key in scanner.objects[element_template_id]:
                    if key.split("+")[-1] == "_labels":
                        overrides[key] = labels
                element_pairs.append((element_name, writer.clone(element_template_id, overrides)))
                enum = writer.inline(face_enum_id, {"value__": face})
                element_face_pairs.append((enum, element_name))
            element_faces = writer.dictionary(element_faces_template_id, element_face_pairs)
            overrides = named_overrides(surface_template, name, False)
            overrides.update({
                "_type": writer.inline(surface_template["_type"]["__ref__"], {"value__": 0}),
                # Native FrmSurface explicitly reconstructs an editable mesh
                # selection from FaceIds when CreationData is null (INP path).
                "_createdFrom": writer.inline(surface_template["_createdFrom"]["__ref__"], {"value__": 0}),
                "_nodeSetName": node_name, "_createdFromNodeSetName": None,
                "_faceIds": writer.primitive_array(8, sorted(face_ids)),
                "_area": float(skin["area_mm2"]), "_elementFaces": element_faces,
                "_creationData": None,
                "_surfaceFaceTypes": writer.inline(surface_template["_surfaceFaceTypes"]["__ref__"],
                                                     {"value__": 4}),
            })
            surface_pairs.append((name, writer.clone(surface_template_id, overrides)))
        values = dict(_name=selection["name"], _active=True, _visible=True, _valid=True,
                      _internal=False, _checkName=True,
                      _masterRegionName=surface_names["master"],
                      _masterRegionType=writer.inline(contact_template["_masterRegionType"]["__ref__"],
                                                      {"value__": 5}),
                      _slaveRegionName=surface_names["slave"],
                      _slaveRegionType=writer.inline(contact_template["_slaveRegionType"]["__ref__"],
                                                     {"value__": 5}),
                      _masterCreationIds=None, _masterCreationData=None,
                      _slaveCreationIds=None, _slaveCreationData=None,
                      _masterColor=contact_template["_masterColor"],
                      _slaveColor=contact_template["_slaveColor"], _twoD=False,
                      _positionTolerance=tolerance, _adjust=False)
        if tie_schema_id is None:
            tie = writer.new_class(tie_schema, values)
            tie_schema_id = tie["__ref__"]
        else:
            tie = writer.using_schema(tie_schema_id, values)
        tie_pairs.append((selection["name"], tie))
        audit_ties.append(dict(name=selection["name"], master_surface=surface_names["master"],
                               slave_surface=surface_names["slave"], position_tolerance_mm=tolerance,
                               adjust=False, master_facets=len(selection["master"]["facets"]),
                               slave_facets=len(selection["slave"]["facets"]),
                               slave_nodes=len(selection["slave"]["node_ids"])))
    node_sets = writer.ordered(original_mesh["_nodeSets"]["__ref__"], node_pairs)
    element_sets = writer.ordered(original_mesh["_elementSets"]["__ref__"], element_pairs)
    surfaces = writer.ordered(original_mesh["_surfaces"]["__ref__"], surface_pairs)
    mesh = writer.clone(mesh_id, {"_nodeSets": node_sets, "_elementSets": element_sets, "_surfaces": surfaces})
    constraints = writer.ordered(original_model["_constraints"]["__ref__"], tie_pairs,
                                 ("CaeModel.Constraint", model_lib))
    contacts = writer.ordered(original_model["_contactPairs"]["__ref__"], [])
    model = writer.clone(model_id, {"_mesh": mesh, "_constraints": constraints, "_contactPairs": contacts})
    replacements = {(holder_id, "_model"): model}
    history_audit = dict(requested=reset_history, reset=False)
    if reset_history and "_commands" in scanner.objects[holder_id]:
        commands_id = scanner.objects[holder_id]["_commands"]["__ref__"]
        command_collection = scanner.objects[commands_id]
        if command_collection["__class__"] != "PrePoMax.Commands.CommandsCollection":
            raise ValueError("Unknown command-history type")
        command_list_id = command_collection["_commands"]["__ref__"]
        history_list_id = command_collection["_history"]["__ref__"]
        command_list = scanner.objects[command_list_id]
        history_list = scanner.objects[history_list_id]
        command_schema = scanner.schema_for(command_list_id)
        array_index = command_schema.names.index("_items")
        command_array_type, command_array_library = command_schema.additional[array_index]
        if not command_array_type.endswith("[]"):
            raise ValueError("Command history is not an array of commands")
        empty_commands = writer.array(4, (command_array_type[:-2], command_array_library), [])
        commands = writer.clone(command_list_id, {"_items": empty_commands, "_size": 0,
                                                   "_version": command_list["_version"] + 1})
        history = writer.clone(history_list_id, {"_items": writer.string_array([]), "_size": 0,
                                                 "_version": history_list["_version"] + 1})
        previous_view = writer.inline(command_collection["_previousView"]["__ref__"], {"value__": 0})
        commands_container = writer.clone(commands_id, {"_currPositionIndex": -1,
                                                        "_commands": commands, "_history": history,
                                                        "_previousView": previous_view})
        replacements[(holder_id, "_commands")] = commands_container
        history_audit.update(reset=True, commands_before=command_list["_size"],
                             history_lines_before=history_list["_size"],
                             previous_current_index=command_collection["_currPositionIndex"],
                             commands_after=0, history_lines_after=0, current_index_after=-1,
                             original_bytes_preserved=True)
    result = writer.finish(replacements)
    check = Scanner(result)
    check.parse()
    validation = validate_references(check)
    new_model = check.raw(check.objects[holder_id]["_model"])
    new_mesh = check.raw(new_model["_mesh"])
    assert new_model["_geometry"] == original_model["_geometry"]
    preserved_model_fields = [k for k in original_model if k not in ["_mesh", "_constraints", "_contactPairs"]]
    for key in preserved_model_fields:
        assert check.raw(new_model[key]) == scanner.raw(original_model[key]), key
    for key in original_mesh:
        if key not in ["_nodeSets", "_elementSets", "_surfaces"]:
            assert check.raw(new_mesh[key]) == scanner.raw(original_mesh[key]), key
    assert len(check.ordered(new_model["_constraints"]["__ref__"])) == len(selections)
    assert not check.ordered(new_model["_contactPairs"]["__ref__"])
    # Existing collections remain in original order with identical value refs.
    for key in ["_nodeSets", "_elementSets", "_surfaces"]:
        before = scanner.ordered(original_mesh[key]["__ref__"])
        after = check.ordered(new_mesh[key]["__ref__"])
        assert after[:len(before)] == before, key
    patched_ranges = sorted(scanner.member_offsets[key] for key in replacements)
    previous_end = 0
    for start, end in patched_ranges:
        assert result[previous_end:start] == data[previous_end:start]
        previous_end = end
    assert result[previous_end:len(data) - 1] == data[previous_end:-1]
    if history_audit["reset"]:
        commands = check.raw(check.objects[holder_id]["_commands"])
        assert commands["_currPositionIndex"] == -1
        assert check.raw(commands["_commands"])["_size"] == 0
        assert check.raw(commands["_history"])["_size"] == 0
    report = dict(all_checks_pass=True, original_sha256=sha(data), output_sha256=sha(result),
                  initial_validation=initial_validation, output_validation=validation,
                  original_bytes=len(data), output_bytes=len(result),
                  append_bytes=len(result) - len(data), patched_reference_ranges=patched_ranges,
                  patched_reference_byte_count=5 * len(replacements), original_model_id=model_id,
                  output_model_id=model["__ref__"], holder_id=holder_id,
                  preserved_model_fields=preserved_model_fields,
                  original_mesh_metadata_object_id=mesh_id,
                  output_mesh_metadata_object_id=mesh["__ref__"],
                  existing_collection_entries_preserved=True,
                  geometry_mesh_analysis_unchanged=True,
                  contact_pairs_after=0, bonded_ties_after=len(selections), ties=audit_ties,
                  command_history=history_audit)
    return result, report


def main():
    parser = argparse.ArgumentParser()
    for name in ["input", "output", "selection", "coordinates", "report"]:
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--reset-history", action="store_true")
    args = parser.parse_args()
    selection = json.loads(Path(args.selection).read_text())
    coordinates = json.loads(Path(args.coordinates).read_text())
    if "nodes" in coordinates:
        coordinates = coordinates["nodes"]
    ties = selection.get("ties")
    if ties is None:
        ties = selection["existing_contact_distances"] + selection["new_interfaces"]
    result, report = repair(Path(args.input).read_bytes(), ties, coordinates, args.reset_history)
    if Path(args.output).resolve() == Path(args.input).resolve():
        raise ValueError("The output must be a separate file")
    Path(args.output).write_bytes(result)
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ["all_checks_pass", "bonded_ties_after", "append_bytes"]}))


if __name__ == "__main__":
    main()
