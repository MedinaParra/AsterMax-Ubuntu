using AsterMax.MechanicalGui;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: RemoteForceSmoke <gmsh.exe> <step-file>");
    return 31;
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
        throw new InvalidOperationException("Remote Force benchmark did not produce a valid TET4 mesh and face topology.");

    var ordered = topology.Faces.Values.OrderBy(face => face.Centroid.X).ToArray();
    var fixedFace = ordered.First();
    var loadedFace = ordered.Last();
    if (fixedFace.Tag == loadedFace.Tag)
        throw new InvalidOperationException("Remote Force benchmark selected the same support and load face.");

    var geometrySignature = $"remote-force-smoke:{mesh.Nodes.Count}:{mesh.Tetrahedra.Count}:{topology.Faces.Count}";
    var faceScope = new MechanicalScope([], [], new[] { loadedFace.Tag }, [], []);
    var selection = new NamedSelectionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Remote load face",
        EntityType = NamedSelectionEntityType.Face,
        GenerationMode = NamedSelectionGenerationMode.Manual,
        ManualScope = faceScope
    };
    selection.AcceptEvaluation(faceScope, geometrySignature, DateTimeOffset.UtcNow);
    var selections = new NamedSelectionCatalog();
    selections.Add(selection);

    var remotePoint = new RemoteVector3(
        loadedFace.Centroid.X,
        loadedFace.Centroid.Y + 17.0,
        loadedFace.Centroid.Z + 11.0);
    var condition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Deformable Remote Force benchmark",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Force,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Deformable,
            RemoteWeightingMethod.AreaWeighted,
            null),
        Components = new RemoteComponents(1000.0, 175.0, -125.0, null, null, null)
    };

    var remoteLoad = RemoteForceRuntime.Build(mesh, selections, geometrySignature, condition);
    if (remoteLoad.SurfaceForces.Count == 0)
        throw new InvalidOperationException("Remote Force runtime returned no equivalent surface loads.");
    if (remoteLoad.ForceConservationError > 1e-10)
        throw new InvalidOperationException($"Remote Force resultant conservation failed: {remoteLoad.ForceConservationError:E3}.");
    if (remoteLoad.MomentConservationError > 1e-10)
        throw new InvalidOperationException($"Remote Force moment conservation failed: {remoteLoad.MomentConservationError:E3}.");

    var localCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Local-frame Remote Force transform",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Force,
        RemotePoint = remotePoint,
        CoordinateFrame = new RemoteCoordinateFrame(
            false,
            new RemoteVector3(0, 1, 0),
            new RemoteVector3(0, 0, 1)),
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Deformable,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(1000.0, 175.0, -125.0, null, null, null)
    };
    var localLoad = RemoteForceRuntime.Build(mesh, selections, geometrySignature, localCondition);
    var expectedLocalToGlobal = new Vec3(-125.0, 1000.0, 175.0);
    var localTransformError = (localLoad.RequestedForceN - expectedLocalToGlobal).Length /
                              Math.Max(expectedLocalToGlobal.Length, 1.0);
    if (localTransformError > 1e-12)
        throw new InvalidOperationException($"Remote Force local coordinate transform failed: {localTransformError:E3}.");

    var rigidCondition = new RemoteBoundaryConditionDefinition
    {
        Id = Guid.NewGuid(),
        Name = "Rigid Remote Force must reject",
        ScopeSelectionId = selection.Id,
        Type = RemoteBoundaryConditionType.Force,
        RemotePoint = remotePoint,
        CoordinateFrame = RemoteCoordinateFrame.Global,
        Coupling = new RemoteCouplingDefinition(
            RemoteCouplingBehavior.Rigid,
            RemoteWeightingMethod.Uniform,
            null),
        Components = new RemoteComponents(1000.0, 0.0, 0.0, null, null, null)
    };
    var rigidRejected = false;
    try
    {
        _ = RemoteForceRuntime.Build(mesh, selections, geometrySignature, rigidCondition);
    }
    catch (InvalidOperationException exception) when (exception.Message.Contains("rigid", StringComparison.OrdinalIgnoreCase))
    {
        rigidRejected = true;
    }
    if (!rigidRejected)
        throw new InvalidOperationException("Remote Force runtime silently accepted rigid coupling before remote-point MPC support exists.");
    Console.WriteLine("PASS Remote Force unsupported-rigid rejection");

    using var solveTimeout = new CancellationTokenSource(TimeSpan.FromSeconds(90));
    var solution = GeneralCadTet4Solver.Solve(
        mesh,
        new StaticMaterial(),
        fixedFace.NodeIndices.ToArray(),
        remoteLoad.SurfaceForces,
        message => Console.WriteLine(message),
        solveTimeout.Token);

    if (!double.IsFinite(solution.MaxDisplacementMm) || solution.MaxDisplacementMm <= 0)
        throw new InvalidOperationException("Remote Force TET4 solution returned invalid displacement.");
    if (!double.IsFinite(solution.MaxVonMisesMpa) || solution.MaxVonMisesMpa <= 0)
        throw new InvalidOperationException("Remote Force TET4 solution returned invalid von Mises stress.");
    if (!double.IsFinite(solution.RelativeResidual) || solution.RelativeResidual > 2e-6)
        throw new InvalidOperationException($"Remote Force TET4 PCG residual failed: {solution.RelativeResidual:E3}.");
    if (!double.IsFinite(solution.EquilibriumError) || solution.EquilibriumError > 5e-5)
        throw new InvalidOperationException($"Remote Force TET4 force equilibrium failed: {solution.EquilibriumError:E3}.");

    var resultant = remoteLoad.SurfaceForces.Aggregate(Vec3.Zero, (sum, load) => sum + load.TotalForceN);
    var requested = remoteLoad.RequestedForceN;
    var resultantError = (resultant - requested).Length / Math.Max(requested.Length, 1.0);
    if (resultantError > 1e-10)
        throw new InvalidOperationException($"Surface-load emission changed the Remote Force resultant: {resultantError:E3}.");

    Console.WriteLine(
        $"PASS Remote Force runtime | nodes={mesh.Nodes.Count}, TET4={mesh.Tetrahedra.Count}, faces={topology.Faces.Count}, " +
        $"surface-loads={remoteLoad.SurfaceForces.Count}, requested=({requested.X:G8},{requested.Y:G8},{requested.Z:G8}) N, " +
        $"force-error={remoteLoad.ForceConservationError:E3}, moment-error={remoteLoad.MomentConservationError:E3}, " +
        $"local-transform-error={localTransformError:E3}, Umax={solution.MaxDisplacementMm:G8} mm, " +
        $"VM={solution.MaxVonMisesMpa:G8} MPa, residual={solution.RelativeResidual:E3}, " +
        $"equilibrium={solution.EquilibriumError:E3}");
    return 0;
}
catch (OperationCanceledException)
{
    Console.Error.WriteLine("REMOTE FORCE RUNTIME SMOKE FAILED: numerical timeout.");
    return 31;
}
catch (Exception exception)
{
    Console.Error.WriteLine("REMOTE FORCE RUNTIME SMOKE FAILED");
    Console.Error.WriteLine(exception);
    return 31;
}
