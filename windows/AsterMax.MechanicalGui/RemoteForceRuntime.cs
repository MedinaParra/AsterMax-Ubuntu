namespace AsterMax.MechanicalGui;

internal sealed record RemoteForceSurfaceLoadSet(
    string Name,
    IReadOnlyList<CadSurfaceForce> SurfaceForces,
    Vec3 RemotePointMm,
    Vec3 RequestedForceN,
    double ForceConservationError,
    double MomentConservationError);

internal static class RemoteForceRuntime
{
    public static RemoteForceSurfaceLoadSet Build(
        CadMesh mesh,
        NamedSelectionCatalog selections,
        string activeGeometrySignature,
        RemoteBoundaryConditionDefinition condition)
    {
        ArgumentNullException.ThrowIfNull(condition);
        condition.Validate(selections, activeGeometrySignature);
        if (condition.Type != RemoteBoundaryConditionType.Force)
            throw new InvalidOperationException($"Remote runtime '{condition.Name}' is not a Remote Force.");
        if (condition.Coupling.Behavior != RemoteCouplingBehavior.Deformable)
            throw new InvalidOperationException(
                $"Remote Force '{condition.Name}' requests rigid coupling. " +
                "The current runtime slice certifies deformable load transfer only; rigid remote kinematics require remote-point MPC DOFs.");

        var components = condition.Components;
        var localForce = new Vec3(components.X ?? 0.0, components.Y ?? 0.0, components.Z ?? 0.0);
        var requestedForce = RemoteSurfaceLoadTransferRuntime.ToGlobal(
            condition.CoordinateFrame,
            localForce,
            condition.Name);
        if (!double.IsFinite(requestedForce.Length) || requestedForce.Length <= 1e-12)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' resolves to a zero or invalid global force vector.");

        var transfer = RemoteSurfaceLoadTransferRuntime.Build(
            mesh,
            selections,
            activeGeometrySignature,
            condition,
            requestedForce,
            Vec3.Zero);

        return new RemoteForceSurfaceLoadSet(
            condition.Name,
            transfer.SurfaceForces,
            new Vec3(condition.RemotePoint.X, condition.RemotePoint.Y, condition.RemotePoint.Z),
            requestedForce,
            transfer.ForceConservationError,
            transfer.MomentConservationError);
    }
}
