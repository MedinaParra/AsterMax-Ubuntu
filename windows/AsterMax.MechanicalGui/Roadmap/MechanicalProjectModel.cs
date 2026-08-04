namespace AsterMax.MechanicalGui.Roadmap;

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
    InchPoundPsi
}

internal sealed record MechanicalProjectIdentity(Guid Id, string Name, int SchemaVersion);

internal sealed class MechanicalProjectModel
{
    public const int CurrentSchemaVersion = 1;

    public MechanicalProjectIdentity Identity { get; init; } =
        new(Guid.NewGuid(), "Untitled", CurrentSchemaVersion);

    public MechanicalUnitSystem UnitSystem { get; set; } =
        MechanicalUnitSystem.MillimeterNewtonMegapascal;

    public List<MechanicalAnalysisSystem> Systems { get; } = [];

    public DateTimeOffset CreatedUtc { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset ModifiedUtc { get; set; } = DateTimeOffset.UtcNow;

    public void Touch() => ModifiedUtc = DateTimeOffset.UtcNow;
}

internal sealed class MechanicalAnalysisSystem
{
    public Guid Id { get; init; } = Guid.NewGuid();
    public string Name { get; set; } = "Static Structural";
    public string AnalysisType { get; set; } = "StaticStructural";
    public MechanicalObjectState State { get; set; } = MechanicalObjectState.Incomplete;
    public List<MechanicalTreeObject> Objects { get; } = [];
}

internal sealed class MechanicalTreeObject
{
    public Guid Id { get; init; } = Guid.NewGuid();
    public Guid? ParentId { get; set; }
    public string Kind { get; set; } = "Object";
    public string Name { get; set; } = "Object";
    public MechanicalObjectState State { get; set; } = MechanicalObjectState.Incomplete;
    public bool IsSuppressed { get; set; }
    public Dictionary<string, string> Properties { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> ScopeTokens { get; } = [];
}
