from pathlib import Path

import numpy as np

from astermax.mesh_inspector import build_mesh_inspector_payload, write_mesh_inspector


def test_mesh_inspector_regular_tet_is_pass(tmp_path: Path):
    nodes=np.array([[0.,0.,0.],[1.,0.,0.],[0.5,0.866025403784,0.],[0.5,0.288675134595,0.816496580928]])
    elements=np.array([[0,1,2,3]],dtype=int)
    p=build_mesh_inspector_payload(nodes,elements)
    assert p['gate_report']['status']=='PASS'
    assert p['elements'][0]['status']=='PASS'
    assert p['worst_element_index']==0
    assert p['claims']['acceptance_driven_by_inspector_ranking'] is False
    out=tmp_path/'mesh.html'; m=write_mesh_inspector(out,nodes,elements)
    assert out.is_file() and 'Mesh Inspector' in out.read_text(encoding='utf-8')
    assert len(m['html_sha256'])==64


def test_mesh_inspector_inverted_tet_is_fail():
    nodes=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    elements=np.array([[0,2,1,3]],dtype=int)
    p=build_mesh_inspector_payload(nodes,elements)
    assert p['gate_report']['status']=='FAIL'
    assert p['gate_report']['inverted_elements']==1
    assert p['elements'][0]['status']=='FAIL'


def test_mesh_inspector_tet10_uses_volume_owner_for_surface_coloring():
    nodes=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[.5,0,0],[.5,.5,0],[0,.5,0],[0,0,.5],[0,.5,.5],[.5,0,.5]])
    elements=np.array([[0,1,2,3,4,5,6,7,8,9]],dtype=int)
    p=build_mesh_inspector_payload(nodes,elements)
    assert len(p['surface_triangles'])==16
    assert set(p['surface_owner'])=={0}
    assert p['gate_report']['element_count']==1
