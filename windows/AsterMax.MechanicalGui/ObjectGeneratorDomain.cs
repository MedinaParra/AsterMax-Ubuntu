namespace AsterMax.MechanicalGui;

public enum GeneratedObjectKind
{
    MaterialAssignment,
    MeshControl,
    FixedSupport,
    DisplacementSupport,
    Force,
    Pressure,
    ResultProbe
}

public enum GeneratorValueType
{
    Text,
    Number,
    Boolean,
    Identifier
}

public sealed record ObjectGeneratorColumn(
    string Key,
    string DisplayName,
    GeneratorValueType ValueType,
    bool Required,
    string? Unit = null);

public sealed record ObjectGeneratorRow(
    string StableId,
    IReadOnlyDictionary<string, string> Values);

public sealed record GeneratedMechanicalObject(
    string StableId,
    GeneratedObjectKind Kind,
    string Name,
    string ScopeId,
    IReadOnlyDictionary<string, string> Properties,
    string GeneratorRowId);

public sealed class ObjectGeneratorDefinition
{
    public ObjectGeneratorDefinition(
        string stableId,
        string name,
        GeneratedObjectKind objectKind,
        IEnumerable<ObjectGeneratorColumn> columns,
        IEnumerable<ObjectGeneratorRow> rows)
    {
        StableId = RequireIdentifier(stableId, nameof(stableId));
        Name = RequireText(name, nameof(name));
        ObjectKind = objectKind;
        Columns = columns?.ToArray() ?? throw new ArgumentNullException(nameof(columns));
        Rows = rows?.ToArray() ?? throw new ArgumentNullException(nameof(rows));
        Validate();
    }

    public string StableId { get; }
    public string Name { get; }
    public GeneratedObjectKind ObjectKind { get; }
    public IReadOnlyList<ObjectGeneratorColumn> Columns { get; }
    public IReadOnlyList<ObjectGeneratorRow> Rows { get; }

    public IReadOnlyList<GeneratedMechanicalObject> Generate()
    {
        var generated = new List<GeneratedMechanicalObject>(Rows.Count);
        foreach (var row in Rows)
        {
            var name = row.Values["name"].Trim();
            var scopeId = row.Values["scopeId"].Trim();
            var properties = row.Values
                .Where(pair => pair.Key is not "name" and not "scopeId")
                .ToDictionary(pair => pair.Key, pair => pair.Value, StringComparer.Ordinal);

            generated.Add(new GeneratedMechanicalObject(
                $"{StableId}:{row.StableId}",
                ObjectKind,
                name,
                scopeId,
                properties,
                row.StableId));
        }

        return generated;
    }

    private void Validate()
    {
        if (Columns.Count == 0)
        {
            throw new InvalidOperationException("An object generator requires at least one column.");
        }

        var duplicateColumn = Columns
            .GroupBy(column => column.Key, StringComparer.Ordinal)
            .FirstOrDefault(group => group.Count() > 1);
        if (duplicateColumn is not null)
        {
            throw new InvalidOperationException($"Duplicate generator column '{duplicateColumn.Key}'.");
        }

        var columnMap = Columns.ToDictionary(column => column.Key, StringComparer.Ordinal);
        if (!columnMap.ContainsKey("name") || !columnMap.ContainsKey("scopeId"))
        {
            throw new InvalidOperationException("Object generators require 'name' and 'scopeId' columns.");
        }

        var duplicateRow = Rows
            .GroupBy(row => row.StableId, StringComparer.Ordinal)
            .FirstOrDefault(group => group.Count() > 1);
        if (duplicateRow is not null)
        {
            throw new InvalidOperationException($"Duplicate generator row '{duplicateRow.Key}'.");
        }

        foreach (var row in Rows)
        {
            RequireIdentifier(row.StableId, nameof(row.StableId));

            foreach (var key in row.Values.Keys)
            {
                if (!columnMap.ContainsKey(key))
                {
                    throw new InvalidOperationException($"Row '{row.StableId}' contains unknown column '{key}'.");
                }
            }

            foreach (var column in Columns.Where(column => column.Required))
            {
                if (!row.Values.TryGetValue(column.Key, out var value) || string.IsNullOrWhiteSpace(value))
                {
                    throw new InvalidOperationException($"Row '{row.StableId}' is missing required value '{column.Key}'.");
                }
            }

            foreach (var column in Columns)
            {
                if (!row.Values.TryGetValue(column.Key, out var value) || string.IsNullOrWhiteSpace(value))
                {
                    continue;
                }

                ValidateValue(row.StableId, column, value);
            }
        }
    }

    private static void ValidateValue(string rowId, ObjectGeneratorColumn column, string value)
    {
        switch (column.ValueType)
        {
            case GeneratorValueType.Number:
                if (!double.TryParse(value, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var numeric) || !double.IsFinite(numeric))
                {
                    throw new InvalidOperationException($"Row '{rowId}' has invalid finite number in '{column.Key}'.");
                }
                break;
            case GeneratorValueType.Boolean:
                if (!bool.TryParse(value, out _))
                {
                    throw new InvalidOperationException($"Row '{rowId}' has invalid Boolean in '{column.Key}'.");
                }
                break;
            case GeneratorValueType.Identifier:
                RequireIdentifier(value, column.Key);
                break;
            case GeneratorValueType.Text:
                RequireText(value, column.Key);
                break;
            default:
                throw new ArgumentOutOfRangeException(nameof(column.ValueType));
        }
    }

    private static string RequireIdentifier(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Any(char.IsWhiteSpace))
        {
            throw new ArgumentException("A stable identifier must be non-empty and contain no whitespace.", parameterName);
        }

        return value;
    }

    private static string RequireText(string value, string parameterName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("A non-empty value is required.", parameterName);
        }

        return value.Trim();
    }
}
