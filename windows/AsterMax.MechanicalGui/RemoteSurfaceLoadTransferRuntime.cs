namespace AsterMax.MechanicalGui;

internal sealed record RemoteSurfaceLoadTransferResult(
    IReadOnlyList<CadSurfaceForce> SurfaceForces,
    Vec3 RequestedForceN,
    Vec3 RequestedMomentNmm,
    Vec3 TransferredForceN,
    Vec3 TransferredMomentNmm,
    double ForceConservationError,
    double MomentConservationError);

/// <summary>
/// Converts a remote force/moment resultant into equivalent forces on real CAD surface triangles.
/// The transfer enforces both resultant force and resultant moment about the remote point.
/// </summary>
internal static class RemoteSurfaceLoadTransferRuntime
{
    private const double RankTolerance = 1e-11;
    private const double EmissionTolerance = 1e-14;

    public static RemoteSurfaceLoadTransferResult Build(
        CadMesh mesh,
        NamedSelectionCatalog selections,
        string activeGeometrySignature,
        RemoteBoundaryConditionDefinition condition,
        Vec3 requestedForceN,
        Vec3 requestedMomentNmm)
    {
        ArgumentNullException.ThrowIfNull(mesh);
        ArgumentNullException.ThrowIfNull(selections);
        ArgumentNullException.ThrowIfNull(condition);

        if (!double.IsFinite(requestedForceN.Length) || !double.IsFinite(requestedMomentNmm.Length))
            throw new InvalidOperationException($"Remote load '{condition.Name}' contains a non-finite resultant.");
        if (requestedForceN.Length <= 1e-12 && requestedMomentNmm.Length <= 1e-12)
            throw new InvalidOperationException($"Remote load '{condition.Name}' has zero force and zero moment.");
        if (condition.Coupling.Behavior != RemoteCouplingBehavior.Deformable)
            throw new InvalidOperationException(
                $"Remote load '{condition.Name}' requests rigid coupling. " +
                "The current surface-transfer runtime certifies deformable coupling only.");

        var scopeDefinition = selections.Get(condition.ScopeSelectionId);
        if (scopeDefinition.EntityType != NamedSelectionEntityType.Face)
            throw new InvalidOperationException(
                $"Remote surface-load runtime requires a face-based named selection, not {scopeDefinition.EntityType}.");
        var scope = selections.Resolve(condition.ScopeSelectionId, activeGeometrySignature);
        var triangles = ResolveScopedTriangles(mesh, scope);
        if (triangles.Count < 2)
            throw new InvalidOperationException($"Remote load '{condition.Name}' requires at least two scoped surface triangles.");

        var remotePoint = new Vec3(condition.RemotePoint.X, condition.RemotePoint.Y, condition.RemotePoint.Z);
        var centroids = triangles.Select(index => TriangleCentroid(mesh, index)).ToArray();
        var weights = BuildWeights(mesh, triangles, centroids, remotePoint, condition.Coupling);
        var equivalentForces = SolveEquivalentTriangleForces(
            centroids,
            weights,
            remotePoint,
            requestedForceN,
            requestedMomentNmm,
            condition.Name);

        var surfaceForces = new List<CadSurfaceForce>(triangles.Count);
        for (var index = 0; index < triangles.Count; index++)
        {
            var force = equivalentForces[index];
            if (!double.IsFinite(force.Length))
                throw new InvalidOperationException($"Remote load '{condition.Name}' produced a non-finite triangle force.");
            if (force.Length <= EmissionTolerance)
                continue;
            surfaceForces.Add(new CadSurfaceForce(
                new[] { triangles[index] },
                force,
                $"{condition.Name} / triangle {triangles[index] + 1}"));
        }
        if (surfaceForces.Count == 0)
            throw new InvalidOperationException($"Remote load '{condition.Name}' produced no non-zero equivalent surface forces.");

        var transferredForce = Vec3.Zero;
        var transferredMoment = Vec3.Zero;
        foreach (var load in surfaceForces)
        {
            var triangleIndex = load.TriangleIndices.Single();
            var centroid = TriangleCentroid(mesh, triangleIndex);
            transferredForce += load.TotalForceN;
            transferredMoment += Cross(centroid - remotePoint, load.TotalForceN);
        }

        var characteristicLength = centroids
            .Select(point => (point - remotePoint).Length)
            .Where(length => length > 1e-12)
            .DefaultIfEmpty(1.0)
            .Max();
        var forceScale = Math.Max(requestedForceN.Length, 1.0);
        var momentScale = Math.Max(
            requestedMomentNmm.Length,
            Math.Max(requestedForceN.Length * Math.Max(characteristicLength, 1.0), 1.0));
        var forceError = (transferredForce - requestedForceN).Length / forceScale;
        var momentError = (transferredMoment - requestedMomentNmm).Length / momentScale;

        if (!double.IsFinite(forceError) || forceError > 1e-10)
            throw new InvalidOperationException($"Remote load '{condition.Name}' failed force conservation: {forceError:E3}.");
        if (!double.IsFinite(momentError) || momentError > 1e-10)
            throw new InvalidOperationException($"Remote load '{condition.Name}' failed moment conservation: {momentError:E3}.");

        return new RemoteSurfaceLoadTransferResult(
            surfaceForces,
            requestedForceN,
            requestedMomentNmm,
            transferredForce,
            transferredMoment,
            forceError,
            momentError);
    }

    public static Vec3 ToGlobal(RemoteCoordinateFrame frame, Vec3 localVector, string name)
    {
        ArgumentNullException.ThrowIfNull(frame);
        frame.Validate(name);
        if (frame.UseGlobalAxes)
            return localVector;

        var primary = ToVec(frame.PrimaryAxis!.Value);
        var secondary = ToVec(frame.SecondaryAxis!.Value);
        var x = primary / primary.Length;
        var y = secondary / secondary.Length;
        var z = Cross(x, y);
        var zLength = z.Length;
        if (zLength <= 1e-12)
            throw new InvalidOperationException($"Remote load '{name}' has a degenerate local coordinate frame.");
        z /= zLength;
        return x * localVector.X + y * localVector.Y + z * localVector.Z;
    }

    private static IReadOnlyList<int> ResolveScopedTriangles(CadMesh mesh, MechanicalScope scope)
    {
        var topology = CadTopologyRegistry.Get(mesh);
        var triangles = new SortedSet<int>();
        foreach (var faceId in scope.FaceIds)
        {
            if (!topology.Faces.TryGetValue(faceId, out var face))
                throw new InvalidOperationException($"Remote load face scope references Face {faceId}, absent from the active mesh.");
            foreach (var triangleIndex in face.TriangleIndices)
                triangles.Add(triangleIndex);
        }
        return triangles.ToArray();
    }

    private static double[] BuildWeights(
        CadMesh mesh,
        IReadOnlyList<int> triangles,
        IReadOnlyList<Vec3> centroids,
        Vec3 remotePoint,
        RemoteCouplingDefinition coupling)
    {
        var raw = new double[triangles.Count];
        switch (coupling.Weighting)
        {
            case RemoteWeightingMethod.Uniform:
                Array.Fill(raw, 1.0);
                break;
            case RemoteWeightingMethod.AreaWeighted:
                for (var index = 0; index < triangles.Count; index++)
                {
                    var triangle = mesh.SurfaceTriangles[triangles[index]];
                    raw[index] = TriangleArea(mesh.Nodes[triangle[0]], mesh.Nodes[triangle[1]], mesh.Nodes[triangle[2]]);
                }
                break;
            case RemoteWeightingMethod.DistanceWeighted:
                var exponent = coupling.DistanceWeightExponent!.Value;
                var distances = centroids.Select(point => (point - remotePoint).Length).ToArray();
                var characteristic = distances.Where(distance => distance > 1e-12).DefaultIfEmpty(1.0).Average();
                var floor = Math.Max(characteristic * 1e-9, 1e-12);
                for (var index = 0; index < triangles.Count; index++)
                    raw[index] = 1.0 / Math.Pow(Math.Max(distances[index], floor), exponent);
                break;
            default:
                throw new InvalidOperationException($"Unsupported remote-load weighting {coupling.Weighting}.");
        }

        if (raw.Any(value => !double.IsFinite(value) || value <= 0.0))
            throw new InvalidOperationException("Remote load weighting produced a non-positive or non-finite triangle weight.");
        var sum = raw.Sum();
        return raw.Select(value => value / sum).ToArray();
    }

    private static Vec3[] SolveEquivalentTriangleForces(
        IReadOnlyList<Vec3> centroids,
        IReadOnlyList<double> weights,
        Vec3 remotePoint,
        Vec3 requestedForce,
        Vec3 requestedMoment,
        string name)
    {
        var characteristicLength = centroids
            .Select(point => (point - remotePoint).Length)
            .Where(length => length > 1e-12)
            .DefaultIfEmpty(0.0)
            .Max();
        if (!double.IsFinite(characteristicLength) || characteristicLength <= 1e-12)
            throw new InvalidOperationException($"Remote load '{name}' has no finite geometric lever arm relative to its remote point.");
        var inverseLength = 1.0 / characteristicLength;

        var unknownCount = centroids.Count * 3;
        var a = new double[6, unknownCount];
        for (var item = 0; item < centroids.Count; item++)
        {
            var r = centroids[item] - remotePoint;
            var column = item * 3;
            a[0, column] = 1.0;
            a[1, column + 1] = 1.0;
            a[2, column + 2] = 1.0;
            a[3, column + 1] = -r.Z * inverseLength;
            a[3, column + 2] = r.Y * inverseLength;
            a[4, column] = r.Z * inverseLength;
            a[4, column + 2] = -r.X * inverseLength;
            a[5, column] = -r.Y * inverseLength;
            a[5, column + 1] = r.X * inverseLength;
        }

        var gram = new double[6, 6];
        for (var row = 0; row < 6; row++)
        for (var column = 0; column < 6; column++)
        {
            var sum = 0.0;
            for (var item = 0; item < centroids.Count; item++)
            {
                var weight = weights[item];
                var baseColumn = item * 3;
                for (var component = 0; component < 3; component++)
                    sum += a[row, baseColumn + component] * weight * a[column, baseColumn + component];
            }
            gram[row, column] = sum;
        }

        var rhs = new[]
        {
            requestedForce.X,
            requestedForce.Y,
            requestedForce.Z,
            requestedMoment.X * inverseLength,
            requestedMoment.Y * inverseLength,
            requestedMoment.Z * inverseLength
        };
        var multipliers = SolveDensePivoted(
            gram,
            rhs,
            $"Remote load '{name}' scope cannot represent the requested force/moment transfer. " +
            "Use a surface with sufficient geometric span or move the remote point.");

        var result = new Vec3[centroids.Count];
        for (var item = 0; item < centroids.Count; item++)
        {
            var weight = weights[item];
            var baseColumn = item * 3;
            var force = new double[3];
            for (var component = 0; component < 3; component++)
            for (var equation = 0; equation < 6; equation++)
                force[component] += weight * a[equation, baseColumn + component] * multipliers[equation];
            result[item] = new Vec3(force[0], force[1], force[2]);
        }
        return result;
    }

    private static double[] SolveDensePivoted(double[,] matrix, double[] rhs, string failureMessage)
    {
        const int size = 6;
        var augmented = new double[size, size + 1];
        var scale = 0.0;
        for (var row = 0; row < size; row++)
        for (var column = 0; column < size; column++)
        {
            augmented[row, column] = matrix[row, column];
            scale = Math.Max(scale, Math.Abs(matrix[row, column]));
        }
        for (var row = 0; row < size; row++)
            augmented[row, size] = rhs[row];
        var tolerance = Math.Max(1e-14, scale * RankTolerance);

        for (var column = 0; column < size; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < size; row++)
                if (Math.Abs(augmented[row, column]) > Math.Abs(augmented[pivot, column]))
                    pivot = row;
            if (!double.IsFinite(augmented[pivot, column]) || Math.Abs(augmented[pivot, column]) <= tolerance)
                throw new InvalidOperationException(failureMessage);
            if (pivot != column)
                for (var entry = column; entry <= size; entry++)
                    (augmented[column, entry], augmented[pivot, entry]) = (augmented[pivot, entry], augmented[column, entry]);

            var divisor = augmented[column, column];
            for (var entry = column; entry <= size; entry++)
                augmented[column, entry] /= divisor;
            for (var row = 0; row < size; row++)
            {
                if (row == column) continue;
                var factor = augmented[row, column];
                for (var entry = column; entry <= size; entry++)
                    augmented[row, entry] -= factor * augmented[column, entry];
            }
        }

        var solution = Enumerable.Range(0, size).Select(row => augmented[row, size]).ToArray();
        if (solution.Any(value => !double.IsFinite(value)))
            throw new InvalidOperationException(failureMessage);
        return solution;
    }

    private static Vec3 TriangleCentroid(CadMesh mesh, int triangleIndex)
    {
        if ((uint)triangleIndex >= (uint)mesh.SurfaceTriangles.Count)
            throw new InvalidOperationException($"Remote load references boundary triangle {triangleIndex}, outside the active mesh.");
        var triangle = mesh.SurfaceTriangles[triangleIndex];
        return (mesh.Nodes[triangle[0]] + mesh.Nodes[triangle[1]] + mesh.Nodes[triangle[2]]) / 3.0;
    }

    private static Vec3 ToVec(RemoteVector3 value) => new(value.X, value.Y, value.Z);
    private static Vec3 Cross(Vec3 a, Vec3 b) => new(
        a.Y * b.Z - a.Z * b.Y,
        a.Z * b.X - a.X * b.Z,
        a.X * b.Y - a.Y * b.X);
    private static double TriangleArea(Vec3 a, Vec3 b, Vec3 c) => Cross(b - a, c - a).Length * 0.5;
}
