namespace AsterMax.MechanicalGui;

internal enum MeshElementFamily
{
    Tetrahedron,
    Hexahedron,
    Wedge,
    Pyramid,
    Triangle,
    Quadrilateral,
    Beam
}

internal enum MeshOrder
{
    Linear,
    Quadratic
}

internal enum MeshCreationMethod
{
    Automatic,
    Tetrahedrons,
    Sweep,
    MultiZone,
    Surface,
    Line
}

internal sealed record MeshBodyScope(
    Guid BodyId,
    MeshCreationMethod Method,
    MeshElementFamily ElementFamily,
    MeshOrder Order)
{
    public void Validate(string meshName)
    {
        if (BodyId == Guid.Empty)
            throw new InvalidOperationException($"Mesh '{meshName}' contains an empty body identifier.");
        if (!Enum.IsDefined(Method) || !Enum.IsDefined(ElementFamily) || !Enum.IsDefined(Order))
            throw new InvalidOperationException($"Mesh '{meshName}' contains an unsupported body meshing option.");

        var compatible = Method switch
        {
            MeshCreationMethod.Automatic => true,
            MeshCreationMethod.Tetrahedrons => ElementFamily == MeshElementFamily.Tetrahedron,
            MeshCreationMethod.Sweep => ElementFamily is MeshElementFamily.Hexahedron or MeshElementFamily.Wedge,
            MeshCreationMethod.MultiZone => ElementFamily is MeshElementFamily.Hexahedron or MeshElementFamily.Wedge or MeshElementFamily.Pyramid,
            MeshCreationMethod.Surface => ElementFamily is MeshElementFamily.Triangle or MeshElementFamily.Quadrilateral,
            MeshCreationMethod.Line => ElementFamily == MeshElementFamily.Beam,
            _ => false
        };

        if (!compatible)
            throw new InvalidOperationException($"Mesh '{meshName}' uses an incompatible method and element family.");
    }
}

internal sealed record MeshStatistics(long NodeCount, long ElementCount)
{
    public void Validate(string meshName)
    {
        if (NodeCount < 1 || ElementCount < 1)
            throw new InvalidOperationException($"Mesh '{meshName}' requires positive node and element counts.");
    }
}

internal sealed class MeshDefinition
{
    public required Guid Id { get; init; }
    public required Guid AnalysisId { get; init; }
    public required string Name { get; init; }
    public required string GeometrySignature { get; init; }
    public double GlobalElementSize { get; init; }
    public double MinimumElementSize { get; init; }
    public double GrowthRate { get; init; } = 1.2;
    public IReadOnlyList<MeshBodyScope> BodyScopes { get; init; } = [];
    public MeshStatistics? GeneratedStatistics { get; init; }

    public void Validate(string activeGeometrySignature)
    {
        if (Id == Guid.Empty || AnalysisId == Guid.Empty)
            throw new InvalidOperationException("Mesh and analysis identifiers must be stable.");
        if (string.IsNullOrWhiteSpace(Name))
            throw new InvalidOperationException("Mesh name cannot be empty.");
        if (string.IsNullOrWhiteSpace(GeometrySignature) || !string.Equals(GeometrySignature, activeGeometrySignature, StringComparison.Ordinal))
            throw new InvalidOperationException($"Mesh '{Name}' is stale for the active geometry.");
        if (!double.IsFinite(GlobalElementSize) || GlobalElementSize <= 0.0)
            throw new InvalidOperationException($"Mesh '{Name}' requires a positive global element size.");
        if (!double.IsFinite(MinimumElementSize) || MinimumElementSize <= 0.0 || MinimumElementSize > GlobalElementSize)
            throw new InvalidOperationException($"Mesh '{Name}' requires a valid minimum element size.");
        if (!double.IsFinite(GrowthRate) || GrowthRate < 1.0 || GrowthRate > 2.0)
            throw new InvalidOperationException($"Mesh '{Name}' requires a growth rate between 1.0 and 2.0.");
        if (BodyScopes.Count == 0)
            throw new InvalidOperationException($"Mesh '{Name}' requires at least one body scope.");

        var bodyIds = new HashSet<Guid>();
        foreach (var scope in BodyScopes)
        {
            scope.Validate(Name);
            if (!bodyIds.Add(scope.BodyId))
                throw new InvalidOperationException($"Mesh '{Name}' contains duplicate body scopes.");
        }

        GeneratedStatistics?.Validate(Name);
    }
}

internal sealed class MeshDefinitionCatalog
{
    private readonly Dictionary<Guid, MeshDefinition> _meshes = [];

    public IReadOnlyCollection<MeshDefinition> Meshes => _meshes.Values;

    public void Add(MeshDefinition mesh, string activeGeometrySignature)
    {
        mesh.Validate(activeGeometrySignature);
        if (_meshes.ContainsKey(mesh.Id))
            throw new InvalidOperationException($"Mesh '{mesh.Id}' already exists.");
        if (_meshes.Values.Any(item => item.AnalysisId == mesh.AnalysisId))
            throw new InvalidOperationException($"Analysis '{mesh.AnalysisId}' already has a mesh definition.");
        if (_meshes.Values.Any(item => string.Equals(item.Name, mesh.Name, StringComparison.OrdinalIgnoreCase)))
            throw new InvalidOperationException($"Mesh name '{mesh.Name}' is already in use.");
        _meshes.Add(mesh.Id, mesh);
    }

    public MeshDefinition Get(Guid id) =>
        _meshes.TryGetValue(id, out var mesh)
            ? mesh
            : throw new KeyNotFoundException($"Mesh '{id}' was not found.");
}
