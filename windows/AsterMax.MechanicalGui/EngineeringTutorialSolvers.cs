namespace AsterMax.MechanicalGui;

internal sealed record MeshConvergencePoint(
    double ElementSizeMm,
    int Nodes,
    int Elements,
    double MaxDisplacementMm,
    double MaxVonMisesMpa,
    double DisplacementDifferencePercent,
    double StressDifferencePercent,
    double EquilibriumError,
    double SolveSeconds);

internal static class MeshConvergenceStudy
{
    public static IReadOnlyList<MeshConvergencePoint> Run(
        SimpleStepSolid solid,
        StaticMaterial material,
        SimpleStaticSetup setup,
        IEnumerable<double> elementSizes)
    {
        var raw = new List<(double Size, TetMesh Mesh, StaticSolution Solution)>();
        foreach (var size in elementSizes.Where(value => value > 0).Distinct().OrderByDescending(value => value))
        {
            var mesh = StructuredTetMesher.Generate(solid, size);
            var solution = Tet4LinearStaticSolver.Solve(solid, mesh, material, setup);
            raw.Add((size, mesh, solution));
        }
        if (raw.Count < 2) throw new InvalidOperationException("A convergence study requires at least two mesh sizes.");

        var reference = raw[^1].Solution;
        return raw.Select(item => new MeshConvergencePoint(
            item.Size,
            item.Mesh.Nodes.Count,
            item.Mesh.Elements.Count,
            item.Solution.MaxDisplacementMm,
            item.Solution.MaxVonMisesMpa,
            RelativePercent(item.Solution.MaxDisplacementMm, reference.MaxDisplacementMm),
            RelativePercent(item.Solution.MaxVonMisesMpa, reference.MaxVonMisesMpa),
            item.Solution.EquilibriumError,
            item.Solution.Elapsed.TotalSeconds)).ToArray();
    }

    private static double RelativePercent(double value, double reference) =>
        Math.Abs(reference) < 1e-15 ? 0 : Math.Abs(value - reference) / Math.Abs(reference) * 100.0;
}

internal sealed record DesignPointResult(
    int Index,
    double ForceMagnitudeN,
    double YoungModulusMpa,
    double ElementSizeMm,
    double MaxDisplacementMm,
    double MaxVonMisesMpa,
    double SafetyFactor,
    double EquilibriumError);

internal static class StaticDesignPointStudy
{
    public static IReadOnlyList<DesignPointResult> Run(
        SimpleStepSolid solid,
        StaticMaterial baseMaterial,
        SimpleStaticSetup baseSetup,
        IEnumerable<double> forceMagnitudes)
    {
        var directionLength = baseSetup.ForceN.Length;
        if (directionLength <= 1e-12) throw new InvalidOperationException("The base force direction is undefined.");
        var direction = baseSetup.ForceN / directionLength;
        var mesh = StructuredTetMesher.Generate(solid, baseSetup.ElementSizeMm);
        var results = new List<DesignPointResult>();
        var index = 1;
        foreach (var magnitude in forceMagnitudes.Where(value => value > 0))
        {
            var setup = new SimpleStaticSetup
            {
                ElementSizeMm = baseSetup.ElementSizeMm,
                FixedFace = baseSetup.FixedFace,
                LoadFace = baseSetup.LoadFace,
                ForceN = direction * magnitude
            };
            var material = new StaticMaterial
            {
                Name = baseMaterial.Name,
                YoungModulusMpa = baseMaterial.YoungModulusMpa,
                PoissonRatio = baseMaterial.PoissonRatio,
                YieldStrengthMpa = baseMaterial.YieldStrengthMpa
            };
            var solution = Tet4LinearStaticSolver.Solve(solid, mesh, material, setup);
            results.Add(new DesignPointResult(
                index++, magnitude, material.YoungModulusMpa, setup.ElementSizeMm,
                solution.MaxDisplacementMm, solution.MaxVonMisesMpa,
                solution.MaxVonMisesMpa > 0 ? material.YieldStrengthMpa / solution.MaxVonMisesMpa : double.PositiveInfinity,
                solution.EquilibriumError));
        }
        return results;
    }
}

internal sealed class BeamModalSetup
{
    public double DensityKgM3 { get; set; } = 7850.0;
    public int BeamElements { get; set; } = 16;
    public int RequestedModes { get; set; } = 6;
}

internal sealed record BeamModeResult(
    int Mode,
    double FrequencyHz,
    double AnalyticalFrequencyHz,
    double DifferencePercent,
    double[] NormalizedDeflection);

internal static class EulerBernoulliModalSolver
{
    private static readonly double[] Beta = [1.8751040687, 4.6940911330, 7.8547574382, 10.995540735, 14.137168391, 17.278759532];

    public static IReadOnlyList<BeamModeResult> Solve(
        SimpleStepSolid solid,
        StaticMaterial material,
        BeamModalSetup setup)
    {
        if (solid.LengthX <= 0 || solid.LengthY <= 0 || solid.LengthZ <= 0)
            throw new InvalidOperationException("Modal analysis requires positive beam dimensions.");
        if (solid.LengthX < 2.0 * Math.Max(solid.LengthY, solid.LengthZ))
            throw new InvalidOperationException("The modal tutorial requires a slender prism aligned with X.");
        if (setup.DensityKgM3 <= 0 || setup.BeamElements < 2 || setup.RequestedModes < 1)
            throw new InvalidOperationException("Density, element count and mode count must be positive.");

        var length = solid.LengthX / 1000.0;
        var width = solid.LengthY / 1000.0;
        var height = solid.LengthZ / 1000.0;
        var area = width * height;
        var inertia = width * Math.Pow(height, 3) / 12.0;
        var young = material.YoungModulusMpa * 1e6;
        var elementCount = Math.Clamp(setup.BeamElements, 2, 40);
        var nodeCount = elementCount + 1;
        var fullDofs = nodeCount * 2;
        var k = new double[fullDofs, fullDofs];
        var m = new double[fullDofs, fullDofs];
        var le = length / elementCount;
        var stiffnessScale = young * inertia / Math.Pow(le, 3);
        var massScale = setup.DensityKgM3 * area * le / 420.0;
        var ke = new[,]
        {
            { 12.0, 6.0 * le, -12.0, 6.0 * le },
            { 6.0 * le, 4.0 * le * le, -6.0 * le, 2.0 * le * le },
            { -12.0, -6.0 * le, 12.0, -6.0 * le },
            { 6.0 * le, 2.0 * le * le, -6.0 * le, 4.0 * le * le }
        };
        var me = new[,]
        {
            { 156.0, 22.0 * le, 54.0, -13.0 * le },
            { 22.0 * le, 4.0 * le * le, 13.0 * le, -3.0 * le * le },
            { 54.0, 13.0 * le, 156.0, -22.0 * le },
            { -13.0 * le, -3.0 * le * le, -22.0 * le, 4.0 * le * le }
        };

        for (var element = 0; element < elementCount; element++)
        {
            var map = new[] { element * 2, element * 2 + 1, element * 2 + 2, element * 2 + 3 };
            for (var row = 0; row < 4; row++)
            for (var column = 0; column < 4; column++)
            {
                k[map[row], map[column]] += stiffnessScale * ke[row, column];
                m[map[row], map[column]] += massScale * me[row, column];
            }
        }

        var free = Enumerable.Range(2, fullDofs - 2).ToArray();
        var kr = DenseTutorialMath.Submatrix(k, free);
        var mr = DenseTutorialMath.Submatrix(m, free);
        var (eigenvalues, eigenvectors) = DenseTutorialMath.GeneralizedSymmetricEigen(kr, mr);
        var positive = eigenvalues.Select((value, index) => (value, index))
            .Where(item => item.value > 1e-8 && double.IsFinite(item.value))
            .OrderBy(item => item.value)
            .Take(Math.Min(setup.RequestedModes, Beta.Length))
            .ToArray();
        if (positive.Length == 0) throw new InvalidOperationException("No positive modal eigenvalues were obtained.");

        var results = new List<BeamModeResult>();
        for (var mode = 0; mode < positive.Length; mode++)
        {
            var eigen = positive[mode];
            var frequency = Math.Sqrt(eigen.value) / (2.0 * Math.PI);
            var analytical = Math.Pow(Beta[mode], 2) / (2.0 * Math.PI * length * length) *
                             Math.Sqrt(young * inertia / (setup.DensityKgM3 * area));
            var deflection = new double[nodeCount];
            for (var node = 1; node < nodeCount; node++)
                deflection[node] = eigenvectors[(node - 1) * 2, eigen.index];
            var maximum = deflection.Select(Math.Abs).DefaultIfEmpty(1).Max();
            if (maximum > 1e-15)
                for (var node = 0; node < deflection.Length; node++) deflection[node] /= maximum;
            results.Add(new BeamModeResult(
                mode + 1,
                frequency,
                analytical,
                Math.Abs(frequency - analytical) / analytical * 100.0,
                deflection));
        }
        return results;
    }
}

internal sealed class ThermalSetup
{
    public double ConductivityWmK { get; set; } = 45.0;
    public SimpleFace HotFace { get; set; } = SimpleFace.XMin;
    public SimpleFace ColdFace { get; set; } = SimpleFace.XMax;
    public double HotTemperatureC { get; set; } = 100.0;
    public double ColdTemperatureC { get; set; } = 20.0;
}

internal sealed class ThermalSolution
{
    public required double[] NodalTemperatureC { get; init; }
    public required double[] ElementHeatFluxWm2 { get; init; }
    public required double MinimumTemperatureC { get; init; }
    public required double MaximumTemperatureC { get; init; }
    public required double HeatFlowW { get; init; }
    public required double AnalyticalHeatFlowW { get; init; }
    public required double HeatFlowDifferencePercent { get; init; }
    public required double MaximumHeatFluxWm2 { get; init; }
    public required double EnergyBalanceError { get; init; }
}

internal static class Tet4SteadyThermalSolver
{
    public static ThermalSolution Solve(SimpleStepSolid solid, TetMesh mesh, ThermalSetup setup)
    {
        if (setup.ConductivityWmK <= 0) throw new InvalidOperationException("Thermal conductivity must be positive.");
        if (setup.HotFace == setup.ColdFace) throw new InvalidOperationException("Hot and cold faces must be different.");
        if (Math.Abs(setup.HotTemperatureC - setup.ColdTemperatureC) < 1e-12)
            throw new InvalidOperationException("Hot and cold temperatures must be different.");

        var count = mesh.Nodes.Count;
        var conductivity = new double[count, count];
        var gradients = new List<double[,]>(mesh.Elements.Count);
        var volumes = new List<double>(mesh.Elements.Count);
        foreach (var element in mesh.Elements)
        {
            var points = element.Select(index => mesh.Nodes[index] / 1000.0).ToArray();
            var (gradient, volume) = GradientMatrix(points);
            gradients.Add(gradient);
            volumes.Add(volume);
            for (var localRow = 0; localRow < 4; localRow++)
            for (var localColumn = 0; localColumn < 4; localColumn++)
            {
                var dot = 0.0;
                for (var axis = 0; axis < 3; axis++) dot += gradient[axis, localRow] * gradient[axis, localColumn];
                conductivity[element[localRow], element[localColumn]] += setup.ConductivityWmK * volume * dot;
            }
        }

        var hot = Tet4LinearStaticSolver.FaceNodes(solid, mesh, setup.HotFace);
        var cold = Tet4LinearStaticSolver.FaceNodes(solid, mesh, setup.ColdFace);
        var fixedValues = new Dictionary<int, double>();
        foreach (var node in hot) fixedValues[node] = setup.HotTemperatureC;
        foreach (var node in cold) fixedValues[node] = setup.ColdTemperatureC;
        var free = Enumerable.Range(0, count).Where(index => !fixedValues.ContainsKey(index)).ToArray();
        var temperature = new double[count];
        foreach (var pair in fixedValues) temperature[pair.Key] = pair.Value;

        if (free.Length > 0)
        {
            var reduced = new double[free.Length, free.Length];
            var rhs = new double[free.Length];
            for (var row = 0; row < free.Length; row++)
            {
                for (var column = 0; column < free.Length; column++)
                    reduced[row, column] = conductivity[free[row], free[column]];
                foreach (var pair in fixedValues) rhs[row] -= conductivity[free[row], pair.Key] * pair.Value;
            }
            var solved = DenseTutorialMath.SolveCholesky(reduced, rhs);
            for (var index = 0; index < free.Length; index++) temperature[free[index]] = solved[index];
        }

        var residual = DenseTutorialMath.Multiply(conductivity, temperature);
        var hotFlow = hot.Sum(node => residual[node]);
        var coldFlow = cold.Sum(node => residual[node]);
        var heatFlow = Math.Abs(hotFlow);
        var balance = Math.Abs(hotFlow + coldFlow) / Math.Max(heatFlow, 1e-12);
        var flux = new double[mesh.Elements.Count];
        for (var elementIndex = 0; elementIndex < mesh.Elements.Count; elementIndex++)
        {
            var element = mesh.Elements[elementIndex];
            var gradientTemperature = Vec3.Zero;
            for (var local = 0; local < 4; local++)
            {
                var value = temperature[element[local]];
                gradientTemperature += new Vec3(
                    gradients[elementIndex][0, local] * value,
                    gradients[elementIndex][1, local] * value,
                    gradients[elementIndex][2, local] * value);
            }
            flux[elementIndex] = setup.ConductivityWmK * gradientTemperature.Length;
        }

        var analytical = AnalyticalHeatFlow(solid, setup);
        var difference = analytical > 1e-15 ? Math.Abs(heatFlow - analytical) / analytical * 100.0 : double.NaN;
        return new ThermalSolution
        {
            NodalTemperatureC = temperature,
            ElementHeatFluxWm2 = flux,
            MinimumTemperatureC = temperature.Min(),
            MaximumTemperatureC = temperature.Max(),
            HeatFlowW = heatFlow,
            AnalyticalHeatFlowW = analytical,
            HeatFlowDifferencePercent = difference,
            MaximumHeatFluxWm2 = flux.DefaultIfEmpty(0).Max(),
            EnergyBalanceError = balance
        };
    }

    private static double AnalyticalHeatFlow(SimpleStepSolid solid, ThermalSetup setup)
    {
        var delta = Math.Abs(setup.HotTemperatureC - setup.ColdTemperatureC);
        return (setup.HotFace, setup.ColdFace) switch
        {
            (SimpleFace.XMin, SimpleFace.XMax) or (SimpleFace.XMax, SimpleFace.XMin) =>
                setup.ConductivityWmK * (solid.LengthY * solid.LengthZ / 1e6) * delta / (solid.LengthX / 1000.0),
            (SimpleFace.YMin, SimpleFace.YMax) or (SimpleFace.YMax, SimpleFace.YMin) =>
                setup.ConductivityWmK * (solid.LengthX * solid.LengthZ / 1e6) * delta / (solid.LengthY / 1000.0),
            (SimpleFace.ZMin, SimpleFace.ZMax) or (SimpleFace.ZMax, SimpleFace.ZMin) =>
                setup.ConductivityWmK * (solid.LengthX * solid.LengthY / 1e6) * delta / (solid.LengthZ / 1000.0),
            _ => double.NaN
        };
    }

    private static (double[,] Gradient, double Volume) GradientMatrix(IReadOnlyList<Vec3> point)
    {
        var coordinates = new double[4, 4];
        for (var row = 0; row < 4; row++)
        {
            coordinates[row, 0] = 1.0;
            coordinates[row, 1] = point[row].X;
            coordinates[row, 2] = point[row].Y;
            coordinates[row, 3] = point[row].Z;
        }
        var inverse = DenseTutorialMath.Invert4x4(coordinates);
        var gradient = new double[3, 4];
        for (var node = 0; node < 4; node++)
        {
            gradient[0, node] = inverse[1, node];
            gradient[1, node] = inverse[2, node];
            gradient[2, node] = inverse[3, node];
        }
        var volume = Math.Abs(DenseTutorialMath.Dot(point[1] - point[0], DenseTutorialMath.Cross(point[2] - point[0], point[3] - point[0]))) / 6.0;
        if (volume <= 1e-18) throw new InvalidOperationException("A zero-volume thermal element was generated.");
        return (gradient, volume);
    }
}

internal static class DenseTutorialMath
{
    public static double[,] Submatrix(double[,] source, IReadOnlyList<int> indices)
    {
        var result = new double[indices.Count, indices.Count];
        for (var row = 0; row < indices.Count; row++)
        for (var column = 0; column < indices.Count; column++)
            result[row, column] = source[indices[row], indices[column]];
        return result;
    }

    public static double[] Multiply(double[,] matrix, double[] vector)
    {
        var result = new double[matrix.GetLength(0)];
        for (var row = 0; row < result.Length; row++)
        for (var column = 0; column < vector.Length; column++)
            result[row] += matrix[row, column] * vector[column];
        return result;
    }

    public static double[] SolveCholesky(double[,] matrix, double[] rhs)
    {
        var lower = Cholesky(matrix);
        var size = rhs.Length;
        var y = new double[size];
        for (var row = 0; row < size; row++)
        {
            var sum = rhs[row];
            for (var column = 0; column < row; column++) sum -= lower[row, column] * y[column];
            y[row] = sum / lower[row, row];
        }
        var x = new double[size];
        for (var row = size - 1; row >= 0; row--)
        {
            var sum = y[row];
            for (var column = row + 1; column < size; column++) sum -= lower[column, row] * x[column];
            x[row] = sum / lower[row, row];
        }
        return x;
    }

    public static (double[] Eigenvalues, double[,] Eigenvectors) GeneralizedSymmetricEigen(double[,] stiffness, double[,] mass)
    {
        var lower = Cholesky(mass);
        var inverseLower = InvertLower(lower);
        var transformed = Multiply(Multiply(inverseLower, stiffness), Transpose(inverseLower));
        Symmetrize(transformed);
        var (values, vectors) = Jacobi(transformed);
        var physicalVectors = Multiply(Transpose(inverseLower), vectors);
        return (values, physicalVectors);
    }

    private static double[,] Cholesky(double[,] matrix)
    {
        var size = matrix.GetLength(0);
        var lower = new double[size, size];
        var maximum = Enumerable.Range(0, size).Select(index => Math.Abs(matrix[index, index])).DefaultIfEmpty(1).Max();
        var tolerance = Math.Max(1e-18, maximum * 1e-13);
        for (var row = 0; row < size; row++)
        for (var column = 0; column <= row; column++)
        {
            var sum = matrix[row, column];
            for (var inner = 0; inner < column; inner++) sum -= lower[row, inner] * lower[column, inner];
            if (row == column)
            {
                if (sum <= tolerance) throw new InvalidOperationException("The matrix is singular or not positive definite.");
                lower[row, column] = Math.Sqrt(sum);
            }
            else lower[row, column] = sum / lower[column, column];
        }
        return lower;
    }

    private static double[,] InvertLower(double[,] lower)
    {
        var size = lower.GetLength(0);
        var inverse = new double[size, size];
        for (var column = 0; column < size; column++)
        {
            for (var row = 0; row < size; row++)
            {
                var sum = row == column ? 1.0 : 0.0;
                for (var inner = 0; inner < row; inner++) sum -= lower[row, inner] * inverse[inner, column];
                inverse[row, column] = sum / lower[row, row];
            }
        }
        return inverse;
    }

    private static (double[] Values, double[,] Vectors) Jacobi(double[,] source)
    {
        var size = source.GetLength(0);
        var matrix = (double[,])source.Clone();
        var vectors = Identity(size);
        var scale = Enumerable.Range(0, size).Select(index => Math.Abs(matrix[index, index])).DefaultIfEmpty(1).Max();
        var tolerance = Math.Max(1e-13, scale * 1e-12);
        var iterations = Math.Max(100, size * size * 40);
        for (var iteration = 0; iteration < iterations; iteration++)
        {
            var p = 0;
            var q = 1;
            var maximum = 0.0;
            for (var row = 0; row < size; row++)
            for (var column = row + 1; column < size; column++)
                if (Math.Abs(matrix[row, column]) > maximum)
                {
                    maximum = Math.Abs(matrix[row, column]);
                    p = row;
                    q = column;
                }
            if (maximum < tolerance) break;
            var angle = 0.5 * Math.Atan2(2.0 * matrix[p, q], matrix[q, q] - matrix[p, p]);
            var cosine = Math.Cos(angle);
            var sine = Math.Sin(angle);
            for (var index = 0; index < size; index++)
            {
                if (index == p || index == q) continue;
                var aip = matrix[index, p];
                var aiq = matrix[index, q];
                matrix[index, p] = matrix[p, index] = cosine * aip - sine * aiq;
                matrix[index, q] = matrix[q, index] = sine * aip + cosine * aiq;
            }
            var app = matrix[p, p];
            var aqq = matrix[q, q];
            var apq = matrix[p, q];
            matrix[p, p] = cosine * cosine * app - 2.0 * sine * cosine * apq + sine * sine * aqq;
            matrix[q, q] = sine * sine * app + 2.0 * sine * cosine * apq + cosine * cosine * aqq;
            matrix[p, q] = matrix[q, p] = 0.0;
            for (var row = 0; row < size; row++)
            {
                var vip = vectors[row, p];
                var viq = vectors[row, q];
                vectors[row, p] = cosine * vip - sine * viq;
                vectors[row, q] = sine * vip + cosine * viq;
            }
        }
        var values = Enumerable.Range(0, size).Select(index => matrix[index, index]).ToArray();
        return (values, vectors);
    }

    private static double[,] Identity(int size)
    {
        var result = new double[size, size];
        for (var index = 0; index < size; index++) result[index, index] = 1.0;
        return result;
    }

    private static double[,] Multiply(double[,] left, double[,] right)
    {
        var result = new double[left.GetLength(0), right.GetLength(1)];
        for (var row = 0; row < result.GetLength(0); row++)
        for (var inner = 0; inner < left.GetLength(1); inner++)
        for (var column = 0; column < result.GetLength(1); column++)
            result[row, column] += left[row, inner] * right[inner, column];
        return result;
    }

    private static double[,] Transpose(double[,] matrix)
    {
        var result = new double[matrix.GetLength(1), matrix.GetLength(0)];
        for (var row = 0; row < matrix.GetLength(0); row++)
        for (var column = 0; column < matrix.GetLength(1); column++) result[column, row] = matrix[row, column];
        return result;
    }

    private static void Symmetrize(double[,] matrix)
    {
        for (var row = 0; row < matrix.GetLength(0); row++)
        for (var column = row + 1; column < matrix.GetLength(1); column++)
            matrix[row, column] = matrix[column, row] = (matrix[row, column] + matrix[column, row]) / 2.0;
    }

    public static double[,] Invert4x4(double[,] input)
    {
        const int size = 4;
        var augmented = new double[size, size * 2];
        for (var row = 0; row < size; row++)
        for (var column = 0; column < size; column++)
        {
            augmented[row, column] = input[row, column];
            augmented[row, column + size] = row == column ? 1.0 : 0.0;
        }
        for (var column = 0; column < size; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < size; row++)
                if (Math.Abs(augmented[row, column]) > Math.Abs(augmented[pivot, column])) pivot = row;
            if (Math.Abs(augmented[pivot, column]) < 1e-20) throw new InvalidOperationException("Degenerate tetrahedron.");
            if (pivot != column)
                for (var entry = 0; entry < size * 2; entry++)
                    (augmented[column, entry], augmented[pivot, entry]) = (augmented[pivot, entry], augmented[column, entry]);
            var divisor = augmented[column, column];
            for (var entry = 0; entry < size * 2; entry++) augmented[column, entry] /= divisor;
            for (var row = 0; row < size; row++)
            {
                if (row == column) continue;
                var factor = augmented[row, column];
                for (var entry = 0; entry < size * 2; entry++) augmented[row, entry] -= factor * augmented[column, entry];
            }
        }
        var inverse = new double[size, size];
        for (var row = 0; row < size; row++)
        for (var column = 0; column < size; column++) inverse[row, column] = augmented[row, column + size];
        return inverse;
    }

    public static Vec3 Cross(Vec3 a, Vec3 b) =>
        new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);

    public static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}
