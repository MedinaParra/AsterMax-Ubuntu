#!/usr/bin/env python3
from pathlib import Path
import os, shutil, math

HERE = Path(__file__).resolve().parent
CASE = HERE / "case"
tutorials = Path(os.environ["FOAM_TUTORIALS"])
template = tutorials / "heatTransfer" / "buoyantBoussinesqPimpleFoam" / "hotRoom"

if CASE.exists():
    shutil.rmtree(CASE)
shutil.copytree(template, CASE)

# Some OpenFOAM tutorials keep initial fields in 0.orig.
if (CASE / "0.orig").exists():
    if (CASE / "0").exists():
        shutil.rmtree(CASE / "0")
    shutil.copytree(CASE / "0.orig", CASE / "0")

# Keep only fields required by the laminar buoyantBoussinesq baseline.
# The hotRoom tutorial also carries turbulence fields (alphat/k/epsilon/nut);
# leaving them behind makes post-processing and patch validation fail after
# snappyHexMesh adds the skin/cambucho patches.
for p in (CASE / "0").iterdir():
    if p.is_file() and p.name not in {"U", "T", "p_rgh", "alphat"}:
        p.unlink()

tri = CASE / "constant" / "triSurface"
tri.mkdir(parents=True, exist_ok=True)

# Baseline geometry: full 360-degree conical newspaper shell.
# These are assumptions until the real cambucho is measured.
L = 0.50
r_small = 0.020       # Dmin = 40 mm at skin
r_large = 0.125       # Dmax = 250 mm
th = 0.008            # numerical wall thickness for robust meshing; NOT physical paper thickness
z0 = 0.002            # 2 mm above plane to avoid geometric degeneracy in first run
nseg = 96

def facet(f, a, b, c):
    import numpy as np
    a=np.array(a,float); b=np.array(b,float); c=np.array(c,float)
    n=np.cross(b-a,c-a)
    nn=np.linalg.norm(n)
    if nn > 0: n /= nn
    f.write(f"facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\n")
    f.write("  outer loop\n")
    for p in (a,b,c):
        f.write(f"    vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\n")
    f.write("  endloop\nendfacet\n")

import numpy as np
with (tri/"cambucho.stl").open("w") as f:
    f.write("solid cambucho\n")
    ri = r_small-th
    Ri = r_large-th
    for k in range(nseg):
        a1=2*math.pi*k/nseg
        a2=2*math.pi*(k+1)/nseg
        ob1=(r_small*math.cos(a1), r_small*math.sin(a1), z0)
        ob2=(r_small*math.cos(a2), r_small*math.sin(a2), z0)
        ot1=(r_large*math.cos(a1), r_large*math.sin(a1), z0+L)
        ot2=(r_large*math.cos(a2), r_large*math.sin(a2), z0+L)
        ib1=(ri*math.cos(a1), ri*math.sin(a1), z0)
        ib2=(ri*math.cos(a2), ri*math.sin(a2), z0)
        it1=(Ri*math.cos(a1), Ri*math.sin(a1), z0+L)
        it2=(Ri*math.cos(a2), Ri*math.sin(a2), z0+L)
        # outer and inner conical faces
        facet(f,ob1,ob2,ot2); facet(f,ob1,ot2,ot1)
        facet(f,it1,it2,ib2); facet(f,it1,ib2,ib1)
        # annular rims; central openings remain open
        facet(f,ot1,ot2,it2); facet(f,ot1,it2,it1)
        facet(f,ib1,ib2,ob2); facet(f,ib1,ob2,ob1)
    f.write("endsolid cambucho\n")

header = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 | OpenFOAM v2312 - Cambucho baseline             |
\\*---------------------------------------------------------------------------*/
"""

def w(rel, txt):
    p = CASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header + txt, encoding="utf-8")

w("system/blockMeshDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }
convertToMeters 1;
vertices
(
    (-0.30 -0.30 0.00) (0.30 -0.30 0.00)
    (0.30 0.30 0.00) (-0.30 0.30 0.00)
    (-0.30 -0.30 0.70) (0.30 -0.30 0.70)
    (0.30 0.30 0.70) (-0.30 0.30 0.70)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (16 16 20) simpleGrading (1 1 1)
);
edges ();
boundary
(
    skin
    {
        type wall;
        faces ((0 3 2 1));
    }
    atmosphere
    {
        type patch;
        faces
        (
            (4 5 6 7)
            (0 1 5 4)
            (1 2 6 5)
            (2 3 7 6)
            (3 0 4 7)
        );
    }
);
mergePatchPairs ();
""")

w("system/surfaceFeatureExtractDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object surfaceFeatureExtractDict; }
cambucho.stl
{
    extractionMethod extractFromSurface;
    extractFromSurfaceCoeffs { includedAngle 150; }
    writeObj yes;
}
""")

w("system/snappyHexMeshDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }

castellatedMesh true;
snap true;
addLayers false;

geometry
{
    cambucho.stl
    {
        type triSurfaceMesh;
        name cambucho;
    }

    nearCone
    {
        type searchableCylinder;
        point1 (0 0 0.00);
        point2 (0 0 0.56);
        radius 0.19;
    }

    throat
    {
        type searchableCylinder;
        point1 (0 0 0.00);
        point2 (0 0 0.10);
        radius 0.07;
    }
}

castellatedMeshControls
{
    maxLocalCells 500000;
    maxGlobalCells 750000;
    minRefinementCells 0;
    nCellsBetweenLevels 2;

    features
    (
        { file "cambucho.eMesh"; level 2; }
    );

    refinementSurfaces
    {
        cambucho
        {
            level (2 3);
            patchInfo { type wall; }
        }
    }

    resolveFeatureAngle 35;

    refinementRegions
    {
        nearCone
        {
            mode distance;
            levels ((0.035 3) (0.10 2));
        }
        throat
        {
            mode inside;
            levels ((1e15 3));
        }
    }

    locationInMesh (0.24 0 0.20);
    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 40;
    nRelaxIter 6;
    nFeatureSnapIter 8;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap false;
}

addLayersControls
{
    relativeSizes true;
    layers {};
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 20;
}

meshQualityControls
{
    maxNonOrtho 70;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-30;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}
debug 0;
mergeTolerance 1e-6;
""")

w("0/U", r"""
FoamFile { version 2.0; format ascii; class volVectorField; object U; }
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{
    atmosphere
    {
        type pressureInletOutletVelocity;
        value uniform (0 0 0);
    }
    skin
    {
        type noSlip;
    }
    cambucho
    {
        type noSlip;
    }
}
""")

w("0/T", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object T; }
dimensions [0 0 0 1 0 0 0];
internalField uniform 295.15;
boundaryField
{
    atmosphere
    {
        type inletOutlet;
        inletValue uniform 295.15;
        value uniform 295.15;
    }
    skin
    {
        type fixedValue;
        value uniform 307.15;
    }
    cambucho
    {
        // Baseline validation case: uniform hot wall.
        // Moving burn front will be introduced only after this solver/matrix is verified.
        type fixedValue;
        value uniform 373.15;
    }
}
""")

w("0/p_rgh", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object p_rgh; }
dimensions [0 2 -2 0 0 0 0];
internalField uniform 0;
boundaryField
{
    atmosphere
    {
        type fixedValue;
        value uniform 0;
    }
    skin
    {
        type fixedFluxPressure;
        rho rhok;
        value uniform 0;
    }
    cambucho
    {
        type fixedFluxPressure;
        rho rhok;
        value uniform 0;
    }
}
""")

w("0/alphat", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object alphat; }
dimensions [1 -1 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{
    atmosphere
    {
        type calculated;
        value uniform 0;
    }
    skin
    {
        type alphatJayatillekeWallFunction;
        Prt 0.85;
        value uniform 0;
    }
    cambucho
    {
        type alphatJayatillekeWallFunction;
        Prt 0.85;
        value uniform 0;
    }
}
""")

# Force laminar for a stable verification run.
w("constant/turbulenceProperties", r"""
FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
""")

w("constant/transportProperties", r"""
FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }
transportModel Newtonian;
nu      [0 2 -1 0 0 0 0] 1.55e-05;
beta    [0 0 0 -1 0 0 0] 3.38e-03;
TRef    [0 0 0 1 0 0 0] 295.15;
Pr      [0 0 0 0 0 0 0] 0.71;
Prt     [0 0 0 0 0 0 0] 0.85;
""")

w("constant/g", r"""
FoamFile { version 2.0; format ascii; class uniformDimensionedVectorField; object g; }
dimensions [0 1 -2 0 0 0 0];
value (0 0 -9.81);
""")

w("system/controlDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application buoyantBoussinesqPimpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 2.0;
deltaT 0.002;
writeControl adjustableRunTime;
writeInterval 0.10;
purgeWrite 0;
writeFormat binary;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable true;
adjustTimeStep yes;
maxCo 0.5;
maxDeltaT 0.02;

functions
{
    residuals
    {
        type residuals;
        libs (utilityFunctionObjects);
        fields (U p_rgh T);
        writeControl timeStep;
        writeInterval 1;
    }
    extrema
    {
        type fieldMinMax;
        libs (fieldFunctionObjects);
        mode magnitude;
        fields (T U p_rgh);
        writeControl writeTime;
    }
}
""")

(CASE/"CASE_ASSUMPTIONS.txt").write_text(
f"""OPENFOAM CAMBUCHO BASELINE
Solver: buoyantBoussinesqPimpleFoam
Geometry: 3-D, full 360 degree air domain inside and outside cone
L = {L} m
Dmin = {2*r_small} m
Dmax = {2*r_large} m
Numerical shell thickness = {th} m (not physical paper thickness; chosen for mesh robustness)
Bottom clearance used in verification mesh = {z0} m
Ambient = 295.15 K
Skin wall = 307.15 K
Cambucho wall = 373.15 K (uniform validation stage)
End time = 2 s

This first run validates the OpenFOAM mesh/solver pipeline.
It is NOT yet the final burning-paper model.
""", encoding="utf-8")

print(CASE)
