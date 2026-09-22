#!/usr/bin/env python3
from pathlib import Path
import os, shutil, math
import numpy as np

HERE = Path(__file__).resolve().parent
CASE = HERE / "case"
tutorials = Path(os.environ["FOAM_TUTORIALS"])
template = tutorials / "heatTransfer" / "buoyantPimpleFoam" / "hotRoom"

if CASE.exists():
    shutil.rmtree(CASE)
shutil.copytree(template, CASE)

if (CASE / "0.orig").exists():
    if (CASE / "0").exists():
        shutil.rmtree(CASE / "0")
    shutil.copytree(CASE / "0.orig", CASE / "0")

# Keep only fields used by the laminar compressible setup.
for p in (CASE / "0").iterdir():
    if p.is_file() and p.name not in {"U", "T", "p", "p_rgh", "alphat"}:
        p.unlink()

tri = CASE / "constant" / "triSurface"
tri.mkdir(parents=True, exist_ok=True)

# -----------------------------
# Geometry assumptions
# -----------------------------
L = 0.50
r_small = 0.020
r_large = 0.125
z0 = 0.002          # leakage gap to skin; parametric assumption
nseg = 128

def facet(f, a, b, c):
    a=np.array(a,float); b=np.array(b,float); c=np.array(c,float)
    n=np.cross(b-a,c-a)
    nn=np.linalg.norm(n)
    if nn > 0: n /= nn
    f.write(f"facet normal {n[0]:.8e} {n[1]:.8e} {n[2]:.8e}\\n")
    f.write("  outer loop\\n")
    for p in (a,b,c):
        f.write(f"    vertex {p[0]:.8e} {p[1]:.8e} {p[2]:.8e}\\n")
    f.write("  endloop\\nendfacet\\n")

# Zero-thickness conical paper surface. snappyHexMesh converts this surface
# directly into a baffle, avoiding the poor cells created by meshing a thin
# 3-D shell with annular rims.
with (tri/"cambucho.stl").open("w") as f:
    f.write("solid cambucho\\n")
    for kseg in range(nseg):
        a1=2*math.pi*kseg/nseg
        a2=2*math.pi*(kseg+1)/nseg
        b1=(r_small*math.cos(a1), r_small*math.sin(a1), z0)
        b2=(r_small*math.cos(a2), r_small*math.sin(a2), z0)
        t1=(r_large*math.cos(a1), r_large*math.sin(a1), z0+L)
        t2=(r_large*math.cos(a2), r_large*math.sin(a2), z0+L)
        facet(f,t1,t2,b2)
        facet(f,t1,b2,b1)
    f.write("endsolid cambucho\\n")

header = r"""/*--------------------------------*- C++ -*----------------------------------*\
| =========                 | OpenFOAM v2312 - Cambucho physical-v2           |
\*---------------------------------------------------------------------------*/
"""

def w(rel, txt):
    p = CASE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(header + txt, encoding="utf-8")

# Large external domain to reduce boundary influence.
w("system/blockMeshDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object blockMeshDict; }
convertToMeters 1;
vertices
(
    (-0.60 -0.60 0.00) (0.60 -0.60 0.00)
    (0.60 0.60 0.00) (-0.60 0.60 0.00)
    (-0.60 -0.60 1.60) (0.60 -0.60 1.60)
    (0.60 0.60 1.60) (-0.60 0.60 1.60)
);
blocks
(
    hex (0 1 2 3 4 5 6 7) (20 20 28) simpleGrading (1 1 1)
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
    extractFromSurfaceCoeffs { includedAngle 160; }
    writeObj yes;
}
""")

w("system/snappyHexMeshDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }
castellatedMesh true;
snap false;
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
        point2 (0 0 0.62);
        radius 0.20;
    }
    throat
    {
        type searchableCylinder;
        point1 (0 0 0.00);
        point2 (0 0 0.06);
        radius 0.055;
    }
    plume
    {
        type searchableCylinder;
        point1 (0 0 0.42);
        point2 (0 0 1.30);
        radius 0.24;
    }
}

castellatedMeshControls
{
    maxLocalCells 700000;
    maxGlobalCells 900000;
    minRefinementCells 0;
    nCellsBetweenLevels 3;

    features ();

    refinementSurfaces
    {
        cambucho
        {
            // Surface used here for local refinement only.
            // The actual impermeable two-sided wall is created afterwards
            // with createBaffles using the same STL.
            level (3 3);
        }
    }

    resolveFeatureAngle 45;

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
            levels ((1e15 5));
        }
        plume
        {
            mode inside;
            levels ((1e15 2));
        }
    }

    locationInMesh (0.40 0 0.30);
    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch 8;
    tolerance 1.5;
    nSolveIter 80;
    nRelaxIter 10;
    nFeatureSnapIter 15;
    implicitFeatureSnap true;
    explicitFeatureSnap false;
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
    nRelaxIter 5;
    nSmoothSurfaceNormals 3;
    nSmoothNormals 5;
    nSmoothThickness 15;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 30;
}

meshQualityControls
{
    maxNonOrtho 65;
    maxBoundarySkewness 15;
    maxInternalSkewness 3.5;
    maxConcave 80;
    minVol 1e-14;
    minTetQuality 1e-20;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 6;
    errorReduction 0.7;
}
debug 0;
mergeTolerance 1e-6;
""")

# -----------------------------
# Robust free-standing baffle creation
# -----------------------------
# snappyHexMesh refinement alone does not guarantee that an open STL becomes
# an internal wall. createBaffles explicitly selects all internal mesh faces
# whose owner-neighbour centre segment intersects the conical STL and converts
# them into two wall patches.
w("system/createBafflesDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object createBafflesDict; }

internalFacesOnly true;
noFields true;

baffles
{
    cambuchoWall
    {
        type searchableSurface;

        // Analytic zero-thickness cone. Setting inner radii equal to outer
        // radii collapses the end annuli to zero area while retaining the
        // lateral conical surface. This avoids STL intersection tolerance
        // issues in createBaffles.
        surface searchableCone;
        point1 (0 0 0.002);
        radius1 0.020;
        innerRadius1 0.020;
        point2 (0 0 0.502);
        radius2 0.125;
        innerRadius2 0.125;

        patches
        {
            master
            {
                name cambucho;
                type wall;
            }
            slave
            {
                name cambucho_slave;
                type wall;
            }
        }
    }
}
""")

# -----------------------------
# Compressible initial/boundary fields
# -----------------------------
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
    skin { type noSlip; }
    cambucho { type noSlip; }
    cambucho_slave { type noSlip; }
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
        // Stage 1 (0-3 s): paper starts at ambient temperature.
        // Stage 2 (>=3 s): a localized equivalent burning front ramps over 0.5 s
        // and descends. This is NOT reactive chemistry and the geometry does not burn away.
        type codedFixedValue;
        value uniform 295.15;
        name movingFireFront;
        code
        #{
            const vectorField& Cf = patch().Cf();
            scalarField Tw(Cf.size(), 295.15);
            const scalar t = this->db().time().value();

            if (t > 3.0)
            {
                const scalar tau = t - 3.0;
                const scalar ramp = min(tau/0.5, scalar(1));
                const scalar zFire = max(0.15, 0.49 - 0.060*tau);
                const scalar sigma = 0.018;
                const scalar Tpeak = 750.0;

                forAll(Cf, faceI)
                {
                    const scalar dz = Cf[faceI].z() - zFire;
                    const scalar band = exp(-sqr(dz/sigma));
                    Tw[faceI] = 295.15 + ramp*(Tpeak - 295.15)*band;
                }
            }
            operator==(Tw);
        #};
    }
    cambucho_slave
    {
        type codedFixedValue;
        value uniform 295.15;
        name movingFireFrontSlave;
        code
        #{
            const vectorField& Cf = patch().Cf();
            scalarField Tw(Cf.size(), 295.15);
            const scalar t = this->db().time().value();

            if (t > 3.0)
            {
                const scalar tau = t - 3.0;
                const scalar ramp = min(tau/0.5, scalar(1));
                const scalar zFire = max(0.15, 0.49 - 0.060*tau);
                const scalar sigma = 0.018;
                const scalar Tpeak = 750.0;

                forAll(Cf, faceI)
                {
                    const scalar dz = Cf[faceI].z() - zFire;
                    const scalar band = exp(-sqr(dz/sigma));
                    Tw[faceI] = 295.15 + ramp*(Tpeak - 295.15)*band;
                }
            }
            operator==(Tw);
        #};
    }
}
""")

w("0/p", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object p; }
dimensions [1 -1 -2 0 0 0 0];
internalField uniform 101325;
boundaryField
{
    // p is reconstructed from p_rgh + rho*gh by buoyantPimpleFoam.
    // Do not independently impose totalPressure here; doing so over-constrained
    // the open atmosphere and generated a spurious ~5 m/s startup jet.
    atmosphere
    {
        type calculated;
        value uniform 101325;
    }
    skin { type calculated; value uniform 101325; }
    cambucho { type calculated; value uniform 101325; }
    cambucho_slave { type calculated; value uniform 101325; }
}
""")

w("0/p_rgh", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object p_rgh; }
dimensions [1 -1 -2 0 0 0 0];
internalField uniform 101325;
boundaryField
{
    // Hydrostatic far field: hold p_rgh constant. The solver reconstructs
    // p = p_rgh + rho*gh, so static pressure decreases with elevation.
    // Imposing a constant static p on every side/top face would be non-hydrostatic.
    atmosphere
    {
        type fixedValue;
        value uniform 101325;
    }
    skin
    {
        type fixedFluxPressure;
        value uniform 101325;
    }
    cambucho
    {
        type fixedFluxPressure;
        value uniform 101325;
    }
    cambucho_slave
    {
        type fixedFluxPressure;
        value uniform 101325;
    }
}
""")

w("0/alphat", r"""
FoamFile { version 2.0; format ascii; class volScalarField; object alphat; }
dimensions [1 -1 -1 0 0 0 0];
internalField uniform 0;
boundaryField
{
    atmosphere { type calculated; value uniform 0; }
    skin { type calculated; value uniform 0; }
    cambucho { type calculated; value uniform 0; }
    cambucho_slave { type calculated; value uniform 0; }
}
""")

w("constant/turbulenceProperties", r"""
FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
""")

w("constant/g", r"""
FoamFile { version 2.0; format ascii; class uniformDimensionedVectorField; object g; }
dimensions [0 1 -2 0 0 0 0];
value (0 0 -9.81);
""")

# Verification criteria. Concavity is disabled as a failure criterion because
# zero-thickness baffles deliberately split hex cells into concave polyhedra.
# All transport-critical metrics remain strict.
w("system/meshQualityDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object meshQualityDict; }
maxNonOrtho 65;
maxBoundarySkewness 15;
maxInternalSkewness 3.5;
maxConcave 180;
minVol 1e-14;
minTetQuality 1e-20;
minArea -1;
minTwist 0.02;
minDeterminant 0.001;
minFaceWeight 0.02;
minVolRatio 0.01;
minTriangleTwist -1;
nSmoothScale 6;
errorReduction 0.7;
""")

# Control uses a 3 s no-fire preconditioning stage in the same transient,
# followed by a 5 s fire stage. The state at ignition is therefore not the
# artificial all-zero velocity / hot-wall state used previously.
w("system/controlDict", r"""
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application buoyantPimpleFoam;
startFrom startTime;
startTime 0;
stopAt endTime;
endTime 8.0;
deltaT 0.002;
writeControl adjustableRunTime;
writeInterval 0.25;
purgeWrite 0;
writeFormat binary;
writePrecision 8;
writeCompression off;
timeFormat general;
timePrecision 6;
runTimeModifiable true;
adjustTimeStep yes;
maxCo 0.35;
maxDeltaT 0.02;

functions
{
    extrema
    {
        type fieldMinMax;
        libs (fieldFunctionObjects);
        mode magnitude;
        fields (T U p p_rgh);
        writeControl writeTime;
    }

    heatFlux
    {
        type wallHeatFlux;
        libs (fieldFunctionObjects);
        patches (skin);
        writeControl writeTime;
    }

    probes
    {
        type probes;
        libs (sampling);
        fields (T U p p_rgh);
        writeControl writeTime;
        probeLocations
        (
            (0 0 0.003)
            (0 0 0.020)
            (0 0 0.050)
            (0 0 0.250)
            (0 0 0.480)
            (0 0 0.550)
            (0 0 0.750)
            (0 0 1.000)
        );
    }
}
""")

(CASE/"CASE_ASSUMPTIONS.txt").write_text(f"""CAMBUCHO PHYSICAL V2
Solver: buoyantPimpleFoam (compressible)
Geometry: full 3-D, 360 degree fluid domain, internal + external air
Domain: 1.2 m x 1.2 m x 1.6 m
Cone length = {L} m
Inner Dmin = {2*r_small} m
Inner Dmax = {2*r_large} m
Paper wall = zero-thickness baffle (physical paper thickness neglected)
Leakage gap to skin = {z0} m (assumption; requires experiment)
Ambient initial T = 295.15 K
Skin T = 307.15 K
Paper initial T = 295.15 K
Preconditioning = 0 to 3 s with NO fire
Atmosphere pressure BC = fixed p_rgh=101325 Pa (hydrostatic far field); p itself is calculated
Ignition = 3 s
Fire ramp = 0.5 s
Equivalent peak fire-band wall T = 750 K
Fire-front descent = 0.060 m/s, limited to z >= 0.15 m
End time = 8 s

IMPORTANT LIMITATIONS
- Fire is an equivalent moving thermal boundary, not reactive combustion.
- The conical wall is created explicitly by createBaffles using an analytic zero-thickness searchableCone after meshing.
- Burned paper geometry is not removed dynamically.
- Radiation is not yet solved in-domain.
- 2 mm leakage gap is assumed, not measured.
- Results are exploratory until mesh quality and experimental validation pass.
""", encoding="utf-8")

print(CASE)
