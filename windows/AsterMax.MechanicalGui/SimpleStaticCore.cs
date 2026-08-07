using System.Text.RegularExpressions;

namespace AsterMax.MechanicalGui;

internal readonly record struct Vec3(double X, double Y, double Z)
{
    public static Vec3 Zero => new(0, 0, 0);
    public double Length => Math.Sqrt(X * X + Y * Y + Z * Z);
    public static Vec3 operator +(Vec3 a, Vec3 b) => new(a.X + b.X, a.Y + b.Y, a.Z + b.Z);
    public static Vec3 operator -(Vec3 a, Vec3 b) => new(a.X - b.X, a.Y - b.Y, a.Z - b.Z);
    public static Vec3 operator *(Vec3 a, double scalar) => new(a.X * scalar, a.Y * scalar, a.Z * scalar);
    public static Vec3 operator /(Vec3 a, double scalar) => new(a.X / scalar, a.Y / scalar, a.Z / scalar);
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
        var scale = DetectScaleToMillimetres(text);
        var points = new List<Vec3>();

        foreach (Match match in PointPattern.Matches(text))
        {
            var values = match.Groups[1].Value.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
            if (values.Length < 3) continue;
            if (!double.TryParse(values[0], NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ||
                !double.TryParse(values[1], NumberStyles.Float, CultureInfo.InvariantCulture, out var y) ||
                !double.TryParse(values[2], NumberStyles.Float, CultureInfo.InvariantCulture, out var z)) continue;
            points.Add(new Vec3(x * scale, y * scale, z * scale));
        }

        if (points.Count < 4)
            throw new InvalidDataException("The STEP file does not contain enough CARTESIAN_POINT entities to determine a solid envelope.");

        var min = new Vec3(points.Min(p => p.X), points.Min(p => p.Y), points.Min(p => p.Z));
        var max = new Vec3(points.Max(p => p.X), points.Max(p => p.Y), points.Max(p => p.Z));
        var dimensions = max - min;
        if (dimensions.X <= 1e-6 || dimensions.Y <= 1e-6 || dimensions.Z <= 1e-6)
            throw new InvalidDataException("The imported STEP envelope is not a three-dimensional solid.");

        var curved = Regex.IsMatch(text,
            @"\b(CYLINDRICAL_SURFACE|CONICAL_SURFACE|TOROIDAL_SURFACE|SPHERICAL_SURFACE|B_SPLINE_SURFACE|CIRCLE)\b",
            RegexOptions.IgnoreCase);
        var solidCount = Regex.Matches(text, @"\b(MANIFOLD_SOLID_BREP|FACETED_BREP)\s*\(", RegexOptions.IgnoreCase).Count;
        var tolerance = Math.Max(1e-6, dimensions.Length * 1e-5);
        var boundaryPointCount = points.Count(point =>
        {
            var coordinateCount = 0;
            if (Near(point.X, min.X, tolerance) || Near(point.X, max.X, tolerance)) coordinateCount++;
            if (Near(point.Y, min.Y, tolerance) || Near(point.Y, max.Y, tolerance)) coordinateCount++;
            if (Near(point.Z, min.Z, tolerance) || Near(point.Z, max.Z, tolerance)) coordinateCount++;
            return coordinateCount >= 2;
        });
        var boundaryRatio = boundaryPointCount / (double)points.Count;
        var supported = !curved && solidCount <= 1 && boundaryRatio >= 0.70;
        var fidelity = supported
            ? "Prismatic STEP accepted. This beta represents the solid by its axis-aligned rectangular envelope."
            : "Unsupported STEP complexity. Tutorial 01 accepts only one rectangular/prismatic solid without holes, fillets or curved surfaces.";

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
        if (!solid.IsSupportedPrism) throw new InvalidOperationException(solid.FidelityMessage);
        if (!double.IsFinite(requestedSizeMm) || requestedSizeMm <= 0)
            throw new ArgumentOutOfRangeException(nameof(requestedSizeMm));

        var longest = Math.Max(solid.LengthX, Math.Max(solid.LengthY, solid.LengthZ));
        var longestDivisions = Math.Clamp((int)Math.Ceiling(longest / requestedSizeMm), 2, 10);
        var nx = ScaleDivisions(solid.LengthX, longest, longestDivisions);
        var ny = ScaleDivisions(solid.LengthY, longest, longestDivisions);
        var nz = ScaleDivisions(solid.LengthZ, longest, longestDivisions);
        while ((nx + 1) * (ny + 1) * (nz + 1) > 360)
        {
            if (nx >= ny && nx >= nz && nx > 1) nx--;
            else if (ny >= nz && ny > 1) ny--;
            else if (nz > 1) nz--;
            else break;
        }

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

        return new TetMesh
        {
            Nodes = nodes,
            Elements = elements,
            DivisionsX = nx,
            DivisionsY = ny,
            DivisionsZ = nz
        };
    }

    private static int ScaleDivisions(double length, double longest, int longestDivisions) =>
        Math.Clamp((int)Math.Round(longestDivisions * length / longest), 1, 8);

    private static void AddTet(List<int[]> elements, IReadOnlyList<Vec3> nodes, int a, int b, int c, int d)
    {
        var signedVolume = Dot(nodes[b] - nodes[a], Cross(nodes[c] - nodes[a], nodes[d] - nodes[a]));
        elements.Add(signedVolume >= 0 ? [a, b, c, d] : [a, c, b, d]);
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) =>
        new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);

    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}
