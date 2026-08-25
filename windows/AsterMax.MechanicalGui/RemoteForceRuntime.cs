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
    private const double RankTolerance = 1e-11;

    public static RemoteForceSurfaceLoadSet Build(
        CadMesh mesh,
        NamedSelectionCatalog selections,
        string activeGeometrySignature,
        RemoteBoundaryConditionDefinition condition)
    {
        ArgumentNullException.ThrowIfNull(mesh);
        ArgumentNullException.ThrowIfNull(selections);
        ArgumentNullException.ThrowIfNull(condition);

        condition.Validate(selections, activeGeometrySignature);
        if (condition.Type != RemoteBoundaryConditionType.Force)
            throw new InvalidOperationException($"Remote runtime '{condition.Name}' is not a Remote Force.");
        if (condition.Coupling.Behavior != RemoteCouplingBehavior.Deformable)
            throw new InvalidOperationException(
                $"Remote Force '{condition.Name}' requests rigid coupling. " +
                "The current runtime slice certifies deformable load transfer only; rigid remote kinematics require remote-point MPC DOFs.");

        var scopeDefinition = selections.Get(condition.ScopeSelectionId);
        if (scopeDefinition.EntityType != NamedSelectionEntityType.Face)
            throw new InvalidOperationException(
                $"Remote Force runtime currently requires a face-based named selection, not {scopeDefinition.EntityType}.");
        var scope = selections.Resolve(condition.ScopeSelectionId, activeGeometrySignature);
        var triangles = ResolveScopedTriangles(mesh, scope);
        if (triangles.Count < 2)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' requires at least two scoped surface triangles.");

        var remotePoint = new Vec3(condition.RemotePoint.X, condition.RemotePoint.Y, condition.RemotePoint.Z);
        var requestedForce = ResolveForceVector(condition);
        if (!double.IsFinite(requestedForce.Length) || requestedForce.Length <= 1e-12)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' resolves to a zero or invalid global force vector.");

        var centroids = triangles.Select(index => TriangleCentroid(mesh, index)).ToArray();
        var weights = BuildWeights(mesh, triangles, centroids, remotePoint, condition.Coupling);
        var equivalentForces = SolveEquivalentTriangleForces(
            centroids,
            weights,
            remotePoint,
            requestedForce,
            condition.Name);

        var resultant = Vec3.Zero;
        var momentAboutRemote = Vec3.Zero;
        var surfaceForces = new List<CadSurfaceForce>(triangles.Count);
        for (var index = 0; index < triangles.Count; index++)
        {
            var force = equivalentForces[index];
            resultant += force;
            momentAboutRemote += Cross(centroids[index] - remotePoint, force);
            surfaceForces.Add(new CadSurfaceForce(
                new[] { triangles[index] },
                force,
                $"{condition.Name} / triangle {triangles[index] + 1}"));
        }

        var forceError = (resultant - requestedForce).Length / Math.Max(requestedForce.Length, 1.0);
        var characteristicLength = centroids
            .Select(point => (point - remotePoint).Length)
            .DefaultIfEmpty(1.0)
            .Max();
        var momentScale = Math.Max(requestedForce.Length * Math.Max(characteristicLength, 1.0), 1.0);
        var momentError = momentAboutRemote.Length / momentScale;
        if (!double.IsFinite(forceError) || forceError > 1e-10)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' failed force conservation: {forceError:E3}.");
        if (!double.IsFinite(momentError) || momentError > 1e-10)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' failed moment conservation about its remote point: {momentError:E3}.");

        return new RemoteForceSurfaceLoadSet(
            condition.Name,
            surfaceForces,
            remotePoint,
            requestedForce,
            forceError,
            momentError);
    }

    private static IReadOnlyList<int> ResolveScopedTriangles(CadMesh mesh, MechanicalScope scope)
    {
        var topology = CadTopologyRegistry.Get(mesh);
        var triangles = new SortedSet<int>();
        foreach (var faceId in scope.FaceIds)
        {
            if (!topology.Faces.TryGetValue(faceId, out var face))
                throw new InvalidOperationException($"Remote Force face scope references Face {faceId}, absent from the active mesh.");
            foreach (var triangleIndex in face.TriangleIndices)
                triangles.Add(triangleIndex);
        }
        return triangles.ToArray();
    }

    private static Vec3 ResolveForceVector(RemoteBoundaryConditionDefinition condition)
    {
        var components = condition.Components;
        var local = new Vec3(components.X ?? 0.0, components.Y ?? 0.0, components.Z ?? 0.0);
        if (condition.CoordinateFrame.UseGlobalAxes)
            return local;

        var primary = ToVec(condition.CoordinateFrame.PrimaryAxis!.Value);
        var secondary = ToVec(condition.CoordinateFrame.SecondaryAxis!.Value);
        var x = primary / primary.Length;
        var y = secondary / secondary.Length;
        var z = Cross(x, y);
        var zLength = z.Length;
        if (zLength <= 1e-12)
            throw new InvalidOperationException($"Remote Force '{condition.Name}' has a degenerate local coordinate frame.");
        z /= zLength;
        return x * local.X + y * local.Y + z * local.Z;
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
                throw new InvalidOperationException($"Unsupported Remote Force weighting {coupling.Weighting}.");
        }

        if (raw.Any(value => !double.IsFinite(value) || value <= 0.0))
            throw new InvalidOperationException("Remote Force weighting produced a non-positive or non-finite triangle weight.");
        var sum = raw.Sum();
        return raw.Select(value => value / sum).ToArray();
    }

    private static Vec3[] SolveEquivalentTriangleForces(
        IReadOnlyList<Vec3> centroids,
        IReadOnlyList<double> weights,
        Vec3 remotePoint,
        Vec3 requestedForce,
        string name)
    {
        var characteristicLength = centroids
            .Select(point => (point - remotePoint).Length)
            .Where(length => length > 1e-12)
            .DefaultIfEmpty(0.0)
            .Max();
        if (!double.IsFinite(characteristicLength) || characteristicLength <= 1e-12)
            throw new InvalidOperationException($"Remote Force '{name}' has no finite geometric lever arm relative to its remote point.");
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

            // Moment rows are divided by a characteristic length so all six equilibrium
            // equations have force units and the rank test is not geometry-scale dependent.
            a[3, column + 1] = -r.Z * inverseLength;
            a[3, column + 2] = r.Y * inverseLength;
            a[4, column] = r.Z * inverseLength;
            a[4, column + 2] = -r.X * inverseLength;
            a[5, column] = -r.Y * inverseLength;
            a[5, column + 1] = r.X * inverseLength;
        }

        // Weighted minimum-norm equivalent load: f = W A^T (A W A^T)^-1 b.
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

        var rhs = new[] { requestedForce.X, requestedForce.Y, requestedForce.Z, 0.0, 0.0, 0.0 };
        var multipliers = SolveDensePivoted(
            gram,
            rhs,
            $"Remote Force '{name}' scope cannot represent a full force/moment-equivalent transfer. " +
            "Use a surface with sufficient non-collinear triangle centroids or move the remote point.");

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
        for (var row = 0; row < size; row++) augmented[row, size] = rhs[row];
        var tolerance = Math.Max(1e-14, scale * RankTolerance);

        for (var column = 0; column < size; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < size; row++)
                if (Math.Abs(augmented[row, column]) > Math.Abs(augmented[pivot, column])) pivot = row;
            if (!double.IsFinite(augmented[pivot, column]) || Math.Abs(augmented[pivot, column]) <= tolerance)
                throw new InvalidOperationException(failureMessage);
            if (pivot != column)
                for (var entry = column; entry <= size; entry++)
                    (augmented[column, entry], augmented[pivot, entry]) = (augmented[pivot, entry], augmented[column, entry]);

            var divisor = augmented[column, column];
            for (var entry = column; entry <= size; entry++) augmented[column, entry] /= divisor;
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
            throw new InvalidOperationException($"Remote Force references boundary triangle {triangleIndex}, outside the active mesh.");
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
