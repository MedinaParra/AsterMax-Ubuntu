namespace AsterMax.MechanicalGui;

internal enum ProjectObjectState
{
    Incomplete,
    UpToDate,
    OutOfDate,
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

internal sealed record UnitSystemDefinition(
    MechanicalUnitSystem Id,
    string LengthSymbol,
    string ForceSymbol,
    string StressSymbol,
    double LengthToMillimeter,
    double ForceToNewton,
    double StressToMegapascal)
{
    public static UnitSystemDefinition From(MechanicalUnitSystem system) => system switch
    {
        MechanicalUnitSystem.MillimeterNewtonMegapascal =>
            new(system, "mm", "N", "MPa", 1.0, 1.0, 1.0),
        MechanicalUnitSystem.MeterNewtonPascal =>
            new(system, "m", "N", "Pa", 1000.0, 1.0, 1e-6),
        MechanicalUnitSystem.InchPoundForcePsi =>
            new(system, "in", "lbf", "psi", 25.4, 4.4482216152605, 0.006894757293168),
        _ => throw new ArgumentOutOfRangeException(nameof(system), system, null)
    };
}

internal abstract class ProjectWorkflowObject
{
    protected ProjectWorkflowObject(string name)
    {
        Id = Guid.NewGuid();
        Name = string.IsNullOrWhiteSpace(name) ? GetType().Name : name.Trim();
    }

    public Guid Id { get; init; }
    public string Name { get; set; }
    public ProjectObjectState State { get; private set; } = ProjectObjectState.Incomplete;
    public bool IsSuppressed => State == ProjectObjectState.Suppressed;

    public void MarkUpToDate() => State = ProjectObjectState.UpToDate;
    public void MarkOutOfDate() => State = ProjectObjectState.OutOfDate;
    public void MarkSolving() => State = ProjectObjectState.Solving;
    public void MarkSolved() => State = ProjectObjectState.Solved;
    public void MarkError() => State = ProjectObjectState.Error;
    public void Suppress() => State = ProjectObjectState.Suppressed;
    public void Unsuppress() => State = ProjectObjectState.OutOfDate;
}

internal sealed class MechanicalProjectState
{
    private readonly List<ProjectWorkflowObject> _objects = [];

    public Guid ProjectId { get; init; } = Guid.NewGuid();
    public string Name { get; set; } = "Untitled";
    public MechanicalUnitSystem UnitSystem { get; set; } = MechanicalUnitSystem.MillimeterNewtonMegapascal;
    public int SchemaVersion { get; init; } = 1;
    public IReadOnlyList<ProjectWorkflowObject> Objects => _objects;

    public void Add(ProjectWorkflowObject item)
    {
        ArgumentNullException.ThrowIfNull(item);
        if (_objects.Any(existing => existing.Id == item.Id))
            throw new InvalidOperationException($"Project object '{item.Id}' already exists.");
        _objects.Add(item);
    }

    public bool Remove(Guid id)
    {
        var item = _objects.FirstOrDefault(candidate => candidate.Id == id);
        return item is not null && _objects.Remove(item);
    }

    public void MarkDependentsOutOfDate(Guid sourceId)
    {
        foreach (var item in _objects.Where(item => item.Id != sourceId && !item.IsSuppressed))
            item.MarkOutOfDate();
    }
}
