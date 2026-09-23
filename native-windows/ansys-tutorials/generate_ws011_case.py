#!/usr/bin/env python3
"""Build the exact ANSYS WS01.1 Cap_fillets tutorial mesh for AsterMax/Code_Aster.

Surface scopes reproduce the 17 pressure faces and 13 frictionless-support
faces from the tutorial. The default volume formulation is quadratic TET10
(surface TRI6), matching the ANSYS Mechanical Program Controlled solid
formulation candidate recorded in the WS01 provenance audit.

No FEA result values are embedded.
"""
import argparse, json, os
import gmsh

p=argparse.ArgumentParser()
p.add_argument("--input", required=True)
p.add_argument("--out-dir", required=True)
p.add_argument("--mesh-size", type=float, default=3.0)
p.add_argument("--element-order", type=int, choices=(1,2), default=2)
a=p.parse_args()
os.makedirs(a.out_dir, exist_ok=True)

gmsh.initialize()
try:
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("ANSYS_WS01_1_Cap_fillets")
    gmsh.model.occ.importShapes(os.path.abspath(a.input))
    gmsh.model.occ.synchronize()
    vols=[tag for dim,tag in gmsh.model.getEntities(3)]
    surfs=[tag for dim,tag in gmsh.model.getEntities(2)]
    if len(vols)!=1:
        raise RuntimeError(f"WS01.1 exact STEP must contain one volume, found {len(vols)}")

    records=[]
    for tag in surfs:
        bb=gmsh.model.getBoundingBox(2,tag)
        area=gmsh.model.occ.getMass(2,tag)
        com=gmsh.model.occ.getCenterOfMass(2,tag)
        records.append({"tag":tag,"bbox":bb,"area":area,"com":com})

    tol=2e-3
    def near(x,y): return abs(x-y)<=tol
    def flat_z(r,z):
        b=r["bbox"]
        return near(b[2],z) and near(b[5],z)

    pressure=[]
    for r in records:
        b=r["bbox"]
        lower_skin=(b[2] >= -tol and b[5] <= 0.501+tol)
        corner_fillet=(b[2] >= -tol and 8.0 < r["area"] < 11.0 and r["com"][2] < 0.30)
        outer_wall=(near(b[2],0.5) and near(b[5],20.0) and r["area"]>200.0)
        if lower_skin or corner_fillet or outer_wall:
            pressure.append(r["tag"])

    counter=[r["tag"] for r in records if flat_z(r,1.0) and 20.0<r["area"]<30.0]

    recess=[]
    for r in records:
        b=r["bbox"]
        inner_boundary=(near(b[0],2.0) or near(b[3],78.0) or near(b[1],2.0) or near(b[4],48.0))
        if inner_boundary and b[2]>=3.49-tol and b[5]<=15.01+tol and r["area"]>100:
            recess.append(r["tag"])

    lip=[r["tag"] for r in records if flat_z(r,15.0) and 200.0<r["area"]<300.0]

    expected={"PRESSURE":17,"SUPPORT_COUNTERBORE":4,"SUPPORT_RECESS":8,"SUPPORT_LIP":1}
    actual={"PRESSURE":len(pressure),"SUPPORT_COUNTERBORE":len(counter),
            "SUPPORT_RECESS":len(recess),"SUPPORT_LIP":len(lip)}
    diagnostic={
        "expected":expected,
        "actual":actual,
        "selected":{
            "PRESSURE":pressure,
            "SUPPORT_COUNTERBORE":counter,
            "SUPPORT_RECESS":recess,
            "SUPPORT_LIP":lip,
        },
        "surfaces":records,
    }
    with open(os.path.join(a.out_dir,"ws01-1-selection-diagnostic.json"),"w",encoding="utf-8") as f:
        json.dump(diagnostic,f,indent=2)
    if actual!=expected:
        raise RuntimeError(f"WS01.1 CAD selection contract mismatch: expected={expected}, actual={actual}")

    groups={
        "PRESSURE":pressure,
        "SUPPORT_COUNTERBORE":counter,
        "SUPPORT_RECESS":recess,
        "SUPPORT_LIP":lip,
    }
    for name,tags in groups.items():
        pg=gmsh.model.addPhysicalGroup(2,tags)
        gmsh.model.setPhysicalName(2,pg,name)
    vg=gmsh.model.addPhysicalGroup(3,vols)
    gmsh.model.setPhysicalName(3,vg,"SOLID")

    gmsh.option.setNumber("Mesh.MeshSizeMin", a.mesh_size)
    gmsh.option.setNumber("Mesh.MeshSizeMax", a.mesh_size)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)

    if a.element_order == 2:
        gmsh.model.mesh.setOrder(2)
        # Curve midside nodes back onto the CAD so the quadratic geometry is
        # not merely a straight-sided TET4 mesh with extra nodes.
        try:
            gmsh.model.mesh.optimize("HighOrder")
        except Exception as exc:
            print(f"HighOrder optimization warning: {exc}")

    mesh_path=os.path.join(a.out_dir,"ws01-1-cap-fillets.med")
    gmsh.write(mesh_path)

    node_tags,coords,_=gmsh.model.mesh.getNodes()
    elem_types,elem_tags,_=gmsh.model.mesh.getElements(3)
    surf_types,surf_elem_tags,_=gmsh.model.mesh.getElements(2)
    elem_count=sum(len(x) for x in elem_tags)

    expected_volume_type = 11 if a.element_order == 2 else 4  # Gmsh TET10 / TET4
    expected_surface_type = 9 if a.element_order == 2 else 2  # Gmsh TRI6 / TRI3
    volume_types=[int(x) for x in elem_types]
    surface_types=[int(x) for x in surf_types]
    if volume_types != [expected_volume_type]:
        raise RuntimeError(f"WS01.1 mesh formulation mismatch: expected volume type {expected_volume_type}, got {volume_types}")
    if any(t != expected_surface_type for t in surface_types):
        raise RuntimeError(f"WS01.1 surface formulation mismatch: expected TRI type {expected_surface_type}, got {surface_types}")

    evidence={
        "case":"ANSYS Mechanical WS01.1 Mechanical Basics",
        "source_file":os.path.basename(a.input),
        "geometry":{"volumes":len(vols),"surfaces":len(surfs)},
        "surface_groups":groups,
        "surface_group_counts":actual,
        "mesh":{
            "target_size_mm":a.mesh_size,
            "order":a.element_order,
            "formulation":"TET10/TRI6" if a.element_order==2 else "TET4/TRI3",
            "nodes":len(node_tags),
            "volume_elements":elem_count,
            "surface_elements":sum(len(x) for x in surf_elem_tags),
            "element_types":volume_types,
            "surface_element_types":surface_types,
        },
        "material":{"name":"ANSYS Aluminum Alloy","E_MPa":71000.0,"nu":0.33,"yield_MPa":280.0},
        "load":{"type":"pressure","magnitude_MPa":1.1,"group":"PRESSURE"},
        "supports":[
            {"type":"frictionless","group":"SUPPORT_COUNTERBORE","implementation":"FACE_IMPO DNOR=0"},
            {"type":"frictionless","group":"SUPPORT_RECESS","implementation":"FACE_IMPO DNOR=0"},
            {"type":"frictionless","group":"SUPPORT_LIP","implementation":"FACE_IMPO DNOR=0"},
        ],
        "mesh_file":os.path.basename(mesh_path),
        "ansys_mesh_replication":{
            "target":"pre-refinement tutorial snapshot",
            "candidate_order":"quadratic",
            "candidate_volume_formulation":"TET10",
            "candidate_surface_formulation":"TRI6",
            "run_specific_ansys_element_count_attested":False,
            "note":"Tutorial source does not preserve its Workbench project/mesh database; formulation is reproduced, exact node/element count is not claimed."
        },
        "fea_values_invented":False,
    }
    with open(os.path.join(a.out_dir,"ws01-1-model-evidence.json"),"w",encoding="utf-8") as f:
        json.dump(evidence,f,indent=2)
finally:
    gmsh.finalize()
