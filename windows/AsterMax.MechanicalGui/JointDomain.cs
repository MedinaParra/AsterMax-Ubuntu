namespace AsterMax.MechanicalGui;

internal enum JointType
{
    Fixed,
    Revolute,
    Cylindrical,
    Translational,
    Universal,
    Spherical,
    Planar
}

[Flags]
internal enum JointDegreeOfFreedom
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

internal readonly record struct JointVector3(double X, double Y, double Z)
{
    public bool IsFinite => double.IsFinite(X) && double.IsFinite(Y) && double.IsFinite(Z);
    public double Norm => Math.Sqrt(X * X + Y * Y + Z * Z);

    public static double Dot(JointVector3 left, JointVector3 right) =>
        left.X * right.X + left.Y * right.Y + left.Z * right.Z;
}

internal sealed record JointAxisFrame(
    JointVector3 Origin,
    JointVector3 PrimaryAxis,
    JointVector3? SecondaryAxis)
{
    private const double MinimumAxisNorm = 1e-12;
    private const double OrthogonalityTolerance = 1e-6;

    public void Validate(string jointName, bool secondaryAxisRequired)
    {
        if (!Origin.IsFinite)
            throw new InvalidOperationException($"Joint '{jointName}' contains a non-finite frame origin.");
        if (!PrimaryAxis.IsFinite || PrimaryAxis.Norm <= MinimumAxisNorm)
            throw new InvalidOperationException($"Joint '{jointName}' requires a finite non-zero primary axis.");

        if (secondaryAxisRequired && !SecondaryAxis.HasValue)
            throw new InvalidOperationException($"Joint '{jointName}' requires a secondary axis for its local frame.");

        if (!SecondaryAxis.HasValue)
            return;

        var secondary = SecondaryAxis.Value;
        if (!secondary.IsFinite || secondary.Norm <= MinimumAxisNorm)
            throw new InvalidOperationException($"Joint '{jointName}' requires a finite non-zero secondary axis.");

        var cosine = JointVector3.Dot(PrimaryAxis, secondary) / (PrimaryAxis.Norm * secondary.Norm);
        if (!double.IsFinite(cosine) || Math.Abs(cosine) > OrthogonalityTolerance)
            throw new InvalidOperationException($"Joint '{jointName}' requires orthogonal primary and secondary axes.");
    }
}

internal sealed record JointDofSetting(
    JointDegreeOfFreedom DegreeOfFreedom,
    double ElasticStiffness,
    double? LowerLimit,
    double? UpperLimit,
    double StopStiffness)
{
    public void Validate(string jointName, JointDegreeOfFreedom mobility)
    {
        if (!IsSingleDegreeOfFreedom(DegreeOfFreedom))
            throw new InvalidOperationException($"Joint '{jointName}' contains an invalid DOF setting.");
        if (!mobility.HasFlag(DegreeOfFreedom))
            throw new InvalidOperationException($"Joint '{jointName}' defines elastic or limit data for constrained DOF {DegreeOfFreedom}.");
        if (!double.IsFinite(ElasticStiffness) || ElasticStiffness < 0.0)
            throw new InvalidOperationException($"Joint '{jointName}' contains invalid elastic stiffness for {DegreeOfFreedom}.");
        if (!double.IsFinite(StopStiffness) || StopStiffness < 0.0)
            throw new InvalidOperationException($"Joint '{jointName}' contains invalid stop stiffness for {DegreeOfFreedom}.");
        if (LowerLimit.HasValue && !double.IsFinite(LowerLimit.Value))
            throw new InvalidOperationException($"Joint '{jointName}' contains a non-finite lower limit for {DegreeOfFreedom}.");
        if (UpperLimit.HasValue && !double.IsFinite(UpperLimit.Value))
            throw new InvalidOperationException($"Joint '{jointName}' contains a non-finite upper limit for {DegreeOfFreedom}.");
        if (LowerLimit.HasValue && UpperLimit.HasValue && LowerLimit.Value >= UpperLimit.Value)
            throw new InvalidOperationException($"Joint '{jointName}' requires lower limit < upper limit for {DegreeOfFreedom}.");

        var hasLimit = LowerLimit.HasValue || UpperLimit.HasValue;
        if (hasLimit && StopStiffness <= 0.0)
            throw new InvalidOperationException($"Joint '{jointName}' requires positive stop stiffness when travel limits are active for {DegreeOfFreedom}.");
        if (!hasLimit && StopStiffness != 0.0)
            throw new InvalidOperationException($"Joint '{jointName}' defines stop stiffness without travel limits for {DegreeOfFreedom}.");
    }

    private static bool IsSingleDegreeOfFreedom(JointDegreeOfFreedom value) =>
        value is JointDegreeOfFreedom.TranslationX or
            JointDegreeOfFreedom.TranslationY or
            JointDegreeOfFreedom.TranslationZ or
            JointDegreeOfFreedom.RotationX or
            JointDegreeOfFreedom.RotationY or
            JointDegreeOfFreedom.RotationZ;
}

internal sealed class JointDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid ReferenceSelectionId { get; init; }
    public required Guid MobileSelectionId { get; init; }
    public required JointType Type { get; init; }
    public required JointDegreeOfFreedom Mobility { get; init; }
    public required JointAxisFrame Frame { get; init; }
    public IReadOnlyList<JointDofSetting> DofSettings { get; init; } = Array.Empty<JointDofSetting>();

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(selections);
        ArgumentNullException.ThrowIfNull(Frame);
        ArgumentNullException.ThrowIfNull(DofSettings);

        if (Id == Guid.Empty)
            throw new InvalidOperationException("Joint must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Joint name cannot be empty.");
        if (ReferenceSelectionId == Guid.Empty || MobileSelectionId == Guid.Empty)
            throw new InvalidOperationException($"Joint '{Name}' requires reference and mobile named selections.");
        if (ReferenceSelectionId == MobileSelectionId)
            throw new InvalidOperationException($"Joint '{Name}' cannot connect a named selection to itself.");
        if (!Enum.IsDefined(Type))
            throw new InvalidOperationException($"Joint '{Name}' contains an unsupported joint type.");
        if ((Mobility & ~JointDegreeOfFreedom.All) != 0)
            throw new InvalidOperationException($"Joint '{Name}' contains unknown mobility degrees of freedom.");

        var expectedMobility = ExpectedMobility(Type);
        if (Mobility != expectedMobility)
            throw new InvalidOperationException($"Joint '{Name}' mobility {Mobility} is incompatible with {Type}; expected {expectedMobility}.");

        var secondaryAxisRequired = Type is JointType.Universal or JointType.Planar;
        Frame.Validate(Name, secondaryAxisRequired);

        var duplicateDofs = DofSettings
            .GroupBy(setting => setting.DegreeOfFreedom)
            .Where(group => group.Count() > 1)
            .Select(group => group.Key)
            .ToArray();
        if (duplicateDofs.Length > 0)
            throw new InvalidOperationException($"Joint '{Name}' defines duplicate DOF settings: {string.Join(", ", duplicateDofs)}.");

        foreach (var setting in DofSettings)
            setting.Validate(Name, Mobility);

        var reference = selections.Get(ReferenceSelectionId);
        var mobile = selections.Get(MobileSelectionId);
        if (!IsJointScope(reference.EntityType) || !IsJointScope(mobile.EntityType))
            throw new InvalidOperationException($"Joint '{Name}' requires vertex-, edge- or face-based named selections.");

        var referenceScope = selections.Resolve(ReferenceSelectionId, activeGeometrySignature);
        var mobileScope = selections.Resolve(MobileSelectionId, activeGeometrySignature);
        if (ScopesOverlap(reference.EntityType, referenceScope, mobile.EntityType, mobileScope))
            throw new InvalidOperationException($"Joint '{Name}' has overlapping reference and mobile entities.");
    }

    public static JointDegreeOfFreedom ExpectedMobility(JointType type) => type switch
    {
        JointType.Fixed => JointDegreeOfFreedom.None,
        JointType.Revolute => JointDegreeOfFreedom.RotationZ,
        JointType.Cylindrical => JointDegreeOfFreedom.TranslationZ | JointDegreeOfFreedom.RotationZ,
        JointType.Translational => JointDegreeOfFreedom.TranslationZ,
        JointType.Universal => JointDegreeOfFreedom.RotationX | JointDegreeOfFreedom.RotationY,
        JointType.Spherical => JointDegreeOfFreedom.AllRotations,
        JointType.Planar => JointDegreeOfFreedom.TranslationX | JointDegreeOfFreedom.TranslationY | JointDegreeOfFreedom.RotationZ,
        _ => throw new ArgumentOutOfRangeException(nameof(type))
    };

    private static bool IsJointScope(NamedSelectionEntityType type) =>
        type is NamedSelectionEntityType.Vertex or NamedSelectionEntityType.Edge or NamedSelectionEntityType.Face;

    private static bool ScopesOverlap(
        NamedSelectionEntityType referenceType,
        MechanicalScope referenceScope,
        NamedSelectionEntityType mobileType,
        MechanicalScope mobileScope)
    {
        if (referenceType != mobileType)
            return false;

        return referenceType switch
        {
            NamedSelectionEntityType.Vertex => referenceScope.VertexIds.Intersect(mobileScope.VertexIds).Any(),
            NamedSelectionEntityType.Edge => referenceScope.EdgeIds.Intersect(mobileScope.EdgeIds).Any(),
            NamedSelectionEntityType.Face => referenceScope.FaceIds.Intersect(mobileScope.FaceIds).Any(),
            _ => false
        };
    }
}

internal sealed class JointCatalog
{
    private readonly Dictionary<Guid, JointDefinition> _joints = [];

    public IReadOnlyCollection<JointDefinition> Joints => _joints.Values;

    public void Add(JointDefinition joint, NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(joint);
        joint.Validate(selections, activeGeometrySignature);
        if (_joints.ContainsKey(joint.Id))
            throw new InvalidOperationException($"Joint '{joint.Id}' already exists.");
        if (_joints.Values.Any(item => string.Equals(item.Name, joint.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Joint name '{joint.Name}' is already in use.");
        _joints.Add(joint.Id, joint);
    }

    public JointDefinition Get(Guid id) =>
        _joints.TryGetValue(id, out var joint)
            ? joint
            : throw new KeyNotFoundException($"Joint '{id}' was not found.");
}
