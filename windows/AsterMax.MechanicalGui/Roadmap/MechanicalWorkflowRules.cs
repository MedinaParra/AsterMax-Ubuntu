namespace AsterMax.MechanicalGui.Roadmap;

internal static class MechanicalWorkflowRules
{
    private static readonly IReadOnlyDictionary<string, string[]> RequiredProperties =
        new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
        {
            ["Geometry"] = ["Source"],
            ["Material"] = ["YoungModulus", "PoissonRatio"],
            ["Mesh"] = ["ElementSize"],
            ["FixedSupport"] = ["Scope"],
            ["Force"] = ["Scope", "X", "Y", "Z"],
            ["Pressure"] = ["Scope", "Magnitude"],
            ["Solution"] = ["Backend"]
        };

    public static MechanicalObjectState Evaluate(MechanicalTreeObject item)
    {
        if (item.IsSuppressed) return MechanicalObjectState.Suppressed;
        if (!RequiredProperties.TryGetValue(item.Kind, out var required))
            return item.State == MechanicalObjectState.Error
                ? MechanicalObjectState.Error
                : MechanicalObjectState.UpToDate;

        foreach (var key in required)
        {
            var present = key.Equals("Scope", StringComparison.OrdinalIgnoreCase)
                ? item.ScopeTokens.Count > 0
                : item.Properties.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value);
            if (!present) return MechanicalObjectState.Incomplete;
        }

        return item.State is MechanicalObjectState.Solving or MechanicalObjectState.Solved
            ? item.State
            : MechanicalObjectState.UpToDate;
    }

    public static void MarkDependentsObsolete(MechanicalAnalysisSystem system, Guid changedObjectId)
    {
        var index = system.Objects.FindIndex(item => item.Id == changedObjectId);
        if (index < 0) return;

        for (var i = index + 1; i < system.Objects.Count; i++)
        {
            if (system.Objects[i].IsSuppressed) continue;
            system.Objects[i].State = MechanicalObjectState.Obsolete;
        }
        system.State = MechanicalObjectState.Obsolete;
    }

    public static IReadOnlyList<string> ValidateForSolve(MechanicalAnalysisSystem system)
    {
        var errors = new List<string>();
        foreach (var item in system.Objects)
        {
            var state = Evaluate(item);
            item.State = state;
            if (state == MechanicalObjectState.Incomplete)
                errors.Add($"{item.Name} ({item.Kind}) is incomplete.");
        }

        if (!system.Objects.Any(item => item.Kind.Equals("Geometry", StringComparison.OrdinalIgnoreCase) && !item.IsSuppressed))
            errors.Add("The analysis has no active geometry.");
        if (!system.Objects.Any(item => item.Kind.Equals("Mesh", StringComparison.OrdinalIgnoreCase) && !item.IsSuppressed))
            errors.Add("The analysis has no active mesh.");
        if (!system.Objects.Any(item => item.Kind.EndsWith("Support", StringComparison.OrdinalIgnoreCase) && !item.IsSuppressed))
            errors.Add("The analysis has no active support.");
        if (!system.Objects.Any(item => item.Kind is "Force" or "Pressure" && !item.IsSuppressed))
            errors.Add("The analysis has no active structural load.");

        system.State = errors.Count == 0 ? MechanicalObjectState.UpToDate : MechanicalObjectState.Incomplete;
        return errors;
    }
}
