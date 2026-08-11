using System.Globalization;
using System.Text;
using System.Text.Json;

namespace AsterMax.MechanicalGui;

internal sealed record StepRegressionRecord
{
    public required string File { get; init; }
    public required string Sha256 { get; init; }
    public required long Bytes { get; init; }
    public required string SourceUnit { get; init; }
    public required double SourceToMillimetres { get; init; }
    public required string Classification { get; init; }
    public required int SolidCount { get; init; }
    public required int ClosedShellCount { get; init; }
    public required int FaceCount { get; init; }
    public required int MeshEdgeCount { get; init; }
    public required bool IsClosed { get; init; }
    public required double SkinVolumeMm3 { get; init; }
    public required double BboxXmm { get; init; }
    public required double BboxYmm { get; init; }
    public required double BboxZmm { get; init; }
    public required int SurfaceNodes { get; init; }
    public required int SurfaceTriangles { get; init; }
    public required double SurfaceMilliseconds { get; init; }
    public int? VolumeNodes { get; init; }
    public int? VolumeTriangles { get; init; }
    public int? Tet4 { get; init; }
    public double? VolumeMeshMm3 { get; init; }
    public double? VolumeMilliseconds { get; init; }
    public required string GmshVersion { get; init; }
    public required string[] PersistentFaceIds { get; init; }
    public string? Diagnosis { get; init; }
    public string? Error { get; init; }
}

internal static class StepRegressionBatchBootstrap
{
    [System.Runtime.CompilerServices.ModuleInitializer]
    internal static void Initialize()
    {
        var args = Environment.GetCommandLineArgs().Skip(1).ToArray();
        var index = Array.FindIndex(args,
            arg => string.Equals(arg, "--step-regression-batch", StringComparison.OrdinalIgnoreCase));
        if (index < 0) return;

        var exitCode = StepRegressionBatchRunner.Run(args.Skip(index + 1).ToArray());
        Environment.Exit(exitCode);
    }
}

internal static class StepRegressionBatchRunner
{
    public static int Run(string[] args)
    {
        try
        {
            if (args.Length < 1)
                throw new InvalidOperationException(
                    "Usage: --step-regression-batch <directory> [--out report.json] [--skip-volume]");

            var root = Path.GetFullPath(args[0]);
            if (!Directory.Exists(root)) throw new DirectoryNotFoundException(root);
            var output = ReadOption(args, "--out") is { } configured
                ? Path.GetFullPath(configured)
                : Path.Combine(root, "astermax-step-regression.json");
            var skipVolume = args.Any(arg => string.Equals(arg, "--skip-volume", StringComparison.OrdinalIgnoreCase));
            var gmsh = GmshCliMesher.FindExecutable();
            if (gmsh is null) throw new FileNotFoundException("Bundled Gmsh executable was not found.");

            var files = Directory.EnumerateFiles(root, "*.*", SearchOption.AllDirectories)
                .Where(path => Path.GetExtension(path).Equals(".step", StringComparison.OrdinalIgnoreCase) ||
                               Path.GetExtension(path).Equals(".stp", StringComparison.OrdinalIgnoreCase))
                .OrderBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            if (files.Length == 0) throw new InvalidOperationException("No STEP/STP files were found.");

            var records = new List<StepRegressionRecord>(files.Length);
            var engineFailures = 0;
            Console.WriteLine($"AsterMax P0.3 STEP regression | files={files.Length} | volumeMesh={!skipVolume} | root={root}");

            foreach (var file in files)
            {
                Console.WriteLine($"--- {Path.GetFileName(file)} ---");
                try
                {
                    records.Add(Inspect(gmsh, file, !skipVolume));
                    var record = records[^1];
                    Console.WriteLine(
                        $"PASS import | class={record.Classification} | solids={record.SolidCount} | faces={record.FaceCount} | " +
                        $"bbox={record.BboxXmm:G8}x{record.BboxYmm:G8}x{record.BboxZmm:G8} mm | " +
                        $"surface={record.SurfaceNodes} nodes/{record.SurfaceTriangles} triangles | " +
                        $"tet4={(record.Tet4?.ToString(CultureInfo.InvariantCulture) ?? "n/a")} | " +
                        $"surfaceMs={record.SurfaceMilliseconds:0} | volumeMs={(record.VolumeMilliseconds?.ToString("0", CultureInfo.InvariantCulture) ?? "n/a")}");
                }
                catch (Exception exception)
                {
                    engineFailures++;
                    var hints = SafeHints(file);
                    records.Add(new StepRegressionRecord
                    {
                        File = Path.GetFileName(file),
                        Sha256 = Sha256(file),
                        Bytes = new FileInfo(file).Length,
                        SourceUnit = hints.SourceUnit,
                        SourceToMillimetres = hints.SourceToMillimetres,
                        Classification = "engine_failure",
                        SolidCount = hints.SolidCount,
                        ClosedShellCount = hints.ClosedShellCount,
                        FaceCount = 0,
                        MeshEdgeCount = 0,
                        IsClosed = false,
                        SkinVolumeMm3 = 0,
                        BboxXmm = 0,
                        BboxYmm = 0,
                        BboxZmm = 0,
                        SurfaceNodes = 0,
                        SurfaceTriangles = 0,
                        SurfaceMilliseconds = 0,
                        GmshVersion = "unknown",
                        PersistentFaceIds = Array.Empty<string>(),
                        Diagnosis = "Gmsh/OpenCASCADE failed before a trustworthy classification could be produced.",
                        Error = exception.ToString()
                    });
                    Console.Error.WriteLine("FAIL engine: " + exception.Message);
                }
            }

            Directory.CreateDirectory(Path.GetDirectoryName(output) ?? root);
            File.WriteAllText(output, JsonSerializer.Serialize(new
            {
                generatedAtUtc = DateTimeOffset.UtcNow,
                engine = "AsterMax ManagedGmshMesher / Gmsh OpenCASCADE",
                internalUnit = "millimetre",
                requestedVolumeMesh = !skipVolume,
                fileCount = records.Count,
                engineFailures,
                records
            }, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
            WriteCsv(Path.ChangeExtension(output, ".csv"), records);

            var single = records.Count(record => record.Classification == "single_solid");
            var multi = records.Count(record => record.Classification == "multi_solid_or_assembly");
            var surface = records.Count(record => record.Classification == "surface_or_2d");
            Console.WriteLine($"P0.3 SUMMARY | single={single} | multi={multi} | surface/2D={surface} | engineFailures={engineFailures}");
            Console.WriteLine($"JSON={output}");
            Console.WriteLine($"CSV={Path.ChangeExtension(output, ".csv")}");
            return engineFailures == 0 ? 0 : 8;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 7;
        }
    }

    private static StepRegressionRecord Inspect(string gmsh, string file, bool generateVolume)
    {
        var hints = StepSourceInspector.Inspect(file);
        var surfaceRun = ManagedGmshMesher.GenerateAsync(
                gmsh, file, null, 2, TimeSpan.FromSeconds(ReadTimeout("ASTERMAX_STEP_PREVIEW_TIMEOUT_SECONDS", 60)), CancellationToken.None)
            .GetAwaiter().GetResult();
        var mesh = surfaceRun.Mesh;
        if (mesh.Nodes.Count == 0 || mesh.SurfaceTriangles.Count == 0)
            throw new InvalidDataException("OpenCASCADE returned an empty surface mesh.");

        var topology = CadTopologyRegistry.Get(mesh);
        var closed = IsClosedTriangleSkin(mesh);
        var skinVolume = Math.Abs(SignedSkinVolume(mesh));
        var meshEdges = UniqueMeshEdgeCount(mesh);
        var geometricTolerance = Math.Max(1e-8, Math.Pow(Math.Max(mesh.Max.X - mesh.Min.X,
            Math.Max(mesh.Max.Y - mesh.Min.Y, mesh.Max.Z - mesh.Min.Z)), 3) * 1e-12);
        var hasVolume = closed && skinVolume > geometricTolerance && hints.SolidCount > 0;
        var classification = hasVolume
            ? hints.SolidCount == 1 ? "single_solid" : "multi_solid_or_assembly"
            : "surface_or_2d";

        int? volumeNodes = null;
        int? volumeTriangles = null;
        int? tet4 = null;
        double? volumeMesh = null;
        double? volumeMs = null;
        string? diagnosis = null;
        if (hasVolume && generateVolume)
        {
            var dimensions = mesh.Max - mesh.Min;
            var longest = Math.Max(dimensions.X, Math.Max(dimensions.Y, dimensions.Z));
            var target = Math.Max(longest / 10.0, Math.Max(longest * 1e-4, 0.1));
            var volumeRun = ManagedGmshMesher.GenerateAsync(
                    gmsh, file, target, 3, TimeSpan.FromSeconds(ReadTimeout("ASTERMAX_STEP_VOLUME_TIMEOUT_SECONDS", 180)), CancellationToken.None)
                .GetAwaiter().GetResult();
            volumeNodes = volumeRun.Mesh.Nodes.Count;
            volumeTriangles = volumeRun.Mesh.SurfaceTriangles.Count;
            tet4 = volumeRun.Mesh.Tetrahedra.Count;
            volumeMesh = Math.Abs(TetraVolume(volumeRun.Mesh));
            volumeMs = volumeRun.Elapsed.TotalMilliseconds;
            if (tet4 <= 0)
                diagnosis = "Closed positive-volume STEP imported, but Gmsh produced no TET4 elements.";
        }
        else if (!hasVolume)
        {
            diagnosis = hints.SolidCount == 0
                ? "Valid OpenCASCADE surface/2D geometry. Importable for visualization/topology, but not eligible for 3-D TET4 volume meshing."
                : "STEP contains declared solid entities but the meshed skin is not a verified closed positive-volume region; inspect topology before 3-D solve.";
        }

        var dimensionsMm = mesh.Max - mesh.Min;
        return new StepRegressionRecord
        {
            File = Path.GetFileName(file),
            Sha256 = Sha256(file),
            Bytes = new FileInfo(file).Length,
            SourceUnit = hints.SourceUnit,
            SourceToMillimetres = hints.SourceToMillimetres,
            Classification = classification,
            SolidCount = hints.SolidCount,
            ClosedShellCount = hints.ClosedShellCount,
            FaceCount = topology.Faces.Count,
            MeshEdgeCount = meshEdges,
            IsClosed = closed,
            SkinVolumeMm3 = skinVolume,
            BboxXmm = dimensionsMm.X,
            BboxYmm = dimensionsMm.Y,
            BboxZmm = dimensionsMm.Z,
            SurfaceNodes = mesh.Nodes.Count,
            SurfaceTriangles = mesh.SurfaceTriangles.Count,
            SurfaceMilliseconds = surfaceRun.Elapsed.TotalMilliseconds,
            VolumeNodes = volumeNodes,
            VolumeTriangles = volumeTriangles,
            Tet4 = tet4,
            VolumeMeshMm3 = volumeMesh,
            VolumeMilliseconds = volumeMs,
            GmshVersion = surfaceRun.Version,
            PersistentFaceIds = topology.Faces.Keys.OrderBy(tag => tag).Select(tag => $"face:{tag}").ToArray(),
            Diagnosis = diagnosis
        };
    }

    private static StepSourceHints SafeHints(string file)
    {
        try { return StepSourceInspector.Inspect(file); }
        catch { return new StepSourceHints("unknown", 1.0, 0, 0, 0); }
    }

    private static int UniqueMeshEdgeCount(CadMesh mesh)
    {
        var edges = new HashSet<(int A, int B)>();
        foreach (var triangle in mesh.SurfaceTriangles)
        {
            Add(triangle[0], triangle[1]);
            Add(triangle[1], triangle[2]);
            Add(triangle[2], triangle[0]);
        }
        return edges.Count;
        void Add(int a, int b) => edges.Add(a < b ? (a, b) : (b, a));
    }

    private static bool IsClosedTriangleSkin(CadMesh mesh)
    {
        var owners = new Dictionary<(int A, int B), int>();
        foreach (var triangle in mesh.SurfaceTriangles)
        {
            Add(triangle[0], triangle[1]);
            Add(triangle[1], triangle[2]);
            Add(triangle[2], triangle[0]);
        }
        return owners.Count > 0 && owners.Values.All(count => count == 2);
        void Add(int a, int b)
        {
            var edge = a < b ? (a, b) : (b, a);
            owners[edge] = owners.GetValueOrDefault(edge) + 1;
        }
    }

    private static double SignedSkinVolume(CadMesh mesh)
    {
        var total = 0.0;
        foreach (var triangle in mesh.SurfaceTriangles)
        {
            var a = mesh.Nodes[triangle[0]];
            var b = mesh.Nodes[triangle[1]];
            var c = mesh.Nodes[triangle[2]];
            total += Dot(a, Cross(b, c)) / 6.0;
        }
        return total;
    }

    private static double TetraVolume(CadMesh mesh)
    {
        var total = 0.0;
        foreach (var tet in mesh.Tetrahedra)
        {
            var a = mesh.Nodes[tet[0]];
            var b = mesh.Nodes[tet[1]];
            var c = mesh.Nodes[tet[2]];
            var d = mesh.Nodes[tet[3]];
            total += Math.Abs(Dot(b - a, Cross(c - a, d - a))) / 6.0;
        }
        return total;
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(
        a.Y * b.Z - a.Z * b.Y,
        a.Z * b.X - a.X * b.Z,
        a.X * b.Y - a.Y * b.X);

    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;

    private static string Sha256(string file) =>
        Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(file))).ToLowerInvariant();

    private static int ReadTimeout(string variable, int fallback)
    {
        return int.TryParse(Environment.GetEnvironmentVariable(variable), NumberStyles.Integer, CultureInfo.InvariantCulture, out var seconds) && seconds > 0
            ? seconds
            : fallback;
    }

    private static string? ReadOption(string[] args, string name)
    {
        for (var index = 0; index < args.Length - 1; index++)
            if (string.Equals(args[index], name, StringComparison.OrdinalIgnoreCase)) return args[index + 1];
        return null;
    }

    private static void WriteCsv(string path, IReadOnlyList<StepRegressionRecord> records)
    {
        static string Q(string? value) => "\"" + (value ?? string.Empty).Replace("\"", "\"\"") + "\"";
        var lines = new List<string>
        {
            "file,sha256,bytes,source_unit,classification,solids,faces,closed,bbox_x_mm,bbox_y_mm,bbox_z_mm,skin_volume_mm3,surface_nodes,surface_triangles,tet4,surface_ms,volume_ms,diagnosis,error"
        };
        foreach (var r in records)
            lines.Add(string.Join(",",
                Q(r.File), Q(r.Sha256), r.Bytes, Q(r.SourceUnit), Q(r.Classification), r.SolidCount, r.FaceCount,
                r.IsClosed ? "true" : "false",
                r.BboxXmm.ToString("G17", CultureInfo.InvariantCulture),
                r.BboxYmm.ToString("G17", CultureInfo.InvariantCulture),
                r.BboxZmm.ToString("G17", CultureInfo.InvariantCulture),
                r.SkinVolumeMm3.ToString("G17", CultureInfo.InvariantCulture),
                r.SurfaceNodes, r.SurfaceTriangles, r.Tet4?.ToString(CultureInfo.InvariantCulture) ?? string.Empty,
                r.SurfaceMilliseconds.ToString("0.###", CultureInfo.InvariantCulture),
                r.VolumeMilliseconds?.ToString("0.###", CultureInfo.InvariantCulture) ?? string.Empty,
                Q(r.Diagnosis), Q(r.Error)));
        File.WriteAllLines(path, lines, new UTF8Encoding(false));
    }
}