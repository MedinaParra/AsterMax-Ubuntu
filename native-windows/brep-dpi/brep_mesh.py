"""Native Netgen/OCC BREP adapter. No STL conversion and no solver execution."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import sys


def parameters(path):
    lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    if len(lines) % 2:
        raise ValueError('Incomplete meshing parameter record')
    values = {}
    for i in range(0, len(lines), 2):
        name = lines[i].split()[1]
        values[name] = lines[i+1].strip()
    return values


def run(brep, output, params, refinement):
    from netgen.occ import OCCGeometry
    from netgen.meshing import MeshingParameters
    v = parameters(params)
    def number(name):
        value = float(v[name])
        if not math.isfinite(value):
            raise ValueError('Non-finite meshing parameter: ' + name)
        return value
    if number('maxh') <= 0 or not 0 < number('grading') <= 1:
        raise ValueError('Invalid mesh size or grading')
    if number('quad_dominated'):
        raise ValueError('The Code_Aster tetrahedral BREP adapter does not accept quad-dominated meshing')
    geom = OCCGeometry(str(Path(brep).resolve()))
    mp = MeshingParameters(maxh=number('maxh'), minh=number('minh'),
        grading=number('grading'), segmentsperedge=number('elementsperedge'),
        curvaturesafety=number('elementspercurve'),
        optsteps2d=int(number('optsteps_2d')) if number('optsurfmeshenable') else 0,
        optsteps3d=int(number('optsteps_3d')) if number('optvolmeshenable') else 0,
        meshsizefilename=str(Path(refinement).resolve()))
    mesh = geom.GenerateMesh(mp=mp,
        closeedgefac=number('closeedgefact') if number('closeedgeenable') else None,
        minedgelen=number('minedgelen') if number('minedgelenenable') else None)
    if number('second_order'):
        mesh.SecondOrder()
    nodes = len(list(mesh.Points()))
    elements = len(list(mesh.Elements3D()))
    if nodes == 0 or elements == 0:
        raise ValueError('BREP meshing returned an empty volume mesh')
    target = Path(output)
    temp = target.with_name(target.stem + '.pending.vol')
    mesh.Save(str(temp))
    temp.replace(target)
    evidence = dict(pass_=True, route='BREP_OCC', stl_conversion=False,
        netgen_version=importlib.metadata.version('netgen-mesher'),
        occ_version=importlib.metadata.version('netgen-occt'),
        input_sha256=hashlib.sha256(Path(brep).read_bytes()).hexdigest(),
        output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        nodes=nodes, elements=elements, parameters=v)
    evidence['pass'] = evidence.pop('pass_')
    target.with_suffix('.brep-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print('ASTERMAX_BREP_OCC_PASS ' + json.dumps(evidence), flush=True)
    print('Points: ' + str(nodes), flush=True)
    print('Elements: ' + str(elements), flush=True)


if __name__ == '__main__':
    try:
        if len(sys.argv) != 6 or sys.argv[1] != 'BREP_MESH':
            raise ValueError('Expected BREP_MESH input.brep output.vol parameters refinements')
        run(*sys.argv[2:])
    except Exception as ex:
        print('ASTERMAX_BREP_OCC_FAIL: ' + str(ex), file=sys.stderr, flush=True)
        sys.exit(1)
