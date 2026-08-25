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

internal enum ContactInitialGapTreatment
{
    Preserve,
    UserDefinedOffset,
    AdjustToTouch
}

internal sealed record ContactOffsetControl(
    ContactInitialGapTreatment Treatment,
    double? OffsetDistance,
    double? MaximumInitialAdjustment,
    double? PenetrationTolerance)
{
    public static ContactOffsetControl None { get; } =
        new(ContactInitialGapTreatment.Preserve, null, null, null);

    public void Validate(string contactName, double? pinballRadius)
    {
        if (!Enum.IsDefined(Treatment))
            throw new InvalidOperationException($"Contact region '{contactName}' contains an unsupported initial-gap treatment.");

        if (PenetrationTolerance.HasValue &&
            (!double.IsFinite(PenetrationTolerance.Value) || PenetrationTolerance.Value <= 0.0))
            throw new InvalidOperationException($"Contact region '{contactName}' requires a finite positive penetration tolerance.");

        switch (Treatment)
        {
            case ContactInitialGapTreatment.Preserve:
                if (OffsetDistance.HasValue || MaximumInitialAdjustment.HasValue)
                    throw new InvalidOperationException($"Contact region '{contactName}' cannot define offset or adjustment while preserving the initial gap.");
                break;

            case ContactInitialGapTreatment.UserDefinedOffset:
                if (!OffsetDistance.HasValue || !double.IsFinite(OffsetDistance.Value) || OffsetDistance.Value == 0.0)
                    throw new InvalidOperationException($"Contact region '{contactName}' requires a finite non-zero user-defined contact offset.");
                if (MaximumInitialAdjustment.HasValue)
                    throw new InvalidOperationException($"Contact region '{contactName}' cannot combine a user-defined offset with automatic initial adjustment.");
                if (pinballRadius.HasValue && Math.Abs(OffsetDistance.Value) > pinballRadius.Value)
                    throw new InvalidOperationException($"Contact region '{contactName}' defines an offset outside the contact pinball radius.");
                break;

            case ContactInitialGapTreatment.AdjustToTouch:
                if (OffsetDistance.HasValue)
                    throw new InvalidOperationException($"Contact region '{contactName}' cannot combine AdjustToTouch with a user-defined offset.");
                if (!MaximumInitialAdjustment.HasValue ||
                    !double.IsFinite(MaximumInitialAdjustment.Value) ||
                    MaximumInitialAdjustment.Value <= 0.0)
                    throw new InvalidOperationException($"Contact region '{contactName}' requires a finite positive maximum initial adjustment.");
                if (pinballRadius.HasValue && MaximumInitialAdjustment.Value > pinballRadius.Value)
                    throw new InvalidOperationException($"Contact region '{contactName}' allows initial adjustment beyond the contact pinball radius.");
                break;
        }
    }
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
    public ContactOffsetControl OffsetControl { get; init; } = ContactOffsetControl.None;

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(selections);

        if (Id == Guid.Empty)
            throw new InvalidOperationException("Contact region must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Contact region name cannot be empty.");
        if (SourceSelectionId == Guid.Empty || TargetSelectionId == Guid.Empty)
            throw new InvalidOperationException($"Contact region '{Name}' requires source and target named selections.");
        if (SourceSelectionId == TargetSelectionId)
            throw new InvalidOperationException($"Contact region '{Name}' cannot use the same named selection for source and target.");
        if (!Enum.IsDefined(Formulation) || !Enum.IsDefined(DetectionMethod) || !Enum.IsDefined(Behavior))
            throw new InvalidOperationException($"Contact region '{Name}' contains an unsupported contact option.");
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
        if (OffsetControl is null)
            throw new InvalidOperationException($"Contact region '{Name}' requires a contact offset control definition.");

        OffsetControl.Validate(Name, PinballRadius);

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
        ArgumentNullException.ThrowIfNull(region);
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
