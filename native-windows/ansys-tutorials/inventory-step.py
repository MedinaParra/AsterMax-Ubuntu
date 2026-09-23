import json, os, sys, math
import gmsh

def vec3(v):
    return [float(x) for x in v]

def inspect(step_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.model.add(os.path.basename(step_path))
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()
        vols = gmsh.model.getEntities(3)
        surfs = gmsh.model.getEntities(2)
        volume_rows=[]
        for dim,tag in vols:
            volume_rows.append({
                "tag": tag,
                "mass_volume": gmsh.model.occ.getMass(dim,tag),
                "center": vec3(gmsh.model.occ.getCenterOfMass(dim,tag)),
                "bbox": vec3(gmsh.model.getBoundingBox(dim,tag)),
                "boundary_surfaces":[int(t) for d,t in gmsh.model.getBoundary([(dim,tag)], oriented=False, recursive=False) if d==2],
            })
        surface_rows=[]
        for dim,tag in surfs:
            bbox=gmsh.model.getBoundingBox(dim,tag)
            center=gmsh.model.occ.getCenterOfMass(dim,tag)
            try:
                typ=gmsh.model.getType(dim,tag)
            except Exception:
                typ=None
            adj=gmsh.model.getAdjacencies(dim,tag)
            surface_rows.append({
                "tag":tag,
                "type":typ,
                "area":float(gmsh.model.occ.getMass(dim,tag)),
                "center":vec3(center),
                "bbox":vec3(bbox),
                "adjacent_volumes":[int(x) for x in adj[0]],
            })

        # Bounded coarse volume mesh for topology/capability validation, not the final
        # tutorial accuracy mesh. This keeps the multi-part pump smoke deterministic.
        all_boxes=[v["bbox"] for v in volume_rows]
        if all_boxes:
            xmin=min(b[0] for b in all_boxes); ymin=min(b[1] for b in all_boxes); zmin=min(b[2] for b in all_boxes)
            xmax=max(b[3] for b in all_boxes); ymax=max(b[4] for b in all_boxes); zmax=max(b[5] for b in all_boxes)
            diag=math.sqrt((xmax-xmin)**2+(ymax-ymin)**2+(zmax-zmin)**2)
        else:
            diag=100.0
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 6)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", max(diag/10.0, 1e-3))
        gmsh.option.setNumber("Mesh.MeshSizeMin", max(diag/40.0, 1e-4))
        gmsh.model.mesh.generate(3)
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        types,tags,nodeTags=gmsh.model.mesh.getElements(3)
        element_count=sum(len(x) for x in tags)
        base=os.path.splitext(os.path.basename(step_path))[0]
        msh=os.path.join(out_dir,base+".msh")
        gmsh.write(msh)
        report={
            "source":os.path.basename(step_path),
            "volumes":volume_rows,
            "surfaces":surface_rows,
            "surface_count":len(surface_rows),
            "volume_count":len(volume_rows),
            "geometry_diagonal":diag,
            "mesh":{"nodes":len(node_tags),"volume_elements":element_count,"msh":os.path.basename(msh),
                    "purpose":"COARSE_TOPOLOGY_CAPABILITY_SMOKE_NOT_FINAL_FEA"},
            "invented_fea_results":False,
        }
        with open(os.path.join(out_dir,base+"-inventory.json"),"w",encoding="utf-8") as f:
            json.dump(report,f,indent=2)
        print(json.dumps({"source":report["source"],"volumes":report["volume_count"],"surfaces":report["surface_count"],"nodes":report["mesh"]["nodes"],"elements":report["mesh"]["volume_elements"]}))
    finally:
        gmsh.finalize()

if __name__=="__main__":
    if len(sys.argv)<3:
        raise SystemExit("usage: inventory-step.py OUT_DIR STEP...")
    out=sys.argv[1]
    for p in sys.argv[2:]:
        inspect(p,out)
