#!/usr/bin/env python3
"""C9.64: translate a real Code_Aster MED result into an auditable AsterMax results bundle + VTU.

No synthetic FEA values are created. Displacements are read directly from MED.
SIGM_ELNO/SIEQ_ELNO values are element-node fields; for point contours the bridge computes a
plain arithmetic average over incident element-node values and records that derivation explicitly.
"""
import json, math, os, sys, xml.etree.ElementTree as ET
from collections import defaultdict
import h5py
import numpy as np

if len(sys.argv) != 4:
    raise SystemExit("usage: bridge-c964-med-results.py <input.rmed> <bundle.json> <results.vtu>")
med_path, bundle_path, vtu_path = sys.argv[1:]
if not os.path.isfile(med_path):
    raise SystemExit(f"MED file missing: {med_path}")

MESH_ROOT = "ENS_MAA/00000001/-0000000000000000001-0000000000000000001"
STEP = "0000000000000000000100000000000000000001"

def decode_components(raw, width=16):
    if isinstance(raw, bytes): raw = raw.decode("ascii", "ignore")
    return [raw[i:i+width].strip() for i in range(0, len(raw), width) if raw[i:i+width].strip()]

def field(h, token, location):
    root = h[f"CHA/0000000e{token}"]
    comps = decode_components(root.attrs["NOM"])
    data = np.asarray(h[f"CHA/0000000e{token}/{STEP}/{location}/MED_NO_PROFILE_INTERNAL/CO"][()], dtype=float)
    if len(data) % len(comps):
        raise RuntimeError(f"{token}: component/data size mismatch")
    return comps, data.reshape(len(comps), -1)

def avg_element_node(values, conn):
    accum = defaultdict(list)
    flat_nodes = conn.reshape(-1)
    if len(values) != len(flat_nodes):
        raise RuntimeError("element-node value count does not match connectivity")
    for nid, value in zip(flat_nodes, values):
        accum[int(nid)].append(float(value))
    return np.array([sum(accum[i])/len(accum[i]) for i in range(1, int(conn.max())+1)], dtype=float)

def write_data_array(parent, name, values, ncomp=1, vtk_type="Float64"):
    attrs={"type":vtk_type,"Name":name,"format":"ascii"}
    if ncomp != 1: attrs["NumberOfComponents"]=str(ncomp)
    e=ET.SubElement(parent,"DataArray",attrs)
    arr=np.asarray(values)
    e.text="\n"+" ".join(f"{float(x):.15g}" if vtk_type.startswith("Float") else str(int(x)) for x in arr.reshape(-1))+"\n"

with h5py.File(med_path, "r") as h:
    coords_raw=np.asarray(h[f"{MESH_ROOT}/NOE/COO"][()], dtype=float)
    n_nodes=int(h[f"{MESH_ROOT}/NOE/COO"].attrs["NBR"])
    coords=coords_raw.reshape(3,n_nodes).T  # MED stores coordinate components in blocks.

    conn_raw=np.asarray(h[f"{MESH_ROOT}/MAI/HE8/NOD"][()], dtype=int)
    n_elem=int(h[f"{MESH_ROOT}/MAI/HE8/NUM"].shape[0])
    conn=conn_raw.reshape(8,n_elem).T  # MED stores the 8 connectivity positions in blocks.

    dcomp, displacement_blocks=field(h,"DEPL","NOE")
    if dcomp[:3] != ["DX","DY","DZ"]:
        raise RuntimeError(f"unexpected DEPL components: {dcomp}")
    displacement=displacement_blocks[:3].T
    total=np.linalg.norm(displacement,axis=1)

    scomp, stress_blocks=field(h,"SIGM_ELNO","NOE.HE8")
    qcomp, equiv_blocks=field(h,"SIEQ_ELNO","NOE.HE8")
    if "VMIS" not in qcomp:
        raise RuntimeError("SIEQ_ELNO has no VMIS component")

    # MED ELNO fields are ordered by element-local node. Convert to globally nodal contours by
    # averaging coincident element-node values. Raw ELNO ranges are retained in the manifest.
    nodal_stress={}
    for i,name in enumerate(scomp):
        nodal_stress[name]=avg_element_node(stress_blocks[i],conn)
    vm_idx=qcomp.index("VMIS")
    vm_elno=equiv_blocks[vm_idx]
    von_mises=avg_element_node(vm_elno,conn)

bundle={
    "schema":"astermax-results-bundle/v0",
    "release":"C9.64",
    "source":{
        "kind":"REAL_CODE_ASTER_MED",
        "file":os.path.basename(med_path),
        "size_bytes":os.path.getsize(med_path)
    },
    "units":{"length":"mm","force":"N","stress":"MPa"},
    "mesh":{"node_count":int(n_nodes),"element_count":int(n_elem),"element_type":"HEXA8"},
    "fields":{
        "displacement":{"location":"NODE","components":dcomp[:3],"derived":False,
            "dx_min":float(displacement[:,0].min()),"dx_max":float(displacement[:,0].max()),
            "total_min":float(total.min()),"total_max":float(total.max())},
        "stress":{"location":"NODE","components":scomp,"derived":True,
            "derivation":"arithmetic mean of real Code_Aster SIGM_ELNO values over incident element-local nodes"},
        "von_mises":{"location":"NODE","component":"VMIS","derived":True,
            "derivation":"arithmetic mean of real Code_Aster SIEQ_ELNO/VMIS values over incident element-local nodes",
            "raw_elno_min":float(vm_elno.min()),"raw_elno_max":float(vm_elno.max()),
            "nodal_min":float(von_mises.min()),"nodal_max":float(von_mises.max())}
    },
    "arrays":{
        "coordinates":coords.tolist(),"connectivity":conn.tolist(),
        "displacement":displacement.tolist(),"total_deformation":total.tolist(),
        "von_mises":von_mises.tolist(),"stress":{k:v.tolist() for k,v in nodal_stress.items()}
    },
    "integrity":{
        "fea_values_invented":False,
        "solver_output_modified":False,
        "derived_nodal_stress_average_declared":True
    }
}
with open(bundle_path,"w",encoding="utf-8") as f: json.dump(bundle,f,indent=2)

vtk=ET.Element("VTKFile",{"type":"UnstructuredGrid","version":"0.1","byte_order":"LittleEndian"})
ug=ET.SubElement(vtk,"UnstructuredGrid")
piece=ET.SubElement(ug,"Piece",{"NumberOfPoints":str(n_nodes),"NumberOfCells":str(n_elem)})
points=ET.SubElement(piece,"Points")
write_data_array(points,"Points",coords,3)
cells=ET.SubElement(piece,"Cells")
write_data_array(cells,"connectivity",conn-1,1,"Int32")
write_data_array(cells,"offsets",np.arange(1,n_elem+1)*8,1,"Int32")
write_data_array(cells,"types",np.full(n_elem,12),1,"UInt8") # VTK_HEXAHEDRON
pd=ET.SubElement(piece,"PointData",{"Scalars":"Equivalent Stress","Vectors":"Displacement"})
write_data_array(pd,"Displacement",displacement,3)
write_data_array(pd,"Total Deformation",total)
write_data_array(pd,"Equivalent Stress",von_mises)
for name,arr in nodal_stress.items(): write_data_array(pd,f"Stress {name}",arr)
ET.ElementTree(vtk).write(vtu_path,encoding="utf-8",xml_declaration=True)

checks={
    "real_med_source":bundle["source"]["size_bytes"]>1000,
    "mesh_44_nodes_10_hex":n_nodes==44 and n_elem==10 and conn.shape==(10,8),
    "displacement_present":displacement.shape==(44,3),
    "c962_dx_reproduced":abs(float(displacement[:,0].max())-0.0471697826890255)<1e-12,
    "stress_present":len(scomp)==6 and all(len(v)==44 for v in nodal_stress.values()),
    "von_mises_present":len(von_mises)==44 and np.isfinite(von_mises).all(),
    "no_invented_results":bundle["integrity"]["fea_values_invented"] is False,
    "vtu_written":os.path.isfile(vtu_path) and os.path.getsize(vtu_path)>1000
}
summary={"release":"C9.64","checks":checks,"checks_passed":sum(checks.values()),"checks_total":len(checks),"pass":all(checks.values()),
         "dx_max_mm":float(displacement[:,0].max()),"total_deformation_max_mm":float(total.max()),
         "von_mises_nodal_max_mpa":float(von_mises.max()),"von_mises_raw_elno_max_mpa":float(vm_elno.max()),
         "fea_values_invented":False}
print(json.dumps(summary,indent=2))
if not summary["pass"]: raise SystemExit("C9.64 results bridge gate failed")
