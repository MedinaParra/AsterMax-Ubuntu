namespace AsterMax.MechanicalGui;

internal sealed record NamedSelectionGeneratorBinding(
    string RowId,
    Guid NamedSelectionId);

internal sealed class NamedSelectionObjectGenerator
{
    private readonly ObjectGeneratorDefinition _definition;
    private readonly IReadOnlyDictionary<string, Guid> _bindings;

    public NamedSelectionObjectGenerator(
        ObjectGeneratorDefinition definition,
        IEnumerable<NamedSelectionGeneratorBinding> bindings)
    {
        _definition = definition ?? throw new ArgumentNullException(nameof(definition));
        var materialized = bindings?.ToArray() ?? throw new ArgumentNullException(nameof(bindings));

        var duplicate = materialized
            .GroupBy(binding => binding.RowId, StringComparer.Ordinal)
            .FirstOrDefault(group => group.Count() > 1);
        if (duplicate is not null)
            throw new InvalidOperationException($"Generator row '{duplicate.Key}' has more than one named-selection binding.");

        _bindings = materialized.ToDictionary(binding => RequireRowId(binding.RowId), binding => RequireSelectionId(binding.NamedSelectionId), StringComparer.Ordinal);

        var generatedRows = _definition.Rows.Select(row => row.StableId).ToHashSet(StringComparer.Ordinal);
        var missingBinding = generatedRows.FirstOrDefault(rowId => !_bindings.ContainsKey(rowId));
        if (missingBinding is not null)
            throw new InvalidOperationException($"Generator row '{missingBinding}' has no named-selection binding.");

        var unknownBinding = _bindings.Keys.FirstOrDefault(rowId => !generatedRows.Contains(rowId));
        if (unknownBinding is not null)
            throw new InvalidOperationException($"Named-selection binding references unknown generator row '{unknownBinding}'.");
    }

    public IReadOnlyList<GeneratedMechanicalObject> Generate(
        NamedSelectionCatalog catalog,
        string activeGeometrySignature)
    {
        ArgumentNullException.ThrowIfNull(catalog);
        if (string.IsNullOrWhiteSpace(activeGeometrySignature))
            throw new ArgumentException("Active geometry signature cannot be empty.", nameof(activeGeometrySignature));

        var generated = _definition.Generate();
        var resolved = new List<GeneratedMechanicalObject>(generated.Count);

        foreach (var item in generated)
        {
            var selectionId = _bindings[item.GeneratorRowId];
            var scope = catalog.Resolve(selectionId, activeGeometrySignature);
            var scopeId = $"named-selection:{selectionId:D}";
            var properties = new Dictionary<string, string>(item.Properties, StringComparer.Ordinal)
            {
                ["namedSelectionId"] = selectionId.ToString("D"),
                ["resolvedEntityCount"] = CountEntities(scope).ToString(System.Globalization.CultureInfo.InvariantCulture),
                ["geometrySignature"] = activeGeometrySignature.Trim()
            };

            resolved.Add(item with { ScopeId = scopeId, Properties = properties });
        }

        return resolved;
    }

    private static int CountEntities(MechanicalScope scope) =>
        scope.VertexIds.Count + scope.EdgeIds.Count + scope.FaceIds.Count + scope.BodyIds.Count + scope.NodeIds.Count;

    private static string RequireRowId(string rowId)
    {
        if (string.IsNullOrWhiteSpace(rowId) || rowId.Any(char.IsWhiteSpace))
            throw new ArgumentException("A generator row identifier must be non-empty and contain no whitespace.", nameof(rowId));
        return rowId;
    }

    private static Guid RequireSelectionId(Guid id)
    {
        if (id == Guid.Empty)
            throw new ArgumentException("Named-selection identifier cannot be empty.", nameof(id));
        return id;
    }
}
