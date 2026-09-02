from __future__ import annotations

from pathlib import Path
import tempfile

import h5py
import numpy as np
import gmsh

from astermax.med_physical_group import write_med_with_surface_group


def _decode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        if value.dtype.kind in {"S", "U", "O"}:
            return [_decode(v) for v in value.reshape(-1).tolist()]
        return None
    return str(value) if isinstance(value, str) else None


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="astermax-med-diagnostic-"))
    med = root / "witness.med"
    nodes = np.array([[0.,0.,0.],[10.,0.,0.],[0.,10.,0.],[0.,0.,10.]], dtype=float)
    tet = np.array([[0,1,2,3]], dtype=int)
    tri = np.array([[0,1,2]], dtype=int)
    write_med_with_surface_group(med, nodes_mm=nodes, tetra4=tet, surface_tri3=tri, surface_group="LOAD_FACE", volume_group="SOLID")

    print(f"MED={med}")
    print(f"SIZE={med.stat().st_size}")

    gmsh.initialize()
    try:
        gmsh.clear()
        gmsh.open(str(med))
        print("GMSH_PHYSICAL_GROUPS", gmsh.model.getPhysicalGroups())
        for dim in (0,1,2,3):
            print("GMSH_ENTITIES", dim, gmsh.model.getEntities(dim))
            for _, tag in gmsh.model.getEntities(dim):
                try:
                    print("ENTITY_NAME", dim, tag, repr(gmsh.model.getEntityName(dim, tag)))
                except Exception as exc:
                    print("ENTITY_NAME_ERROR", dim, tag, repr(exc))
    finally:
        gmsh.finalize()

    print("HDF5_BEGIN")
    with h5py.File(med, "r") as handle:
        def visitor(name, obj):
            attrs = {}
            for key, value in obj.attrs.items():
                decoded = _decode(value)
                if decoded is not None:
                    attrs[key] = decoded
            if attrs:
                print("H5ATTR", name, attrs)
            if isinstance(obj, h5py.Dataset):
                try:
                    decoded = _decode(obj[()])
                except Exception:
                    decoded = None
                if decoded is not None:
                    print("H5DATA", name, decoded)
        handle.visititems(visitor)
    print("HDF5_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
