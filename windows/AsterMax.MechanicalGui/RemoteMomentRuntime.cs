namespace AsterMax.MechanicalGui;

internal sealed record RemoteMomentSurfaceLoadSet(
    string Name,
    IReadOnlyList<CadSurfaceForce> SurfaceForces,
    Vec3 RemotePointMm,
    Vec3 RequestedMomentNmm,
    double ForceConservationError,
    double MomentConservationError);

internal static class RemoteMomentRuntime
{
    public static RemoteMomentSurfaceLoadSet Build(
        CadMesh mesh,
        NamedSelectionCatalog selections,
        string activeGeometrySignature,
        RemoteBoundaryConditionDefinition condition)
    {
        ArgumentNullException.ThrowIfNull(condition);
        condition.Validate(selections, activeGeometrySignature);
        if (condition.Type != RemoteBoundaryConditionType.Moment)
            throw new InvalidOperationException($"Remote runtime '{condition.Name}' is not a Remote Moment.");
        if (condition.Coupling.Behavior != RemoteCouplingBehavior.Deformable)
            throw new InvalidOperationException(
                $"Remote Moment '{condition.Name}' requests rigid coupling. " +
                "The current runtime slice certifies deformable moment transfer only; rigid remote kinematics require remote-point MPC DOFs.");

        var components = condition.Components;
        var localMoment = new Vec3(
            components.RotationX ?? 0.0,
            components.RotationY ?? 0.0,
            components.RotationZ ?? 0.0);
        var requestedMoment = RemoteSurfaceLoadTransferRuntime.ToGlobal(
            condition.CoordinateFrame,
            localMoment,
            condition.Name);
        if (!double.IsFinite(requestedMoment.Length) || requestedMoment.Length <= 1e-12)
            throw new InvalidOperationException($"Remote Moment '{condition.Name}' resolves to a zero or invalid global moment vector.");

        var transfer = RemoteSurfaceLoadTransferRuntime.Build(
            mesh,
            selections,
            activeGeometrySignature,
            condition,
            Vec3.Zero,
            requestedMoment);

        return new RemoteMomentSurfaceLoadSet(
            condition.Name,
            transfer.SurfaceForces,
            new Vec3(condition.RemotePoint.X, condition.RemotePoint.Y, condition.RemotePoint.Z),
            requestedMoment,
            transfer.ForceConservationError,
            transfer.MomentConservationError);
    }
}
