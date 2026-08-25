namespace AsterMax.MechanicalGui;

internal enum ConstraintTargetKind
{
    MeshNode,
    RemotePoint
}

internal enum ConstraintDegreeOfFreedom
{
    TranslationX,
    TranslationY,
    TranslationZ,
    RotationX,
    RotationY,
    RotationZ
}

internal sealed record ConstraintTermTarget(
    ConstraintTargetKind Kind,
    int? NodeId,
    Guid? ObjectId)
{
    public void Validate(string equationName, ConstraintDegreeOfFreedom degreeOfFreedom)
    {
        if (!Enum.IsDefined(Kind) || !Enum.IsDefined(degreeOfFreedom))
            throw new InvalidOperationException($"Constraint equation '{equationName}' contains an unsupported target or degree of freedom.");

        switch (Kind)
        {
            case ConstraintTargetKind.MeshNode:
                if (!NodeId.HasValue || NodeId.Value <= 0 || ObjectId.HasValue)
                    throw new InvalidOperationException($"Constraint equation '{equationName}' requires a positive mesh-node ID and no object ID for mesh-node terms.");
                if (IsRotation(degreeOfFreedom))
                    throw new InvalidOperationException($"Constraint equation '{equationName}' cannot assign rotational DOFs directly to a solid mesh node.");
                break;

            case ConstraintTargetKind.RemotePoint:
                if (!ObjectId.HasValue || ObjectId.Value == Guid.Empty || NodeId.HasValue)
                    throw new InvalidOperationException($"Constraint equation '{equationName}' requires a stable remote-point object ID and no node ID for remote-point terms.");
                break;
        }
    }

    public string StableKey => Kind switch
    {
        ConstraintTargetKind.MeshNode => $"node:{NodeId}",
        ConstraintTargetKind.RemotePoint => $"remote:{ObjectId:D}",
        _ => "unsupported"
    };

    private static bool IsRotation(ConstraintDegreeOfFreedom dof) =>
        dof is ConstraintDegreeOfFreedom.RotationX or ConstraintDegreeOfFreedom.RotationY or ConstraintDegreeOfFreedom.RotationZ;
}

internal sealed record ConstraintEquationTerm(
    ConstraintTermTarget Target,
    ConstraintDegreeOfFreedom DegreeOfFreedom,
    double Coefficient)
{
    public void Validate(string equationName)
    {
        ArgumentNullException.ThrowIfNull(Target);
        Target.Validate(equationName, DegreeOfFreedom);
        if (!double.IsFinite(Coefficient) || Coefficient == 0.0)
            throw new InvalidOperationException($"Constraint equation '{equationName}' requires finite non-zero term coefficients.");
    }

    public string StableKey => $"{Target.StableKey}:{DegreeOfFreedom}";
}

internal sealed class ConstraintEquationDefinition
{
    public required Guid Id { get; init; }
    public required string Name { get; init; }
    public required IReadOnlyList<ConstraintEquationTerm> Terms { get; init; }
    public double RightHandSide { get; init; }
    public double? MixedDofLengthScale { get; init; }

    public void Validate()
    {
        ArgumentNullException.ThrowIfNull(Terms);

        if (Id == Guid.Empty)
            throw new InvalidOperationException("Constraint equation must have a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Constraint equation name cannot be empty.");
        if (!double.IsFinite(RightHandSide))
            throw new InvalidOperationException($"Constraint equation '{Name}' requires a finite right-hand side.");
        if (Terms.Count < 2)
            throw new InvalidOperationException($"Constraint equation '{Name}' must contain at least two terms.");

        foreach (var term in Terms)
        {
            if (term is null)
                throw new InvalidOperationException($"Constraint equation '{Name}' contains a null term.");
            term.Validate(Name);
        }

        var duplicateTerms = Terms
            .GroupBy(term => term.StableKey, StringComparer.Ordinal)
            .Where(group => group.Count() > 1)
            .Select(group => group.Key)
            .ToArray();
        if (duplicateTerms.Length > 0)
            throw new InvalidOperationException($"Constraint equation '{Name}' contains duplicate target/DOF terms: {string.Join(", ", duplicateTerms)}.");

        var hasTranslation = Terms.Any(term => IsTranslation(term.DegreeOfFreedom));
        var hasRotation = Terms.Any(term => IsRotation(term.DegreeOfFreedom));
        if (hasTranslation && hasRotation)
        {
            if (!MixedDofLengthScale.HasValue ||
                !double.IsFinite(MixedDofLengthScale.Value) ||
                MixedDofLengthScale.Value <= 0.0)
                throw new InvalidOperationException($"Constraint equation '{Name}' mixes translation and rotation and requires a finite positive length scale.");
        }
        else if (MixedDofLengthScale.HasValue)
        {
            throw new InvalidOperationException($"Constraint equation '{Name}' defines a mixed-DOF length scale although all terms have the same dimensional family.");
        }

        var sumMagnitude = Terms.Sum(term => Math.Abs(term.Coefficient));
        if (!double.IsFinite(sumMagnitude) || sumMagnitude <= 0.0)
            throw new InvalidOperationException($"Constraint equation '{Name}' is algebraically empty.");
    }

    public IReadOnlyList<ConstraintEquationTerm> BuildDimensionallyScaledTerms()
    {
        Validate();
        if (!MixedDofLengthScale.HasValue)
            return Terms;

        var scale = MixedDofLengthScale.Value;
        return Terms
            .Select(term => IsRotation(term.DegreeOfFreedom)
                ? term with { Coefficient = term.Coefficient * scale }
                : term)
            .ToArray();
    }

    private static bool IsTranslation(ConstraintDegreeOfFreedom dof) =>
        dof is ConstraintDegreeOfFreedom.TranslationX or ConstraintDegreeOfFreedom.TranslationY or ConstraintDegreeOfFreedom.TranslationZ;

    private static bool IsRotation(ConstraintDegreeOfFreedom dof) =>
        dof is ConstraintDegreeOfFreedom.RotationX or ConstraintDegreeOfFreedom.RotationY or ConstraintDegreeOfFreedom.RotationZ;
}

internal sealed class ConstraintEquationCatalog
{
    private readonly Dictionary<Guid, ConstraintEquationDefinition> _equations = [];

    public IReadOnlyCollection<ConstraintEquationDefinition> Equations => _equations.Values;

    public void Add(ConstraintEquationDefinition equation)
    {
        ArgumentNullException.ThrowIfNull(equation);
        equation.Validate();
        if (_equations.ContainsKey(equation.Id))
            throw new InvalidOperationException($"Constraint equation '{equation.Id}' already exists.");
        if (_equations.Values.Any(item => string.Equals(item.Name, equation.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Constraint equation name '{equation.Name}' is already in use.");
        _equations.Add(equation.Id, equation);
    }

    public ConstraintEquationDefinition Get(Guid id) =>
        _equations.TryGetValue(id, out var equation)
            ? equation
            : throw new KeyNotFoundException($"Constraint equation '{id}' was not found.");
}
