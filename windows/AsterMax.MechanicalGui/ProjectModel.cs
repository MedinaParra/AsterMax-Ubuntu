using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

internal enum ProjectObjectState
{
    Incomplete,
    UpToDate,
    Obsolete,
    Solving,
    Solved,
    Error,
    Suppressed
}

internal enum AnalysisSystemKind
{
    StaticStructural,
    Modal,
    SteadyStateThermal,
    TransientThermal,
    EigenvalueBuckling,
    Submodel
}

internal sealed record ProjectObjectReference(Guid Id, string Kind);

internal abstract record ProjectObject
{
    public Guid Id { get; init; } = Guid.NewGuid();
    public required string Name { get; init; }
    public ProjectObjectState State { get; set; } = ProjectObjectState.Incomplete;
    public bool IsSuppressed { get; set; }
    public List<ProjectObjectReference> DependsOn { get; init; } = [];
}

internal sealed record AnalysisSystemModel : ProjectObject
{
    public required AnalysisSystemKind SystemKind { get; init; }
    public List<ProjectObjectReference> Children { get; init; } = [];
}

internal sealed record NamedSelectionModel : ProjectObject
{
    public required string EntityType { get; init; }
    public List<string> PersistentEntityKeys { get; init; } = [];
}

internal sealed record MaterialModel : ProjectObject
{
    public double YoungModulusMpa { get; init; }
    public double PoissonRatio { get; init; }
    public double DensityKgPerM3 { get; init; }
    public double ThermalConductivityWPerMK { get; init; }
    public double SpecificHeatJPerKgK { get; init; }
    public double ThermalExpansionPerK { get; init; }
}

internal sealed record BoundaryConditionModel : ProjectObject
{
    public required string BoundaryKind { get; init; }
    public Guid? ScopeId { get; init; }
    public Dictionary<string, double> Values { get; init; } = [];
}

internal sealed record ResultRequestModel : ProjectObject
{
    public required string ResultKind { get; init; }
    public Guid? CoordinateSystemId { get; init; }
    public Guid? ScopeId { get; init; }
}

internal sealed record AsterMaxProjectDocument
{
    public const int CurrentSchemaVersion = 1;

    public int SchemaVersion { get; init; } = CurrentSchemaVersion;
    public Guid ProjectId { get; init; } = Guid.NewGuid();
    public string Name { get; set; } = "Untitled";
    public MechanicalUnitSystem UnitSystem { get; set; } = MechanicalUnitSystem.MillimeterNewtonMegapascal;
    public DateTimeOffset CreatedUtc { get; init; } = DateTimeOffset.UtcNow;
    public DateTimeOffset ModifiedUtc { get; set; } = DateTimeOffset.UtcNow;
    public List<AnalysisSystemModel> Systems { get; init; } = [];
    public List<NamedSelectionModel> NamedSelections { get; init; } = [];
    public List<MaterialModel> Materials { get; init; } = [];
    public List<BoundaryConditionModel> BoundaryConditions { get; init; } = [];
    public List<ResultRequestModel> ResultRequests { get; init; } = [];
    public Dictionary<string, string> Metadata { get; init; } = [];

    [JsonIgnore]
    public IEnumerable<ProjectObject> Objects =>
        Systems.Cast<ProjectObject>()
            .Concat(NamedSelections)
            .Concat(Materials)
            .Concat(BoundaryConditions)
            .Concat(ResultRequests);
}
