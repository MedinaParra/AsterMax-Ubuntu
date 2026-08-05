namespace AsterMax.MechanicalGui;

internal enum BeamConnectionType
{
    Fixed,
    Pinned,
    Translational,
    Rotational,
    Generalized
}

[Flags]
internal enum BeamConnectionDegreeOfFreedom
{
    None = 0,
    TranslationX = 1 << 0,
    TranslationY = 1 << 1,
    TranslationZ = 1 << 2,
    RotationX = 1 << 3,
    RotationY = 1 << 4,
    RotationZ = 1 << 5,
    AllTranslations = TranslationX | TranslationY | TranslationZ,
    AllRotations = RotationX | RotationY | RotationZ,
    All = AllTranslations | AllRotations
}

internal sealed record BeamConnectionStiffness(
    double TranslationX,
    double TranslationY,
    double TranslationZ,
    double RotationX,
    double RotationY,
    double RotationZ)
{
    public double For(BeamConnectionDegreeOfFreedom degreeOfFreedom) => degreeOfFreedom switch
    {
        BeamConnectionDegreeOfFreedom.TranslationX => TranslationX,
        BeamConnectionDegreeOfFreedom.TranslationY => TranslationY,
        BeamConnectionDegreeOfFreedom.TranslationZ => TranslationZ,
        BeamConnectionDegreeOfFreedom.RotationX => RotationX,
        BeamConnectionDegreeOfFreedom.RotationY => RotationY,
        BeamConnectionDegreeOfFreedom.RotationZ => RotationZ,
        _ => throw new ArgumentOutOfRangeException(nameof(degreeOfFreedom))
    };

    public void Validate(string connectionName)
    {
        foreach (var value in new[] { TranslationX, TranslationY, TranslationZ, RotationX, RotationY, RotationZ })
        {
            if (!double.IsFinite(value) || value < 0.0)
                throw new InvalidOperationException($"Beam connection '{connectionName}' contains an invalid stiffness value.");
        }
    }
}

internal sealed class BeamConnectionDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid ReferenceSelectionId { get; init; }
    public required Guid MobileSelectionId { get; init; }
    public required BeamConnectionType Type { get; init; }
    public BeamConnectionDegreeOfFreedom ReleasedDegreesOfFreedom { get; init; }
    public BeamConnectionStiffness Stiffness { get; init; } = new(0, 0, 0, 0, 0, 0);
    public double OffsetX { get; init; }
    public double OffsetY { get; init; }
    public double OffsetZ { get; init; }

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Beam connection must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Beam connection name cannot be empty.");
        if (ReferenceSelectionId == Guid.Empty || MobileSelectionId == Guid.Empty)
            throw new InvalidOperationException($"Beam connection '{Name}' requires reference and mobile named selections.");
        if (ReferenceSelectionId == MobileSelectionId)
            throw new InvalidOperationException($"Beam connection '{Name}' cannot use the same named selection at both ends.");
        if ((ReleasedDegreesOfFreedom & ~BeamConnectionDegreeOfFreedom.All) != 0)
            throw new InvalidOperationException($"Beam connection '{Name}' contains unknown released degrees of freedom.");
        if (!double.IsFinite(OffsetX) || !double.IsFinite(OffsetY) || !double.IsFinite(OffsetZ))
            throw new InvalidOperationException($"Beam connection '{Name}' contains a non-finite offset.");

        Stiffness.Validate(Name);
        ValidateTypeSemantics();

        var reference = selections.Get(ReferenceSelectionId);
        var mobile = selections.Get(MobileSelectionId);
        if (!IsBeamEndScope(reference.EntityType) || !IsBeamEndScope(mobile.EntityType))
            throw new InvalidOperationException($"Beam connection '{Name}' requires vertex- or edge-based end selections.");

        var referenceScope = selections.Resolve(ReferenceSelectionId, activeGeometrySignature);
        var mobileScope = selections.Resolve(MobileSelectionId, activeGeometrySignature);
        if (referenceScope.EntityIds.Intersect(mobileScope.EntityIds).Any())
            throw new InvalidOperationException($"Beam connection '{Name}' has overlapping reference and mobile entities.");
    }

    private void ValidateTypeSemantics()
    {
        switch (Type)
        {
            case BeamConnectionType.Fixed when ReleasedDegreesOfFreedom != BeamConnectionDegreeOfFreedom.None:
                throw new InvalidOperationException($"Fixed beam connection '{Name}' cannot release degrees of freedom.");
            case BeamConnectionType.Pinned when ReleasedDegreesOfFreedom != BeamConnectionDegreeOfFreedom.AllRotations:
                throw new InvalidOperationException($"Pinned beam connection '{Name}' must release all rotations and no translations.");
            case BeamConnectionType.Translational when (ReleasedDegreesOfFreedom & BeamConnectionDegreeOfFreedom.AllTranslations) == BeamConnectionDegreeOfFreedom.None:
                throw new InvalidOperationException($"Translational beam connection '{Name}' must release at least one translation.");
            case BeamConnectionType.Rotational when (ReleasedDegreesOfFreedom & BeamConnectionDegreeOfFreedom.AllRotations) == BeamConnectionDegreeOfFreedom.None:
                throw new InvalidOperationException($"Rotational beam connection '{Name}' must release at least one rotation.");
        }

        if (Type != BeamConnectionType.Generalized && HasPositiveStiffness())
            throw new InvalidOperationException($"Beam connection '{Name}' defines stiffness outside the generalized formulation.");

        if (Type == BeamConnectionType.Generalized)
        {
            foreach (var degreeOfFreedom in EnumerateDegreesOfFreedom())
            {
                if (ReleasedDegreesOfFreedom.HasFlag(degreeOfFreedom) && Stiffness.For(degreeOfFreedom) > 0.0)
                    throw new InvalidOperationException($"Beam connection '{Name}' cannot both release and elastically restrain {degreeOfFreedom}.");
            }
        }
    }

    private bool HasPositiveStiffness() => EnumerateDegreesOfFreedom().Any(dof => Stiffness.For(dof) > 0.0);

    private static bool IsBeamEndScope(NamedSelectionEntityType type) =>
        type is NamedSelectionEntityType.Vertex or NamedSelectionEntityType.Edge;

    private static IEnumerable<BeamConnectionDegreeOfFreedom> EnumerateDegreesOfFreedom()
    {
        yield return BeamConnectionDegreeOfFreedom.TranslationX;
        yield return BeamConnectionDegreeOfFreedom.TranslationY;
        yield return BeamConnectionDegreeOfFreedom.TranslationZ;
        yield return BeamConnectionDegreeOfFreedom.RotationX;
        yield return BeamConnectionDegreeOfFreedom.RotationY;
        yield return BeamConnectionDegreeOfFreedom.RotationZ;
    }
}

internal sealed class BeamConnectionCatalog
{
    private readonly Dictionary<Guid, BeamConnectionDefinition> _connections = [];

    public IReadOnlyCollection<BeamConnectionDefinition> Connections => _connections.Values;

    public void Add(BeamConnectionDefinition connection, NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        connection.Validate(selections, activeGeometrySignature);
        if (_connections.ContainsKey(connection.Id))
            throw new InvalidOperationException($"Beam connection '{connection.Id}' already exists.");
        if (_connections.Values.Any(item => string.Equals(item.Name, connection.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Beam connection name '{connection.Name}' is already in use.");
        _connections.Add(connection.Id, connection);
    }

    public BeamConnectionDefinition Get(Guid id) =>
        _connections.TryGetValue(id, out var connection)
            ? connection
            : throw new KeyNotFoundException($"Beam connection '{id}' was not found.");
}
