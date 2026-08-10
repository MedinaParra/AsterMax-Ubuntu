using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace AsterMax.MechanicalGui;

internal enum OperationOutcome
{
    Running,
    Succeeded,
    Cancelled,
    TimedOut,
    Failed
}

internal sealed record OperationProgress(
    string Stage,
    string Detail,
    double? Percent,
    TimeSpan Elapsed,
    OperationOutcome Outcome);

internal sealed class OperationController : IDisposable
{
    private readonly CancellationTokenSource _cts = new();
    private readonly Stopwatch _watch = Stopwatch.StartNew();
    private bool _disposed;

    public event Action<OperationProgress>? ProgressChanged;
    public CancellationToken Token => _cts.Token;
    public TimeSpan Elapsed => _watch.Elapsed;
    public OperationOutcome Outcome { get; private set; } = OperationOutcome.Running;
    public string Stage { get; private set; } = "Starting";
    public string Detail { get; private set; } = string.Empty;

    public void Report(string stage, string detail, double? percent = null)
    {
        Stage = stage;
        Detail = detail;
        ProgressChanged?.Invoke(new OperationProgress(stage, detail, percent, _watch.Elapsed, Outcome));
    }

    public void Cancel()
    {
        if (_cts.IsCancellationRequested) return;
        Outcome = OperationOutcome.Cancelled;
        _cts.Cancel();
        Report(Stage, "Cancellation requested by user.");
    }

    public void Complete(OperationOutcome outcome, string detail)
    {
        Outcome = outcome;
        Detail = detail;
        ProgressChanged?.Invoke(new OperationProgress(Stage, detail, 1.0, _watch.Elapsed, outcome));
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _watch.Stop();
        _cts.Dispose();
    }
}

internal sealed class CadModelMetadata
{
    public required string SourcePath { get; init; }
    public required string Sha256 { get; init; }
    public required string SourceUnit { get; init; }
    public required double SourceToMillimetres { get; init; }
    public required Vec3 Min { get; init; }
    public required Vec3 Max { get; init; }
    public required int SolidCount { get; init; }
    public required int ClosedShellCount { get; init; }
    public required int FaceCount { get; init; }
    public required int MeshEdgeCount { get; init; }
    public required bool IsClosed { get; init; }
    public required double VolumeMm3 { get; init; }
    public required string GmshVersion { get; init; }
    public required IReadOnlyList<string> PersistentFaceIds { get; init; }
    public Vec3 Dimensions => Max - Min;
}

internal sealed record CadSurfaceMesh(CadMesh Mesh);
internal sealed record CadVolumeMesh(CadMesh Mesh);

internal sealed class CadImportResult
{
    public required CadModelMetadata Metadata { get; init; }
    public required CadSurfaceMesh Surface { get; init; }
    public required string Diagnostics { get; init; }
    public SimpleStepSolid? VerifiedPrismFastPath { get; init; }
}

internal sealed record StepSourceHints(
    string SourceUnit,
    double SourceToMillimetres,
    int SolidCount,
    int ClosedShellCount,
    int DeclaredFaceCount);

internal static class StepSourceInspector
{
    // Text inspection is diagnostic only. It must never be used as the validity gate for general STEP solids.
    public static StepSourceHints Inspect(string path)
    {
        var text = File.ReadAllText(path);
        var (unit, scale) = DetectUnit(text);
        return new StepSourceHints(
            unit,
            scale,
            Regex.Matches(text, @"\b(MANIFOLD_SOLID_BREP|FACETED_BREP)\s*\(", RegexOptions.IgnoreCase).Count,
            Regex.Matches(text, @"\bCLOSED_SHELL\s*\(", RegexOptions.IgnoreCase).Count,
            Regex.Matches(text, @"\bADVANCED_FACE\s*\(", RegexOptions.IgnoreCase).Count);
    }

    private static (string Unit, double Scale) DetectUnit(string text)
    {
        if (Regex.IsMatch(text, @"SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)", RegexOptions.IgnoreCase))
            return ("millimetre", 1.0);
        if (Regex.IsMatch(text, @"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.\s*\)", RegexOptions.IgnoreCase))
            return ("metre", 1000.0);
        if (text.Contains("INCH", StringComparison.OrdinalIgnoreCase))
            return ("inch", 25.4);
        return ("unknown", 1.0);
    }
}

internal sealed record GmshRunResult(
    CadMesh Mesh,
    string Version,
    string Arguments,
    TimeSpan Elapsed,
    int ExitCode,
    string Log);

internal static class ManagedGmshMesher
{
    public static async Task<GmshRunResult> GenerateAsync(
        string executable,
        string stepPath,
        double? targetSizeMm,
        int dimension,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        if (dimension is not (2 or 3)) throw new ArgumentOutOfRangeException(nameof(dimension));
        if (!File.Exists(executable)) throw new FileNotFoundException("Gmsh executable not found.", executable);
        if (!File.Exists(stepPath)) throw new FileNotFoundException("STEP file not found.", stepPath);
        if (targetSizeMm is <= 0 || targetSizeMm is double.NaN or double.PositiveInfinity or double.NegativeInfinity)
            throw new ArgumentOutOfRangeException(nameof(targetSizeMm));

        var runDirectory = Path.Combine(Path.GetTempPath(), "AsterMax", "gmsh", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(runDirectory);
        var localStep = Path.Combine(runDirectory, "model.step");
        var meshPath = Path.Combine(runDirectory, dimension == 3 ? "volume.msh" : "surface.msh");
        File.Copy(stepPath, localStep, true);

        var info = new ProcessStartInfo
        {
            FileName = executable,
            WorkingDirectory = runDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        info.ArgumentList.Add(localStep);
        info.ArgumentList.Add(dimension == 3 ? "-3" : "-2");
        info.ArgumentList.Add("-format");
        info.ArgumentList.Add("msh2");
        info.ArgumentList.Add("-order");
        info.ArgumentList.Add("1");
        info.ArgumentList.Add("-o");
        info.ArgumentList.Add(meshPath);
        info.ArgumentList.Add("-setstring");
        info.ArgumentList.Add("Geometry.OCCTargetUnit");
        info.ArgumentList.Add("MM");
        if (targetSizeMm is double target)
        {
            info.ArgumentList.Add("-setnumber");
            info.ArgumentList.Add("Mesh.MeshSizeMin");
            info.ArgumentList.Add(target.ToString("G17", CultureInfo.InvariantCulture));
            info.ArgumentList.Add("-setnumber");
            info.ArgumentList.Add("Mesh.MeshSizeMax");
            info.ArgumentList.Add(target.ToString("G17", CultureInfo.InvariantCulture));
        }
        info.ArgumentList.Add("-nopopup");
        info.ArgumentList.Add("-v");
        info.ArgumentList.Add("3");

        var arguments = string.Join(" ", info.ArgumentList.Select(Quote));
        var watch = Stopwatch.StartNew();
        Process? process = null;
        try
        {
            process = new Process { StartInfo = info };
            if (!process.Start()) throw new InvalidOperationException("Gmsh process could not be started.");

            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();
            using var timeoutCts = new CancellationTokenSource(timeout);
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutCts.Token);

            try
            {
                await process.WaitForExitAsync(linked.Token);
            }
            catch (OperationCanceledException)
            {
                await KillTreeAndWaitAsync(process);
                var stdoutAfterKill = await stdoutTask;
                var stderrAfterKill = await stderrTask;
                var tail = LastLines(stdoutAfterKill + Environment.NewLine + stderrAfterKill, 18);
                if (cancellationToken.IsCancellationRequested)
                    throw new OperationCanceledException("Gmsh operation cancelled.\n" + tail, cancellationToken);
                throw new TimeoutException($"Gmsh exceeded the {timeout.TotalSeconds:0}-second timeout.\n{tail}");
            }

            var stdout = await stdoutTask;
            var stderr = await stderrTask;
            var log = stdout + Environment.NewLine + stderr;
            if (process.ExitCode != 0)
                throw new InvalidOperationException($"Gmsh exited with code {process.ExitCode}.\n\n{LastLines(log, 18)}");
            if (!File.Exists(meshPath))
                throw new InvalidDataException("Gmsh finished without creating the requested MSH file.\n\n" + LastLines(log, 18));

            var mesh = SelectableGmshMesher.ParseMsh2(meshPath, log);
            var version = await ReadVersionAsync(executable, cancellationToken);
            return new GmshRunResult(mesh, version, arguments, watch.Elapsed, process.ExitCode, log);
        }
        finally
        {
            watch.Stop();
            if (process is not null)
            {
                try
                {
                    if (!process.HasExited) await KillTreeAndWaitAsync(process);
                }
                catch { }
                process.Dispose();
            }
            try { Directory.Delete(runDirectory, true); } catch { }
        }
    }

    private static async Task KillTreeAndWaitAsync(Process process)
    {
        try
        {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
        }
        catch { }
        try { await process.WaitForExitAsync(CancellationToken.None); } catch { }
    }

    private static async Task<string> ReadVersionAsync(string executable, CancellationToken cancellationToken)
    {
        var info = new ProcessStartInfo
        {
            FileName = executable,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        info.ArgumentList.Add("--version");
        using var process = new Process { StartInfo = info };
        if (!process.Start()) return "unknown";
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(10));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch
        {
            await KillTreeAndWaitAsync(process);
            return "unknown";
        }
        var text = ((await outputTask) + " " + (await errorTask)).Trim();
        return string.IsNullOrWhiteSpace(text) ? "unknown" : text.Split('\n', '\r').FirstOrDefault(value => !string.IsNullOrWhiteSpace(value))?.Trim() ?? "unknown";
    }

    private static string LastLines(string text, int count) =>
        string.Join(Environment.NewLine, text.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None).TakeLast(count));

    private static string Quote(string value) => value.Any(char.IsWhiteSpace) ? $"\"{value}\"" : value;
}

internal static class StepImportService
{
    public static async Task<CadImportResult> ImportSurfaceAsync(
        string gmshExecutable,
        string path,
        OperationController operation,
        TimeSpan previewTimeout)
    {
        operation.Report("File validation", "Validating STEP path and source metadata.", 0.05);
        if (!File.Exists(path)) throw new FileNotFoundException("STEP file not found.", path);
        var extension = Path.GetExtension(path);
        if (!extension.Equals(".step", StringComparison.OrdinalIgnoreCase) && !extension.Equals(".stp", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("The selected file is not a STEP/STP file.");
        var fileInfo = new FileInfo(path);
        if (fileInfo.Length == 0) throw new InvalidDataException("The STEP file is empty.");

        var hints = StepSourceInspector.Inspect(path);
        var sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
        operation.Token.ThrowIfCancellationRequested();

        operation.Report("OpenCASCADE read", "Reading STEP topology through Gmsh/OpenCASCADE.", 0.20);
        var surfaceRun = await ManagedGmshMesher.GenerateAsync(
            gmshExecutable,
            path,
            null,
            2,
            previewTimeout,
            operation.Token);
        operation.Token.ThrowIfCancellationRequested();

        operation.Report("Surface mesh", "Reading MSH surface and constructing selectable topology.", 0.72);
        var mesh = surfaceRun.Mesh;
        if (mesh.Nodes.Count == 0 || mesh.SurfaceTriangles.Count == 0)
            throw new InvalidDataException("OpenCASCADE imported the STEP, but the surface mesh is empty.");
        var topology = CadTopologyRegistry.Get(mesh);
        if (topology.Faces.Count == 0)
            throw new InvalidDataException("The surface mesh contains no selectable CAD faces.");

        var isClosed = IsClosedTriangleSkin(mesh);
        var volume = Math.Abs(SignedSkinVolume(mesh));
        var edgeCount = UniqueMeshEdgeCount(mesh);
        var solidCount = hints.SolidCount > 0 ? hints.SolidCount : isClosed ? 1 : 0;
        var metadata = new CadModelMetadata
        {
            SourcePath = path,
            Sha256 = sha256,
            SourceUnit = hints.SourceUnit,
            SourceToMillimetres = hints.SourceToMillimetres,
            Min = mesh.Min,
            Max = mesh.Max,
            SolidCount = solidCount,
            ClosedShellCount = hints.ClosedShellCount,
            FaceCount = topology.Faces.Count,
            MeshEdgeCount = edgeCount,
            IsClosed = isClosed,
            VolumeMm3 = volume,
            GmshVersion = surfaceRun.Version,
            PersistentFaceIds = topology.Faces.Keys.OrderBy(tag => tag).Select(tag => $"face:{tag}").ToArray()
        };

        if (solidCount <= 0 || !isClosed || volume <= 0)
            throw new InvalidDataException($"STEP topology is not a verified closed positive-volume solid (solids={solidCount}, closed={isClosed}, volume={volume:G8} mm^3).");

        // Legacy Cartesian-point prism detection is intentionally after successful OCC import.
        // It can select a fast rectangular solver path, but it can never reject a general B-Rep.
        SimpleStepSolid? prism = null;
        try
        {
            var candidate = SimpleStepReader.ReadPrismaticSolid(path);
            if (candidate.IsSupportedPrism) prism = candidate;
        }
        catch
        {
            // Expected for valid curved B-Reps such as the cylinder regression: never use this as a validity gate.
        }

        operation.Report("Topology", $"Verified {solidCount} solid(s), {metadata.FaceCount} selectable faces and positive volume.", 0.92);
        var diagnostics =
            $"file={path}; size={fileInfo.Length}; sha256={sha256}; sourceUnit={hints.SourceUnit}; sourceToMm={hints.SourceToMillimetres:G8}; " +
            $"gmsh={surfaceRun.Version}; args={surfaceRun.Arguments}; occ+surface={surfaceRun.Elapsed.TotalMilliseconds:0} ms; " +
            $"solids={solidCount}; faces={metadata.FaceCount}; meshEdges={edgeCount}; closed={isClosed}; volumeMm3={volume:G10}; " +
            $"nodes={mesh.Nodes.Count}; triangles={mesh.SurfaceTriangles.Count}";
        return new CadImportResult
        {
            Metadata = metadata,
            Surface = new CadSurfaceMesh(mesh),
            VerifiedPrismFastPath = prism,
            Diagnostics = diagnostics
        };
    }

    public static CadModelMetadata MetadataFromVolume(CadModelMetadata surfaceMetadata, CadMesh volumeMesh)
    {
        var topology = CadTopologyRegistry.Get(volumeMesh);
        return new CadModelMetadata
        {
            SourcePath = surfaceMetadata.SourcePath,
            Sha256 = surfaceMetadata.Sha256,
            SourceUnit = surfaceMetadata.SourceUnit,
            SourceToMillimetres = surfaceMetadata.SourceToMillimetres,
            Min = volumeMesh.Min,
            Max = volumeMesh.Max,
            SolidCount = surfaceMetadata.SolidCount,
            ClosedShellCount = surfaceMetadata.ClosedShellCount,
            FaceCount = topology.Faces.Count,
            MeshEdgeCount = UniqueMeshEdgeCount(volumeMesh),
            IsClosed = IsClosedTriangleSkin(volumeMesh),
            VolumeMm3 = Math.Abs(TetraVolume(volumeMesh)),
            GmshVersion = surfaceMetadata.GmshVersion,
            PersistentFaceIds = topology.Faces.Keys.OrderBy(tag => tag).Select(tag => $"face:{tag}").ToArray()
        };
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
        var sum = 0.0;
        foreach (var triangle in mesh.SurfaceTriangles)
        {
            var a = mesh.Nodes[triangle[0]];
            var b = mesh.Nodes[triangle[1]];
            var c = mesh.Nodes[triangle[2]];
            sum += Dot(a, Cross(b, c)) / 6.0;
        }
        return sum;
    }

    private static double TetraVolume(CadMesh mesh)
    {
        var volume = 0.0;
        foreach (var tet in mesh.Tetrahedra)
        {
            var a = mesh.Nodes[tet[0]];
            var b = mesh.Nodes[tet[1]];
            var c = mesh.Nodes[tet[2]];
            var d = mesh.Nodes[tet[3]];
            volume += Math.Abs(Dot(b - a, Cross(c - a, d - a))) / 6.0;
        }
        return volume;
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(
        a.Y * b.Z - a.Z * b.Y,
        a.Z * b.X - a.X * b.Z,
        a.X * b.Y - a.Y * b.X);

    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}
