#!/usr/bin/env python3
"""Generate the deterministic C10.08 real Code_Aster TETRA4 admission case."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def signed_six_volume(points, connectivity):
    a, b, c, d = (points[index] for index in connectivity)
    ab = tuple(b[i] - a[i] for i in range(3))
    ac = tuple(c[i] - a[i] for i in range(3))
    ad = tuple(d[i] - a[i] for i in range(3))
    cross = (
        ac[1] * ad[2] - ac[2] * ad[1],
        ac[2] * ad[0] - ac[0] * ad[2],
        ac[0] * ad[1] - ac[1] * ad[0],
    )
    return sum(ab[i] * cross[i] for i in range(3))


def write_group(stream, name, ids, per_record=8):
    stream.write(f"GROUP_NO NOM = {name}\n")
    for start in range(0, len(ids), per_record):
        stream.write(" ".join(f"N{x}" for x in ids[start : start + per_record]) + "\n")
    stream.write("FINSF\n")


def sha256(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--name", default="astermax-tet4-bar")
    parser.add_argument("--nx", type=int, default=20)
    parser.add_argument("--ny", type=int, default=4)
    parser.add_argument("--nz", type=int, default=4)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    length, height, width = 100.0, 10.0, 10.0
    young, poisson, force = 210000.0, 0.30, 10000.0

    node_id = {}
    points = {}
    nodes = []
    nid = 1
    for i in range(args.nx + 1):
        for j in range(args.ny + 1):
            for k in range(args.nz + 1):
                xyz = (length * i / args.nx, height * j / args.ny, width * k / args.nz)
                node_id[(i, j, k)] = nid
                points[nid] = xyz
                nodes.append((nid, *xyz))
                nid += 1

    elements = []
    eid = 1
    for i in range(args.nx):
        for j in range(args.ny):
            for k in range(args.nz):
                v000 = node_id[(i, j, k)]
                v100 = node_id[(i + 1, j, k)]
                v110 = node_id[(i + 1, j + 1, k)]
                v010 = node_id[(i, j + 1, k)]
                v001 = node_id[(i, j, k + 1)]
                v101 = node_id[(i + 1, j, k + 1)]
                v111 = node_id[(i + 1, j + 1, k + 1)]
                v011 = node_id[(i, j + 1, k + 1)]
                cell_tets = [
                    [v000, v100, v110, v111],
                    [v000, v110, v010, v111],
                    [v000, v010, v011, v111],
                    [v000, v011, v001, v111],
                    [v000, v001, v101, v111],
                    [v000, v101, v100, v111],
                ]
                for conn in cell_tets:
                    six_v = signed_six_volume(points, conn)
                    if six_v < 0:
                        conn[1], conn[2] = conn[2], conn[1]
                        six_v = -six_v
                    if six_v <= 0:
                        raise RuntimeError(f"Degenerate tetrahedron E{eid}: {conn}")
                    elements.append((eid, conn, six_v / 6.0))
                    eid += 1

    fixed = [node_id[(0, j, k)] for j in range(args.ny + 1) for k in range(args.nz + 1)]
    loaded = [node_id[(args.nx, j, k)] for j in range(args.ny + 1) for k in range(args.nz + 1)]

    # Consistent lumped nodal forces for a uniform traction on the structured
    # end face. Equal force at every node overweights corners and edges and
    # creates a non-physical displacement spread at the probe face.
    load_groups = {"LOAD_CORNERS": [], "LOAD_EDGES": [], "LOAD_INTERIOR": []}
    load_weights = {"LOAD_CORNERS": 1, "LOAD_EDGES": 2, "LOAD_INTERIOR": 4}
    for j in range(args.ny + 1):
        for k in range(args.nz + 1):
            boundary_count = int(j in (0, args.ny)) + int(k in (0, args.nz))
            group = "LOAD_CORNERS" if boundary_count == 2 else ("LOAD_EDGES" if boundary_count == 1 else "LOAD_INTERIOR")
            load_groups[group].append(node_id[(args.nx, j, k)])
    total_lumped_weight = sum(load_weights[name] * len(ids) for name, ids in load_groups.items())
    force_per_weight = force / total_lumped_weight

    mail = out / f"{args.name}.mail"
    with mail.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("TITRE\nASTERMAX C10.08 REAL TETRA4 AXIAL BAR\nFINSF\nCOOR_3D\n")
        for node, x, y, z in nodes:
            stream.write(f"N{node} {x:.12g} {y:.12g} {z:.12g}\n")
        stream.write("FINSF\nTETRA4\n")
        for element, conn, _ in elements:
            stream.write(f"E{element} " + " ".join(f"N{x}" for x in conn) + "\n")
        stream.write("FINSF\n")
        write_group(stream, "FIXED_1", fixed)
        write_group(stream, "CONCENTRATED_FORCE_1", loaded)
        for group_name, ids in load_groups.items():
            if ids:
                write_group(stream, group_name, ids)
        stream.write("FIN\n")

    comm = out / f"{args.name}.comm"
    comm.write_text(
        f"""DEBUT()
mesh=LIRE_MAILLAGE(FORMAT='ASTER',UNITE=20)
model=AFFE_MODELE(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',PHENOMENE='MECANIQUE',MODELISATION='3D'))
steel=DEFI_MATERIAU(ELAS=_F(E={young},NU={poisson}))
matfield=AFFE_MATERIAU(MAILLAGE=mesh,AFFE=_F(TOUT='OUI',MATER=steel))
fixed=AFFE_CHAR_MECA(MODELE=model,DDL_IMPO=_F(GROUP_NO='FIXED_1',DX=0.0,DY=0.0,DZ=0.0))
load=AFFE_CHAR_MECA(MODELE=model,FORCE_NODALE=(
    _F(GROUP_NO='LOAD_CORNERS',FX={force_per_weight:.15g},FY=0.0,FZ=0.0),
    _F(GROUP_NO='LOAD_EDGES',FX={2.0 * force_per_weight:.15g},FY=0.0,FZ=0.0),
    _F(GROUP_NO='LOAD_INTERIOR',FX={4.0 * force_per_weight:.15g},FY=0.0,FZ=0.0),
))
result=MECA_STATIQUE(MODELE=model,CHAM_MATER=matfield,EXCIT=(_F(CHARGE=fixed),_F(CHARGE=load)))
result=CALC_CHAMP(reuse=result,RESULTAT=result,CONTRAINTE=('SIGM_ELNO',),CRITERES=('SIEQ_ELNO',),FORCE=('REAC_NODA',))
disp=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='LOAD_FACE_DISPLACEMENT',RESULTAT=result,NOM_CHAM='DEPL',GROUP_NO='CONCENTRATED_FORCE_1',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))
reaction=POST_RELEVE_T(ACTION=_F(OPERATION='EXTRACTION',INTITULE='FIXED_REACTIONS',RESULTAT=result,NOM_CHAM='REAC_NODA',GROUP_NO='FIXED_1',NOM_CMP=('DX','DY','DZ'),TOUT_ORDRE='OUI'))
IMPR_TABLE(TABLE=disp,UNITE=80)
IMPR_TABLE(TABLE=reaction,UNITE=82)
IMPR_RESU(FORMAT='MED',UNITE=81,RESU=_F(RESULTAT=result))
FIN()
""",
        encoding="utf-8",
    )

    export = out / f"{args.name}.export"
    export.write_text(
        f"""P actions make_etude
P version 15.2
P mode interactif
P time_limit 600
P memory_limit 4096
P ncpus 1
P mpi_nbcpu 1

F comm /analysis/{args.name}.comm D 1
F mail /analysis/{args.name}.mail D 20
F mess /analysis/{args.name}.mess R 6
F resu /analysis/{args.name}.resu R 80
F rmed /analysis/{args.name}.rmed R 81
F repe /analysis/{args.name}.reactions R 82
""",
        encoding="utf-8",
    )

    expected_volume = length * height * width
    actual_volume = sum(x[2] for x in elements)
    metadata = {
        "release": "C10.08",
        "case": args.name,
        "element_type": "TETRA4",
        "nodes": len(nodes),
        "elements": len(elements),
        "fixed_nodes": len(fixed),
        "load_nodes": len(loaded),
        "young_modulus_mpa": young,
        "poisson": poisson,
        "length_mm": length,
        "area_mm2": height * width,
        "total_force_n": force,
        "uniform_traction_mpa": force / (height * width),
        "consistent_nodal_force_per_weight_n": force_per_weight,
        "load_group_cardinalities": {name: len(ids) for name, ids in load_groups.items()},
        "load_group_weights": load_weights,
        "total_lumped_weight": total_lumped_weight,
        "analytical_axial_displacement_mm": force * length / (height * width * young),
        "mesh_volume_mm3": actual_volume,
        "expected_volume_mm3": expected_volume,
        "volume_relative_error": abs(actual_volume - expected_volume) / expected_volume,
        "minimum_tetra_volume_mm3": min(x[2] for x in elements),
        "group_name_map": {
            "Fixed-1": "FIXED_1",
            "Concentrated_Force-1": "CONCENTRATED_FORCE_1",
        },
        "unit_contract": "MM_N_S_MPA",
        "scientific_integrity": {
            "fea_values_invented": False,
            "analytical_reference_is_solver_output": False,
        },
    }
    metadata["input_sha256"] = {
        mail.name: sha256(mail),
        comm.name: sha256(comm),
        export.name: sha256(export),
    }
    (out / f"{args.name}.input.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if not math.isclose(actual_volume, expected_volume, rel_tol=0.0, abs_tol=1e-8):
        raise RuntimeError(f"Tetra volume mismatch: {actual_volume} != {expected_volume}")
    reconstructed_force = sum(
        len(load_groups[name]) * load_weights[name] * force_per_weight for name in load_groups
    )
    if not math.isclose(reconstructed_force, force, rel_tol=0.0, abs_tol=1e-10):
        raise RuntimeError("Consistent nodal traction does not conserve the requested load")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
