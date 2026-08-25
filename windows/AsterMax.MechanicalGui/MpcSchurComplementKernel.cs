namespace AsterMax.MechanicalGui;

internal sealed record LinearSystemSolveResult(
    double[] Solution,
    int Iterations,
    double RelativeResidual);

internal sealed record MpcConstraintRow(
    string Name,
    IReadOnlyDictionary<int, double> Coefficients,
    double RightHandSide);

internal sealed record MpcSchurSolveResult(
    double[] Solution,
    double[] Multipliers,
    int TotalLinearIterations,
    double MaximumLinearResidual,
    double MaximumConstraintResidual);

/// <summary>
/// Exact linear multi-point constraint enforcement for an SPD base system K u = f.
/// The kernel preserves the existing SPD solver by using the Schur complement
/// S = C K^-1 C^T instead of assembling an indefinite KKT matrix.
/// </summary>
internal static class MpcSchurComplementKernel
{
    public static MpcSchurSolveResult Solve(
        int unknownCount,
        IReadOnlyList<double> rightHandSide,
        IReadOnlyList<MpcConstraintRow> constraints,
        Func<double[], LinearSystemSolveResult> solveBaseSystem)
    {
        if (unknownCount <= 0)
            throw new ArgumentOutOfRangeException(nameof(unknownCount));
        ArgumentNullException.ThrowIfNull(rightHandSide);
        ArgumentNullException.ThrowIfNull(constraints);
        ArgumentNullException.ThrowIfNull(solveBaseSystem);

        if (rightHandSide.Count != unknownCount)
            throw new InvalidOperationException("MPC base-system right-hand side has an invalid length.");
        if (rightHandSide.Any(value => !double.IsFinite(value)))
            throw new InvalidOperationException("MPC base-system right-hand side contains a non-finite value.");
        if (constraints.Count == 0)
        {
            var unconstrainedOnly = ValidateLinearSolve(solveBaseSystem(rightHandSide.ToArray()), unknownCount, "base system");
            return new MpcSchurSolveResult(
                unconstrainedOnly.Solution,
                Array.Empty<double>(),
                unconstrainedOnly.Iterations,
                unconstrainedOnly.RelativeResidual,
                0.0);
        }

        var normalizedRows = constraints
            .Select(row => NormalizeRow(row, unknownCount))
            .ToArray();

        var baseSolve = ValidateLinearSolve(solveBaseSystem(rightHandSide.ToArray()), unknownCount, "base system");
        var totalIterations = baseSolve.Iterations;
        var maximumLinearResidual = baseSolve.RelativeResidual;

        var influenceSolutions = new double[normalizedRows.Length][];
        for (var constraintIndex = 0; constraintIndex < normalizedRows.Length; constraintIndex++)
        {
            var row = normalizedRows[constraintIndex];
            var transposeColumn = new double[unknownCount];
            foreach (var (index, coefficient) in row.Coefficients)
                transposeColumn[index] = coefficient;

            var influence = ValidateLinearSolve(
                solveBaseSystem(transposeColumn),
                unknownCount,
                $"constraint influence '{row.Name}'");
            influenceSolutions[constraintIndex] = influence.Solution;
            totalIterations += influence.Iterations;
            maximumLinearResidual = Math.Max(maximumLinearResidual, influence.RelativeResidual);
        }

        var schur = new double[normalizedRows.Length, normalizedRows.Length];
        var mismatch = new double[normalizedRows.Length];
        for (var rowIndex = 0; rowIndex < normalizedRows.Length; rowIndex++)
        {
            var row = normalizedRows[rowIndex];
            mismatch[rowIndex] = SparseDot(row.Coefficients, baseSolve.Solution) - row.RightHandSide;
            for (var columnIndex = 0; columnIndex < normalizedRows.Length; columnIndex++)
                schur[rowIndex, columnIndex] = SparseDot(row.Coefficients, influenceSolutions[columnIndex]);
        }

        SymmetrizeSchur(schur);
        var multipliers = SolvePositiveDefiniteDense(
            schur,
            mismatch,
            "MPC Schur complement. Constraints may be dependent, contradictory or poorly scaled.");

        var constrainedSolution = (double[])baseSolve.Solution.Clone();
        for (var constraintIndex = 0; constraintIndex < normalizedRows.Length; constraintIndex++)
        {
            var multiplier = multipliers[constraintIndex];
            var influence = influenceSolutions[constraintIndex];
            for (var index = 0; index < constrainedSolution.Length; index++)
                constrainedSolution[index] -= influence[index] * multiplier;
        }

        var maximumConstraintResidual = 0.0;
        for (var rowIndex = 0; rowIndex < normalizedRows.Length; rowIndex++)
        {
            var row = normalizedRows[rowIndex];
            var residual = SparseDot(row.Coefficients, constrainedSolution) - row.RightHandSide;
            if (!double.IsFinite(residual))
                throw new InvalidOperationException($"MPC constraint '{row.Name}' produced a non-finite residual.");
            maximumConstraintResidual = Math.Max(maximumConstraintResidual, Math.Abs(residual));
        }

        return new MpcSchurSolveResult(
            constrainedSolution,
            multipliers,
            totalIterations,
            maximumLinearResidual,
            maximumConstraintResidual);
    }

    private static MpcConstraintRow NormalizeRow(MpcConstraintRow row, int unknownCount)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(row.Coefficients);

        if (string.IsNullOrWhiteSpace(row.Name))
            throw new InvalidOperationException("MPC constraint name cannot be empty.");
        if (!double.IsFinite(row.RightHandSide))
            throw new InvalidOperationException($"MPC constraint '{row.Name}' contains a non-finite right-hand side.");
        if (row.Coefficients.Count == 0)
            throw new InvalidOperationException($"MPC constraint '{row.Name}' has no coefficients.");

        var normalized = new SortedDictionary<int, double>();
        foreach (var (index, coefficient) in row.Coefficients)
        {
            if ((uint)index >= (uint)unknownCount)
                throw new InvalidOperationException($"MPC constraint '{row.Name}' references unknown {index}, outside the reduced system.");
            if (!double.IsFinite(coefficient) || coefficient == 0.0)
                throw new InvalidOperationException($"MPC constraint '{row.Name}' requires finite non-zero coefficients.");
            normalized[index] = normalized.GetValueOrDefault(index) + coefficient;
        }

        foreach (var key in normalized.Where(pair => Math.Abs(pair.Value) <= 1e-15).Select(pair => pair.Key).ToArray())
            normalized.Remove(key);
        if (normalized.Count == 0)
            throw new InvalidOperationException($"MPC constraint '{row.Name}' is algebraically empty after coefficient normalization.");

        var norm = Math.Sqrt(normalized.Values.Sum(value => value * value));
        if (!double.IsFinite(norm) || norm <= 1e-15)
            throw new InvalidOperationException($"MPC constraint '{row.Name}' has an invalid coefficient norm.");

        // Normalize each row so Schur rank checks are not dominated by arbitrary coefficient scale.
        var scaled = normalized.ToDictionary(pair => pair.Key, pair => pair.Value / norm);
        return new MpcConstraintRow(row.Name.Trim(), scaled, row.RightHandSide / norm);
    }

    private static LinearSystemSolveResult ValidateLinearSolve(
        LinearSystemSolveResult result,
        int expectedLength,
        string context)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(result.Solution);
        if (result.Solution.Length != expectedLength)
            throw new InvalidOperationException($"The {context} returned an invalid solution length.");
        if (result.Solution.Any(value => !double.IsFinite(value)))
            throw new InvalidOperationException($"The {context} returned a non-finite solution.");
        if (result.Iterations < 0)
            throw new InvalidOperationException($"The {context} returned an invalid iteration count.");
        if (!double.IsFinite(result.RelativeResidual) || result.RelativeResidual < 0.0)
            throw new InvalidOperationException($"The {context} returned an invalid relative residual.");
        return result;
    }

    private static double SparseDot(IReadOnlyDictionary<int, double> coefficients, IReadOnlyList<double> vector)
    {
        var sum = 0.0;
        foreach (var (index, coefficient) in coefficients)
            sum += coefficient * vector[index];
        return sum;
    }

    private static void SymmetrizeSchur(double[,] matrix)
    {
        for (var row = 0; row < matrix.GetLength(0); row++)
        {
            if (!double.IsFinite(matrix[row, row]))
                throw new InvalidOperationException("MPC Schur complement contains a non-finite diagonal entry.");
            for (var column = row + 1; column < matrix.GetLength(1); column++)
            {
                var average = 0.5 * (matrix[row, column] + matrix[column, row]);
                if (!double.IsFinite(average))
                    throw new InvalidOperationException("MPC Schur complement contains a non-finite entry.");
                matrix[row, column] = average;
                matrix[column, row] = average;
            }
        }
    }

    private static double[] SolvePositiveDefiniteDense(double[,] matrix, IReadOnlyList<double> rightHandSide, string failureContext)
    {
        var size = matrix.GetLength(0);
        if (size == 0 || matrix.GetLength(1) != size || rightHandSide.Count != size)
            throw new InvalidOperationException("MPC Schur complement has inconsistent dimensions.");

        var diagonalScale = Enumerable.Range(0, size)
            .Select(index => Math.Abs(matrix[index, index]))
            .DefaultIfEmpty(1.0)
            .Max();
        var pivotTolerance = Math.Max(1e-14, diagonalScale * 1e-12);
        var lower = new double[size, size];

        for (var row = 0; row < size; row++)
        {
            for (var column = 0; column <= row; column++)
            {
                var sum = matrix[row, column];
                for (var inner = 0; inner < column; inner++)
                    sum -= lower[row, inner] * lower[column, inner];

                if (row == column)
                {
                    if (!double.IsFinite(sum) || sum <= pivotTolerance)
                        throw new InvalidOperationException(failureContext);
                    lower[row, column] = Math.Sqrt(sum);
                }
                else
                {
                    lower[row, column] = sum / lower[column, column];
                }
            }
        }

        var forward = new double[size];
        for (var row = 0; row < size; row++)
        {
            var value = rightHandSide[row];
            for (var column = 0; column < row; column++)
                value -= lower[row, column] * forward[column];
            forward[row] = value / lower[row, row];
        }

        var solution = new double[size];
        for (var row = size - 1; row >= 0; row--)
        {
            var value = forward[row];
            for (var column = row + 1; column < size; column++)
                value -= lower[column, row] * solution[column];
            solution[row] = value / lower[row, row];
        }

        if (solution.Any(value => !double.IsFinite(value)))
            throw new InvalidOperationException("MPC Schur solve returned a non-finite multiplier.");
        return solution;
    }
}
