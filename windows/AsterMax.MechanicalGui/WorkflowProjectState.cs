namespace AsterMax.MechanicalGui;

internal enum WorkflowObjectState
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

internal enum MechanicalAnalysisKind
{
    StaticStructural,
    Modal,
    SteadyStateThermal,
    TransientThermal,
    EigenvalueBuckling,
    Submodel
}

internal sealed record WorkflowScope(
    IReadOnlyList<int> VertexIds,
    IReadOnlyList<int> EdgeIds,
    IReadOnlyList<int> FaceIds,
    IReadOnlyList<int> BodyIds,
    IReadOnlyList<int> NodeIds)
{
    public static WorkflowScope Empty { get; } = new([], [], [], [], []);

    public bool IsEmpty =>
        VertexIds.Count == 0 &&
        EdgeIds.Count == 0 &&
        FaceIds.Count == 0 &&
        BodyIds.Count == 0 &&
        NodeIds.Count == 0;
}

internal sealed record WorkflowObjectSnapshot(
    Guid Id,
    Guid? ParentId,
    string ObjectType,
    string Name,
    WorkflowObjectState State,
    bool IsSuppressed,
    WorkflowScope Scope,
    IReadOnlyDictionary<string, string> Properties);

internal sealed record AnalysisSystemSnapshot(
    Guid Id,
    string Name,
    MechanicalAnalysisKind Kind,
    WorkflowObjectState State,
    IReadOnlyList<WorkflowObjectSnapshot> Objects);

internal sealed record MechanicalProjectSnapshot(
    int SchemaVersion,
    string ApplicationVersion,
    string ProjectName,
    MechanicalUnitSystem UnitSystem,
    DateTimeOffset ModifiedUtc,
    IReadOnlyList<AnalysisSystemSnapshot> AnalysisSystems)
{
    public const int CurrentSchemaVersion = 1;

    public static MechanicalProjectSnapshot CreateEmpty(string projectName, string applicationVersion) =>
        new(
            CurrentSchemaVersion,
            applicationVersion,
            projectName,
            MechanicalUnitSystem.MillimeterNewtonMegapascal,
            DateTimeOffset.UtcNow,
            []);
}
