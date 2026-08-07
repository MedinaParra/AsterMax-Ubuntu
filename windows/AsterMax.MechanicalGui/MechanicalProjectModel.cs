using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

internal enum MechanicalObjectState
{
    Incomplete,
    UpToDate,
    Obsolete,
    Solving,
    Solved,
    Error,
    Suppressed
}

internal enum MechanicalUnitSystem
{
    MillimeterNewtonMegapascal,
    MeterNewtonPascal,
    InchPoundForcePsi
}

internal sealed class MechanicalProjectDocument
{
    public const int CurrentSchemaVersion = 1;

    public int SchemaVersion { get; set; } = CurrentSchemaVersion;
    public Guid ProjectId { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = "Untitled";
    public MechanicalUnitSystem UnitSystem { get; set; } = MechanicalUnitSystem.MillimeterNewtonMegapascal;
    public DateTimeOffset CreatedUtc { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset ModifiedUtc { get; set; } = DateTimeOffset.UtcNow;
    public List<MechanicalAnalysisSystem> Systems { get; set; } = [];

    public MechanicalAnalysisSystem AddStaticStructural(string name = "Static Structural")
    {
        var system = MechanicalAnalysisSystem.CreateStaticStructural(name);
        Systems.Add(system);
        Touch();
        return system;
    }

    public void Touch() => ModifiedUtc = DateTimeOffset.UtcNow;

    public void Validate()
    {
        if (SchemaVersion <= 0 || SchemaVersion > CurrentSchemaVersion)
            throw new InvalidOperationException($"Unsupported project schema version {SchemaVersion}.");
        if (ProjectId == Guid.Empty)
            throw new InvalidOperationException("Project identifier is empty.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Project name is required.");

        var ids = new HashSet<Guid>();
        foreach (var system in Systems)
        {
            system.Validate();
            foreach (var item in system.EnumerateObjects())
                if (!ids.Add(item.Id))
                    throw new InvalidOperationException($"Duplicate mechanical object identifier {item.Id}.");
        }
    }
}

internal sealed class MechanicalAnalysisSystem
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = "Static Structural";
    public string AnalysisType { get; set; } = "StaticStructural";
    public MechanicalTreeObject Geometry { get; set; } = MechanicalTreeObject.Create("Geometry");
    public MechanicalTreeObject Materials { get; set; } = MechanicalTreeObject.Create("Engineering Data");
    public MechanicalTreeObject Model { get; set; } = MechanicalTreeObject.Create("Model");
    public MechanicalTreeObject Analysis { get; set; } = MechanicalTreeObject.Create("Static Structural");
    public MechanicalTreeObject Solution { get; set; } = MechanicalTreeObject.Create("Solution");

    public static MechanicalAnalysisSystem CreateStaticStructural(string name)
    {
        return new MechanicalAnalysisSystem
        {
            Name = string.IsNullOrWhiteSpace(name) ? "Static Structural" : name.Trim()
        };
    }

    public IEnumerable<MechanicalTreeObject> EnumerateObjects()
    {
        foreach (var root in new[] { Geometry, Materials, Model, Analysis, Solution })
            foreach (var item in root.EnumerateDepthFirst())
                yield return item;
    }

    public void MarkDownstreamObsolete(Guid changedObjectId)
    {
        var ordered = new[] { Geometry, Materials, Model, Analysis, Solution };
        var index = Array.FindIndex(ordered, root => root.EnumerateDepthFirst().Any(item => item.Id == changedObjectId));
        if (index < 0) return;

        for (var current = index; current < ordered.Length; current++)
            foreach (var item in ordered[current].EnumerateDepthFirst())
                if (item.State is MechanicalObjectState.UpToDate or MechanicalObjectState.Solved)
                    item.State = MechanicalObjectState.Obsolete;
    }

    public void Validate()
    {
        if (Id == Guid.Empty) throw new InvalidOperationException("Analysis system identifier is empty.");
        if (string.IsNullOrWhiteSpace(Name)) throw new InvalidOperationException("Analysis system name is required.");
        foreach (var root in new[] { Geometry, Materials, Model, Analysis, Solution }) root.Validate();
    }
}

internal sealed class MechanicalTreeObject
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string Name { get; set; } = string.Empty;
    public string ObjectType { get; set; } = "Folder";
    public MechanicalObjectState State { get; set; } = MechanicalObjectState.Incomplete;
    public bool IsSuppressed { get; set; }
    public Dictionary<string, JsonElement> Properties { get; set; } = [];
    public List<MechanicalTreeObject> Children { get; set; } = [];

    public static MechanicalTreeObject Create(string name, string objectType = "Folder") => new()
    {
        Name = name,
        ObjectType = objectType
    };

    public MechanicalTreeObject Insert(string name, string objectType)
    {
        var child = Create(name, objectType);
        Children.Add(child);
        State = MechanicalObjectState.Obsolete;
        return child;
    }

    public bool Remove(Guid objectId)
    {
        var direct = Children.FindIndex(child => child.Id == objectId);
        if (direct >= 0)
        {
            Children.RemoveAt(direct);
            State = MechanicalObjectState.Obsolete;
            return true;
        }

        foreach (var child in Children)
            if (child.Remove(objectId)) return true;
        return false;
    }

    public MechanicalTreeObject Duplicate()
    {
        var json = JsonSerializer.Serialize(this, MechanicalProjectStore.JsonOptions);
        var copy = JsonSerializer.Deserialize<MechanicalTreeObject>(json, MechanicalProjectStore.JsonOptions)
                   ?? throw new InvalidOperationException("Unable to duplicate mechanical object.");
        copy.RegenerateIds();
        copy.Name = $"{Name} Copy";
        copy.State = MechanicalObjectState.Obsolete;
        return copy;
    }

    public IEnumerable<MechanicalTreeObject> EnumerateDepthFirst()
    {
        yield return this;
        foreach (var child in Children)
            foreach (var descendant in child.EnumerateDepthFirst())
                yield return descendant;
    }

    public void Validate()
    {
        if (Id == Guid.Empty) throw new InvalidOperationException("Mechanical object identifier is empty.");
        if (string.IsNullOrWhiteSpace(Name)) throw new InvalidOperationException("Mechanical object name is required.");
        if (IsSuppressed) State = MechanicalObjectState.Suppressed;
        foreach (var child in Children) child.Validate();
    }

    private void RegenerateIds()
    {
        Id = Guid.NewGuid();
        foreach (var child in Children) child.RegenerateIds();
    }
}

internal static class MechanicalProjectStore
{
    internal static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    public static void Save(string path, MechanicalProjectDocument project)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        ArgumentNullException.ThrowIfNull(project);
        project.Touch();
        project.Validate();

        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);

        var temporaryPath = path + ".tmp";
        File.WriteAllText(temporaryPath, JsonSerializer.Serialize(project, JsonOptions));
        File.Move(temporaryPath, path, true);
    }

    public static MechanicalProjectDocument Load(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        if (!File.Exists(path)) throw new FileNotFoundException("Mechanical project was not found.", path);

        var project = JsonSerializer.Deserialize<MechanicalProjectDocument>(File.ReadAllText(path), JsonOptions)
                      ?? throw new InvalidDataException("Mechanical project content is empty or invalid.");
        project.Validate();
        return project;
    }
}
