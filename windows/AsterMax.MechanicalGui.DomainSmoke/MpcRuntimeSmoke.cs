using System.Runtime.CompilerServices;
using AsterMax.MechanicalGui;

internal static class MpcRuntimeSmoke
{
    [ModuleInitializer]
    internal static void Run()
    {
        RunTwoDofTieBenchmark();
        RunThreeDofChainBenchmark();
        RunDependentConstraintRejection();
        Console.WriteLine("PASS MPC runtime Schur kernel | 2-DOF tie + 3-DOF chain + equilibrium-force recovery + dependent-row rejection");
    }

    private static void RunTwoDofTieBenchmark()
    {
        static LinearSystemSolveResult SolveBase(double[] rhs)
        {
            if (rhs.Length != 2) throw new InvalidOperationException("2-DOF benchmark received an invalid RHS length.");
            return new LinearSystemSolveResult(
                new[]
                {
                    (2.0 * rhs[0] + rhs[1]) / 3.0,
                    (rhs[0] + 2.0 * rhs[1]) / 3.0
                },
                Iterations: 1,
                RelativeResidual: 0.0);
        }

        var result = MpcSchurComplementKernel.Solve(
            2,
            new[] { 1.0, 0.0 },
            new[]
            {
                new MpcConstraintRow(
                    "equal displacement",
                    new Dictionary<int, double> { [0] = 1.0, [1] = -1.0 },
                    0.0)
            },
            SolveBase);

        AssertNear(result.Solution[0], 0.5, 1e-12, "2-DOF u1");
        AssertNear(result.Solution[1], 0.5, 1e-12, "2-DOF u2");
        if (result.MaximumConstraintResidual > 1e-12)
            throw new InvalidOperationException($"2-DOF MPC residual too large: {result.MaximumConstraintResidual:E3}.");
        if (result.Multipliers.Length != 1 || !double.IsFinite(result.Multipliers[0]))
            throw new InvalidOperationException("2-DOF MPC multiplier was not recovered.");
        if (result.EquilibriumForces.Length != 2)
            throw new InvalidOperationException("2-DOF MPC equilibrium-force vector length mismatch.");
        AssertNear(result.EquilibriumForces[0], -0.5, 1e-12, "2-DOF equilibrium force 1");
        AssertNear(result.EquilibriumForces[1], 0.5, 1e-12, "2-DOF equilibrium force 2");
    }

    private static void RunThreeDofChainBenchmark()
    {
        static LinearSystemSolveResult SolveIdentity(double[] rhs) =>
            new((double[])rhs.Clone(), Iterations: 1, RelativeResidual: 0.0);

        var result = MpcSchurComplementKernel.Solve(
            3,
            new[] { 3.0, 0.0, 0.0 },
            new[]
            {
                new MpcConstraintRow(
                    "u1=u2",
                    new Dictionary<int, double> { [0] = 1.0, [1] = -1.0 },
                    0.0),
                new MpcConstraintRow(
                    "u2=u3",
                    new Dictionary<int, double> { [1] = 1.0, [2] = -1.0 },
                    0.0)
            },
            SolveIdentity);

        for (var index = 0; index < 3; index++)
            AssertNear(result.Solution[index], 1.0, 1e-12, $"3-DOF u{index + 1}");
        if (result.MaximumConstraintResidual > 1e-12)
            throw new InvalidOperationException($"3-DOF MPC residual too large: {result.MaximumConstraintResidual:E3}.");
        if (result.Multipliers.Length != 2)
            throw new InvalidOperationException("3-DOF MPC multiplier count mismatch.");
        if (result.EquilibriumForces.Length != 3)
            throw new InvalidOperationException("3-DOF MPC equilibrium-force vector length mismatch.");
        AssertNear(result.EquilibriumForces[0], -2.0, 1e-12, "3-DOF equilibrium force 1");
        AssertNear(result.EquilibriumForces[1], 1.0, 1e-12, "3-DOF equilibrium force 2");
        AssertNear(result.EquilibriumForces[2], 1.0, 1e-12, "3-DOF equilibrium force 3");
        AssertNear(result.EquilibriumForces.Sum(), 0.0, 1e-12, "3-DOF equilibrium resultant");
    }

    private static void RunDependentConstraintRejection()
    {
        static LinearSystemSolveResult SolveIdentity(double[] rhs) =>
            new((double[])rhs.Clone(), Iterations: 1, RelativeResidual: 0.0);

        try
        {
            _ = MpcSchurComplementKernel.Solve(
                2,
                new[] { 1.0, 0.0 },
                new[]
                {
                    new MpcConstraintRow(
                        "row A",
                        new Dictionary<int, double> { [0] = 1.0, [1] = -1.0 },
                        0.0),
                    new MpcConstraintRow(
                        "row 2A",
                        new Dictionary<int, double> { [0] = 2.0, [1] = -2.0 },
                        0.0)
                },
                SolveIdentity);
        }
        catch (InvalidOperationException exception) when (
            exception.Message.Contains("dependent", StringComparison.OrdinalIgnoreCase) ||
            exception.Message.Contains("Schur", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        throw new InvalidOperationException("MPC kernel accepted linearly dependent constraint rows.");
    }

    private static void AssertNear(double actual, double expected, double tolerance, string name)
    {
        if (!double.IsFinite(actual) || Math.Abs(actual - expected) > tolerance)
            throw new InvalidOperationException($"{name} mismatch: expected {expected:G17}, observed {actual:G17}.");
    }
}
