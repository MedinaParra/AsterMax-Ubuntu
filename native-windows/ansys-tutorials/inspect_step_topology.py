import argparse
import json
import os
import gmsh

def inspect(path):
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.model.add(os.path.basename(path))
        imported = gmsh.model.occ.importShapes(path, highestDimOnly=False)
        gmsh.model.occ.synchronize()

        volumes = []
        for dim, tag in gmsh.model.getEntities(3):
            bbox = gmsh.model.getBoundingBox(dim, tag)
            mass = gmsh.model.occ.getMass(dim, tag)
            com = gmsh.model.occ.getCenterOfMass(dim, tag)
            boundary = gmsh.model.getBoundary([(dim, tag)], combined=False, oriented=False, recursive=False)
            volumes.append({
                "tag": tag,
                "name": gmsh.model.getEntityName(dim, tag),
                "volume": mass,
                "center_of_mass": list(com),
                "bounds": list(bbox),
                "surface_tags": sorted({t for d, t in boundary if d == 2}),
            })

        surfaces = []
        for dim, tag in gmsh.model.getEntities(2):
            bbox = gmsh.model.getBoundingBox(dim, tag)
            mass = gmsh.model.occ.getMass(dim, tag)
            com = gmsh.model.occ.getCenterOfMass(dim, tag)
            up, down = gmsh.model.getAdjacencies(dim, tag)
            surfaces.append({
                "tag": tag,
                "name": gmsh.model.getEntityName(dim, tag),
                "area": mass,
                "center_of_mass": list(com),
                "bounds": list(bbox),
                "adjacent_volumes": sorted(int(x) for x in up),
            })

        return {
            "source_file": os.path.basename(path),
            "imported_dim_tags": [[int(d), int(t)] for d, t in imported],
            "volume_count": len(volumes),
            "surface_count": len(surfaces),
            "volumes": volumes,
            "surfaces": surfaces,
        }
    finally:
        gmsh.finalize()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = inspect(args.input)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(json.dumps({
        "source_file": data["source_file"],
        "volume_count": data["volume_count"],
        "surface_count": data["surface_count"],
    }))

if __name__ == "__main__":
    main()
