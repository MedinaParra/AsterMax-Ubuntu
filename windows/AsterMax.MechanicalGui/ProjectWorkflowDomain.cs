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

internal enum MechanicalObjectKind
{
    Project,
    AnalysisSystem,
    Geometry,
    Material,
    CoordinateSystem,
    NamedSelection,
    Mesh,
    MeshControl,
    Connection,
    RemotePoint,
    Load,
    Support,
    AnalysisSettings,
    Solution,
    Result,
    Probe,
    Chart,
    Report
}

internal sealed record MechanicalScope(
    IReadOnlyList<int> VertexIds,
    IReadOnlyList<int> EdgeIds,
    IReadOnlyList<int> FaceIds,
    IReadOnlyList<int> BodyIds,
    IReadOnlyList<int> NodeIds)
{
    public static MechanicalScope Empty { get; } = new([], [], [], [], []);

    public bool IsEmpty =>
        VertexIds.Count == 0 &&
        EdgeIds.Count == 0 &&
        FaceIds.Count == 0 &&
        BodyIds.Count == 0 &&
        NodeIds.Count == 0;
}

internal sealed class MechanicalTreeObject
{
    public required Guid Id { get; init; }
    public required MechanicalObjectKind Kind { get; init; }
    public required string Name { get; set; }
    public required MechanicalObjectState State { get; set; }
    public Guid? ParentId { get; set; }
    public MechanicalScope Scope { get; set; } = MechanicalScope.Empty;
    public Dictionary<string, string> Properties { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<Guid> ChildIds { get; } = [];

    public void MarkObsolete()
    {
        if (State is MechanicalObjectState.Solving or MechanicalObjectState.Suppressed)
            return;
        State = MechanicalObjectState.Obsolete;
    }
}

internal sealed class MechanicalProjectModel
{
    private readonly Dictionary<Guid, MechanicalTreeObject> _objects = [];

    public Guid ProjectId { get; init; } = Guid.NewGuid();
    public string Name { get; set; } = "Untitled";
    public MechanicalUnitSystem UnitSystem { get; set; } = MechanicalUnitSystem.MillimeterNewtonMegapascal;
    public int SchemaVersion { get; set; } = 1;
    public bool IsDirty { get; private set; }
    public IReadOnlyCollection<MechanicalTreeObject> Objects => _objects.Values;

    public MechanicalTreeObject Add(
        MechanicalObjectKind kind,
        string name,
        Guid? parentId = null,
        MechanicalScope? scope = null)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Object name cannot be empty.", nameof(name));
        if (parentId.HasValue && !_objects.ContainsKey(parentId.Value))
            throw new InvalidOperationException("The parent object does not exist in the project.");

        var item = new MechanicalTreeObject
        {
            Id = Guid.NewGuid(),
            Kind = kind,
            Name = name.Trim(),
            State = MechanicalObjectState.Incomplete,
            ParentId = parentId,
            Scope = scope ?? MechanicalScope.Empty
        };
        _objects.Add(item.Id, item);
        if (parentId.HasValue)
            _objects[parentId.Value].ChildIds.Add(item.Id);
        IsDirty = true;
        return item;
    }

    public MechanicalTreeObject Duplicate(Guid sourceId, string? newName = null)
    {
        var source = Get(sourceId);
        var copy = Add(source.Kind, newName ?? $"{source.Name} Copy", source.ParentId, source.Scope);
        foreach (var property in source.Properties)
            copy.Properties[property.Key] = property.Value;
        copy.State = MechanicalObjectState.Obsolete;
        return copy;
    }

    public void Rename(Guid id, string name)
    {
        if (string.IsNullOrWhiteSpace(name))
            throw new ArgumentException("Object name cannot be empty.", nameof(name));
        Get(id).Name = name.Trim();
        IsDirty = true;
    }

    public void Suppress(Guid id, bool suppressed)
    {
        var item = Get(id);
        item.State = suppressed ? MechanicalObjectState.Suppressed : MechanicalObjectState.Obsolete;
        MarkDependentsObsolete(id);
        IsDirty = true;
    }

    public void Remove(Guid id)
    {
        var item = Get(id);
        foreach (var childId in item.ChildIds.ToArray())
            Remove(childId);
        if (item.ParentId.HasValue && _objects.TryGetValue(item.ParentId.Value, out var parent))
            parent.ChildIds.Remove(id);
        _objects.Remove(id);
        IsDirty = true;
    }

    public MechanicalTreeObject Get(Guid id) =>
        _objects.TryGetValue(id, out var item)
            ? item
            : throw new KeyNotFoundException($"Project object '{id}' was not found.");

    public void SetProperty(Guid id, string key, string value)
    {
        var item = Get(id);
        item.Properties[key] = value;
        item.MarkObsolete();
        MarkDependentsObsolete(id);
        IsDirty = true;
    }

    public void MarkSaved() => IsDirty = false;

    private void MarkDependentsObsolete(Guid id)
    {
        foreach (var candidate in _objects.Values)
        {
            if (candidate.ParentId == id)
                candidate.MarkObsolete();
        }
    }
}
