using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AsterMax.MechanicalGui;

internal readonly record struct Vec3(double X, double Y, double Z)
{
    public static Vec3 Zero => new(0, 0, 0);
    public double Length => Math.Sqrt(X * X + Y * Y + Z * Z);
    public static Vec3 operator +(Vec3 a, Vec3 b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
    public static Vec3 operator -(Vec3 a, Vec3 b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
    public static Vec3 operator *(Vec3 a, double s) => new(a.X * s, a.Y * s, a.Z * s);
    public static Vec3 operator /(Vec3 a, double s) => new(a.X / s, a.Y / s, a.Z / s);
    public override string ToString() => $"({X:0.###}, {Y:0.###}, {Z:0.###})";
}

internal enum SimpleFace { XMin, XMax, YMin, YMax, ZMin, ZMax }

internal sealed class SimpleStepSolid
{
    public required string SourcePath { get; init; }
    public required Vec3 Min { get; init; }
    public required Vec3 Max { get; init; }
    public required int CartesianPointCount { get; init; }
    public required bool IsSupportedPrism { get; init; }
    public required string FidelityMessage { get; init; }
    public double LengthX => Max.X - Min.X;
    public double LengthY => Max.Y - Min.Y;
    public double LengthZ => Max.Z - Min.Z;
    public double Volume => LengthX * LengthY * LengthZ;
    public Vec3 Center => (Min + Max) / 2.0;
}

internal sealed class StaticMaterial
{
    public string Name { get; set; } = "Structural Steel";
    public double YoungModulusMpa { get; set; } = 200000.0;
    public double PoissonRatio { get; set; } = 0.30;
    public double YieldStrengthMpa { get; set; } = 250.0;
}

internal sealed class SimpleStaticSetup
{
    public double ElementSizeMm { get; set; } = 25.0;
    public SimpleFace FixedFace { get; set; } = SimpleFace.XMin;
    public SimpleFace LoadFace { get; set; } = SimpleFace.XMax;
    public Vec3 ForceN { get; set; } = new(0, 0, -1000);
}

internal sealed class TetMesh
{
    public required List<Vec3> Nodes { get; init; }
    public required List<int[]> Elements { get; init; }
    public required int DivisionsX { get; init; }
    public required int DivisionsY { get; init; }
    public required int DivisionsZ { get; init; }
}

internal sealed class StaticSolution
{
    public required double[] Displacements { get; init; }
    public required double[] ElementVonMisesMpa { get; init; }
    public required Vec3 ReactionN { get; init; }
    public required Vec3 AppliedForceN { get; init; }
    public required double MaxDisplacementMm { get; init; }
    public required Vec3 LoadedFaceAverageDisplacementMm { get; init; }
    public required double MaxVonMisesMpa { get; init; }
    public required double EquilibriumError { get; init; }
    public required double? BeamTheoryDisplacementMm { get; init; }
    public required double? BeamTheoryStressMpa { get; init; }
    public required TimeSpan Elapsed { get; init; }
}

internal static class SimpleStepReader
{
    private static readonly Regex PointPattern = new(
        @"CARTESIAN_POINT\s*\(\s*[^,]*,\s*\(([^\)]*)\)\s*\)",
        RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.Compiled);

    public static SimpleStepSolid ReadPrismaticSolid(string path)
    {
        var text = File.ReadAllText(path);
        var scaleToMillimetres = DetectScaleToMillimetres(text);
        var points = new List<Vec3>();
        foreach (Match match in PointPattern.Matches(text))
        {
            var values = match.Groups[1].Value.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (values.Length < 3) continue;
            if (!double.TryParse(values[0], NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ||
                !double.TryParse(values[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var y) ||
                !double.TryParse(values[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var z)) continue;
            points.Add(new Vec3(x * scaleToMillimetres, y * scaleToMillimetres, z * scaleToMillimetres));
        }

        if (points.Count < 4)
            throw new InvalidDataException("The STEP file does not contain enough CARTESIAN_POINT entities to determine a solid envelope.");

        var min = new Vec3(points.Min(p => p.X), points.Min(p => p.Y), points.Min(p => p.Z));
        var max = new Vec3(points.Max(p => p.X), points.Max(p => p.Y), points.Max(p => p.Z));
        var dimensions = max - min;
        if (dimensions.X <= 1e-6 || dimensions.Y <= 1e-6 || dimensions.Z <= 1e-6)
            throw new InvalidDataException("The imported STEP envelope is not a three-dimensional solid.");

        var curved = Regex.IsMatch(text, @"\b(CYLINDRICAL_SURFACE|CONICAL_SURFACE|TOROIDAL_SURFACE|SPHERICAL_SURFACE|B_SPLINE_SURFACE|CIRCLE)\b", RegexOptions.IgnoreCase);
        var solidCount = Regex.Matches(text, @"\b(MANIFOLD_SOLID_BREP|FACETED_BREP)\s*\(", RegexOptions.IgnoreCase).Count;
        var diagonal = dimensions.Length;
        var tolerance = Math.Max(1e-6, diagonal * 1e-5);
        var boundaryPoints = points.Count(point =>
        {
            var boundaryCoordinates = 0;
            if (Near(point.X, min.X, tolerance) || Near(point.X, max.X, tolerance)) boundaryCoordinates++;
            if (Near(point.Y, min.Y, tolerance) || Near(point.Y, max.Y, tolerance)) boundaryCoordinates++;
            if (Near(point.Z, min.Z, tolerance) || Near(point.Z, max.Z, tolerance)) boundaryCoordinates++;
            return boundaryCoordinates >= 2;
        });
        var boundaryRatio = boundaryPoints / (double)points.Count;
        var supported = !curved && solidCount <= 1 && boundaryRatio >= 0.70;
        var fidelity = supported
            ? "Prismatic STEP accepted. The current solver represents the solid by its axis-aligned rectangular envelope."
            : "Unsupported STEP complexity detected. Only a single rectangular/prismatic solid without holes or curved surfaces is accepted in this beta.";

        return new SimpleStepSolid
        {
            SourcePath = path,
            Min = min,
            Max = max,
            CartesianPointCount = points.Count,
            IsSupportedPrism = supported,
            FidelityMessage = fidelity
        };
    }

    private static bool Near(double a, double b, double tolerance) => Math.Abs(a - b) <= tolerance;

    private static double DetectScaleToMillimetres(string text)
    {
        if (Regex.IsMatch(text, @"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", RegexOptions.IgnoreCase)) return 1.0;
        if (Regex.IsMatch(text, @"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.\s*\)", RegexOptions.IgnoreCase)) return 1000.0;
        if (text.Contains("INCH", StringComparison.OrdinalIgnoreCase)) return 25.4;
        return 1.0;
    }
}

internal static class StructuredTetMesher
{
    public static TetMesh Generate(SimpleStepSolid solid, double requestedSizeMm)
    {
        if (!solid.IsSupportedPrism)
            throw new InvalidOperationException(solid.FidelityMessage);
        if (requestedSizeMm <= 0) throw new ArgumentOutOfRangeException(nameof(requestedSizeMm));

        var longest = Math.Max(solid.LengthX, Math.Max(solid.LengthY, solid.LengthZ));
        var longestDivisions = Math.Clamp((int)Math.Ceiling(longest / requestedSizeMm), 2, 12);
        var nx = ScaleDivisions(solid.LengthX, longest, longestDivisions);
        var ny = ScaleDivisions(solid.LengthY, longest, longestDivisions);
        var nz = ScaleDivisions(solid.LengthZ, longest, longestDivisions);
        var nodes = new List<Vec3>((nx + 1) * (ny + 1) * (nz + 1));

        for (var k = 0; k <= nz; k++)
        for (var j = 0; j <= ny; j++)
        for (var i = 0; i <= nx; i++)
            nodes.Add(new Vec3(
                solid.Min.X + solid.LengthX * i / nx,
                solid.Min.Y + solid.LengthY * j / ny,
                solid.Min.Z + solid.LengthZ * k / nz));

        int Node(int i, int j, int k) => i + (nx + 1) * (j + (ny + 1) * k);
        var elements = new List<int[]>(nx * ny * nz * 6);
        for (var k = 0; k < nz; k++)
        for (var j = 0; j < ny; j++)
        for (var i = 0; i < nx; i++)
        {
            var v0 = Node(i, j, k);
            var v1 = Node(i + 1, j, k);
            var v2 = Node(i + 1, j + 1, k);
            var v3 = Node(i, j + 1, k);
            var v4 = Node(i, j, k + 1);
            var v5 = Node(i + 1, j, k + 1);
            var v6 = Node(i + 1, j + 1, k + 1);
            var v7 = Node(i, j + 1, k + 1);
            AddTet(elements, nodes, v0, v1, v2, v6);
            AddTet(elements, nodes, v0, v2, v3, v6);
            AddTet(elements, nodes, v0, v3, v7, v6);
            AddTet(elements, nodes, v0, v7, v4, v6);
            AddTet(elements, nodes, v0, v4, v5, v6);
            AddTet(elements, nodes, v0, v5, v1, v6);
        }

        return new TetMesh { Nodes = nodes, Elements = elements, DivisionsX = nx, DivisionsY = ny, DivisionsZ = nz };
    }

    private static int ScaleDivisions(double length, double longest, int longestDivisions) =>
        Math.Clamp((int)Math.Round(longestDivisions * length / longest), 1, 8);

    private static void AddTet(List<int[]> elements, List<Vec3> nodes, int a, int b, int c, int d)
    {
        var signed = Dot(nodes[b] - nodes[a], Cross(nodes[c] - nodes[a], nodes[d] - nodes[a]));
        elements.Add(signed >= 0 ? [a, b, c, d] : [a, c, b, d]);
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);
    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}

internal static class Tet4LinearStaticSolver
{
    public static StaticSolution Solve(SimpleStepSolid solid, TetMesh mesh, StaticMaterial material, SimpleStaticSetup setup)
    {
        var watch = System.Diagnostics.Stopwatch.StartNew();
        if (material.YoungModulusMpa <= 0 || material.PoissonRatio <= -0.99 || material.PoissonRatio >= 0.499)
            throw new InvalidOperationException("Invalid isotropic elastic material properties.");
        if (setup.FixedFace == setup.LoadFace)
            throw new InvalidOperationException("Fixed support and force cannot be scoped to the same face in the tutorial solver.");
        if (setup.ForceN.Length <= 1e-12)
            throw new InvalidOperationException("The applied force vector is zero.");

        var dofCount = mesh.Nodes.Count * 3;
        var stiffness = new double[dofCount, dofCount];
        var load = new double[dofCount];
        var constitutive = Constitutive(material.YoungModulusMpa, material.PoissonRatio);
        var elementB = new List<double[,]>(mesh.Elements.Count);

        foreach (var element in mesh.Elements)
        {
            var points = element.Select(index => mesh.Nodes[index]).ToArray();
            var (b, volume) = StrainMatrix(points);
            elementB.Add(b);
            var db = Multiply(constitutive, b);
            var ke = MultiplyTransposeLeft(b, db, volume);
            for (var localI = 0; localI < 12; localI++)
            for (var localJ = 0; localJ < 12; localJ++)
            {
                var globalI = element[localI / 3] * 3 + localI % 3;
                var globalJ = element[localJ / 3] * 3 + localJ % 3;
                stiffness[globalI, globalJ] += ke[localI, localJ];
            }
        }

        var loadedNodes = FaceNodes(solid, mesh, setup.LoadFace);
        if (loadedNodes.Count == 0) throw new InvalidOperationException("No mesh nodes were found on the loaded face.");
        var nodalForce = setup.ForceN / loadedNodes.Count;
        foreach (var node in loadedNodes)
        {
            load[node * 3] += nodalForce.X;
            load[node * 3 + 1] += nodalForce.Y;
            load[node * 3 + 2] += nodalForce.Z;
        }

        var fixedNodes = FaceNodes(solid, mesh, setup.FixedFace);
        if (fixedNodes.Count == 0) throw new InvalidOperationException("No mesh nodes were found on the fixed face.");
        var constrained = new HashSet<int>(fixedNodes.SelectMany(node => new[] { node * 3, node * 3 + 1, node * 3 + 2 }));
        var free = Enumerable.Range(0, dofCount).Where(dof => !constrained.Contains(dof)).ToArray();
        var reduced = new double[free.Length, free.Length];
        var rhs = new double[free.Length];
        for (var i = 0; i < free.Length; i++)
        {
            rhs[i] = load[free[i]];
            for (var j = 0; j < free.Length; j++) reduced[i, j] = stiffness[free[i], free[j]];
        }

        var freeDisplacement = SolveCholesky(reduced, rhs);
        var displacement = new double[dofCount];
        for (var i = 0; i < free.Length; i++) displacement[free[i]] = freeDisplacement[i];

        var reactions = new double[dofCount];
        for (var i = 0; i < dofCount; i++)
        {
            var value = -load[i];
            for (var j = 0; j < dofCount; j++) value += stiffness[i, j] * displacement[j];
            reactions[i] = value;
        }

        var reaction = Vec3.Zero;
        foreach (var node in fixedNodes)
            reaction += new Vec3(reactions[node * 3], reactions[node * 3 + 1], reactions[node * 3 + 2]);

        var maxDisplacement = 0.0;
        for (var node = 0; node < mesh.Nodes.Count; node++)
        {
            var magnitude = new Vec3(displacement[node * 3], displacement[node * 3 + 1], displacement[node * 3 + 2]).Length;
            maxDisplacement = Math.Max(maxDisplacement, magnitude);
        }

        var loadedAverage = Vec3.Zero;
        foreach (var node in loadedNodes)
            loadedAverage += new Vec3(displacement[node * 3], displacement[node * 3 + 1], displacement[node * 3 + 2]);
        loadedAverage /= loadedNodes.Count;

        var vonMises = new double[mesh.Elements.Count];
        for (var elementIndex = 0; elementIndex < mesh.Elements.Count; elementIndex++)
        {
            var element = mesh.Elements[elementIndex];
            var ue = new double[12];
            for (var local = 0; local < 12; local++) ue[local] = displacement[element[local / 3] * 3 + local % 3];
            var strain = Multiply(elementB[elementIndex], ue);
            var stress = Multiply(constitutive, strain);
            vonMises[elementIndex] = VonMises(stress);
        }

        var equilibrium = (reaction + setup.ForceN).Length / Math.Max(setup.ForceN.Length, 1.0);
        var (beamDeflection, beamStress) = BeamTheory(solid, material, setup);
        watch.Stop();
        return new StaticSolution
        {
            Displacements = displacement,
            ElementVonMisesMpa = vonMises,
            ReactionN = reaction,
            AppliedForceN = setup.ForceN,
            MaxDisplacementMm = maxDisplacement,
            LoadedFaceAverageDisplacementMm = loadedAverage,
            MaxVonMisesMpa = vonMises.Length == 0 ? 0 : vonMises.Max(),
            EquilibriumError = equilibrium,
            BeamTheoryDisplacementMm = beamDeflection,
            BeamTheoryStressMpa = beamStress,
            Elapsed = watch.Elapsed
        };
    }

    public static List<int> FaceNodes(SimpleStepSolid solid, TetMesh mesh, SimpleFace face)
    {
        var diagonal = (solid.Max - solid.Min).Length;
        var tolerance = Math.Max(1e-7, diagonal * 1e-7);
        return mesh.Nodes.Select((point, index) => (point, index)).Where(item => face switch
        {
            SimpleFace.XMin => Math.Abs(item.point.X - solid.Min.X) <= tolerance,
            SimpleFace.XMax => Math.Abs(item.point.X - solid.Max.X) <= tolerance,
            SimpleFace.YMin => Math.Abs(item.point.Y - solid.Min.Y) <= tolerance,
            SimpleFace.YMax => Math.Abs(item.point.Y - solid.Max.Y) <= tolerance,
            SimpleFace.ZMin => Math.Abs(item.point.Z - solid.Min.Z) <= tolerance,
            SimpleFace.ZMax => Math.Abs(item.point.Z - solid.Max.Z) <= tolerance,
            _ => false
        }).Select(item => item.index).ToList();
    }

    private static double[,] Constitutive(double e, double nu)
    {
        var lambda = e * nu / ((1 + nu) * (1 - 2 * nu));
        var mu = e / (2 * (1 + nu));
        var d = new double[6, 6];
        for (var i = 0; i < 3; i++)
        for (var j = 0; j < 3; j++) d[i, j] = i == j ? lambda + 2 * mu : lambda;
        d[3, 3] = d[4, 4] = d[5, 5] = mu;
        return d;
    }

    private static (double[,] B, double Volume) StrainMatrix(Vec3[] points)
    {
        var a = new double[4, 4];
        for (var i = 0; i < 4; i++)
        {
            a[i, 0] = 1;
            a[i, 1] = points[i].X;
            a[i, 2] = points[i].Y;
            a[i, 3] = points[i].Z;
        }
        var inverse = Invert(a);
        var volume = Math.Abs(Dot(points[1] - points[0], Cross(points[2] - points[0], points[3] - points[0]))) / 6.0;
        if (volume <= 1e-12) throw new InvalidOperationException("A zero-volume tetrahedral element was generated.");
        var b = new double[6, 12];
        for (var i = 0; i < 4; i++)
        {
            var bx = inverse[1, i];
            var by = inverse[2, i];
            var bz = inverse[3, i];
            var column = i * 3;
            b[0, column] = bx;
            b[1, column + 1] = by;
            b[2, column + 2] = bz;
            b[3, column] = by; b[3, column + 1] = bx;
            b[4, column + 1] = bz; b[4, column + 2] = by;
            b[5, column] = bz; b[5, column + 2] = bx;
        }
        return (b, volume);
    }

    private static double[,] Multiply(double[,] a, double[,] b)
    {
        var result = new double[a.GetLength(0), b.GetLength(1)];
        for (var i = 0; i < result.GetLength(0); i++)
        for (var k = 0; k < a.GetLength(1); k++)
        for (var j = 0; j < result.GetLength(1); j++) result[i, j] += a[i, k] * b[k, j];
        return result;
    }

    private static double[] Multiply(double[,] a, double[] b)
    {
        var result = new double[a.GetLength(0)];
        for (var i = 0; i < result.Length; i++)
        for (var j = 0; j < b.Length; j++) result[i] += a[i, j] * b[j];
        return result;
    }

    private static double[,] MultiplyTransposeLeft(double[,] b, double[,] db, double scale)
    {
        var result = new double[b.GetLength(1), db.GetLength(1)];
        for (var i = 0; i < result.GetLength(0); i++)
        for (var k = 0; k < b.GetLength(0); k++)
        for (var j = 0; j < result.GetLength(1); j++) result[i, j] += b[k, i] * db[k, j] * scale;
        return result;
    }

    private static double[] SolveCholesky(double[,] matrix, double[] rhs)
    {
        var n = rhs.Length;
        var l = new double[n, n];
        var maxDiagonal = Enumerable.Range(0, n).Select(i => Math.Abs(matrix[i, i])).DefaultIfEmpty(1).Max();
        var tolerance = Math.Max(1e-14, maxDiagonal * 1e-12);
        for (var i = 0; i < n; i++)
        for (var j = 0; j <= i; j++)
        {
            var sum = matrix[i, j];
            for (var k = 0; k < j; k++) sum -= l[i, k] * l[j, k];
            if (i == j)
            {
                if (sum <= tolerance) throw new InvalidOperationException("The stiffness matrix is singular or insufficiently constrained.");
                l[i, j] = Math.Sqrt(sum);
            }
            else l[i, j] = sum / l[j, j];
        }
        var y = new double[n];
        for (var i = 0; i < n; i++)
        {
            var sum = rhs[i];
            for (var k = 0; k < i; k++) sum -= l[i, k] * y[k];
            y[i] = sum / l[i, i];
        }
        var x = new double[n];
        for (var i = n - 1; i >= 0; i--)
        {
            var sum = y[i];
            for (var k = i + 1; k < n; k++) sum -= l[k, i] * x[k];
            x[i] = sum / l[i, i];
        }
        return x;
    }

    private static double[,] Invert(double[,] input)
    {
        const int n = 4;
        var work = new double[n, n * 2];
        for (var i = 0; i < n; i++)
        for (var j = 0; j < n; j++)
        {
            work[i, j] = input[i, j];
            work[i, j + n] = i == j ? 1 : 0;
        }
        for (var column = 0; column < n; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < n; row++)
                if (Math.Abs(work[row, column]) > Math.Abs(work[pivot, column])) pivot = row;
            if (Math.Abs(work[pivot, column]) < 1e-18) throw new InvalidOperationException("Degenerate tetrahedral geometry.");
            if (pivot != column)
                for (var j = 0; j < n * 2; j++) (work[column, j], work[pivot, j]) = (work[pivot, j], work[column, j]);
            var divisor = work[column, column];
            for (var j = 0; j < n * 2; j++) work[column, j] /= divisor;
            for (var row = 0; row < n; row++)
            {
                if (row == column) continue;
                var factor = work[row, column];
                for (var j = 0; j < n * 2; j++) work[row, j] -= factor * work[column, j];
            }
        }
        var inverse = new double[n, n];
        for (var i = 0; i < n; i++)
        for (var j = 0; j < n; j++) inverse[i, j] = work[i, j + n];
        return inverse;
    }

    private static double VonMises(double[] stress)
    {
        var sx = stress[0]; var sy = stress[1]; var sz = stress[2];
        var txy = stress[3]; var tyz = stress[4]; var txz = stress[5];
        return Math.Sqrt(0.5 * (Math.Pow(sx - sy, 2) + Math.Pow(sy - sz, 2) + Math.Pow(sz - sx, 2)) + 3 * (txy * txy + tyz * tyz + txz * txz));
    }

    private static (double? Deflection, double? Stress) BeamTheory(SimpleStepSolid solid, StaticMaterial material, SimpleStaticSetup setup)
    {
        if (setup.FixedFace != SimpleFace.XMin || setup.LoadFace != SimpleFace.XMax || solid.LengthX < Math.Max(solid.LengthY, solid.LengthZ) * 2) return (null, null);
        var fy = Math.Abs(setup.ForceN.Y);
        var fz = Math.Abs(setup.ForceN.Z);
        if (fy >= fz && fy > 0)
        {
            var inertia = solid.LengthZ * Math.Pow(solid.LengthY, 3) / 12.0;
            return (fy * Math.Pow(solid.LengthX, 3) / (3 * material.YoungModulusMpa * inertia), fy * solid.LengthX * (solid.LengthY / 2) / inertia);
        }
        if (fz > 0)
        {
            var inertia = solid.LengthY * Math.Pow(solid.LengthZ, 3) / 12.0;
            return (fz * Math.Pow(solid.LengthX, 3) / (3 * material.YoungModulusMpa * inertia), fz * solid.LengthX * (solid.LengthZ / 2) / inertia);
        }
        return (null, null);
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);
    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}

internal static class SimpleCalculationReport
{
    public static void Write(string htmlPath, SimpleStepSolid solid, TetMesh mesh, StaticMaterial material, SimpleStaticSetup setup, StaticSolution solution)
    {
        var title = Path.GetFileNameWithoutExtension(solid.SourcePath);
        var csvPath = Path.ChangeExtension(htmlPath, ".csv");
        var jsonPath = Path.ChangeExtension(htmlPath, ".json");
        File.WriteAllText(csvPath, BuildCsv(mesh, solution), new UTF8Encoding(false));
        File.WriteAllText(jsonPath, JsonSerializer.Serialize(new
        {
            schema = "astermax.simple-static.v1",
            generated = DateTimeOffset.Now,
            geometry = new { solid.SourcePath, solid.Min, solid.Max, solid.LengthX, solid.LengthY, solid.LengthZ, solid.Volume, solid.FidelityMessage },
            material,
            setup,
            mesh = new { nodes = mesh.Nodes.Count, elements = mesh.Elements.Count, mesh.DivisionsX, mesh.DivisionsY, mesh.DivisionsZ },
            results = new { solution.MaxDisplacementMm, solution.MaxVonMisesMpa, solution.ReactionN, solution.AppliedForceN, solution.EquilibriumError, solution.BeamTheoryDisplacementMm, solution.BeamTheoryStressMpa }
        }, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));

        var safetyFactor = solution.MaxVonMisesMpa > 0 ? material.YieldStrengthMpa / solution.MaxVonMisesMpa : double.PositiveInfinity;
        var html = $"""
<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Memoria preliminar - {H(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:38px;color:#23303d;line-height:1.45}}h1,h2{{color:#075f9f}}table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}th,td{{border:1px solid #bcc8d4;padding:8px;text-align:left}}th{{background:#eaf2f8}}.warn{{padding:12px;background:#fff3cd;border-left:5px solid #d99800}}.ok{{color:#147a42;font-weight:600}}code{{background:#f2f5f8;padding:2px 4px}}</style></head><body>
<h1>Memoria de cálculo preliminar — {H(title)}</h1>
<p><b>Software:</b> AsterMax Mechanical 0.5 beta · <b>Fecha:</b> {DateTime.Now:yyyy-MM-dd HH:mm}</p>
<div class="warn"><b>Alcance:</b> cálculo educativo/preliminar de un único prisma rectangular, material elástico lineal, pequeñas deformaciones y elementos tetraédricos TET4. La geometría STEP se representa mediante su envolvente rectangular. No reemplaza revisión de un ingeniero competente ni una verificación reglamentaria.</div>
<h2>1. Modelo geométrico</h2><table><tr><th>Archivo</th><td>{H(solid.SourcePath)}</td></tr><tr><th>Dimensiones X × Y × Z</th><td>{solid.LengthX:0.###} × {solid.LengthY:0.###} × {solid.LengthZ:0.###} mm</td></tr><tr><th>Volumen representado</th><td>{solid.Volume:0.###} mm³</td></tr><tr><th>Fidelidad</th><td>{H(solid.FidelityMessage)}</td></tr></table>
<h2>2. Material</h2><table><tr><th>Nombre</th><td>{H(material.Name)}</td></tr><tr><th>Módulo de Young</th><td>{material.YoungModulusMpa:0.###} MPa</td></tr><tr><th>Poisson</th><td>{material.PoissonRatio:0.####}</td></tr><tr><th>Límite elástico de referencia</th><td>{material.YieldStrengthMpa:0.###} MPa</td></tr></table>
<h2>3. Discretización y condiciones de borde</h2><table><tr><th>Malla</th><td>{mesh.Nodes.Count} nodos · {mesh.Elements.Count} TET4 · divisiones {mesh.DivisionsX} × {mesh.DivisionsY} × {mesh.DivisionsZ}</td></tr><tr><th>Apoyo fijo</th><td>{setup.FixedFace}</td></tr><tr><th>Cara cargada</th><td>{setup.LoadFace}</td></tr><tr><th>Fuerza total</th><td>{setup.ForceN} N</td></tr></table>
<h2>4. Método</h2><p>Se resuelve <code>[K]{{u}}={{F}}</code> con elasticidad isotrópica 3-D. Cada tetraedro usa interpolación lineal y deformación constante. La fuerza se distribuye entre los nodos de la cara cargada y los tres grados de libertad de la cara fija se anulan.</p>
<h2>5. Resultados</h2><table><tr><th>Desplazamiento máximo</th><td>{solution.MaxDisplacementMm:0.######} mm</td></tr><tr><th>Desplazamiento medio cara cargada</th><td>{solution.LoadedFaceAverageDisplacementMm} mm</td></tr><tr><th>von Mises máximo</th><td>{solution.MaxVonMisesMpa:0.######} MPa</td></tr><tr><th>Factor de seguridad simple</th><td>{safetyFactor:0.###}</td></tr><tr><th>Reacción total</th><td>{solution.ReactionN} N</td></tr><tr><th>Error relativo de equilibrio</th><td class="{(solution.EquilibriumError < 1e-6 ? "ok" : "")}">{solution.EquilibriumError:E3}</td></tr><tr><th>Tiempo de solución</th><td>{solution.Elapsed.TotalSeconds:0.###} s</td></tr></table>
<h2>6. Comparación analítica</h2><table><tr><th>Flecha de viga</th><td>{Format(solution.BeamTheoryDisplacementMm, "mm")}</td></tr><tr><th>Tensión de flexión</th><td>{Format(solution.BeamTheoryStressMpa, "MPa")}</td></tr></table>
<h2>7. Archivos anexos</h2><p>Datos nodales y tensiones: <b>{H(Path.GetFileName(csvPath))}</b><br>Modelo y resultados JSON: <b>{H(Path.GetFileName(jsonPath))}</b></p>
<h2>8. Limitaciones obligatorias</h2><ul><li>Solo un prisma rectangular sin perforaciones, redondeos, superficies curvas ni ensamblajes.</li><li>Malla estructurada TET4 de primer orden; se requiere estudio de convergencia para uso ingenieril.</li><li>Sin plasticidad, contacto, pandeo, grandes deformaciones, fatiga ni dinámica.</li><li>Las tensiones cercanas al empotramiento pueden depender fuertemente de la malla.</li></ul>
</body></html>
""";
        File.WriteAllText(htmlPath, html, new UTF8Encoding(false));
    }

    private static string BuildCsv(TetMesh mesh, StaticSolution solution)
    {
        var builder = new StringBuilder("type,id,x_mm,y_mm,z_mm,ux_mm,uy_mm,uz_mm,value_mpa\n");
        for (var i = 0; i < mesh.Nodes.Count; i++)
        {
            var p = mesh.Nodes[i];
            builder.AppendLine(FormattableString.Invariant($"node,{i + 1},{p.X},{p.Y},{p.Z},{solution.Displacements[i * 3]},{solution.Displacements[i * 3 + 1]},{solution.Displacements[i * 3 + 2]},"));
        }
        for (var i = 0; i < mesh.Elements.Count; i++) builder.AppendLine(FormattableString.Invariant($"element,{i + 1},,,,,,,{solution.ElementVonMisesMpa[i]}"));
        return builder.ToString();
    }

    private static string H(string value) => WebUtility.HtmlEncode(value);
    private static string Format(double? value, string unit) => value.HasValue ? $"{value.Value:0.######} {unit}" : "No aplicable";
}

internal sealed class SimpleStaticSetupDialog : Form
{
    private readonly NumericUpDown _young = Number(1, 1_000_000, 200000, 0);
    private readonly NumericUpDown _poisson = Number(-0.9m, 0.49m, 0.30m, 3);
    private readonly NumericUpDown _yield = Number(1, 10000, 250, 1);
    private readonly NumericUpDown _size = Number(0.1m, 100000, 25, 2);
    private readonly ComboBox _fixed = Faces();
    private readonly ComboBox _loaded = Faces();
    private readonly NumericUpDown _fx = Number(-10_000_000, 10_000_000, 0, 2);
    private readonly NumericUpDown _fy = Number(-10_000_000, 10_000_000, 0, 2);
    private readonly NumericUpDown _fz = Number(-10_000_000, 10_000_000, -1000, 2);

    public SimpleStaticSetupDialog(StaticMaterial material, SimpleStaticSetup setup)
    {
        Text = "Tutorial 01 — Linear Static Setup";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = MinimizeBox = false;
        ClientSize = new Size(500, 430);
        Font = new Font("Segoe UI", 9.2f);
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, Padding = new Padding(16), AutoSize = true };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 52));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 48));
        Controls.Add(table);
        Add(table, "Young modulus [MPa]", _young);
        Add(table, "Poisson ratio", _poisson);
        Add(table, "Yield strength [MPa]", _yield);
        Add(table, "Target element size [mm]", _size);
        Add(table, "Fixed face", _fixed);
        Add(table, "Loaded face", _loaded);
        Add(table, "Force X [N]", _fx);
        Add(table, "Force Y [N]", _fy);
        Add(table, "Force Z [N]", _fz);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Bottom, Height = 48, FlowDirection = FlowDirection.RightToLeft, Padding = new Padding(8) };
        var ok = new Button { Text = "Accept", DialogResult = DialogResult.OK, Width = 100 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 100 };
        buttons.Controls.Add(ok); buttons.Controls.Add(cancel); Controls.Add(buttons);
        AcceptButton = ok; CancelButton = cancel;
        _young.Value = Clamp(material.YoungModulusMpa, _young);
        _poisson.Value = Clamp(material.PoissonRatio, _poisson);
        _yield.Value = Clamp(material.YieldStrengthMpa, _yield);
        _size.Value = Clamp(setup.ElementSizeMm, _size);
        _fixed.SelectedItem = setup.FixedFace.ToString();
        _loaded.SelectedItem = setup.LoadFace.ToString();
        _fx.Value = Clamp(setup.ForceN.X, _fx); _fy.Value = Clamp(setup.ForceN.Y, _fy); _fz.Value = Clamp(setup.ForceN.Z, _fz);
    }

    public void Apply(StaticMaterial material, SimpleStaticSetup setup)
    {
        material.YoungModulusMpa = (double)_young.Value;
        material.PoissonRatio = (double)_poisson.Value;
        material.YieldStrengthMpa = (double)_yield.Value;
        setup.ElementSizeMm = (double)_size.Value;
        setup.FixedFace = Enum.Parse<SimpleFace>(_fixed.SelectedItem?.ToString() ?? nameof(SimpleFace.XMin));
        setup.LoadFace = Enum.Parse<SimpleFace>(_loaded.SelectedItem?.ToString() ?? nameof(SimpleFace.XMax));
        setup.ForceN = new Vec3((double)_fx.Value, (double)_fy.Value, (double)_fz.Value);
    }

    private static NumericUpDown Number(decimal min, decimal max, decimal value, int decimals) => new() { Minimum = min, Maximum = max, Value = value, DecimalPlaces = decimals, ThousandsSeparator = true, Dock = DockStyle.Fill };
    private static ComboBox Faces() { var box = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill }; box.Items.AddRange(Enum.GetNames<SimpleFace>()); return box; }
    private static void Add(TableLayoutPanel table, string label, Control control) { var row = table.RowCount++; table.RowStyles.Add(new RowStyle(SizeType.Absolute, 36)); table.Controls.Add(new Label { Text = label, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft }, 0, row); table.Controls.Add(control, 1, row); }
    private static decimal Clamp(double value, NumericUpDown box) => Math.Clamp((decimal)value, box.Minimum, box.Maximum);
}
