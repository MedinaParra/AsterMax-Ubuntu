using System.Security.Cryptography;
using System.Text;

namespace AsterMax.MechanicalGui;

internal sealed record RigidRemoteDisplacementConstraintSet(
    string Name,
    IReadOnlyList<ConstraintEquationDefinition> Equations,
    IReadOnlyList<int> ScopedNodeIds,
    int AnchorNodeId,
    Vec3 RemotePointMm,
    Vec3 TranslationMm,
    Vec3 RotationRad);

/// <summary>
/// Translates a fully prescribed small-rotation rigid Remote Displacement into exact
/// mesh-node MPC equations. The anchor node must belong to the solver's zero-valued
/// fixed-support set; its terms are eliminated by the existing TET4 MPC reduction.
/// </summary>
internal static class RigidRemoteDisplacementRuntime
{
    private const double MaximumSmallRotationRad = 0.1;

    public static RigidRemoteDisplacementConstraintSet Build(
        CadMesh mesh,
        NamedSelectionCatalog selections,
        string activeGeometrySignature,
        RemoteBoundaryConditionDefinition condition,
        IReadOnlyCollection<int> fixedNodeIndices)
    {
        ArgumentNullException.ThrowIfNull(mesh);
        ArgumentNullException.ThrowIfNull(selections);
        ArgumentNullException.ThrowIfNull(condition);
        ArgumentNullException.ThrowIfNull(fixedNodeIndices);

        condition.Validate(selections, activeGeometrySignature);
        if (condition.Type != RemoteBoundaryConditionType.Displacement)
            throw new InvalidOperationException($"Remote runtime '{condition.Name}' is not a Remote Displacement.");
        if (condition.Coupling.Behavior != RemoteCouplingBehavior.Rigid)
            throw new InvalidOperationException(
                $"Remote Displacement '{condition.Name}' requests deformable coupling. " +
                "This runtime slice certifies fully prescribed rigid kinematics only.");
        if (fixedNodeIndices.Count == 0)
            throw new InvalidOperationException(
                $"Remote Displacement '{condition.Name}' requires at least one zero-valued fixed-support node as an MPC anchor.");

        var components = condition.Components;
        if (!components.X.HasValue || !components.Y.HasValue || !components.Z.HasValue ||
            !components.RotationX.HasValue || !components.RotationY.HasValue || !components.RotationZ.HasValue)
            throw new InvalidOperationException(
                $"Remote Displacement '{condition.Name}' requires all six translation/rotation components in the current fully prescribed runtime slice.");

        var localTranslation = new Vec3(components.X.Value, components.Y.Value, components.Z.Value);
        var localRotation = new Vec3(components.RotationX.Value, components.RotationY.Value, components.RotationZ.Value);
        var translation = RemoteSurfaceLoadTransferRuntime.ToGlobal(condition.CoordinateFrame, localTranslation, condition.Name);
        var rotation = RemoteSurfaceLoadTransferRuntime.ToGlobal(condition.CoordinateFrame, localRotation, condition.Name);
        if (!double.IsFinite(translation.Length) || !double.IsFinite(rotation.Length))
            throw new InvalidOperationException($"Remote Displacement '{condition.Name}' resolves to non-finite global kinematics.");
        if (rotation.Length > MaximumSmallRotationRad)
            throw new InvalidOperationException(
                $"Remote Displacement '{condition.Name}' requests rotation magnitude {rotation.Length:G6} rad, above the " +
                $"linearized small-rotation limit of {MaximumSmallRotationRad:G6} rad.");

        var scopeDefinition = selections.Get(condition.ScopeSelectionId);
        if (scopeDefinition.EntityType != NamedSelectionEntityType.Face)
            throw new InvalidOperationException(
                $"Rigid Remote Displacement runtime currently requires a face-based named selection, not {scopeDefinition.EntityType}.");
        var scope = selections.Resolve(condition.ScopeSelectionId, activeGeometrySignature);
        var scopedNodeIndices = ResolveFaceNodes(mesh, scope);
        if (scopedNodeIndices.Count < 3)
            throw new InvalidOperationException($"Remote Displacement '{condition.Name}' requires at least three scoped face nodes.");

        foreach (var node in fixedNodeIndices)
            if ((uint)node >= (uint)mesh.Nodes.Count)
                throw new InvalidOperationException(
                    $"Remote Displacement '{condition.Name}' received fixed-support node {node}, outside the active mesh.");

        var scopedSet = scopedNodeIndices.ToHashSet();
        var anchorIndex = fixedNodeIndices
            .Where(node => !scopedSet.Contains(node))
            .OrderBy(node => node)
            .FirstOrDefault(-1);
        if (anchorIndex < 0)
            throw new InvalidOperationException(
                $"Remote Displacement '{condition.Name}' cannot use a scoped node as its zero-valued MPC anchor. " +
                "Provide a fixed-support node outside the remote scope.");

        var remotePoint = new Vec3(condition.RemotePoint.X, condition.RemotePoint.Y, condition.RemotePoint.Z);
        var equations = new List<ConstraintEquationDefinition>(scopedNodeIndices.Count * 3);
        foreach (var nodeIndex in scopedNodeIndices)
        {
            var lever = mesh.Nodes[nodeIndex] - remotePoint;
            var target = translation + Cross(rotation, lever);
            AddEquation(equations, condition.Id, condition.Name, nodeIndex + 1, anchorIndex + 1,
                ConstraintDegreeOfFreedom.TranslationX, target.X);
            AddEquation(equations, condition.Id, condition.Name, nodeIndex + 1, anchorIndex + 1,
                ConstraintDegreeOfFreedom.TranslationY, target.Y);
            AddEquation(equations, condition.Id, condition.Name, nodeIndex + 1, anchorIndex + 1,
                ConstraintDegreeOfFreedom.TranslationZ, target.Z);
        }

        foreach (var equation in equations)
            equation.Validate();

        if (equations.Select(equation => equation.Id).Distinct().Count() != equations.Count)
            throw new InvalidOperationException($"Remote Displacement '{condition.Name}' produced duplicate deterministic MPC identifiers.");

        return new RigidRemoteDisplacementConstraintSet(
            condition.Name,
            equations,
            scopedNodeIndices.Select(index => index + 1).ToArray(),
            anchorIndex + 1,
            remotePoint,
            translation,
            rotation);
    }

    public static Vec3 ExpectedNodeDisplacement(
        RigidRemoteDisplacementConstraintSet constraintSet,
        Vec3 nodePositionMm)
    {
        ArgumentNullException.ThrowIfNull(constraintSet);
        return constraintSet.TranslationMm +
               Cross(constraintSet.RotationRad, nodePositionMm - constraintSet.RemotePointMm);
    }

    private static IReadOnlyList<int> ResolveFaceNodes(CadMesh mesh, MechanicalScope scope)
    {
        var topology = CadTopologyRegistry.Get(mesh);
        var nodes = new SortedSet<int>();
        foreach (var faceId in scope.FaceIds)
        {
            if (!topology.Faces.TryGetValue(faceId, out var face))
                throw new InvalidOperationException($"Remote Displacement face scope references Face {faceId}, absent from the active mesh.");
            foreach (var node in face.NodeIndices)
                nodes.Add(node);
        }
        return nodes.ToArray();
    }

    private static void AddEquation(
        ICollection<ConstraintEquationDefinition> equations,
        Guid remoteId,
        string remoteName,
        int nodeId,
        int anchorNodeId,
        ConstraintDegreeOfFreedom dof,
        double targetMm)
    {
        var equation = new ConstraintEquationDefinition
        {
            Id = StableEquationId(remoteId, nodeId, dof),
            Name = $"{remoteName} / node {nodeId} / {dof}",
            Terms = new[]
            {
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.MeshNode, nodeId, null),
                    dof,
                    1.0),
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.MeshNode, anchorNodeId, null),
                    dof,
                    -1.0)
            },
            RightHandSide = targetMm
        };
        equations.Add(equation);
    }

    private static Guid StableEquationId(Guid remoteId, int nodeId, ConstraintDegreeOfFreedom dof)
    {
        var key = Encoding.UTF8.GetBytes($"rigid-remote-displacement|{remoteId:D}|node:{nodeId}|dof:{dof}");
        var hash = SHA256.HashData(key);
        return new Guid(hash.Take(16).ToArray());
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) => new(
        a.Y * b.Z - a.Z * b.Y,
        a.Z * b.X - a.X * b.Z,
        a.X * b.Y - a.Y * b.X);
}
