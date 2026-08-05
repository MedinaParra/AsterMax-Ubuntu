using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal static class GeneralCadAutomaticStabilizationBootstrap
{
    [ModuleInitializer]
    internal static void Install() => Application.AddMessageFilter(new StabilizationMessageFilter());

    private sealed class StabilizationMessageFilter : IMessageFilter
    {
        private const int WmLeftButtonDown = 0x0201;
        private const int WmKeyDown = 0x0100;

        public bool PreFilterMessage(ref Message message)
        {
            if (message.Msg is not (WmLeftButtonDown or WmKeyDown)) return false;
            var control = Control.FromHandle(message.HWnd);
            var button = FindButton(control);
            if (button is null || !button.Text.Replace("&", string.Empty).Contains("Solve", StringComparison.OrdinalIgnoreCase))
                return false;
            if (message.Msg == WmKeyDown)
            {
                var key = (Keys)(int)message.WParam;
                if (key is not (Keys.Space or Keys.Enter)) return false;
            }
            if (button.FindForm() is MechanicalForm form)
                form.PrepareAutomaticCadStabilization();
            return false;
        }

        private static Button? FindButton(Control? control)
        {
            while (control is not null)
            {
                if (control is Button button) return button;
                control = control.Parent;
            }
            return null;
        }
    }
}

internal sealed partial class MechanicalForm
{
    private CadMesh? _automaticallyStabilizedMesh;

    internal void PrepareAutomaticCadStabilization()
    {
        var mesh = _cadVolumeMesh;
        if (mesh is null || ReferenceEquals(mesh, _automaticallyStabilizedMesh)) return;

        var topology = CadTopologyRegistry.Get(mesh);
        if (topology.Faces is not Dictionary<int, CadSurfaceFace> mutableFaces) return;

        var supportTags = ScopedCadTags(ObjectKind.Support).Distinct().ToArray();
        if (supportTags.Length == 0) return;

        var supportFaces = supportTags
            .Where(mutableFaces.ContainsKey)
            .Select(tag => mutableFaces[tag])
            .ToArray();
        if (supportFaces.Length == 0) return;

        var constrained = supportFaces.SelectMany(face => face.NodeIndices).ToHashSet();
        var adjacency = BuildNodeAdjacency(mesh);
        var expanded = new HashSet<int>(constrained);
        foreach (var node in constrained)
            foreach (var neighbour in adjacency[node])
                expanded.Add(neighbour);

        var components = FindConnectedComponents(mesh, adjacency);
        var unsupportedComponents = 0;
        foreach (var component in components)
        {
            if (component.Any(expanded.Contains)) continue;
            unsupportedComponents++;
            expanded.Add(ChooseAnchorNode(mesh, component, constrained));
        }

        var primary = supportFaces[0];
        mutableFaces[primary.Tag] = primary with { NodeIndices = expanded.OrderBy(index => index).ToArray() };
        _automaticallyStabilizedMesh = mesh;

        var quality = EvaluateTetQuality(mesh);
        var added = expanded.Count - constrained.Count;
        var message = $"Automatic solver stabilization: support layer expanded by {added:N0} nodes";
        if (unsupportedComponents > 0)
            message += $"; {unsupportedComponents:N0} disconnected region(s) anchored";
        message += $"; minimum TET4 quality {quality.Minimum:0.000}.";
        Log(message);
        _statusMain.Text = unsupportedComponents > 0
            ? "Automatic stabilization applied to disconnected mesh regions"
            : "Automatic support stabilization applied";

        foreach (var node in AllNodes().Where(node => node.Tag is ModelObject { Kind: ObjectKind.Support }))
        {
            var model = (ModelObject)node.Tag;
            if (!model.Properties.TryGetValue("CadSurfaceTag", out var tagText) ||
                !int.TryParse(tagText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var tag) ||
                tag != primary.Tag) continue;
            model.Properties["Automatic Stabilization"] = "One tetrahedral layer";
            model.Properties["Solver Nodes"] = expanded.Count.ToString("N0");
            model.Properties["Disconnected Regions Anchored"] = unsupportedComponents.ToString("N0");
            model.Properties["Minimum TET4 Quality"] = quality.Minimum.ToString("0.000", CultureInfo.InvariantCulture);
        }
    }

    private static List<int>[] BuildNodeAdjacency(CadMesh mesh)
    {
        var sets = Enumerable.Range(0, mesh.Nodes.Count).Select(_ => new HashSet<int>()).ToArray();
        foreach (var tet in mesh.Tetrahedra)
        {
            for (var first = 0; first < 4; first++)
            for (var second = first + 1; second < 4; second++)
            {
                sets[tet[first]].Add(tet[second]);
                sets[tet[second]].Add(tet[first]);
            }
        }
        return sets.Select(set => set.ToList()).ToArray();
    }

    private static IReadOnlyList<int[]> FindConnectedComponents(CadMesh mesh, IReadOnlyList<List<int>> adjacency)
    {
        var active = mesh.Tetrahedra.SelectMany(tet => tet).ToHashSet();
        var visited = new bool[mesh.Nodes.Count];
        var components = new List<int[]>();
        foreach (var seed in active)
        {
            if (visited[seed]) continue;
            var nodes = new List<int>();
            var queue = new Queue<int>();
            queue.Enqueue(seed);
            visited[seed] = true;
            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                nodes.Add(current);
                foreach (var neighbour in adjacency[current])
                {
                    if (visited[neighbour]) continue;
                    visited[neighbour] = true;
                    queue.Enqueue(neighbour);
                }
            }
            components.Add(nodes.ToArray());
        }
        return components;
    }

    private static int ChooseAnchorNode(CadMesh mesh, IReadOnlyList<int> component, IReadOnlyCollection<int> constrained)
    {
        if (constrained.Count == 0) return component[0];
        var reference = constrained.Aggregate(Vec3.Zero, (sum, index) => sum + mesh.Nodes[index]) / constrained.Count;
        return component.OrderBy(index => (mesh.Nodes[index] - reference).Length).First();
    }

    private static (double Minimum, int PoorCount) EvaluateTetQuality(CadMesh mesh)
    {
        var minimum = 1.0;
        var poor = 0;
        foreach (var tet in mesh.Tetrahedra)
        {
            var a = mesh.Nodes[tet[0]];
            var b = mesh.Nodes[tet[1]];
            var c = mesh.Nodes[tet[2]];
            var d = mesh.Nodes[tet[3]];
            var volume = Math.Abs(Dot(b - a, Cross(c - a, d - a))) / 6.0;
            var edgeSquareSum =
                Square((b - a).Length) + Square((c - a).Length) + Square((d - a).Length) +
                Square((c - b).Length) + Square((d - b).Length) + Square((d - c).Length);
            var quality = edgeSquareSum <= 1e-30 ? 0 : 12.0 * Math.Pow(3.0 * volume, 2.0 / 3.0) / edgeSquareSum;
            quality = Math.Clamp(quality, 0, 1);
            minimum = Math.Min(minimum, quality);
            if (quality < 0.03) poor++;
        }
        return (minimum, poor);
    }

    private static double Square(double value) => value * value;
    private static Vec3 Cross(Vec3 first, Vec3 second) => new(
        first.Y * second.Z - first.Z * second.Y,
        first.Z * second.X - first.X * second.Z,
        first.X * second.Y - first.Y * second.X);
    private static double Dot(Vec3 first, Vec3 second) => first.X * second.X + first.Y * second.Y + first.Z * second.Z;
}
