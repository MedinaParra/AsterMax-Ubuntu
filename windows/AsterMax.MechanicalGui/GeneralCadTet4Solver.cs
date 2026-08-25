namespace AsterMax.MechanicalGui;

internal sealed record CadSurfaceForce(
    IReadOnlyList<int> TriangleIndices,
    Vec3 TotalForceN,
    string Name);

internal sealed class GeneralCadStaticSolution
{
    public required double[] Displacements { get; init; }
    public required double[] ElementVonMisesMpa { get; init; }
    public required double[] NodalVonMisesMpa { get; init; }
    public required Vec3 ReactionN { get; init; }
    public required Vec3 AppliedForceN { get; init; }
    public required double MaxDisplacementMm { get; init; }
    public required int MaxDisplacementNode { get; init; }
    public required double MaxVonMisesMpa { get; init; }
    public required int MaxVonMisesElement { get; init; }
    public required double EquilibriumError { get; init; }
    public required double RelativeResidual { get; init; }
    public required int Iterations { get; init; }
    public required int FreeDofCount { get; init; }
    public required TimeSpan Elapsed { get; init; }
    public int ActiveConstraintCount { get; init; }
    public double MaximumConstraintResidual { get; init; }
    public double MaximumConstraintMultiplier { get; init; }
}

internal static class GeneralCadTet4Solver
{
    public static GeneralCadStaticSolution Solve(
        CadMesh mesh,
        StaticMaterial material,
        IReadOnlyCollection<int> fixedNodes,
        IReadOnlyList<CadSurfaceForce> surfaceForces,
        Action<string>? progress = null,
        CancellationToken cancellationToken = default,
        IReadOnlyList<ConstraintEquationDefinition>? constraintEquations = null)
    {
        var watch = Stopwatch.StartNew();
        Validate(mesh, material, fixedNodes, surfaceForces);
        progress?.Invoke("Validating TET4 topology and boundary-condition scopes...");

        var degreeCount = checked(mesh.Nodes.Count * 3);
        var constrained = new bool[degreeCount];
        foreach (var node in fixedNodes)
        {
            if ((uint)node >= (uint)mesh.Nodes.Count)
                throw new InvalidOperationException($"Fixed-support node {node} lies outside the active mesh.");
            constrained[node * 3] = constrained[node * 3 + 1] = constrained[node * 3 + 2] = true;
        }

        var globalToFree = Enumerable.Repeat(-1, degreeCount).ToArray();
        var freeToGlobal = new List<int>(degreeCount);
        for (var global = 0; global < degreeCount; global++)
        {
            if (constrained[global]) continue;
            globalToFree[global] = freeToGlobal.Count;
            freeToGlobal.Add(global);
        }
        if (freeToGlobal.Count == 0)
            throw new InvalidOperationException("All degrees of freedom are constrained.");

        var fullLoad = new double[degreeCount];
        var appliedForce = Vec3.Zero;
        foreach (var force in surfaceForces)
        {
            cancellationToken.ThrowIfCancellationRequested();
            DistributeSurfaceForce(mesh, force, fullLoad);
            appliedForce += force.TotalForceN;
        }
        if (!double.IsFinite(appliedForce.Length) || appliedForce.Length <= 1e-12)
            throw new InvalidOperationException("The resultant applied force is zero or invalid.");

        var reducedLoad = new double[freeToGlobal.Count];
        for (var free = 0; free < freeToGlobal.Count; free++)
            reducedLoad[free] = fullLoad[freeToGlobal[free]];
        var freeLoadNorm = Norm(reducedLoad);
        if (freeLoadNorm <= 1e-14)
            throw new InvalidOperationException("All applied force is acting on constrained degrees of freedom.");

        progress?.Invoke($"Assembling sparse stiffness matrix: {mesh.Tetrahedra.Count:N0} TET4, {freeToGlobal.Count:N0} free DOF...");
        var constitutive = Constitutive(material.YoungModulusMpa, material.PoissonRatio);
        var stiffness = new SparseMatrix(freeToGlobal.Count);
        for (var elementIndex = 0; elementIndex < mesh.Tetrahedra.Count; elementIndex++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var element = mesh.Tetrahedra[elementIndex];
            ValidateElementIndices(mesh, element, elementIndex);
            var coordinates = element.Select(index => mesh.Nodes[index]).ToArray();
            var (strainMatrix, volume) = StrainMatrix(coordinates, elementIndex);
            var db = Multiply(constitutive, strainMatrix);
            var elementStiffness = TransposeProduct(strainMatrix, db, volume);

            for (var localRow = 0; localRow < 12; localRow++)
            {
                var globalRow = element[localRow / 3] * 3 + localRow % 3;
                var freeRow = globalToFree[globalRow];
                if (freeRow < 0) continue;
                for (var localColumn = 0; localColumn < 12; localColumn++)
                {
                    var globalColumn = element[localColumn / 3] * 3 + localColumn % 3;
                    var freeColumn = globalToFree[globalColumn];
                    if (freeColumn < 0) continue;
                    stiffness.Add(freeRow, freeColumn, elementStiffness[localRow, localColumn]);
                }
            }

            if ((elementIndex + 1) % 1000 == 0)
                progress?.Invoke($"Stiffness assembly: {elementIndex + 1:N0}/{mesh.Tetrahedra.Count:N0} elements...");
        }
        stiffness.ValidateDiagonal();
        stiffness.Freeze();

        var maximumIterations = Math.Clamp(freeToGlobal.Count * 3, 300, 8000);
        var reducedConstraints = BuildReducedMpcRows(mesh, constraintEquations, globalToFree);
        double[] reducedDisplacement;
        int iterations;
        double relativeResidual;
        var maximumConstraintResidual = 0.0;
        var maximumConstraintMultiplier = 0.0;

        if (reducedConstraints.Count == 0)
        {
            progress?.Invoke($"Solving sparse positive-definite system ({freeToGlobal.Count:N0} unknowns)...");
            (reducedDisplacement, iterations, relativeResidual) = SolvePreconditionedConjugateGradient(
                stiffness,
                reducedLoad,
                maximumIterations,
                1e-6,
                progress,
                cancellationToken);
        }
        else
        {
            progress?.Invoke(
                $"Solving sparse TET4 system with {reducedConstraints.Count:N0} exact MPC equation(s) using a Schur complement...");
            var constrainedSolve = MpcSchurComplementKernel.Solve(
                freeToGlobal.Count,
                reducedLoad,
                reducedConstraints,
                rightHandSide =>
                {
                    var (solution, localIterations, localResidual) = SolvePreconditionedConjugateGradient(
                        stiffness,
                        rightHandSide,
                        maximumIterations,
                        1e-7,
                        null,
                        cancellationToken);
                    return new LinearSystemSolveResult(solution, localIterations, localResidual);
                });

            reducedDisplacement = constrainedSolve.Solution;
            iterations = constrainedSolve.TotalLinearIterations;
            relativeResidual = constrainedSolve.MaximumLinearResidual;
            maximumConstraintResidual = constrainedSolve.MaximumConstraintResidual;
            maximumConstraintMultiplier = constrainedSolve.Multipliers.Select(Math.Abs).DefaultIfEmpty(0.0).Max();
            if (!double.IsFinite(maximumConstraintResidual) || maximumConstraintResidual > 1e-8)
                throw new InvalidOperationException(
                    $"The MPC solve did not satisfy the active equations. Maximum residual: {maximumConstraintResidual:E3}.");
            progress?.Invoke(
                $"MPC enforcement passed: {reducedConstraints.Count:N0} equation(s), maximum residual {maximumConstraintResidual:E3}.");
        }

        var displacement = new double[degreeCount];
        for (var free = 0; free < freeToGlobal.Count; free++)
            displacement[freeToGlobal[free]] = reducedDisplacement[free];

        progress?.Invoke("Recovering stresses, nodal averages and support reactions...");
        var internalForce = new double[degreeCount];
        var elementVonMises = new double[mesh.Tetrahedra.Count];
        var nodalStressSum = new double[mesh.Nodes.Count];
        var nodalVolumeSum = new double[mesh.Nodes.Count];
        var maxVonMises = 0.0;
        var maxVonMisesElement = -1;

        for (var elementIndex = 0; elementIndex < mesh.Tetrahedra.Count; elementIndex++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var element = mesh.Tetrahedra[elementIndex];
            var coordinates = element.Select(index => mesh.Nodes[index]).ToArray();
            var (strainMatrix, volume) = StrainMatrix(coordinates, elementIndex);
            var db = Multiply(constitutive, strainMatrix);
            var elementStiffness = TransposeProduct(strainMatrix, db, volume);
            var elementDisplacement = new double[12];
            for (var local = 0; local < 12; local++)
                elementDisplacement[local] = displacement[element[local / 3] * 3 + local % 3];

            var elementInternalForce = Multiply(elementStiffness, elementDisplacement);
            for (var local = 0; local < 12; local++)
                internalForce[element[local / 3] * 3 + local % 3] += elementInternalForce[local];

            var strain = Multiply(strainMatrix, elementDisplacement);
            var stress = Multiply(constitutive, strain);
            var equivalent = EquivalentStress(stress);
            elementVonMises[elementIndex] = equivalent;
            if (equivalent > maxVonMises)
            {
                maxVonMises = equivalent;
                maxVonMisesElement = elementIndex;
            }
            foreach (var node in element)
            {
                nodalStressSum[node] += equivalent * volume;
                nodalVolumeSum[node] += volume;
            }
        }

        var nodalVonMises = new double[mesh.Nodes.Count];
        for (var node = 0; node < nodalVonMises.Length; node++)
            nodalVonMises[node] = nodalVolumeSum[node] <= 1e-18 ? 0 : nodalStressSum[node] / nodalVolumeSum[node];

        var reaction = Vec3.Zero;
        foreach (var node in fixedNodes)
        {
            var x = internalForce[node * 3] - fullLoad[node * 3];
            var y = internalForce[node * 3 + 1] - fullLoad[node * 3 + 1];
            var z = internalForce[node * 3 + 2] - fullLoad[node * 3 + 2];
            reaction += new Vec3(x, y, z);
        }

        var maxDisplacement = 0.0;
        var maxDisplacementNode = -1;
        for (var node = 0; node < mesh.Nodes.Count; node++)
        {
            var vector = new Vec3(displacement[node * 3], displacement[node * 3 + 1], displacement[node * 3 + 2]);
            if (vector.Length <= maxDisplacement) continue;
            maxDisplacement = vector.Length;
            maxDisplacementNode = node;
        }

        var equilibriumError = (reaction + appliedForce).Length / Math.Max(appliedForce.Length, 1.0);
        if (!double.IsFinite(equilibriumError))
            throw new InvalidOperationException("The force-equilibrium result is not finite.");

        watch.Stop();
        progress?.Invoke(
            $"Solution complete: {iterations:N0} aggregate PCG iterations, residual {relativeResidual:E3}, " +
            $"equilibrium {equilibriumError:E3}, MPC residual {maximumConstraintResidual:E3}.");
        return new GeneralCadStaticSolution
        {
            Displacements = displacement,
            ElementVonMisesMpa = elementVonMises,
            NodalVonMisesMpa = nodalVonMises,
            ReactionN = reaction,
            AppliedForceN = appliedForce,
            MaxDisplacementMm = maxDisplacement,
            MaxDisplacementNode = maxDisplacementNode,
            MaxVonMisesMpa = maxVonMises,
            MaxVonMisesElement = maxVonMisesElement,
            EquilibriumError = equilibriumError,
            RelativeResidual = relativeResidual,
            Iterations = iterations,
            FreeDofCount = freeToGlobal.Count,
            Elapsed = watch.Elapsed,
            ActiveConstraintCount = reducedConstraints.Count,
            MaximumConstraintResidual = maximumConstraintResidual,
            MaximumConstraintMultiplier = maximumConstraintMultiplier
        };
    }

    private static IReadOnlyList<MpcConstraintRow> BuildReducedMpcRows(
        CadMesh mesh,
        IReadOnlyList<ConstraintEquationDefinition>? equations,
        IReadOnlyList<int> globalToFree)
    {
        if (equations is null || equations.Count == 0)
            return Array.Empty<MpcConstraintRow>();

        var rows = new List<MpcConstraintRow>(equations.Count);
        foreach (var equation in equations)
        {
            if (equation is null)
                throw new InvalidOperationException("The active MPC collection contains a null equation.");
            equation.Validate();
            var coefficients = new Dictionary<int, double>();
            foreach (var term in equation.BuildDimensionallyScaledTerms())
            {
                if (term.Target.Kind != ConstraintTargetKind.MeshNode)
                    throw new InvalidOperationException(
                        $"Constraint equation '{equation.Name}' contains a remote-point DOF. " +
                        "The native TET4 runtime currently accepts mesh-node translational MPC terms only.");

                var nodeId = term.Target.NodeId!.Value;
                var nodeIndex = nodeId - 1;
                if ((uint)nodeIndex >= (uint)mesh.Nodes.Count)
                    throw new InvalidOperationException(
                        $"Constraint equation '{equation.Name}' references mesh node {nodeId}, outside the active mesh (1..{mesh.Nodes.Count}).");

                var component = term.DegreeOfFreedom switch
                {
                    ConstraintDegreeOfFreedom.TranslationX => 0,
                    ConstraintDegreeOfFreedom.TranslationY => 1,
                    ConstraintDegreeOfFreedom.TranslationZ => 2,
                    _ => throw new InvalidOperationException(
                        $"Constraint equation '{equation.Name}' contains rotational DOF {term.DegreeOfFreedom}; " +
                        "solid TET4 nodes expose translational DOFs only.")
                };
                var globalDof = nodeIndex * 3 + component;
                var freeDof = globalToFree[globalDof];
                if (freeDof < 0)
                    continue; // fixed support value is exactly zero, so its term contributes nothing to RHS.
                coefficients[freeDof] = coefficients.GetValueOrDefault(freeDof) + term.Coefficient;
            }

            foreach (var key in coefficients.Where(pair => Math.Abs(pair.Value) <= 1e-15).Select(pair => pair.Key).ToArray())
                coefficients.Remove(key);

            if (coefficients.Count == 0)
            {
                if (Math.Abs(equation.RightHandSide) <= 1e-12)
                    continue; // equation is already satisfied entirely by zero-valued fixed DOFs.
                throw new InvalidOperationException(
                    $"Constraint equation '{equation.Name}' conflicts with the fixed supports: all active terms are fixed at zero but RHS={equation.RightHandSide:G17}.");
            }

            rows.Add(new MpcConstraintRow(equation.Name, coefficients, equation.RightHandSide));
        }
        return rows;
    }

    private static void Validate(
        CadMesh mesh,
        StaticMaterial material,
        IReadOnlyCollection<int> fixedNodes,
        IReadOnlyList<CadSurfaceForce> surfaceForces)
    {
        if (mesh.Nodes.Count < 4 || mesh.Tetrahedra.Count == 0)
            throw new InvalidOperationException("Generate a non-empty tetrahedral volume mesh before solving.");
        if (!double.IsFinite(material.YoungModulusMpa) || material.YoungModulusMpa <= 0)
            throw new InvalidOperationException("Young's modulus must be positive.");
        if (!double.IsFinite(material.PoissonRatio) || material.PoissonRatio <= -0.99 || material.PoissonRatio >= 0.499)
            throw new InvalidOperationException("Poisson's ratio must lie between -0.99 and 0.499.");
        if (fixedNodes.Count == 0)
            throw new InvalidOperationException("The model has no fixed-support nodes.");
        if (surfaceForces.Count == 0)
            throw new InvalidOperationException("The model has no scoped surface force.");
        foreach (var force in surfaceForces)
        {
            if (force.TriangleIndices.Count == 0)
                throw new InvalidOperationException($"Load '{force.Name}' has an empty surface scope.");
            if (!double.IsFinite(force.TotalForceN.Length) || force.TotalForceN.Length <= 1e-12)
                throw new InvalidOperationException($"Load '{force.Name}' has a zero or invalid force vector.");
        }
    }

    private static void ValidateElementIndices(CadMesh mesh, IReadOnlyList<int> element, int elementIndex)
    {
        if (element.Count != 4)
            throw new InvalidOperationException($"Element {elementIndex + 1} is not a four-node tetrahedron.");
        if (element.Distinct().Count() != 4)
            throw new InvalidOperationException($"Element {elementIndex + 1} contains repeated nodes.");
        foreach (var node in element)
            if ((uint)node >= (uint)mesh.Nodes.Count)
                throw new InvalidOperationException($"Element {elementIndex + 1} references node {node}, outside the mesh.");
    }

    private static void DistributeSurfaceForce(CadMesh mesh, CadSurfaceForce force, double[] fullLoad)
    {
        var nodalWeights = new Dictionary<int, double>();
        var totalArea = 0.0;
        foreach (var triangleIndex in force.TriangleIndices)
        {
            if ((uint)triangleIndex >= (uint)mesh.SurfaceTriangles.Count)
                throw new InvalidOperationException($"Load '{force.Name}' references boundary triangle {triangleIndex}, outside the mesh.");
            var triangle = mesh.SurfaceTriangles[triangleIndex];
            var area = TriangleArea(mesh.Nodes[triangle[0]], mesh.Nodes[triangle[1]], mesh.Nodes[triangle[2]]);
            if (area <= 1e-18) continue;
            totalArea += area;
            foreach (var node in triangle)
                nodalWeights[node] = nodalWeights.GetValueOrDefault(node) + area / 3.0;
        }
        if (totalArea <= 1e-18 || nodalWeights.Count == 0)
            throw new InvalidOperationException($"Load '{force.Name}' is scoped to a zero-area surface.");

        foreach (var (node, weight) in nodalWeights)
        {
            var fraction = weight / totalArea;
            fullLoad[node * 3] += force.TotalForceN.X * fraction;
            fullLoad[node * 3 + 1] += force.TotalForceN.Y * fraction;
            fullLoad[node * 3 + 2] += force.TotalForceN.Z * fraction;
        }
    }

    private static (double[] Solution, int Iterations, double RelativeResidual) SolvePreconditionedConjugateGradient(
        SparseMatrix matrix,
        double[] rightHandSide,
        int maximumIterations,
        double relativeTolerance,
        Action<string>? progress,
        CancellationToken cancellationToken)
    {
        var size = rightHandSide.Length;
        var solution = new double[size];
        var residual = (double[])rightHandSide.Clone();
        var preconditioned = new double[size];
        var direction = new double[size];
        var matrixDirection = new double[size];
        var normB = Norm(rightHandSide);
        var absoluteTolerance = Math.Max(1e-12, normB * relativeTolerance);

        for (var index = 0; index < size; index++)
        {
            preconditioned[index] = residual[index] / matrix.Diagonal[index];
            direction[index] = preconditioned[index];
        }
        var residualDotPreconditioned = Dot(residual, preconditioned);
        if (!double.IsFinite(residualDotPreconditioned) || residualDotPreconditioned <= 0)
            throw new InvalidOperationException("The stiffness matrix is not positive definite or the model is insufficiently constrained.");

        var residualNorm = Norm(residual);
        if (residualNorm <= absoluteTolerance) return (solution, 0, residualNorm / Math.Max(normB, 1e-30));

        for (var iteration = 1; iteration <= maximumIterations; iteration++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            matrix.Multiply(direction, matrixDirection);
            var denominator = Dot(direction, matrixDirection);
            if (!double.IsFinite(denominator) || denominator <= 1e-30)
                throw new InvalidOperationException("The stiffness system lost positive definiteness. Check supports, disconnected regions and tetrahedron quality.");

            var alpha = residualDotPreconditioned / denominator;
            for (var index = 0; index < size; index++)
            {
                solution[index] += alpha * direction[index];
                residual[index] -= alpha * matrixDirection[index];
            }

            residualNorm = Norm(residual);
            var relativeResidual = residualNorm / Math.Max(normB, 1e-30);
            if (iteration == 1 || iteration % 100 == 0)
                progress?.Invoke($"PCG iteration {iteration:N0}: relative residual {relativeResidual:E3}...");
            if (residualNorm <= absoluteTolerance)
                return (solution, iteration, relativeResidual);

            for (var index = 0; index < size; index++)
                preconditioned[index] = residual[index] / matrix.Diagonal[index];
            var nextResidualDotPreconditioned = Dot(residual, preconditioned);
            if (!double.IsFinite(nextResidualDotPreconditioned) || nextResidualDotPreconditioned <= 0)
                throw new InvalidOperationException("The iterative solver encountered a non-positive preconditioned residual.");
            var beta = nextResidualDotPreconditioned / residualDotPreconditioned;
            for (var index = 0; index < size; index++)
                direction[index] = preconditioned[index] + beta * direction[index];
            residualDotPreconditioned = nextResidualDotPreconditioned;
        }

        throw new InvalidOperationException(
            $"The sparse solver did not converge after {maximumIterations:N0} iterations. " +
            $"Final relative residual: {residualNorm / Math.Max(normB, 1e-30):E3}. Refine the supports or improve mesh quality.");
    }

    private sealed class SparseMatrix
    {
        private readonly Dictionary<int, double>[] _rows;
        private int[]? _rowPointers;
        private int[]? _columnIndices;
        private double[]? _values;
        public double[] Diagonal { get; }

        public SparseMatrix(int size)
        {
            _rows = Enumerable.Range(0, size).Select(_ => new Dictionary<int, double>(48)).ToArray();
            Diagonal = new double[size];
        }

        public void Add(int row, int column, double value)
        {
            if (_rowPointers is not null)
                throw new InvalidOperationException("Cannot add stiffness entries after CSR finalization.");
            if (Math.Abs(value) <= 1e-30) return;
            var entries = _rows[row];
            entries[column] = entries.GetValueOrDefault(column) + value;
            if (row == column) Diagonal[row] += value;
        }

        public void ValidateDiagonal()
        {
            var maximum = Diagonal.Select(Math.Abs).DefaultIfEmpty(1.0).Max();
            var minimumAllowed = Math.Max(1e-18, maximum * 1e-14);
            for (var index = 0; index < Diagonal.Length; index++)
            {
                if (!double.IsFinite(Diagonal[index]) || Diagonal[index] <= minimumAllowed)
                    throw new InvalidOperationException(
                        $"The stiffness diagonal is singular at free degree of freedom {index + 1}. " +
                        "The mesh may contain disconnected nodes or insufficient supports.");
            }
        }

        public void Freeze()
        {
            if (_rowPointers is not null) return;
            _rowPointers = new int[_rows.Length + 1];
            var nonzeroCount = 0;
            for (var row = 0; row < _rows.Length; row++)
            {
                _rowPointers[row] = nonzeroCount;
                nonzeroCount += _rows[row].Count;
            }
            _rowPointers[^1] = nonzeroCount;
            _columnIndices = new int[nonzeroCount];
            _values = new double[nonzeroCount];
            var cursor = 0;
            for (var row = 0; row < _rows.Length; row++)
            {
                foreach (var entry in _rows[row].OrderBy(entry => entry.Key))
                {
                    _columnIndices[cursor] = entry.Key;
                    _values[cursor] = entry.Value;
                    cursor++;
                }
                _rows[row].Clear();
            }
        }

        public void Multiply(double[] vector, double[] result)
        {
            if (_rowPointers is null || _columnIndices is null || _values is null) Freeze();
            Array.Clear(result);
            for (var row = 0; row < _rows.Length; row++)
            {
                var sum = 0.0;
                for (var index = _rowPointers![row]; index < _rowPointers[row + 1]; index++)
                    sum += _values![index] * vector[_columnIndices![index]];
                result[row] = sum;
            }
        }
    }

    private static double[,] Constitutive(double young, double poisson)
    {
        var lambda = young * poisson / ((1 + poisson) * (1 - 2 * poisson));
        var shear = young / (2 * (1 + poisson));
        var matrix = new double[6, 6];
        for (var row = 0; row < 3; row++)
        for (var column = 0; column < 3; column++)
            matrix[row, column] = row == column ? lambda + 2 * shear : lambda;
        matrix[3, 3] = matrix[4, 4] = matrix[5, 5] = shear;
        return matrix;
    }

    private static (double[,] Matrix, double Volume) StrainMatrix(IReadOnlyList<Vec3> point, int elementIndex)
    {
        var coordinates = new double[4, 4];
        for (var row = 0; row < 4; row++)
        {
            coordinates[row, 0] = 1;
            coordinates[row, 1] = point[row].X;
            coordinates[row, 2] = point[row].Y;
            coordinates[row, 3] = point[row].Z;
        }
        var inverse = Invert4x4(coordinates, elementIndex);
        var signedSixVolume = Dot(point[1] - point[0], Cross(point[2] - point[0], point[3] - point[0]));
        var volume = Math.Abs(signedSixVolume) / 6.0;
        var characteristic = Math.Max(
            (point[1] - point[0]).Length,
            Math.Max((point[2] - point[0]).Length, (point[3] - point[0]).Length));
        var minimumVolume = Math.Max(1e-18, Math.Pow(Math.Max(characteristic, 1e-9), 3) * 1e-13);
        if (!double.IsFinite(volume) || volume <= minimumVolume)
            throw new InvalidOperationException($"Tetrahedron {elementIndex + 1} has zero or near-zero volume ({volume:E3} mm³).");

        var matrix = new double[6, 12];
        for (var node = 0; node < 4; node++)
        {
            var bx = inverse[1, node];
            var by = inverse[2, node];
            var bz = inverse[3, node];
            var column = node * 3;
            matrix[0, column] = bx;
            matrix[1, column + 1] = by;
            matrix[2, column + 2] = bz;
            matrix[3, column] = by;
            matrix[3, column + 1] = bx;
            matrix[4, column + 1] = bz;
            matrix[4, column + 2] = by;
            matrix[5, column] = bz;
            matrix[5, column + 2] = bx;
        }
        return (matrix, volume);
    }

    private static double[,] Multiply(double[,] left, double[,] right)
    {
        var result = new double[left.GetLength(0), right.GetLength(1)];
        for (var row = 0; row < result.GetLength(0); row++)
        for (var inner = 0; inner < left.GetLength(1); inner++)
        for (var column = 0; column < result.GetLength(1); column++)
            result[row, column] += left[inner, row] * right[inner, column];
        return result;
    }

    private static double[] Multiply(double[,] matrix, double[] vector)
    {
        var result = new double[matrix.GetLength(0)];
        for (var row = 0; row < result.Length; row++)
        for (var column = 0; column < vector.Length; column++)
            result[row] += matrix[row, column] * vector[column];
        return result;
    }

    private static double[,] TransposeProduct(double[,] left, double[,] right, double scale)
    {
        var result = new double[left.GetLength(1), right.GetLength(1)];
        for (var row = 0; row < result.GetLength(0); row++)
        for (var inner = 0; inner < left.GetLength(0); inner++)
        for (var column = 0; column < result.GetLength(1); column++)
            result[row, column] += left[inner, row] * right[inner, column] * scale;
        return result;
    }

    private static double[,] Invert4x4(double[,] input, int elementIndex)
    {
        const int size = 4;
        var augmented = new double[size, size * 2];
        for (var row = 0; row < size; row++)
        for (var column = 0; column < size; column++)
        {
            augmented[row, column] = input[row, column];
            augmented[row, column + size] = row == column ? 1 : 0;
        }

        for (var column = 0; column < size; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < size; row++)
                if (Math.Abs(augmented[row, column]) > Math.Abs(augmented[pivot, column])) pivot = row;
            if (Math.Abs(augmented[pivot, column]) < 1e-20)
                throw new InvalidOperationException($"Tetrahedron {elementIndex + 1} is geometrically degenerate.");
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

    private static double EquivalentStress(IReadOnlyList<double> stress)
    {
        var sx = stress[0];
        var sy = stress[1];
        var sz = stress[2];
        var txy = stress[3];
        var tyz = stress[4];
        var txz = stress[5];
        return Math.Sqrt(
            0.5 * (Math.Pow(sx - sy, 2) + Math.Pow(sy - sz, 2) + Math.Pow(sz - sx, 2)) +
            3 * (txy * txy + tyz * tyz + txz * txz));
    }

    private static double TriangleArea(Vec3 a, Vec3 b, Vec3 c) => Cross(b - a, c - a).Length * .5;
    private static Vec3 Cross(Vec3 first, Vec3 second) => new(
        first.Y * second.Z - first.Z * second.Y,
        first.Z * second.X - first.X * second.Z,
        first.X * second.Y - first.Y * second.X);
    private static double Dot(Vec3 first, Vec3 second) => first.X * second.X + first.Y * second.Y + first.Z * second.Z;
    private static double Dot(IReadOnlyList<double> first, IReadOnlyList<double> second)
    {
        var sum = 0.0;
        for (var index = 0; index < first.Count; index++) sum += first[index] * second[index];
        return sum;
    }
    private static double Norm(IReadOnlyList<double> vector) => Math.Sqrt(Math.Max(Dot(vector, vector), 0));
}
