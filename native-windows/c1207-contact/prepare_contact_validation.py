#!/usr/bin/env python3
"""Inspect production export and derive its original-orientation negative control.

The only mechanical difference between the two decks is master/slave orientation.
Both get the same additional reaction observation after the production MED write.
"""

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path


ZONE = re.compile(r"(?P<prefix>_F\(\s*GROUP_MA_MAIT\s*=\s*')(?P<master>[^']+)"
                  r"(?P<middle>'\s*,\s*GROUP_MA_ESCL\s*=\s*')(?P<slave>[^']+)(?P<tail>')")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_mail(text):
    mode, nodes, cells, groups = None, {}, {}, {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in ("FINSF", "FIN"):
            mode = None
        elif line in ("COOR_3D", "HEXA8", "QUAD4"):
            mode = line
        elif line.startswith("GROUP_MA NOM = ") or line.startswith("GROUP_NO NOM = "):
            mode = ("group", line.split("=", 1)[1].strip())
            require(mode[1] not in groups, "Repeated mesh group: " + mode[1])
            groups[mode[1]] = []
        elif isinstance(mode, tuple):
            groups[mode[1]].extend(line.split())
        elif mode == "COOR_3D":
            name, *values = line.split()
            require(name not in nodes and len(values) == 3, "Invalid node record: " + line)
            nodes[name] = tuple(float(value) for value in values)
        elif mode in ("HEXA8", "QUAD4"):
            name, *values = line.split()
            require(name not in cells, "Repeated element identifier: " + name)
            cells[name] = (mode, values)
    return nodes, cells, groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    contract = json.loads((root / "contact-contract.json").read_text(encoding="utf-8-sig"))
    metadata = json.loads((root / "contact-fixture.input.json").read_text(encoding="utf-8"))
    stem = metadata["case"]
    corrected, original = root / "corrected", root / "original"
    original.mkdir(parents=True, exist_ok=True)
    comm_path = corrected / f"{stem}.comm"
    mail_path = corrected / f"{stem}.mail"
    comm = comm_path.read_text(encoding="utf-8-sig")
    mail = mail_path.read_text(encoding="utf-8-sig")
    manifest = json.loads((corrected / f"{stem}.native-export.json").read_text(encoding="utf-8-sig"))
    nodes, cells, groups = read_mail(mail)

    expected_nodes = {node["id"]: tuple(float(node[axis]) for axis in ("x", "y", "z"))
                      for node in contract["mesh"]["nodes"]}
    expected_cells = {cell["id"]: (cell["type"], cell["nodes"]) for cell in contract["mesh"]["elements"]}
    for contact in contract["contacts"]:
        for role in ("master", "slave"):
            surface = contact[role]
            require(groups.get(surface["group"]) is not None, "Production export lost a contact surface group.")
            require(set(groups[surface["group"]]) == {face["id"] for face in surface["elements"]},
                    "Contact surface faces changed during orientation.")
            for face in surface["elements"]:
                require(face["id"] not in expected_cells, "Fixture element IDs must be unique.")
                expected_cells[face["id"]] = (face["type"], face["nodes"])
    require(nodes == expected_nodes, "Production export changed the fixture nodes.")
    require(cells == expected_cells, "Production export dropped, duplicated, or changed mesh/contact faces.")
    require("DEFI_CONTACT(" in comm and "STAT_NON_LINE(" in comm, "Production export must use real contact.")
    require(re.search(r"FORMULATION\s*=\s*'CONTINUE'", comm), "Contact formulation changed.")
    require(re.search(r"FROTTEMENT\s*=\s*'SANS'", comm), "Contact friction law changed.")
    require(len(re.findall(r"CONTACT_INIT\s*=\s*'OUI'", comm)) == 2, "Initial contact state changed.")
    require(re.search(r"IMPR_RESU\([^\r\n]*INST\s*=\s*1\.0", comm),
            "Contact MED output must explicitly select final static time 1.0.")
    require(re.search(r"POST_RELEVE_T\([^\r\n]*INST\s*=\s*1\.0", comm),
            "Contact displacement table must explicitly select final static time 1.0.")

    original_pairs = {frozenset((item["master"]["group"], item["slave"]["group"])): item
                      for item in contract["contacts"]}
    exported_zones = list(ZONE.finditer(comm))
    require(len(exported_zones) == len(original_pairs) == 2, "Expected exactly two preserved contact zones.")
    seen, slave_sets, swaps = set(), [], []
    for match in exported_zones:
        key = frozenset((match["master"], match["slave"]))
        require(key in original_pairs and key not in seen, "Contact pairing changed or was duplicated.")
        seen.add(key)
        source = original_pairs[key]
        slave_sets.append(set(node for face_id in groups[match["slave"]] for node in cells[face_id][1]))
        swaps.append({"name": source["name"], "original_master_group": source["master"]["group"],
                      "original_slave_group": source["slave"]["group"],
                      "exported_master_group": match["master"], "exported_slave_group": match["slave"],
                      "swapped": match["master"] != source["master"]["group"]})
    require(not (slave_sets[0] & slave_sets[1]), "Production export still has duplicate slave membership.")
    require(any(item["swapped"] for item in swaps), "The regression fixture must exercise a real role reversal.")

    # No solver inputs are changed by this observation, which runs after the
    # application's own MED write. Preserve the uninstrumented production file.
    (corrected / f"{stem}.production.comm").write_text(comm, encoding="utf-8")
    fixed_group = manifest["node_group_name_map"]["FIXED"]
    require(set(groups[fixed_group]) == set(metadata["fixed_nodes"]), "Fixed node group changed.")
    observation = f"""# C12.07 validation-only observation; no loads, contacts, or constitutive laws changed.
result = CALC_CHAMP(reuse=result, RESULTAT=result, FORCE=('REAC_NODA',))
reaction = POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION', INTITULE='FIXED_REACTIONS', RESULTAT=result, NOM_CHAM='REAC_NODA', GROUP_NO='{fixed_group}', NOM_CMP=('DX','DY','DZ'), INST=1.0))
IMPR_TABLE(TABLE=reaction, UNITE=82)
FIN()
"""
    require(len(re.findall(r"(?m)^FIN\(\)\s*$", comm)) == 1, "Expected exactly one final FIN() call.")
    observed = re.sub(r"(?m)^FIN\(\)\s*$", lambda _match: observation, comm)
    comm_path.write_text(observed, encoding="utf-8")

    def restore_original(match):
        source = original_pairs[frozenset((match["master"], match["slave"]))]
        return (match["prefix"] + source["master"]["group"] + match["middle"]
                + source["slave"]["group"] + match["tail"])

    legacy = ZONE.sub(restore_original, observed)
    require(legacy != observed, "The original-orientation control must differ from the corrected deck.")
    erase_roles = lambda text: ZONE.sub(lambda match: match["prefix"] + "MASTER" + match["middle"] + "SLAVE" + match["tail"], text)
    require(erase_roles(legacy) == erase_roles(observed), "The comparison changed more than contact roles.")
    (original / f"{stem}.comm").write_text(legacy, encoding="utf-8")
    (original / f"{stem}.mail").write_bytes(mail_path.read_bytes())
    for directory in (original, corrected):
        (directory / f"{stem}.export").write_text(f"""P actions make_etude
P version stable
P mode interactif
P time_limit 600
P memory_limit 4096
P ncpus 1
P mpi_nbcpu 1
F comm ./{stem}.comm D 1
F mail ./{stem}.mail D 20
F mess ./{stem}.mess R 6
F resu ./{stem}.resu R 80
F rmed ./{stem}.rmed R 81
F repe ./{stem}.reactions R 82
""", encoding="utf-8")

    (root / "contact-orientation.diff").write_text("".join(difflib.unified_diff(
        legacy.splitlines(keepends=True), observed.splitlines(keepends=True),
        fromfile="original-orientation.comm", tofile="production-oriented.comm")), encoding="utf-8")
    report = {"release": "C12.07", "original_shared_slave_nodes": metadata["original_shared_slave_node_count"],
              "exported_shared_slave_nodes": len(slave_sets[0] & slave_sets[1]),
              "zones": swaps, "mechanical_difference": "MASTER_SLAVE_ORIENTATION_ONLY",
              "mesh_and_faces_preserved": True, "contact_law_preserved": True,
              "observation_only_instrumentation": "REAC_NODA table after production MED output",
              "production_comm_sha256": digest(corrected / f"{stem}.production.comm"),
              "input_sha256": {str(path.relative_to(root)).replace("\\", "/"): digest(path)
                               for directory in (original, corrected)
                               for path in sorted(directory.iterdir()) if path.is_file()}}
    (root / "contact-validation-decks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
