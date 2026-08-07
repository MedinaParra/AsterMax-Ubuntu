namespace AsterMax.MechanicalGui;

internal enum ContactFormulation
{
    Frictionless,
    Frictional,
    Bonded,
    NoSeparation
}

internal enum ContactDetectionMethod
{
    NodalNormalToTarget,
    GaussPointToTarget,
    Symmetric
}

internal enum ContactBehavior
{
    Asymmetric,
    Symmetric
}

internal sealed class ContactRegionDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid SourceSelectionId { get; init; }
    public required Guid TargetSelectionId { get; init; }
    public required ContactFormulation Formulation { get; init; }
    public ContactDetectionMethod DetectionMethod { get; init; } = ContactDetectionMethod.GaussPointToTarget;
    public ContactBehavior Behavior { get; init; } = ContactBehavior.Asymmetric;
    public double FrictionCoefficient { get; init; }
    public double NormalPenaltyFactor { get; init; } = 1.0;
    public double? PinballRadius { get; init; }
    public bool AllowInitialPenetration { get; init; }

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Contact region must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Contact region name cannot be empty.");
        if (SourceSelectionId == Guid.Empty || TargetSelectionId == Guid.Empty)
            throw new InvalidOperationException($"Contact region '{Name}' requires source and target named selections.");
        if (SourceSelectionId == TargetSelectionId)
            throw new InvalidOperationException($"Contact region '{Name}' cannot use the same named selection for source and target.");
        if (!double.IsFinite(NormalPenaltyFactor) || NormalPenaltyFactor <= 0.0)
            throw new InvalidOperationException($"Contact region '{Name}' requires a finite positive normal penalty factor.");
        if (PinballRadius.HasValue && (!double.IsFinite(PinballRadius.Value) || PinballRadius.Value <= 0.0))
            throw new InvalidOperationException($"Contact region '{Name}' has an invalid pinball radius.");
        if (!double.IsFinite(FrictionCoefficient) || FrictionCoefficient < 0.0)
            throw new InvalidOperationException($"Contact region '{Name}' has an invalid friction coefficient.");
        if (Formulation == ContactFormulation.Frictional && FrictionCoefficient <= 0.0)
            throw new InvalidOperationException($"Frictional contact region '{Name}' requires a positive friction coefficient.");
        if (Formulation != ContactFormulation.Frictional && FrictionCoefficient != 0.0)
            throw new InvalidOperationException($"Contact region '{Name}' defines friction for a non-frictional formulation.");

        var source = selections.Get(SourceSelectionId);
        var target = selections.Get(TargetSelectionId);
        if (source.EntityType != NamedSelectionEntityType.Face || target.EntityType != NamedSelectionEntityType.Face)
            throw new InvalidOperationException($"Contact region '{Name}' requires face-based source and target selections.");

        var sourceScope = selections.Resolve(SourceSelectionId, activeGeometrySignature);
        var targetScope = selections.Resolve(TargetSelectionId, activeGeometrySignature);
        if (sourceScope.FaceIds.Intersect(targetScope.FaceIds).Any())
            throw new InvalidOperationException($"Contact region '{Name}' has overlapping source and target faces.");
    }
}

internal sealed class ContactRegionCatalog
{
    private readonly Dictionary<Guid, ContactRegionDefinition> _regions = [];

    public IReadOnlyCollection<ContactRegionDefinition> Regions => _regions.Values;

    public void Add(ContactRegionDefinition region, NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        region.Validate(selections, activeGeometrySignature);
        if (_regions.ContainsKey(region.Id))
            throw new InvalidOperationException($"Contact region '{region.Id}' already exists.");
        if (_regions.Values.Any(item => string.Equals(item.Name, region.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Contact region name '{region.Name}' is already in use.");
        _regions.Add(region.Id, region);
    }

    public ContactRegionDefinition Get(Guid id) =>
        _regions.TryGetValue(id, out var region)
            ? region
            : throw new KeyNotFoundException($"Contact region '{id}' was not found.");
}
