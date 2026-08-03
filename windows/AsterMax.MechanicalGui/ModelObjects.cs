using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

internal enum ObjectState { Undefined, NeedsAttention, Ready, Updating, UpToDate, Solved, Suppressed, Error }
internal enum ObjectKind { Project, Model, Geometry, Body, Materials, Material, CoordinateSystems, CoordinateSystem, Connections, Contact, NamedSelections, NamedSelection, Mesh, MeshControl, Analysis, AnalysisSettings, Support, Load, Solution, SolutionInformation, Result, Probe, Chart }

internal sealed class ModelObject
{
    public required string Name { get; set; }
    public required ObjectKind Kind { get; init; }
    public ObjectState State { get; set; }
    public string Category { get; set; } = string.Empty;
    public Dictionary<string, string> Properties { get; } = new(StringComparer.OrdinalIgnoreCase);
}

internal sealed class ProjectSnapshot
{
    public string Product { get; set; } = "AsterMax Mechanical";
    public string Version { get; set; } = "0.4.0-beta";
    public string ProjectName { get; set; } = "Untitled";
    public string Units { get; set; } = "Metric (mm, kg, N, s)";
    public string? GeometryPath { get; set; }
    public string? CodeAsterLauncher { get; set; }
    public bool MeshGenerated { get; set; }
    public bool Solved { get; set; }
    public DateTimeOffset SavedAt { get; set; } = DateTimeOffset.Now;
}
