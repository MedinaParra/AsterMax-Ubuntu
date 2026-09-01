from astermax.windows_shell import build_project_tree_spec


def test_project_tree_has_complete_verified_workflow_navigation():
    spec = build_project_tree_spec()
    ids = [node_id for node_id, _label, _target in spec]
    assert ids == [
        "model",
        "geometry",
        "materials",
        "connections",
        "mesh",
        "static",
        "supports",
        "loads",
        "solution",
        "review",
        "results",
        "provenance",
    ]
    targets = {node_id: target for node_id, _label, target in spec}
    assert targets["geometry"] == "Analysis"
    assert targets["supports"] == "Picker"
    assert targets["loads"] == "Picker"
    assert targets["mesh"] == "Review"
    assert targets["results"] == "Results"
    assert targets["provenance"] == "Results"


def test_project_tree_does_not_claim_unimplemented_connections():
    spec = build_project_tree_spec()
    connections = next(row for row in spec if row[0] == "connections")
    assert "not enabled" in connections[1]
    assert connections[2] is None


def test_project_tree_exposes_units_and_persistent_cad_semantics():
    labels = " | ".join(label for _node_id, label, _target in build_project_tree_spec())
    assert "STEP [mm]" in labels
    assert "CAD faces" in labels
    assert "TET10" in labels
    assert "Evidence / Provenance" in labels


def test_project_tree_labels_are_unique_for_deterministic_navigation():
    labels = [label for _node_id, label, _target in build_project_tree_spec()]
    assert len(labels) == len(set(labels))
