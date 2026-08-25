using AsterMax.MechanicalGui;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: RemoteMomentSmoke <gmsh.exe> <step-file>");
    return 32;
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
        throw new InvalidOperationException("Remote Moment benchmark did not produce a valid TET4 mesh and face topology.");

    var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
    var fixedFace = ordered.First();
    var loadedFace = ordered.Last();
    if (fixedFace.Tag == loadedFace.Tag)
        throw new InvalidOperationException("Remote Moment benchmark selected the same support and load face.");

    var geometrySignature = $"remote-moment-smoke:{mesh.Nodes.Count}:{mesh.Tetrahedra.Count}:{topology.Faces.Count}";
    var faceScope = new MechanicalScope([], [], new[] { loadedFace.Tag }, [], []);
    var selection = new NamedSelectionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Remote moment face",
        EntityType = NamedSelectionEntityType.Face,
        GenerationMode = NamedSelectionGenerationMode.Manual,
        ManualScope = faceScope
    };
    selection.AcceptEvaluation(faceScope, geometrySignature, DateTimeOffset.UtcNow);
    var selections = new NamedSelectionCatalog();
    selections.Add(selection);

    var remotePoint = new RemoteVector3(
        loadedFace.Centroid.X,
        loadedFace.Centroid.Y + 13.0,
        loadedFace.Centroid.Z - 9.0);
    var requestedMoment = new Vec3(4500.0, -3200.0, 6100.0);
    var condition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Deformable Remote Moment benchmark",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Moment,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Deformable,
            RemoteWeightingMethod.AreaWeighted,
            null),
        Components = new RemoteComponents(
            null,
            null,
            null,
            requestedMoment.X,
            requestedMoment.Y,
            requestedMoment.Z)
    };

    var remoteLoad = RemoteMomentRuntime.Build(mesh, selections, geometrySignature, condition);
    if (remoteLoad.SurfaceForces.Count == 0)
        throw new InvalidOperationException("Remote Moment runtime returned no equivalent surface forces.");
    if (remoteLoad.ForceConservationError > 1e-10)
        throw new InvalidOperationException($"Remote Moment zero-force conservation failed: {remoteLoad.ForceConservationError:E3}.");
    if (remoteLoad.MomentConservationError > 1e-10)
        throw new InvalidOperationException($"Remote Moment conservation failed: {remoteLoad.MomentConservationError:E3}.");

    var emittedForce = remoteLoad.SurfaceForces.Aggregate(Vec3.Zero, (sum, load) => sum + load.TotalForceN);
    if (emittedForce.Length > 1e-8)
        throw new InvalidOperationException($"Remote Moment emitted a non-zero resultant force: {emittedForce.Length:E3} N.");

    var localCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Local-frame Remote Moment transform",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Moment,
        RemotePoint = remotePoint,
        CoordinateFrame = new RemoteCoordinateFrame(
            false,
            new RemoteVector3(0, 1, 0),
            new RemoteVector3(0, 0, 1)),
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Deformable,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(null, null, null, 4500.0, -3200.0, 6100.0)
    };
    var localLoad = RemoteMomentRuntime.Build(mesh, selections, geometrySignature, localCondition);
    var expectedLocalToGlobal = new Vec3(6100.0, 4500.0, -3200.0);
    var localTransformError = (localLoad.RequestedMomentNmm - expectedLocalToGlobal).Length /
                              Math.Max(expectedLocalToGlobal.Length, 1.0);
    if (localTransformError > 1e-12)
        throw new InvalidOperationException($"Remote Moment local coordinate transform failed: {localTransformError:E3}.");

    var rigidCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Rigid Remote Moment must reject",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Moment,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Rigid,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(null, null, null, 0.0, 0.0, 5000.0)
    };
    var rigidRejected = false;
    try
    {
        _ = RemoteMomentRuntime.Build(mesh, selections, geometrySignature, rigidCondition);
    }
    catch (InvalidOperationException exception) when (exception.Message.Contains("rigid", StringComparison.OrdinalIgnoreCase))
    {
        rigidRejected = true;
    }
    if (!rigidRejected)
        throw new InvalidOperationException("Remote Moment runtime silently accepted rigid coupling before remote-point MPC support exists.");
    Console.WriteLine("PASS Remote Moment unsupported-rigid rejection");

    using var solveTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
    var solution = GeneralCadTet4Solver.Solve(
        mesh,
        new StaticMaterial(),
        fixedFace.NodeIndices.ToArray(),
        remoteLoad.SurfaceForces,
        message => Console.WriteLine(message),
        solveTimeout.Token);

    if (!double.IsFinite(solution.MaxDisplacementMm) || solution.MaxDisplacementMm <= 0)
        throw new InvalidOperationException("Remote Moment TET4 solution returned invalid displacement.");
    if (!double.IsFinite(solution.MaxVonMisesMpa) || solution.MaxVonMisesMpa <= 0)
        throw new InvalidOperationException("Remote Moment TET4 solution returned invalid von Mises stress.");
    if (!double.IsFinite(solution.RelativeResidual) || solution.RelativeResidual > 2e-6)
        throw new InvalidOperationException($"Remote Moment TET4 PCG residual failed: {solution.RelativeResidual:E3}.");
    if (!double.IsFinite(solution.EquilibriumError) || solution.EquilibriumError > 5e-5)
        throw new InvalidOperationException($"Remote Moment TET4 force equilibrium failed: {solution.EquilibriumError:E3}.");
    if (!double.IsFinite(solution.MomentEquilibriumError) || solution.MomentEquilibriumError > 5e-5)
        throw new InvalidOperationException($"Remote Moment TET4 moment equilibrium failed: {solution.MomentEquilibriumError:E3}.");
    if (solution.AppliedForceN.Length > 1e-8)
        throw new InvalidOperationException($"Pure Remote Moment solver path has non-zero applied resultant: {solution.AppliedForceN.Length:E3} N.");

    var appliedMomentError = (solution.AppliedMomentNmm - requestedMoment).Length /
                             Math.Max(requestedMoment.Length, 1.0);
    if (appliedMomentError > 1e-10)
        throw new InvalidOperationException($"Solver nodal load moment differs from requested Remote Moment: {appliedMomentError:E3}.");

    Console.WriteLine(
        $"PASS Remote Moment runtime | nodes={mesh.Nodes.Count}, TET4={mesh.Tetrahedra.Count}, faces={topology.Faces.Count}, " +
        $"surface-loads={remoteLoad.SurfaceForces.Count}, requestedM=({requestedMoment.X:G8},{requestedMoment.Y:G8},{requestedMoment.Z:G8}) Nmm, " +
        $"force-error={remoteLoad.ForceConservationError:E3}, moment-error={remoteLoad.MomentConservationError:E3}, " +
        $"local-transform-error={localTransformError:E3}, applied-moment-error={appliedMomentError:E3}, " +
        $"Umax={solution.MaxDisplacementMm:G8} mm, VM={solution.MaxVonMisesMpa:G8} MPa, " +
        $"residual={solution.RelativeResidual:E3}, force-equilibrium={solution.EquilibriumError:E3}, " +
        $"moment-equilibrium={solution.MomentEquilibriumError:E3}");
    return 0;
}
catch (OperationCanceledException)
{
    Console.Error.WriteLine("REMOTE MOMENT RUNTIME SMOKE FAILED: numerical timeout.");
    return 32;
}
catch (Exception exception)
{
    Console.Error.WriteLine("REMOTE MOMENT RUNTIME SMOKE FAILED");
    Console.Error.WriteLine(exception);
    return 32;
}
