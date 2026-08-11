using System.Globalization;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AsterMax.MechanicalGui;

internal sealed record TutorialCaseDefinition(
    string Id,
    string Name,
    string[] RequiredFiles,
    string RequiredCapability);

internal sealed record TutorialInputEvidence(
    string File,
    bool Present,
    long? Bytes,
    string? Sha256,
    string? LocatedPath);

internal sealed record TutorialCaseResult
{
    public required string Id { get; init; }
    public required string Name { get; init; }
    public required string Status { get; init; }
    public required string RequiredCapability { get; init; }
    public required IReadOnlyList<TutorialInputEvidence> Inputs { get; init; }
    public required string Diagnosis { get; init; }
    public double? ReferenceValue { get; init; }
    public double? ComputedValue { get; init; }
    public double? Tolerance { get; init; }
    public double? DifferencePercent { get; init; }
    public string? EvidenceDirectory { get; init; }
}

internal static class TutorialCertificationBootstrap
{
    [System.Runtime.CompilerServices.ModuleInitializer]
    internal static void Initialize()
    {
        var args = Environment.GetCommandLineArgs().Skip(1).ToArray();
        var index = Array.FindIndex(args,
            arg => string.Equals(arg, "--tutorial-suite", StringComparison.OrdinalIgnoreCase));
        if (index < 0) return;

        var code = TutorialCertificationSuite.Run(args.Skip(index + 1).ToArray());
        Environment.Exit(code);
    }
}

internal static class TutorialCertificationSuite
{
    private const string Passed = "Passed";
    private const string Failed = "Failed";
    private const string Unavailable = "Unavailable";
    private const string TimedOut = "TimedOut";
    private const string NotRun = "NotRun";

    private static readonly TutorialCaseDefinition[] Definitions =
    [
        new("WS01.1", "Mechanical Basics", ["Cap_fillets.stp"], "General 3-D linear static solid analysis with aluminum, pressure, frictionless supports, stress/deformation/FOS and yield verification."),
        new("WS02.1", "2D Gear and Rack", ["Gear_Set_2D.stp"], "2-D plane-stress formulation, gear/rack contact, 2500 N force, remote displacement and reaction moment."),
        new("WS02.2", "Named Selections", ["Named_Selections.wbpz"], "Manual and criteria-based named selections with persistent scoping, fixed support and radial displacement."),
        new("WS02.3", "Object Generator", ["Bolt_Plates.stp"], "Generate 12 beam connections over plate holes, fix lower edges, apply 1000 N and solve."),
        new("WS02.4", "Object Generator with Named Selections", ["Valve_RM_20130113.stp"], "Criteria named selections and generated objects over the real valve model, followed by solve."),
        new("WS03.1", "Linear Structural Analysis", ["Pump_assy_3.stp"], "Five-part pump assembly, per-body materials, contacts, frictionless support, 100 N bearing load and displacement/yield checks."),
        new("WS03.2", "Beam Connections", ["Flange Mount.stp"], "Beam fasteners, fixed end, remote force 1000 N at Z=100 mm, reactions and stresses."),
        new("WS04.1", "Mesh Evaluation", ["Mesh_Arm_2.stp"], "Real mesh-quality and convergence study under tension/bending on the arm web region."),
        new("WS04.2", "Parameter Management", ["Bracket.stp"], "Bracket/gusset thickness parameters, design-point combinations and structural response comparison."),
        new("WS05.1", "Mesh Creation", ["Meshing.wbpz"], "Assembly meshing with symmetry, per-body mesh methods, controls and real statistics."),
        new("WS05.2", "Mesh Control", ["assembly_solid.stp"], "Mesh controls applied to the real assembly with quantified effect on mesh defects/quality."),
        new("WS06.1", "Contact Offset Control", ["Contact_Interface.wbpz"], "Valve/piston 0.39 mm gap solved without and with initial contact offset, with comparison."),
        new("WS06.2", "Joints", ["Joint_Connection.wbpz"], "Four-part assembly, required contact, automatic joints, edited DOF and solve."),
        new("WS06.3", "Remote Boundary Conditions", ["Remote_BC.wbpz"], "Jack base with point mass, remote force, correct remote locations/coupling and reactions."),
        new("WS06.4", "Constraint Equations", ["ConstEqn.wbpz"], "Hook fastener constraint equation 5*UY-UX=0 with 25 mm X and 5 mm Y verification."),
        new("WS07.1", "Modal Analysis", ["Machine_Frame.stp"], "3-D modal analysis comparing eight-hole mount against four corner holes with authentic mode shapes."),
        new("WS07.2", "Steady-State Thermal", ["Pump_housing.stp"], "Steady thermal comparison plastic/aluminum: 60 C mount, 90 C interior, convection to 20 C air."),
        new("WS07.3", "Multistep Analysis", ["Pipe_Clamp.wbpz"], "Four-step pipe clamp analysis with bolt pretension, lock, internal pressure and axial force history."),
        new("WS08.1", "Eigenvalue Buckling", ["Pipe.stp"], "Fixed-free pipe, 10,000 lbf compression, eigenvalue buckling and comparison to ~65,648.3 lbf closed reference."),
        new("WS08.2", "Submodeling", ["Submodeling_WS_APPXB.wbpz", "Submodelv150.stp", "Pump_housing.stp"], "Coarse global pump-housing solve, displacement transfer to cut boundaries and refined submodel convergence.")
    ];

    public static int Run(string[] args)
    {
        string? extractionRoot = null;
        try
        {
            if (Definitions.Length != 20)
                throw new InvalidOperationException($"TutorialSuite_ReportsExactlyTwentyCases failed: definitions={Definitions.Length}.");
            if (args.Length < 1)
                throw new InvalidOperationException("Usage: --tutorial-suite <zip-or-directory> --output <directory> [--case WS01.1]");

            var source = Path.GetFullPath(args[0]);
            var outputOption = ReadOption(args, "--output");
            if (string.IsNullOrWhiteSpace(outputOption))
                throw new InvalidOperationException("--output <directory> is required.");
            var output = Path.GetFullPath(outputOption);
            var selectedId = ReadOption(args, "--case");
            Directory.CreateDirectory(output);

            string root;
            if (Directory.Exists(source))
            {
                root = source;
            }
            else if (File.Exists(source) && Path.GetExtension(source).Equals(".zip", StringComparison.OrdinalIgnoreCase))
            {
                extractionRoot = Path.Combine(Path.GetTempPath(), "AsterMax", "tutorial-suite", Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(extractionRoot);
                ZipFile.ExtractToDirectory(source, extractionRoot);
                root = extractionRoot;
            }
            else
            {
                throw new FileNotFoundException("Tutorial source must be the Mechanical ZIP or an extracted directory.", source);
            }

            var index = BuildFileIndex(root);
            var selected = string.IsNullOrWhiteSpace(selectedId)
                ? Definitions
                : Definitions.Where(definition => definition.Id.Equals(selectedId, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (selected.Length == 0)
                throw new InvalidOperationException($"Unknown tutorial case '{selectedId}'.");

            var results = selected.Select(definition => EvaluateNotYetCertified(definition, index, output)).ToArray();
            if (results.Any(result => result.Status == Passed && result.Diagnosis.Contains("skip", StringComparison.OrdinalIgnoreCase)))
                throw new InvalidOperationException("TutorialSuite_DoesNotPassSkippedCases failed.");

            var fullRun = string.IsNullOrWhiteSpace(selectedId);
            var allResults = fullRun ? results : Definitions.Select(definition =>
            {
                var selectedResult = results.FirstOrDefault(result => result.Id == definition.Id);
                return selectedResult ?? new TutorialCaseResult
                {
                    Id = definition.Id,
                    Name = definition.Name,
                    Status = NotRun,
                    RequiredCapability = definition.RequiredCapability,
                    Inputs = Array.Empty<TutorialInputEvidence>(),
                    Diagnosis = $"Not selected in single-case debug run ({selectedId})."
                };
            }).ToArray();

            WriteOutputs(source, output, allResults, selectedId);
            var passed = allResults.Count(result => result.Status == Passed);
            var failed = allResults.Count(result => result.Status == Failed);
            var unavailable = allResults.Count(result => result.Status == Unavailable);
            var timedOut = allResults.Count(result => result.Status == TimedOut);
            var notRun = allResults.Count(result => result.Status == NotRun);
            var strictPercent = passed / 20.0 * 100.0;

            Console.WriteLine($"Tutorial certification suite | Passed={passed}/20 ({strictPercent:0.0}%) | Failed={failed} | Unavailable={unavailable} | TimedOut={timedOut} | NotRun={notRun}");
            foreach (var result in results)
                Console.WriteLine($"{result.Id} | {result.Status} | {result.Name} | {result.Diagnosis}");

            // Full certification returns 0 only at 20/20. Single-case debug returns 0 only if that selected case really Passed.
            return fullRun ? passed == 20 ? 0 : 20 : results.All(result => result.Status == Passed) ? 0 : 21;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 22;
        }
        finally
        {
            if (extractionRoot is not null)
            {
                try { Directory.Delete(extractionRoot, true); } catch { }
            }
        }
    }

    private static TutorialCaseResult EvaluateNotYetCertified(
        TutorialCaseDefinition definition,
        IReadOnlyDictionary<string, string> index,
        string outputRoot)
    {
        var inputs = definition.RequiredFiles.Select(file =>
        {
            if (!index.TryGetValue(file, out var located))
                return new TutorialInputEvidence(file, false, null, null, null);
            var info = new FileInfo(located);
            var hash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(located))).ToLowerInvariant();
            return new TutorialInputEvidence(file, true, info.Length, hash, located);
        }).ToArray();
        var missing = inputs.Where(input => !input.Present).Select(input => input.File).ToArray();
        var caseDirectory = Path.Combine(outputRoot, definition.Id.Replace('.', '_'));
        Directory.CreateDirectory(caseDirectory);
        File.WriteAllText(Path.Combine(caseDirectory, "inputs.json"), JsonSerializer.Serialize(inputs, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));

        if (missing.Length > 0)
        {
            return new TutorialCaseResult
            {
                Id = definition.Id,
                Name = definition.Name,
                Status = Unavailable,
                RequiredCapability = definition.RequiredCapability,
                Inputs = inputs,
                Diagnosis = "Required source input missing: " + string.Join(", ", missing),
                EvidenceDirectory = caseDirectory
            };
        }

        return new TutorialCaseResult
        {
            Id = definition.Id,
            Name = definition.Name,
            Status = NotRun,
            RequiredCapability = definition.RequiredCapability,
            Inputs = inputs,
            Diagnosis = "Inputs discovered and hashed, but this exact workshop has not yet completed the required native AsterMax E2E solve, persistence, physical comparison and Windows automated test. It is intentionally not Passed.",
            EvidenceDirectory = caseDirectory
        };
    }

    private static Dictionary<string, string> BuildFileIndex(string root)
    {
        return Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
            .GroupBy(Path.GetFileName, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.First(), StringComparer.OrdinalIgnoreCase);
    }

    private static void WriteOutputs(string source, string output, IReadOnlyList<TutorialCaseResult> results, string? selectedId)
    {
        var passed = results.Count(result => result.Status == Passed);
        var summary = new
        {
            product = "AsterMax Windows 2.0 beta",
            generatedAtUtc = DateTimeOffset.UtcNow,
            source,
            selectedCase = selectedId,
            totalCases = 20,
            passed,
            failed = results.Count(result => result.Status == Failed),
            unavailable = results.Count(result => result.Status == Unavailable),
            timedOut = results.Count(result => result.Status == TimedOut),
            notRun = results.Count(result => result.Status == NotRun),
            strictCertificationPercent = passed / 20.0 * 100.0,
            rule = "A case is Passed only with exact E2E physics, JSON/CSV/HTML evidence, save/reopen persistence, Windows automation, explicit reference/tolerance and controlled failure behavior.",
            cases = results
        };
        File.WriteAllText(Path.Combine(output, "tutorial-certification.json"), JsonSerializer.Serialize(summary, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
        WriteCsv(Path.Combine(output, "tutorial-certification.csv"), results);
        WriteHtml(Path.Combine(output, "tutorial-certification.html"), results, passed);
    }

    private static void WriteCsv(string path, IReadOnlyList<TutorialCaseResult> results)
    {
        static string Q(string? value) => "\"" + (value ?? string.Empty).Replace("\"", "\"\"") + "\"";
        var lines = new List<string> { "id,name,status,required_capability,inputs_present,diagnosis,reference,computed,tolerance,difference_percent" };
        foreach (var result in results)
        {
            var present = $"{result.Inputs.Count(input => input.Present)}/{result.Inputs.Count}";
            lines.Add(string.Join(",",
                Q(result.Id), Q(result.Name), Q(result.Status), Q(result.RequiredCapability), Q(present), Q(result.Diagnosis),
                result.ReferenceValue?.ToString("G17", CultureInfo.InvariantCulture) ?? string.Empty,
                result.ComputedValue?.ToString("G17", CultureInfo.InvariantCulture) ?? string.Empty,
                result.Tolerance?.ToString("G17", CultureInfo.InvariantCulture) ?? string.Empty,
                result.DifferencePercent?.ToString("G17", CultureInfo.InvariantCulture) ?? string.Empty));
        }
        File.WriteAllLines(path, lines, new UTF8Encoding(false));
    }

    private static void WriteHtml(string path, IReadOnlyList<TutorialCaseResult> results, int passed)
    {
        static string H(string? value) => System.Net.WebUtility.HtmlEncode(value ?? string.Empty);
        var rows = string.Join(Environment.NewLine, results.Select(result =>
            $"<tr><td>{H(result.Id)}</td><td>{H(result.Name)}</td><td>{H(result.Status)}</td><td>{result.Inputs.Count(input => input.Present)}/{result.Inputs.Count}</td><td>{H(result.Diagnosis)}</td></tr>"));
        var html = $"""
        <!doctype html>
        <html><head><meta charset="utf-8"><title>AsterMax Tutorial Certification</title>
        <style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#202a34}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #c5ced8;padding:7px;vertical-align:top}}th{{background:#edf2f7}}code{{background:#eef2f5;padding:2px 4px}}</style></head>
        <body><h1>AsterMax Windows 2.0 beta — Tutorial Certification</h1>
        <p><strong>Strict certification:</strong> {passed}/20 = {(passed / 20.0 * 100.0):0.0}%</p>
        <p><code>Passed</code> is never assigned to NotRun, Unavailable, TimedOut or skipped cases.</p>
        <table><thead><tr><th>ID</th><th>Workshop</th><th>Status</th><th>Inputs</th><th>Diagnosis</th></tr></thead><tbody>{rows}</tbody></table></body></html>
        """;
        File.WriteAllText(path, html, new UTF8Encoding(false));
    }

    private static string? ReadOption(string[] args, string name)
    {
        for (var index = 0; index < args.Length - 1; index++)
            if (string.Equals(args[index], name, StringComparison.OrdinalIgnoreCase)) return args[index + 1];
        return null;
    }
}