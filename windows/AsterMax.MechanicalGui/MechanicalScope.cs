namespace AsterMax.MechanicalGui;

internal sealed record MechanicalScope(
    IReadOnlyList<int> VertexIds,
    IReadOnlyList<int> EdgeIds,
    IReadOnlyList<int> FaceIds,
    IReadOnlyList<int> BodyIds,
    IReadOnlyList<int> NodeIds)
{
    public static MechanicalScope Empty { get; } = new([], [], [], [], []);

    public bool IsEmpty =>
        VertexIds.Count == 0 &&
        EdgeIds.Count == 0 &&
        FaceIds.Count == 0 &&
        BodyIds.Count == 0 &&
        NodeIds.Count == 0;
}
