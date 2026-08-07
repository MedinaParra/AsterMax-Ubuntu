namespace AsterMax.MechanicalGui;

internal enum TwoDimensionalFormulation
{
    PlaneStress,
    PlaneStrain,
    Axisymmetric
}

internal enum PlanarBodyRole
{
    Flexible,
    Rigid,
    Suppressed
}

internal sealed record PlanarSectionDefinition(
    Guid Id,
    string Name,
    TwoDimensionalFormulation Formulation,
    double ThicknessM,
    Vec3 AnalysisPlaneNormal,
    Vec3 AnalysisPlaneOrigin)
{
    public void Validate()
    {
        if (Id == Guid.Empty) throw new InvalidOperationException("A planar section requires a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name)) throw new InvalidOperationException("A planar section requires a name.");
        if (!double.IsFinite(ThicknessM) || ThicknessM <= 0)
            throw new InvalidOperationException("Plane-stress and plane-strain thickness must be positive.");
        if (!double.IsFinite(AnalysisPlaneNormal.Length) || AnalysisPlaneNormal.Length <= 1e-12)
            throw new InvalidOperationException("The analysis-plane normal is invalid.");
    }
}

internal sealed record PlanarBodyDefinition(
    Guid Id,
    Guid GeometryBodyId,
    Guid SectionId,
    Guid MaterialId,
    PlanarBodyRole Role,
    string PersistentFaceSignature)
{
    public void Validate()
    {
        if (Id == Guid.Empty || GeometryBodyId == Guid.Empty || SectionId == Guid.Empty || MaterialId == Guid.Empty)
            throw new InvalidOperationException("A planar body requires stable object, geometry, section and material identifiers.");
        if (string.IsNullOrWhiteSpace(PersistentFaceSignature))
            throw new InvalidOperationException("A planar body must be scoped through a persistent face signature.");
    }
}

internal sealed record PlanarContactPair(
    Guid Id,
    Guid SourceEdgeSelectionId,
    Guid TargetEdgeSelectionId,
    bool Bonded,
    double DetectionToleranceM)
{
    public void Validate()
    {
        if (Id == Guid.Empty || SourceEdgeSelectionId == Guid.Empty || TargetEdgeSelectionId == Guid.Empty)
            throw new InvalidOperationException("A planar contact pair requires stable identifiers.");
        if (!double.IsFinite(DetectionToleranceM) || DetectionToleranceM < 0)
            throw new InvalidOperationException("The contact detection tolerance cannot be negative.");
    }
}

internal sealed record PlanarAnalysisDefinition(
    Guid Id,
    string Name,
    IReadOnlyList<PlanarSectionDefinition> Sections,
    IReadOnlyList<PlanarBodyDefinition> Bodies,
    IReadOnlyList<PlanarContactPair> Contacts)
{
    public void Validate()
    {
        if (Id == Guid.Empty) throw new InvalidOperationException("A 2-D analysis requires a stable identifier.");
        if (string.IsNullOrWhiteSpace(Name)) throw new InvalidOperationException("A 2-D analysis requires a name.");
        if (Sections.Count == 0) throw new InvalidOperationException("A 2-D analysis requires at least one section.");
        if (Bodies.Count == 0) throw new InvalidOperationException("A 2-D analysis requires at least one body.");

        foreach (var section in Sections) section.Validate();
        foreach (var body in Bodies) body.Validate();
        foreach (var contact in Contacts) contact.Validate();

        var sectionIds = Sections.Select(section => section.Id).ToHashSet();
        foreach (var body in Bodies)
            if (!sectionIds.Contains(body.SectionId))
                throw new InvalidOperationException($"Planar body {body.Id} references an unknown section.");

        if (Sections.Select(section => section.Formulation).Distinct().Count() > 1)
            throw new InvalidOperationException("A single 2-D analysis system cannot mix planar formulations.");

        var formulation = Sections[0].Formulation;
        if (formulation == TwoDimensionalFormulation.Axisymmetric)
        {
            var normal = Sections[0].AnalysisPlaneNormal;
            if (Math.Abs(normal.Length - 1.0) > 1e-6)
                throw new InvalidOperationException("Axisymmetric analysis requires a normalized analysis-plane normal.");
        }
    }
}

internal static class GearRackWorkshopContract
{
    public static void Validate(PlanarAnalysisDefinition analysis)
    {
        analysis.Validate();
        if (analysis.Sections[0].Formulation != TwoDimensionalFormulation.PlaneStress)
            throw new InvalidOperationException("WS02.1 requires a plane-stress formulation.");
        if (analysis.Bodies.Count(body => body.Role != PlanarBodyRole.Suppressed) < 2)
            throw new InvalidOperationException("WS02.1 requires active gear and rack bodies.");
        if (analysis.Contacts.Count == 0)
            throw new InvalidOperationException("WS02.1 requires at least one scoped gear-to-rack edge pair.");
    }
}
