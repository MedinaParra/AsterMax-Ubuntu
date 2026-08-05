namespace AsterMax.MechanicalGui;

internal enum DesignPointParameterRole
{
    Input,
    Output
}

internal sealed record DesignPointParameterDefinition(
    Guid Id,
    string Name,
    string Unit,
    DesignPointParameterRole Role)
{
    public void Validate()
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Design-point parameter must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Design-point parameter name cannot be empty.");
        if (string.IsNullOrWhiteSpace(Unit))
            throw new InvalidOperationException($"Design-point parameter '{Name}' must define a unit.");
        if (!Enum.IsDefined(Role))
            throw new InvalidOperationException($"Design-point parameter '{Name}' has an unsupported role.");
    }
}

internal sealed record DesignPointValue(Guid ParameterId, double Value)
{
    public void Validate(string pointName)
    {
        if (ParameterId == Guid.Empty)
            throw new InvalidOperationException($"Design point '{pointName}' contains an invalid parameter identifier.");
        if (!double.IsFinite(Value))
            throw new InvalidOperationException($"Design point '{pointName}' contains a non-finite parameter value.");
    }
}

internal sealed class DesignPoint
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required int Sequence { get; init; }
    public IReadOnlyList<DesignPointValue> Values { get; init; } = [];

    public void Validate(IReadOnlyDictionary<Guid, DesignPointParameterDefinition> parameters)
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Design point must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Design point name cannot be empty.");
        if (Sequence < 1)
            throw new InvalidOperationException($"Design point '{Name}' must have a positive sequence.");
        if (Values.Count == 0)
            throw new InvalidOperationException($"Design point '{Name}' must contain parameter values.");

        var ids = new HashSet<Guid>();
        foreach (var value in Values)
        {
            value.Validate(Name);
            if (!ids.Add(value.ParameterId))
                throw new InvalidOperationException($"Design point '{Name}' contains duplicate parameter values.");
            if (!parameters.ContainsKey(value.ParameterId))
                throw new InvalidOperationException($"Design point '{Name}' references unknown parameter '{value.ParameterId}'.");
        }

        foreach (var input in parameters.Values.Where(parameter => parameter.Role == DesignPointParameterRole.Input))
        {
            if (!ids.Contains(input.Id))
                throw new InvalidOperationException($"Design point '{Name}' is missing required input parameter '{input.Name}'.");
        }
    }
}

internal sealed class DesignPointStudy
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required Guid AnalysisId { get; init; }
    public IReadOnlyList<DesignPointParameterDefinition> Parameters { get; init; } = [];
    public IReadOnlyList<DesignPoint> Points { get; init; } = [];

    public void Validate()
    {
        if (Id == Guid.Empty)
            throw new InvalidOperationException("Design-point study must have a stable identifier.");
        if (AnalysisId == Guid.Empty)
            throw new InvalidOperationException($"Design-point study '{Name}' must reference an analysis.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Design-point study name cannot be empty.");
        if (Parameters.Count == 0)
            throw new InvalidOperationException($"Design-point study '{Name}' requires parameters.");
        if (Points.Count == 0)
            throw new InvalidOperationException($"Design-point study '{Name}' requires at least one point.");

        var parameters = new Dictionary<Guid, DesignPointParameterDefinition>();
        var parameterNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var parameter in Parameters)
        {
            parameter.Validate();
            if (!parameters.TryAdd(parameter.Id, parameter))
                throw new InvalidOperationException($"Design-point study '{Name}' contains duplicate parameter identifiers.");
            if (!parameterNames.Add(parameter.Name))
                throw new InvalidOperationException($"Design-point study '{Name}' contains duplicate parameter names.");
        }

        if (!Parameters.Any(parameter => parameter.Role == DesignPointParameterRole.Input))
            throw new InvalidOperationException($"Design-point study '{Name}' requires at least one input parameter.");
        if (!Parameters.Any(parameter => parameter.Role == DesignPointParameterRole.Output))
            throw new InvalidOperationException($"Design-point study '{Name}' requires at least one output parameter.");

        var pointIds = new HashSet<Guid>();
        var pointNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var sequences = new HashSet<int>();
        foreach (var point in Points)
        {
            point.Validate(parameters);
            if (!pointIds.Add(point.Id))
                throw new InvalidOperationException($"Design-point study '{Name}' contains duplicate point identifiers.");
            if (!pointNames.Add(point.Name))
                throw new InvalidOperationException($"Design-point study '{Name}' contains duplicate point names.");
            if (!sequences.Add(point.Sequence))
                throw new InvalidOperationException($"Design-point study '{Name}' contains duplicate point sequences.");
        }
    }
}

internal sealed class DesignPointCatalog
{
    private readonly Dictionary<Guid, DesignPointStudy> _studies = [];

    public IReadOnlyCollection<DesignPointStudy> Studies => _studies.Values;

    public void Add(DesignPointStudy study)
    {
        study.Validate();
        if (_studies.ContainsKey(study.Id))
            throw new InvalidOperationException($"Design-point study '{study.Id}' already exists.");
        if (_studies.Values.Any(item => string.Equals(item.Name, study.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Design-point study name '{study.Name}' is already in use.");
        _studies.Add(study.Id, study);
    }

    public DesignPointStudy Get(Guid id) =>
        _studies.TryGetValue(id, out var study)
            ? study
            : throw new KeyNotFoundException($"Design-point study '{id}' was not found.");
}
