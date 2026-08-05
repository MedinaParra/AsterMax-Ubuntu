namespace AsterMax.MechanicalGui;

internal enum MeshControlKind
{
    BodySizing,
    FaceSizing,
    EdgeSizing,
    SphereOfInfluence,
    Inflation,
    Refinement
}

internal enum MeshSizingBehavior
{
    Hard,
    Soft
}

internal sealed record MeshControlScope(
    IReadOnlyList<Guid> BodyIds,
    IReadOnlyList<int> FaceIds,
    IReadOnlyList<int> EdgeIds)
{
    public static MeshControlScope Empty { get; } = new([], [], []);

    public bool IsEmpty => BodyIds.Count == 0 && FaceIds.Count == 0 && EdgeIds.Count == 0;

    public void Validate(string controlName, MeshControlKind kind)
    {
        if (BodyIds.Any(id => id == Guid.Empty))
            throw new InvalidOperationException($"Mesh control '{controlName}' contains an empty body identifier.");
        if (FaceIds.Any(id => id < 0) || EdgeIds.Any(id => id < 0))
            throw new InvalidOperationException($"Mesh control '{controlName}' contains a negative topology identifier.");
        if (BodyIds.Count != BodyIds.Distinct().Count() ||
            FaceIds.Count != FaceIds.Distinct().Count() ||
            EdgeIds.Count != EdgeIds.Distinct().Count())
            throw new InvalidOperationException($"Mesh control '{controlName}' contains duplicate scope entities.");

        var valid = kind switch
        {
            MeshControlKind.BodySizing => BodyIds.Count > 0 && FaceIds.Count == 0 && EdgeIds.Count == 0,
            MeshControlKind.FaceSizing => FaceIds.Count > 0 && BodyIds.Count == 0 && EdgeIds.Count == 0,
            MeshControlKind.EdgeSizing => EdgeIds.Count > 0 && BodyIds.Count == 0 && FaceIds.Count == 0,
            MeshControlKind.SphereOfInfluence => BodyIds.Count > 0 && FaceIds.Count == 0 && EdgeIds.Count == 0,
            MeshControlKind.Inflation => FaceIds.Count > 0 && EdgeIds.Count == 0,
            MeshControlKind.Refinement => !IsEmpty,
            _ => false
        };

        if (!valid)
            throw new InvalidOperationException($"Mesh control '{controlName}' has an incompatible scope for {kind}.");
    }
}

internal sealed class MeshControlDefinition
{
    public required Guid Id { get; init; }
    public required Guid MeshId { get; init; }
    public required string Name { get; init; }
    public required string GeometrySignature { get; init; }
    public required MeshControlKind Kind { get; init; }
    public MeshSizingBehavior Behavior { get; init; } = MeshSizingBehavior.Hard;
    public required MeshControlScope Scope { get; init; }
    public double? ElementSize { get; init; }
    public int RefinementLevel { get; init; }
    public double? SphereRadius { get; init; }
    public int InflationLayers { get; init; }
    public double? InflationGrowthRate { get; init; }
    public double? FirstLayerHeight { get; init; }

    public void Validate(string activeGeometrySignature)
    {
        if (Id == Guid.Empty || MeshId == Guid.Empty)
            throw new InvalidOperationException("Mesh control and mesh identifiers must be stable.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Mesh control name cannot be empty.");
        if (string.IsNullOrWhiteSpace(GeometrySignature) ||
            !string.Equals(GeometrySignature, activeGeometrySignature, StringComparison.Ordinal))
            throw new InvalidOperationException($"Mesh control '{Name}' is stale for the active geometry.");
        if (!Enum.IsDefined(Kind) || !Enum.IsDefined(Behavior))
            throw new InvalidOperationException($"Mesh control '{Name}' contains an unsupported option.");

        Scope.Validate(Name, Kind);

        if (ElementSize.HasValue && (!double.IsFinite(ElementSize.Value) || ElementSize.Value <= 0.0))
            throw new InvalidOperationException($"Mesh control '{Name}' requires a positive element size.");
        if (SphereRadius.HasValue && (!double.IsFinite(SphereRadius.Value) || SphereRadius.Value <= 0.0))
            throw new InvalidOperationException($"Mesh control '{Name}' requires a positive sphere radius.");
        if (FirstLayerHeight.HasValue && (!double.IsFinite(FirstLayerHeight.Value) || FirstLayerHeight.Value <= 0.0))
            throw new InvalidOperationException($"Mesh control '{Name}' requires a positive first-layer height.");
        if (InflationGrowthRate.HasValue &&
            (!double.IsFinite(InflationGrowthRate.Value) || InflationGrowthRate.Value < 1.0 || InflationGrowthRate.Value > 2.0))
            throw new InvalidOperationException($"Mesh control '{Name}' requires an inflation growth rate between 1.0 and 2.0.");

        switch (Kind)
        {
            case MeshControlKind.BodySizing:
            case MeshControlKind.FaceSizing:
            case MeshControlKind.EdgeSizing:
                if (!ElementSize.HasValue)
                    throw new InvalidOperationException($"Mesh control '{Name}' requires an element size.");
                break;
            case MeshControlKind.SphereOfInfluence:
                if (!ElementSize.HasValue || !SphereRadius.HasValue)
                    throw new InvalidOperationException($"Mesh control '{Name}' requires element size and sphere radius.");
                break;
            case MeshControlKind.Refinement:
                if (RefinementLevel is < 1 or > 3)
                    throw new InvalidOperationException($"Mesh control '{Name}' requires refinement level 1 through 3.");
                break;
            case MeshControlKind.Inflation:
                if (InflationLayers is < 1 or > 100 || !InflationGrowthRate.HasValue || !FirstLayerHeight.HasValue)
                    throw new InvalidOperationException($"Mesh control '{Name}' requires valid inflation layers, growth rate and first-layer height.");
                break;
        }
    }
}

internal sealed class MeshControlCatalog
{
    private readonly Dictionary<Guid, MeshControlDefinition> _controls = [];

    public IReadOnlyCollection<MeshControlDefinition> Controls => _controls.Values;

    public void Add(MeshControlDefinition control, MeshDefinition mesh, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(control);
        ArgumentNullException.ThrowIfNull(mesh);
        control.Validate(activeGeometrySignature);
        if (control.MeshId != mesh.Id)
            throw new InvalidOperationException($"Mesh control '{control.Name}' does not belong to mesh '{mesh.Name}'.");
        if (!string.Equals(control.GeometrySignature, mesh.GeometrySignature, StringComparison.Ordinal))
            throw new InvalidOperationException($"Mesh control '{control.Name}' and mesh '{mesh.Name}' use different geometry signatures.");
        if (_controls.ContainsKey(control.Id))
            throw new InvalidOperationException($"Mesh control '{control.Id}' already exists.");
        if (_controls.Values.Any(item => item.MeshId == control.MeshId &&
                                        string.Equals(item.Name, control.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Mesh control name '{control.Name}' is already in use for this mesh.");
        _controls.Add(control.Id, control);
    }

    public IReadOnlyList<MeshControlDefinition> ForMesh(Guid meshId) =>
        _controls.Values.Where(control => control.MeshId == meshId).OrderBy(control => control.Name).ToArray();
}
