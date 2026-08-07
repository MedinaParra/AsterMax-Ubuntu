namespace AsterMax.MechanicalGui;

internal static class Tet4LinearStaticSolver
{
    public static StaticSolution Solve(SimpleStepSolid solid, TetMesh mesh, StaticMaterial material, SimpleStaticSetup setup)
    {
        var watch = Stopwatch.StartNew();
        Validate(material, setup);

        var degreeCount = mesh.Nodes.Count * 3;
        var stiffness = new double[degreeCount, degreeCount];
        var load = new double[degreeCount];
        var constitutive = Constitutive(material.YoungModulusMpa, material.PoissonRatio);
        var strainMatrices = new List<double[,]>(mesh.Elements.Count);

        foreach (var element in mesh.Elements)
        {
            var coordinates = element.Select(index => mesh.Nodes[index]).ToArray();
            var (strainMatrix, volume) = StrainMatrix(coordinates);
            strainMatrices.Add(strainMatrix);
            var db = Multiply(constitutive, strainMatrix);
            var elementStiffness = TransposeProduct(strainMatrix, db, volume);

            for (var localRow = 0; localRow < 12; localRow++)
            for (var localColumn = 0; localColumn < 12; localColumn++)
            {
                var globalRow = element[localRow / 3] * 3 + localRow % 3;
                var globalColumn = element[localColumn / 3] * 3 + localColumn % 3;
                stiffness[globalRow, globalColumn] += elementStiffness[localRow, localColumn];
            }
        }

        var loadedNodes = FaceNodes(solid, mesh, setup.LoadFace);
        var fixedNodes = FaceNodes(solid, mesh, setup.FixedFace);
        if (loadedNodes.Count == 0 || fixedNodes.Count == 0)
            throw new InvalidOperationException("The mesh does not contain nodes on the selected boundary faces.");

        var nodalForce = setup.ForceN / loadedNodes.Count;
        foreach (var node in loadedNodes)
        {
            load[node * 3] += nodalForce.X;
            load[node * 3 + 1] += nodalForce.Y;
            load[node * 3 + 2] += nodalForce.Z;
        }

        var constrained = new HashSet<int>(fixedNodes.SelectMany(node => new[] { node * 3, node * 3 + 1, node * 3 + 2 }));
        var free = Enumerable.Range(0, degreeCount).Where(index => !constrained.Contains(index)).ToArray();
        if (free.Length == 0) throw new InvalidOperationException("All degrees of freedom are constrained.");

        var reducedStiffness = new double[free.Length, free.Length];
        var reducedLoad = new double[free.Length];
        for (var row = 0; row < free.Length; row++)
        {
            reducedLoad[row] = load[free[row]];
            for (var column = 0; column < free.Length; column++)
                reducedStiffness[row, column] = stiffness[free[row], free[column]];
        }

        var reducedDisplacement = SolveCholesky(reducedStiffness, reducedLoad);
        var displacement = new double[degreeCount];
        for (var index = 0; index < free.Length; index++) displacement[free[index]] = reducedDisplacement[index];

        var residual = Multiply(stiffness, displacement);
        for (var index = 0; index < residual.Length; index++) residual[index] -= load[index];
        var reaction = Vec3.Zero;
        foreach (var node in fixedNodes)
            reaction += new Vec3(residual[node * 3], residual[node * 3 + 1], residual[node * 3 + 2]);

        var loadedFaceAverage = Vec3.Zero;
        foreach (var node in loadedNodes)
            loadedFaceAverage += new Vec3(displacement[node * 3], displacement[node * 3 + 1], displacement[node * 3 + 2]);
        loadedFaceAverage /= loadedNodes.Count;

        var maxDisplacement = 0.0;
        for (var node = 0; node < mesh.Nodes.Count; node++)
        {
            var vector = new Vec3(displacement[node * 3], displacement[node * 3 + 1], displacement[node * 3 + 2]);
            maxDisplacement = Math.Max(maxDisplacement, vector.Length);
        }

        var vonMises = new double[mesh.Elements.Count];
        for (var elementIndex = 0; elementIndex < mesh.Elements.Count; elementIndex++)
        {
            var element = mesh.Elements[elementIndex];
            var elementDisplacement = new double[12];
            for (var local = 0; local < 12; local++)
                elementDisplacement[local] = displacement[element[local / 3] * 3 + local % 3];
            var strain = Multiply(strainMatrices[elementIndex], elementDisplacement);
            var stress = Multiply(constitutive, strain);
            vonMises[elementIndex] = EquivalentStress(stress);
        }

        var equilibriumError = (reaction + setup.ForceN).Length / Math.Max(setup.ForceN.Length, 1.0);
        var analytical = BeamTheory(solid, material, setup);
        watch.Stop();
        return new StaticSolution
        {
            Displacements = displacement,
            ElementVonMisesMpa = vonMises,
            ReactionN = reaction,
            AppliedForceN = setup.ForceN,
            MaxDisplacementMm = maxDisplacement,
            LoadedFaceAverageDisplacementMm = loadedFaceAverage,
            MaxVonMisesMpa = vonMises.Length == 0 ? 0 : vonMises.Max(),
            EquilibriumError = equilibriumError,
            BeamTheoryDisplacementMm = analytical.Displacement,
            BeamTheoryStressMpa = analytical.Stress,
            Elapsed = watch.Elapsed
        };
    }

    public static List<int> FaceNodes(SimpleStepSolid solid, TetMesh mesh, SimpleFace face)
    {
        var tolerance = Math.Max(1e-7, (solid.Max - solid.Min).Length * 1e-7);
        return mesh.Nodes.Select((point, index) => (point, index)).Where(item => face switch
        {
            SimpleFace.XMin => Math.Abs(item.point.X - solid.Min.X) <= tolerance,
            SimpleFace.XMax => Math.Abs(item.point.X - solid.Max.X) <= tolerance,
            SimpleFace.YMin => Math.Abs(item.point.Y - solid.Min.Y) <= tolerance,
            SimpleFace.YMax => Math.Abs(item.point.Y - solid.Max.Y) <= tolerance,
            SimpleFace.ZMin => Math.Abs(item.point.Z - solid.Min.Z) <= tolerance,
            SimpleFace.ZMax => Math.Abs(item.point.Z - solid.Max.Z) <= tolerance,
            _ => false
        }).Select(item => item.index).ToList();
    }

    private static void Validate(StaticMaterial material, SimpleStaticSetup setup)
    {
        if (!double.IsFinite(material.YoungModulusMpa) || material.YoungModulusMpa <= 0)
            throw new InvalidOperationException("Young's modulus must be positive.");
        if (!double.IsFinite(material.PoissonRatio) || material.PoissonRatio <= -0.99 || material.PoissonRatio >= 0.499)
            throw new InvalidOperationException("Poisson's ratio must lie between -0.99 and 0.499.");
        if (setup.FixedFace == setup.LoadFace)
            throw new InvalidOperationException("Fixed support and force cannot use the same face.");
        if (!double.IsFinite(setup.ForceN.Length) || setup.ForceN.Length <= 1e-12)
            throw new InvalidOperationException("The applied force vector is zero or invalid.");
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

    private static (double[,] Matrix, double Volume) StrainMatrix(IReadOnlyList<Vec3> point)
    {
        var coordinates = new double[4, 4];
        for (var row = 0; row < 4; row++)
        {
            coordinates[row, 0] = 1;
            coordinates[row, 1] = point[row].X;
            coordinates[row, 2] = point[row].Y;
            coordinates[row, 3] = point[row].Z;
        }

        var inverse = Invert4x4(coordinates);
        var volume = Math.Abs(Dot(point[1] - point[0], Cross(point[2] - point[0], point[3] - point[0]))) / 6.0;
        if (volume <= 1e-12) throw new InvalidOperationException("A zero-volume tetrahedral element was generated.");

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
            result[row, column] += left[row, inner] * right[inner, column];
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

    private static double[] SolveCholesky(double[,] matrix, double[] rightHandSide)
    {
        var size = rightHandSide.Length;
        var lower = new double[size, size];
        var maximumDiagonal = Enumerable.Range(0, size).Select(index => Math.Abs(matrix[index, index])).DefaultIfEmpty(1).Max();
        var tolerance = Math.Max(1e-14, maximumDiagonal * 1e-12);

        for (var row = 0; row < size; row++)
        for (var column = 0; column <= row; column++)
        {
            var sum = matrix[row, column];
            for (var inner = 0; inner < column; inner++) sum -= lower[row, inner] * lower[column, inner];
            if (row == column)
            {
                if (sum <= tolerance)
                    throw new InvalidOperationException("The stiffness matrix is singular or insufficiently constrained.");
                lower[row, column] = Math.Sqrt(sum);
            }
            else lower[row, column] = sum / lower[column, column];
        }

        var intermediate = new double[size];
        for (var row = 0; row < size; row++)
        {
            var sum = rightHandSide[row];
            for (var inner = 0; inner < row; inner++) sum -= lower[row, inner] * intermediate[inner];
            intermediate[row] = sum / lower[row, row];
        }

        var solution = new double[size];
        for (var row = size - 1; row >= 0; row--)
        {
            var sum = intermediate[row];
            for (var inner = row + 1; inner < size; inner++) sum -= lower[inner, row] * solution[inner];
            solution[row] = sum / lower[row, row];
        }
        return solution;
    }

    private static double[,] Invert4x4(double[,] input)
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
            if (Math.Abs(augmented[pivot, column]) < 1e-18)
                throw new InvalidOperationException("Degenerate tetrahedral geometry.");
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

    private static (double? Displacement, double? Stress) BeamTheory(SimpleStepSolid solid, StaticMaterial material, SimpleStaticSetup setup)
    {
        if (setup.FixedFace != SimpleFace.XMin || setup.LoadFace != SimpleFace.XMax ||
            solid.LengthX < 2 * Math.Max(solid.LengthY, solid.LengthZ)) return (null, null);

        var forceY = Math.Abs(setup.ForceN.Y);
        var forceZ = Math.Abs(setup.ForceN.Z);
        if (forceY >= forceZ && forceY > 0)
        {
            var inertia = solid.LengthZ * Math.Pow(solid.LengthY, 3) / 12.0;
            var displacement = forceY * Math.Pow(solid.LengthX, 3) / (3 * material.YoungModulusMpa * inertia);
            var stress = forceY * solid.LengthX * (solid.LengthY / 2) / inertia;
            return (displacement, stress);
        }
        if (forceZ > 0)
        {
            var inertia = solid.LengthY * Math.Pow(solid.LengthZ, 3) / 12.0;
            var displacement = forceZ * Math.Pow(solid.LengthX, 3) / (3 * material.YoungModulusMpa * inertia);
            var stress = forceZ * solid.LengthX * (solid.LengthZ / 2) / inertia;
            return (displacement, stress);
        }
        return (null, null);
    }

    private static Vec3 Cross(Vec3 a, Vec3 b) =>
        new(a.Y * b.Z - a.Z * b.Y, a.Z * b.X - a.X * b.Z, a.X * b.Y - a.Y * b.X);

    private static double Dot(Vec3 a, Vec3 b) => a.X * b.X + a.Y * b.Y + a.Z * b.Z;
}
