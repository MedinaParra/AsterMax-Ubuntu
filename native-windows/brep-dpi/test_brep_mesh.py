"""Real OCC meshing regression; compares tetra volumes with CAD dimensions."""
from pathlib import Path
import argparse
import json
import math
import tempfile
from netgen.occ import Cylinder, Pnt, Z
from netgen.meshing import Mesh
from brep_mesh import run


def volume(mesh):
    result = 0.0
    for element in mesh.Elements3D():
        vertices = [mesh[p].p for p in element.vertices]
        if len(vertices) != 4:
            raise AssertionError('Expected tetrahedral volume elements')
        a, b, c, d = vertices
        u, v, w = [[p[i]-a[i] for i in range(3)] for p in [b,c,d]]
        determinant = u[0]*(v[1]*w[2]-v[2]*w[1])-u[1]*(v[0]*w[2]-v[2]*w[0])+u[2]*(v[0]*w[1]-v[1]*w[0])
        measure = abs(determinant)/6
        if not math.isfinite(measure) or measure <= 1e-12:
            raise AssertionError('Non-finite or degenerate tetrahedron')
        result += measure
    return result


def test(out):
    fixtures = Path(__file__).with_name('fixtures')
    out.mkdir(parents=True, exist_ok=True)
    refinement=out/'refinement'; refinement.write_text('0\n0\n')
    tube=Cylinder(Pnt(0,0,0), Z, 5, 20)-Cylinder(Pnt(0,0,0), Z, 2, 20)
    tube.WriteBrep(str(out/'tube.brep'))
    rows=[]
    for name, brep, expected, tolerance, size in [
        ('b01',fixtures/'b01.brep',10000.0,1e-9,5),
        ('tube',out/'tube.brep',math.pi*(25-4)*20,0.03,1)]:
        params=(fixtures/'meshParameters').read_text().splitlines()
        params[3]=str(size)
        params[23]='1' # curved second-order nodes, using the native OCC geometry
        param_file=out/(name+'.parameters');param_file.write_text('\n'.join(params)+'\n')
        output=out/(name+'.vol')
        run(brep,output,param_file,refinement)
        mesh=Mesh(dim=3);mesh.Load(str(output))
        measured=volume(mesh)
        error=abs(measured-expected)/expected
        assert error < tolerance,(name,measured,expected,error)
        assert all(len(e.points)==10 for e in mesh.Elements3D()), 'Quadratic tetrahedra were not produced'
        rows.append(dict(case=name,cad_volume_mm3=expected,
            corner_tetra_volume_mm3=measured,relative_error=error,tolerance=tolerance,
            nodes=len(list(mesh.Points())),elements=len(list(mesh.Elements3D())),stl_conversion=False))
    result={'pass':True,'cases':rows,'solver_execution':False,'fea_results_invented':False}
    (out/'brep-regression.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    test(parser.parse_args().out)
