namespace AsterMax.MechanicalGui;

internal enum RemoteBoundaryConditionType
{
    Displacement,
    Force,
    Moment
}

internal enum RemoteCouplingBehavior
{
    Rigid,
    Deformable
}

internal enum RemoteWeightingMethod
{
    Uniform,
    AreaWeighted,
    DistanceWeighted
}

internal readonly record struct RemoteVector3(double X, double Y, double Z)
{
    public bool IsFinite => double.IsFinite(X) && double.IsFinite(Y) && double.IsFinite(Z);
    public double Norm => Math.Sqrt(X * X + Y * Y + Z * Z);
    public static double Dot(RemoteVector3 left, RemoteVector3 right) =>
        left.X * right.X + left.Y * right.Y + left.Z * right.Z;
}

internal sealed record RemoteCoordinateFrame(
    bool UseGlobalAxes,
    RemoteVector3? PrimaryAxis,
    RemoteVector3? SecondaryAxis)
{
    private const double MinimumAxisNorm = 1e-12;
    private const double OrthogonalityTolerance = 1e-6;

    public static RemoteCoordinateFrame Global { get; } = new(true, null, null);

    public void Validate(string name)
    {
        if (UseGlobalAxes)
        {
            if (PrimaryAxis.HasValue || SecondaryAxis.HasValue)
                throw new InvalidOperationException($"Remote boundary condition '{name}' cannot define local axes while using global coordinates.");
            return;
        }

        if (!PrimaryAxis.HasValue || !SecondaryAxis.HasValue)
            throw new InvalidOperationException($"Remote boundary condition '{name}' requires two local coordinate axes.");

        var primary = PrimaryAxis.Value;
        var secondary = SecondaryAxis.Value;
        if (!primary.IsFinite || primary.Norm <= MinimumAxisNorm)
            throw new InvalidOperationException($"Remote boundary condition '{name}' requires a finite non-zero primary axis.");
        if (!secondary.IsFinite || secondary.Norm <= MinimumAxisNorm)
            throw new InvalidOperationException($"Remote boundary condition '{name}' requires a finite non-zero secondary axis.");

        var cosine = RemoteVector3.Dot(primary, secondary) / (primary.Norm * secondary.Norm);
        if (!double.IsFinite(cosine) || Math.Abs(cosine) > OrthogonalityTolerance)
            throw new InvalidOperationException($"Remote boundary condition '{name}' requires orthogonal local axes.");
    }
}

internal sealed record RemoteComponents(
    double? X,
    double? Y,
    double? Z,
    double? RotationX,
    double? RotationY,
    double? RotationZ)
{
    public bool HasTranslation => X.HasValue || Y.HasValue || Z.HasValue;
    public bool HasRotation => RotationX.HasValue || RotationY.HasValue || RotationZ.HasValue;
    public bool HasAny => HasTranslation || HasRotation;

    public void Validate(string name, RemoteBoundaryConditionType type)
    {
        var values = new[] { X, Y, Z, RotationX, RotationY, RotationZ };
        if (values.Where(value => value.HasValue).Any(value => !double.IsFinite(value!.Value)))
            throw new InvalidOperationException($"Remote boundary condition '{name}' contains a non-finite component.");

        if (!HasAny)
            throw new InvalidOperationException($"Remote boundary condition '{name}' must define at least one component.");

        switch (type)
        {
            case RemoteBoundaryConditionType.Displacement:
                return;

            case RemoteBoundaryConditionType.Force:
                if (HasRotation)
                    throw new InvalidOperationException($"Remote force '{name}' cannot define rotational components.");
                if (!HasNonZero(X, Y, Z))
                    throw new InvalidOperationException($"Remote force '{name}' requires at least one non-zero force component.");
                return;

            case RemoteBoundaryConditionType.Moment:
                if (HasTranslation)
                    throw new InvalidOperationException($"Remote moment '{name}' cannot define translational components.");
                if (!HasNonZero(RotationX, RotationY, RotationZ))
                    throw new InvalidOperationException($"Remote moment '{name}' requires at least one non-zero moment component.");
                return;

            default:
                throw new InvalidOperationException($"Remote boundary condition '{name}' contains an unsupported type.");
        }
    }

    private static bool HasNonZero(params double?[] values) =>
        values.Any(value => value.HasValue && value.Value != 0.0);
}

internal sealed record RemoteCouplingDefinition(
    RemoteCouplingBehavior Behavior,
    RemoteWeightingMethod Weighting,
    double? DistanceWeightExponent)
{
    public void Validate(string name)
    {
        if (!Enum.IsDefined(Behavior) || !Enum.IsDefined(Weighting))
            throw new InvalidOperationException($"Remote boundary condition '{name}' contains an unsupported coupling option.");

        if (Behavior == RemoteCouplingBehavior.Rigid && Weighting != RemoteWeightingMethod.Uniform)
            throw new InvalidOperationException($"Rigid remote boundary condition '{name}' must use uniform coupling.");

        if (Weighting == RemoteWeightingMethod.DistanceWeighted)
        {
            if (!DistanceWeightExponent.HasValue ||
                !double.IsFinite(DistanceWeightExponent.Value) ||
                DistanceWeightExponent.Value <= 0.0)
                throw new InvalidOperationException($"Distance-weighted remote boundary condition '{name}' requires a finite positive exponent.");
            return;
        }

        if (DistanceWeightExponent.HasValue)
            throw new InvalidOperationException($"Remote boundary condition '{name}' defines a distance exponent without distance weighting.");
    }
}

internal sealed class RemoteBoundaryConditionDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid ScopeSelectionId { get; init; }
    public required RemoteBoundaryConditionType Type { get; init; }
    public required RemoteVector3 RemotePoint { get; init; }
    public RemoteCoordinateFrame CoordinateFrame { get; init; } = RemoteCoordinateFrame.Global;
    public RemoteCouplingDefinition Coupling { get; init; } =
        new(RemoteCouplingBehavior.Rigid, RemoteWeightingMethod.Uniform, null);
    public required RemoteComponents Components { get; init; }

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(selections);
        ArgumentNullException.ThrowIfNull(CoordinateFrame);
        ArgumentNullException.ThrowIfNull(Coupling);
        ArgumentNullException.ThrowIfNull(Components);

        if (Id == Guid.Empty)
            throw new InvalidOperationException("Remote boundary condition must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Remote boundary condition name cannot be empty.");
        if (ScopeSelectionId == Guid.Empty)
            throw new InvalidOperationException($"Remote boundary condition '{Name}' requires a named selection scope.");
        if (!Enum.IsDefined(Type))
            throw new InvalidOperationException($"Remote boundary condition '{Name}' contains an unsupported type.");
        if (!RemotePoint.IsFinite)
            throw new InvalidOperationException($"Remote boundary condition '{Name}' contains a non-finite remote point.");

        CoordinateFrame.Validate(Name);
        Coupling.Validate(Name);
        Components.Validate(Name, Type);

        var definition = selections.Get(ScopeSelectionId);
        if (definition.EntityType is not (NamedSelectionEntityType.Vertex or
            NamedSelectionEntityType.Edge or
            NamedSelectionEntityType.Face or
            NamedSelectionEntityType.MeshNode))
            throw new InvalidOperationException($"Remote boundary condition '{Name}' requires vertex-, edge-, face- or mesh-node scoping.");

        _ = selections.Resolve(ScopeSelectionId, activeGeometrySignature);
    }
}

internal sealed class RemoteBoundaryConditionCatalog
{
    private readonly Dictionary<Guid, RemoteBoundaryConditionDefinition> _conditions = [];

    public IReadOnlyCollection<RemoteBoundaryConditionDefinition> Conditions => _conditions.Values;

    public void Add(RemoteBoundaryConditionDefinition condition, NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(condition);
        condition.Validate(selections, activeGeometrySignature);
        if (_conditions.ContainsKey(condition.Id))
            throw new InvalidOperationException($"Remote boundary condition '{condition.Id}' already exists.");
        if (_conditions.Values.Any(item => string.Equals(item.Name, condition.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Remote boundary condition name '{condition.Name}' is already in use.");
        _conditions.Add(condition.Id, condition);
    }

    public RemoteBoundaryConditionDefinition Get(Guid id) =>
        _conditions.TryGetValue(id, out var condition)
            ? condition
            : throw new KeyNotFoundException($"Remote boundary condition '{id}' was not found.");
}
