using AsterMax.MechanicalGui;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: RemoteDisplacementSmoke <gmsh.exe> <step-file>");
    return 33;
}

try
{
    var gmsh = Path.GetFullPath(args[0]);
    var step = Path.GetFullPath(args[1]);
    if (!File.Exists(gmsh)) throw new FileNotFoundException("Gmsh executable not found.", gmsh);
    if (!File.Exists(step)) throw new FileNotFoundException("STEP benchmark not found.", step);

    var envelope = SimpleStepReader.ReadPrismaticSolid(step);
    var longest = Math.Max(envelope.LengthX, Math.Max(envelope.LengthY, envelope.LengthZ));
    var targetSize = Math.Max(longest / 3.0, 0.1);
    var mesh = SelectableGmshMesher.GenerateAsync(gmsh, step, targetSize, 3, CancellationToken.None)
        .GetAwaiter().GetResult();
    var topology = CadTopologyRegistry.Get(mesh);
    if (mesh.Tetrahedra.Count == 0 || topology.Faces.Count < 4)
        throw new InvalidOperationException("Remote Displacement benchmark did not produce a valid TET4 mesh and face topology.");

    var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
    var fixedFace = ordered.First();
    var remoteFace = ordered.Last();
    if (fixedFace.Tag == remoteFace.Tag)
        throw new InvalidOperationException("Remote Displacement benchmark selected the same support and remote face.");

    var geometrySignature = $"remote-displacement-smoke:{mesh.Nodes.Count}:{mesh.Tetrahedra.Count}:{topology.Faces.Count}";
    var faceScope = new MechanicalScope([], [], new[] { remoteFace.Tag }, [], []);
    var selection = new NamedSelectionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Rigid remote displacement face",
        EntityType = NamedSelectionEntityType.Face,
        GenerationMode = NamedSelectionGenerationMode.Manual,
        ManualScope = faceScope
    };
    selection.AcceptEvaluation(faceScope, geometrySignature, DateTimeOffset.UtcNow);
    var selections = new NamedSelectionCatalog();
    selections.Add(selection);

    var remotePoint = new RemoteVector3(
        remoteFace.Centroid.X,
        remoteFace.Centroid.Y + 7.0,
        remoteFace.Centroid.Z - 4.0);
    var condition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Rigid Remote Displacement benchmark",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Displacement,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Rigid,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(
            0.020,
            -0.010,
            0.005,
            0.0008,
            -0.0005,
            0.0012)
    };

    var rigid = RigidRemoteDisplacementRuntime.Build(
        mesh,
        selections,
        geometrySignature,
        condition,
        fixedFace.NodeIndices.ToArray());
    if (rigid.Equations.Count != rigid.ScopedNodeIds.Count * 3)
        throw new InvalidOperationException("Rigid Remote Displacement did not emit three translational MPC equations per scoped node.");
    if (rigid.AnchorNodeId <= 0 || rigid.ScopedNodeIds.Contains(rigid.AnchorNodeId))
        throw new InvalidOperationException("Rigid Remote Displacement selected an invalid MPC anchor node.");

    var localCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Local-frame Remote Displacement transform",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Displacement,
        RemotePoint = remotePoint,
        CoordinateFrame = new RemoteCoordinateFrame(
            false,
            new RemoteVector3(0, 1, 0),
            new RemoteVector3(0, 0, 1)),
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Rigid,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(0.020, -0.010, 0.005, 0.001, -0.002, 0.003)
    };
    var localRigid = RigidRemoteDisplacementRuntime.Build(
        mesh,
        selections,
        geometrySignature,
        localCondition,
        fixedFace.NodeIndices.ToArray());
    var expectedTranslation = new Vec3(0.005, 0.020, -0.010);
    var expectedRotation = new Vec3(0.003, 0.001, -0.002);
    var localTranslationError = (localRigid.TranslationMm - expectedTranslation).Length;
    var localRotationError = (localRigid.RotationRad - expectedRotation).Length;
    if (localTranslationError > 1e-14 || localRotationError > 1e-14)
        throw new InvalidOperationException(
            $"Rigid Remote Displacement local transform failed: translation={localTranslationError:E3}, rotation={localRotationError:E3}.");

    var partialCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Partial Remote Displacement must reject",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Displacement,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(RemoteCouplingBehavior.Rigid, RemoteWeightingMethod.Uniform, null),
        Components = new RemoteComponents(0.01, 0.0, 0.0, 0.0, 0.0, null)
    };
    RequireRejection(
        () => RigidRemoteDisplacementRuntime.Build(mesh, selections, geometrySignature, partialCondition, fixedFace.NodeIndices.ToArray()),
        "six",
        "partial-component rejection");

    var deformableCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Deformable Remote Displacement must reject",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Displacement,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(RemoteCouplingBehavior.Deformable, RemoteWeightingMethod.Uniform, null),
        Components = new RemoteComponents(0.01, 0.0, 0.0, 0.0, 0.0, 0.0)
    };
    RequireRejection(
        () => RigidRemoteDisplacementRuntime.Build(mesh, selections, geometrySignature, deformableCondition, fixedFace.NodeIndices.ToArray()),
        "rigid",
        "deformable-coupling rejection");

    var largeRotationCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Large-rotation Remote Displacement must reject",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Displacement,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(RemoteCouplingBehavior.Rigid, RemoteWeightingMethod.Uniform, null),
        Components = new RemoteComponents(0.0, 0.0, 0.0, 0.11, 0.0, 0.0)
    };
    RequireRejection(
        () => RigidRemoteDisplacementRuntime.Build(mesh, selections, geometrySignature, largeRotationCondition, fixedFace.NodeIndices.ToArray()),
        "small-rotation",
        "large-rotation rejection");

    var probeLoad = new CadSurfaceForce(
        remoteFace.TriangleIndices.ToArray(),
        new Vec3(0.0, 500.0, -175.0),
        "Remote Displacement verification load");
    using var solveTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(120));
    var solution = GeneralCadTet4Solver.Solve(
        mesh,
        new StaticMaterial(),
        fixedFace.NodeIndices.ToArray(),
        new[] { probeLoad },
        message => Console.WriteLine(message),
        solveTimeout.Token,
        rigid.Equations);

    if (solution.ActiveConstraintCount != rigid.Equations.Count)
        throw new InvalidOperationException(
            $"Rigid Remote Displacement expected {rigid.Equations.Count} active MPC rows but solver reported {solution.ActiveConstraintCount}.");
    if (!double.IsFinite(solution.MaximumConstraintResidual) || solution.MaximumConstraintResidual > 1e-8)
        throw new InvalidOperationException($"Rigid Remote Displacement MPC residual failed: {solution.MaximumConstraintResidual:E3}.");
    if (!double.IsFinite(solution.RelativeResidual) || solution.RelativeResidual > 2e-7)
        throw new InvalidOperationException($"Rigid Remote Displacement PCG residual failed: {solution.RelativeResidual:E3}.");
    if (!double.IsFinite(solution.MaxDisplacementMm) || solution.MaxDisplacementMm <= 0.0)
        throw new InvalidOperationException("Rigid Remote Displacement returned invalid displacement magnitude.");
    if (!double.IsFinite(solution.MaxVonMisesMpa) || solution.MaxVonMisesMpa <= 0.0)
        throw new InvalidOperationException("Rigid Remote Displacement returned invalid von Mises stress.");

    var maximumNodalKinematicError = 0.0;
    foreach (var nodeId in rigid.ScopedNodeIds)
    {
        var nodeIndex = nodeId - 1;
        var expected = RigidRemoteDisplacementRuntime.ExpectedNodeDisplacement(rigid, mesh.Nodes[nodeIndex]);
        var actual = new Vec3(
            solution.Displacements[nodeIndex * 3],
            solution.Displacements[nodeIndex * 3 + 1],
            solution.Displacements[nodeIndex * 3 + 2]);
        maximumNodalKinematicError = Math.Max(maximumNodalKinematicError, (actual - expected).Length);
    }
    if (!double.IsFinite(maximumNodalKinematicError) || maximumNodalKinematicError > 2e-8)
        throw new InvalidOperationException(
            $"Rigid Remote Displacement nodal kinematics failed: maximum error {maximumNodalKinematicError:E3} mm.");

    Console.WriteLine(
        $"PASS Rigid Remote Displacement runtime | nodes={mesh.Nodes.Count}, TET4={mesh.Tetrahedra.Count}, faces={topology.Faces.Count}, " +
        $"scoped-nodes={rigid.ScopedNodeIds.Count}, MPC={rigid.Equations.Count}, anchor={rigid.AnchorNodeId}, " +
        $"translation=({rigid.TranslationMm.X:G8},{rigid.TranslationMm.Y:G8},{rigid.TranslationMm.Z:G8}) mm, " +
        $"rotation=({rigid.RotationRad.X:G8},{rigid.RotationRad.Y:G8},{rigid.RotationRad.Z:G8}) rad, " +
        $"nodal-kinematic-error={maximumNodalKinematicError:E3} mm, constraint-residual={solution.MaximumConstraintResidual:E3}, " +
        $"PCG={solution.RelativeResidual:E3}, Umax={solution.MaxDisplacementMm:G8} mm, VM={solution.MaxVonMisesMpa:G8} MPa, " +
        $"local-translation-error={localTranslationError:E3}, local-rotation-error={localRotationError:E3}");
    return 0;
}
catch (OperationCanceledException)
{
    Console.Error.WriteLine("REMOTE DISPLACEMENT RUNTIME SMOKE FAILED: numerical timeout.");
    return 33;
}
catch (Exception exception)
{
    Console.Error.WriteLine("REMOTE DISPLACEMENT RUNTIME SMOKE FAILED");
    Console.Error.WriteLine(exception);
    return 33;
}

static void RequireRejection(Action action, string expectedText, string label)
{
    var rejected = false;
    try
    {
        action();
    }
    catch (InvalidOperationException exception) when (
        exception.Message.Contains(expectedText, StringComparison.OrdinalIgnoreCase))
    {
        rejected = true;
    }
    if (!rejected)
        throw new InvalidOperationException($"Rigid Remote Displacement {label} did not reject as required.");
    Console.WriteLine($"PASS Rigid Remote Displacement {label}");
}
