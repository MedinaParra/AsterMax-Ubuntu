namespace AsterMax.MechanicalGui;

internal enum NamedSelectionEntityType
{
    Vertex,
    Edge,
    Face,
    Body,
    MeshNode
}

internal enum NamedSelectionGenerationMode
{
    Manual,
    Worksheet
}

internal enum NamedSelectionCriterionKind
{
    EntityId,
    LocationX,
    LocationY,
    LocationZ,
    Size,
    DistanceFromPoint,
    NormalX,
    NormalY,
    NormalZ
}

internal enum NamedSelectionComparison
{
    Equal,
    NotEqual,
    LessThan,
    LessThanOrEqual,
    GreaterThan,
    GreaterThanOrEqual,
    Between
}

internal enum NamedSelectionBooleanOperator
{
    And,
    Or
}

internal sealed record NamedSelectionCriterion(
    NamedSelectionCriterionKind Kind,
    NamedSelectionComparison Comparison,
    double Value,
    double? UpperValue = null,
    NamedSelectionBooleanOperator Operator = NamedSelectionBooleanOperator.And);

internal sealed class NamedSelectionDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; set; }
    public required NamedSelectionEntityType EntityType { get; init; }
    public required NamedSelectionGenerationMode GenerationMode { get; init; }
    public MechanicalScope ManualScope { get; set; } = MechanicalScope.Empty;
    public List<NamedSelectionCriterion> Criteria { get; } = [];
    public MechanicalScope EvaluatedScope { get; private set; } = MechanicalScope.Empty;
    public string GeometrySignature { get; private set; } = string.Empty;
    public DateTimeOffset EvaluatedAt { get; private set; }

    public void Validate()
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Named selection must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Named selection name cannot be empty.");

        if (GenerationMode == NamedSelectionGenerationMode.Manual)
        {
            if (ManualScope.IsEmpty)
                throw new InvalidOperationException($"Manual named selection '{Name}' has an empty scope.");
            EnsureScopeMatchesEntityType(ManualScope);
            return;
        }

        if (Criteria.Count == 0)
            throw new InvalidOperationException($"Worksheet named selection '{Name}' has no criteria.");

        foreach (var criterion in Criteria)
        {
            if (!double.IsFinite(criterion.Value))
                throw new InvalidOperationException($"Named-selection criterion in '{Name}' contains a non-finite value.");
            if (criterion.Comparison == NamedSelectionComparison.Between)
            {
                if (!criterion.UpperValue.HasValue || !double.IsFinite(criterion.UpperValue.Value))
                    throw new InvalidOperationException($"Between criterion in '{Name}' requires a finite upper value.");
                if (criterion.UpperValue.Value < criterion.Value)
                    throw new InvalidOperationException($"Between criterion in '{Name}' has an upper value below its lower value.");
            }
        }
    }

    public void AcceptEvaluation(MechanicalScope scope, string geometrySignature, DateTimeOffset evaluatedAt)
    {
        if (string.IsNullOrWhiteSpace(geometrySignature))
            throw new ArgumentException("Geometry signature cannot be empty.", nameof(geometrySignature));
        EnsureScopeMatchesEntityType(scope);
        EvaluatedScope = scope;
        GeometrySignature = geometrySignature.Trim();
        EvaluatedAt = evaluatedAt;
    }

    public bool IsCurrentFor(string geometrySignature) =>
        !string.IsNullOrWhiteSpace(GeometrySignature) &&
        string.Equals(GeometrySignature, geometrySignature, StringComparison.Ordinal);

    private void EnsureScopeMatchesEntityType(MechanicalScope scope)
    {
        var selectedCount = EntityType switch
        {
            NamedSelectionEntityType.Vertex => scope.VertexIds.Count,
            NamedSelectionEntityType.Edge => scope.EdgeIds.Count,
            NamedSelectionEntityType.Face => scope.FaceIds.Count,
            NamedSelectionEntityType.Body => scope.BodyIds.Count,
            NamedSelectionEntityType.MeshNode => scope.NodeIds.Count,
            _ => 0
        };

        var totalCount = scope.VertexIds.Count + scope.EdgeIds.Count + scope.FaceIds.Count + scope.BodyIds.Count + scope.NodeIds.Count;
        if (selectedCount == 0 || selectedCount != totalCount)
            throw new InvalidOperationException($"Named selection '{Name}' contains entities outside its declared type {EntityType}.");
    }
}

internal sealed class NamedSelectionCatalog
{
    private readonly Dictionary<Guid, NamedSelectionDefinition> _definitions = [];

    public IReadOnlyCollection<NamedSelectionDefinition> Definitions => _definitions.Values;

    public void Add(NamedSelectionDefinition definition)
    {
        definition.Validate();
        if (_definitions.ContainsKey(definition.Id))
            throw new InvalidOperationException($"Named selection '{definition.Id}' already exists.");
        if (_definitions.Values.Any(item => string.Equals(item.Name, definition.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Named selection name '{definition.Name}' is already in use.");
        _definitions.Add(definition.Id, definition);
    }

    public NamedSelectionDefinition Get(Guid id) =>
        _definitions.TryGetValue(id, out var definition)
            ? definition
            : throw new KeyNotFoundException($"Named selection '{id}' was not found.");

    public MechanicalScope Resolve(Guid id, string activeGeometrySignature)
    {
        var definition = Get(id);
        definition.Validate();
        if (!definition.IsCurrentFor(activeGeometrySignature))
            throw new InvalidOperationException($"Named selection '{definition.Name}' is stale for the active geometry.");
        if (definition.EvaluatedScope.IsEmpty)
            throw new InvalidOperationException($"Named selection '{definition.Name}' evaluates to an empty scope.");
        return definition.EvaluatedScope;
    }
}
