namespace AsterMax.MechanicalGui;

internal enum MeshConvergenceQuantity
{
    TotalDeformation,
    EquivalentStress,
    MaximumPrincipalStress,
    StrainEnergy,
    ReactionForce
}

internal enum MeshConvergenceRefinementMode
{
    GlobalElementSize,
    ScopedElementSize,
    Adaptive
}

internal sealed record MeshConvergencePoint(
    int Sequence,
    double CharacteristicElementSize,
    long NodeCount,
    long ElementCount,
    double ResultValue)
{
    public void Validate(string studyName)
    {
        if (Sequence < 1)
            throw new InvalidOperationException($"Mesh convergence study '{studyName}' contains an invalid sequence number.");
        if (!double.IsFinite(CharacteristicElementSize) || CharacteristicElementSize <= 0.0)
            throw new InvalidOperationException($"Mesh convergence study '{studyName}' contains an invalid element size.");
        if (NodeCount < 1 || ElementCount < 1)
            throw new InvalidOperationException($"Mesh convergence study '{studyName}' requires positive node and element counts.");
        if (!double.IsFinite(ResultValue))
            throw new InvalidOperationException($"Mesh convergence study '{studyName}' contains a non-finite result value.");
    }
}

internal sealed class MeshConvergenceStudy
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid AnalysisId { get; init; }
    public required MeshConvergenceQuantity Quantity { get; init; }
    public required MeshConvergenceRefinementMode RefinementMode { get; init; }
    public Guid? ScopeSelectionId { get; init; }
    public double RelativeTolerance { get; init; } = 0.05;
    public int RequiredConsecutivePasses { get; init; } = 2;
    public IReadOnlyList<MeshConvergencePoint> Points { get; init; } = [];

    public void Validate(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Mesh convergence study must have a stable identifier.");
        if (AnalysisId == Guid.Empty)
            throw new InvalidOperationException($"Mesh convergence study '{Name}' must reference an analysis.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Mesh convergence study name cannot be empty.");
        if (!Enum.IsDefined(Quantity) || !Enum.IsDefined(RefinementMode))
            throw new InvalidOperationException($"Mesh convergence study '{Name}' contains an unsupported mode.");
        if (!double.IsFinite(RelativeTolerance) || RelativeTolerance <= 0.0 || RelativeTolerance >= 1.0)
            throw new InvalidOperationException($"Mesh convergence study '{Name}' requires a relative tolerance between zero and one.");
        if (RequiredConsecutivePasses < 1)
            throw new InvalidOperationException($"Mesh convergence study '{Name}' requires at least one consecutive pass.");
        if (Points.Count < 2)
            throw new InvalidOperationException($"Mesh convergence study '{Name}' requires at least two refinement points.");

        ValidateScope(selections, activeGeometrySignature);
        ValidatePoints();
    }

    public bool IsConverged()
    {
        var ordered = Points.OrderBy(point => point.Sequence).ToArray();
        var passes = 0;
        for (var index = 1; index < ordered.Length; index++)
        {
            var previous = ordered[index - 1].ResultValue;
            var current = ordered[index].ResultValue;
            var denominator = Math.Max(Math.Abs(current), 1e-12);
            var relativeChange = Math.Abs(current - previous) / denominator;
            passes = relativeChange <= RelativeTolerance ? passes + 1 : 0;
        }

        return passes >= RequiredConsecutivePasses;
    }

    private void ValidateScope(NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        if (RefinementMode == MeshConvergenceRefinementMode.GlobalElementSize)
        {
            if (ScopeSelectionId.HasValue)
                throw new InvalidOperationException($"Global mesh convergence study '{Name}' cannot define a scoped selection.");
            return;
        }

        if (!ScopeSelectionId.HasValue || ScopeSelectionId.Value == Guid.Empty)
            throw new InvalidOperationException($"Mesh convergence study '{Name}' requires a named-selection scope.");

        var selection = selections.Get(ScopeSelectionId.Value);
        if (selection.EntityType is not (NamedSelectionEntityType.Edge or NamedSelectionEntityType.Face or NamedSelectionEntityType.Body))
            throw new InvalidOperationException($"Mesh convergence study '{Name}' requires an edge, face or body selection.");
        selections.Resolve(ScopeSelectionId.Value, activeGeometrySignature);
    }

    private void ValidatePoints()
    {
        var sequences = new HashSet<int>();
        var ordered = Points.OrderBy(point => point.Sequence).ToArray();
        foreach (var point in ordered)
        {
            point.Validate(Name);
            if (!sequences.Add(point.Sequence))
                throw new InvalidOperationException($"Mesh convergence study '{Name}' contains duplicate sequence values.");
        }

        for (var index = 1; index < ordered.Length; index++)
        {
            if (ordered[index].CharacteristicElementSize >= ordered[index - 1].CharacteristicElementSize)
                throw new InvalidOperationException($"Mesh convergence study '{Name}' must reduce element size at every refinement step.");
            if (ordered[index].NodeCount <= ordered[index - 1].NodeCount || ordered[index].ElementCount <= ordered[index - 1].ElementCount)
                throw new InvalidOperationException($"Mesh convergence study '{Name}' must increase node and element counts at every refinement step.");
        }
    }
}

internal sealed class MeshConvergenceCatalog
{
    private readonly Dictionary<Guid, MeshConvergenceStudy> _studies = [];

    public IReadOnlyCollection<MeshConvergenceStudy> Studies => _studies.Values;

    public void Add(MeshConvergenceStudy study, NamedSelectionCatalog selections, string activeGeometrySignature)
    {
        study.Validate(selections, activeGeometrySignature);
        if (_studies.ContainsKey(study.Id))
            throw new InvalidOperationException($"Mesh convergence study '{study.Id}' already exists.");
        if (_studies.Values.Any(item => string.Equals(item.Name, study.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Mesh convergence study name '{study.Name}' is already in use.");
        _studies.Add(study.Id, study);
    }

    public MeshConvergenceStudy Get(Guid id) =>
        _studies.TryGetValue(id, out var study)
            ? study
            : throw new KeyNotFoundException($"Mesh convergence study '{id}' was not found.");
}
