#!/usr/bin/env python3
"""Build the exact ANSYS WS01.1 Cap_fillets tutorial mesh for AsterMax/Code_Aster.

No FEA result values are embedded. Surface groups are selected from exact CAD
geometry invariants documented by the workshop and asserted by count.
"""
import argparse, json, math, os
import gmsh

p=argparse.ArgumentParser()
p.add_argument("--input", required=True)
p.add_argument("--out-dir", required=True)
p.add_argument("--mesh-size", type=float, default=3.0)
a=p.parse_args()
os.makedirs(a.out_dir, exist_ok=True)

gmsh.initialize()
try:
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("ANSYS_WS01_1_Cap_fillets")
    ents=gmsh.model.occ.importShapes(os.path.abspath(a.input))
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

    # Workshop: 17 exterior surfaces. For this exact CAD they are the continuous
    # outer skin around x/y envelope, excluding the open-side top rim, plus the
    # broad outside face at z=0.
    pressure=[]
    for r in records:
        b=r["bbox"]
        envelope=(near(b[0],0.0) or near(b[3],80.0) or near(b[1],0.0) or near(b[4],50.0))
        top_rim=flat_z(r,20.0) and r["area"]>200
        broad_outer=flat_z(r,0.0) and r["area"]>3000
        if (envelope and not top_rim) or broad_outer:
            pressure.append(r["tag"])

    # Four planar annular counterbore seats at z=1 mm.
    counter=[r["tag"] for r in records if flat_z(r,1.0) and 20.0<r["area"]<30.0]

    # Eight surfaces around the inner bottom recess: four straight walls and four
    # corner cylinders spanning z=3.5..15 at x/y = 2/78/2/48 mm.
    recess=[]
    for r in records:
        b=r["bbox"]
        inner_boundary=(near(b[0],2.0) or near(b[3],78.0) or near(b[1],2.0) or near(b[4],48.0))
        if inner_boundary and b[2]>=3.49-tol and b[5]<=15.01+tol and r["area"]>100:
            recess.append(r["tag"])

    # Single horizontal lip at z=15 mm.
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
    gmsh.option.setNumber("Mesh.ElementOrder", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)
    gmsh.model.mesh.generate(3)

    mesh_path=os.path.join(a.out_dir,"ws01-1-cap-fillets.mmed")
    gmsh.write(mesh_path)

    node_tags,coords,_=gmsh.model.mesh.getNodes()
    elem_types,elem_tags,_=gmsh.model.mesh.getElements(3)
    elem_count=sum(len(x) for x in elem_tags)
    evidence={
        "case":"ANSYS Mechanical WS01.1 Mechanical Basics",
        "source_file":os.path.basename(a.input),
        "geometry":{"volumes":len(vols),"surfaces":len(surfs)},
        "surface_groups":groups,
        "surface_group_counts":actual,
        "mesh":{"target_size_mm":a.mesh_size,"nodes":len(node_tags),"volume_elements":elem_count,
                "element_types":[int(x) for x in elem_types]},
        "material":{"name":"ANSYS Aluminum Alloy","E_MPa":71000.0,"nu":0.33,"yield_MPa":280.0},
        "load":{"type":"pressure","magnitude_MPa":1.1,"group":"PRESSURE"},
        "supports":[
            {"type":"frictionless","group":"SUPPORT_COUNTERBORE","implementation":"FACE_IMPO DNOR=0"},
            {"type":"frictionless","group":"SUPPORT_RECESS","implementation":"FACE_IMPO DNOR=0"},
            {"type":"frictionless","group":"SUPPORT_LIP","implementation":"FACE_IMPO DNOR=0"},
        ],
        "fea_values_invented":False,
    }
    with open(os.path.join(a.out_dir,"ws01-1-model-evidence.json"),"w",encoding="utf-8") as f:
        json.dump(evidence,f,indent=2)
finally:
    gmsh.finalize()
