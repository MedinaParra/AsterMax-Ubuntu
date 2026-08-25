using AsterMax.MechanicalGui;

static class DomainSmoke
{
    public static int Main()
    {
        try
        {
            RunContactOffsetSmoke();
            RunJointSmoke();
            RunRemoteBoundaryConditionSmoke();
            RunConstraintEquationSmoke();
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 1;
        }
    }

    private static void RunContactOffsetSmoke()
    {
        var expectedFailures = 0;

        ContactOffsetControl.None.Validate("preserve", 10.0);

        new ContactOffsetControl(
            ContactInitialGapTreatment.UserDefinedOffset,
            0.25,
            null,
            0.01).Validate("positive-offset", 5.0);

        new ContactOffsetControl(
            ContactInitialGapTreatment.UserDefinedOffset,
            -0.25,
            null,
            0.01).Validate("negative-offset", 5.0);

        new ContactOffsetControl(
            ContactInitialGapTreatment.AdjustToTouch,
            null,
            2.0,
            0.01).Validate("adjust-to-touch", 5.0);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.Preserve,
                0.1,
                null,
                null).Validate("preserve-with-offset", 5.0),
            "preserve mode accepted a user offset",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.UserDefinedOffset,
                0.0,
                null,
                null).Validate("zero-offset", 5.0),
            "zero user offset was accepted",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.UserDefinedOffset,
                6.0,
                null,
                null).Validate("offset-outside-pinball", 5.0),
            "offset beyond pinball radius was accepted",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.AdjustToTouch,
                null,
                null,
                null).Validate("missing-adjustment", 5.0),
            "AdjustToTouch accepted a missing maximum adjustment",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.AdjustToTouch,
                null,
                6.0,
                null).Validate("adjustment-outside-pinball", 5.0),
            "adjustment beyond pinball radius was accepted",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ContactOffsetControl(
                ContactInitialGapTreatment.UserDefinedOffset,
                0.25,
                null,
                -0.01).Validate("negative-penetration-tolerance", 5.0),
            "negative penetration tolerance was accepted",
            ref expectedFailures);

        if (expectedFailures != 6)
            throw new InvalidOperationException($"WS06.1 expected 6 deterministic rejection fixtures, observed {expectedFailures}.");

        Console.WriteLine("PASS WS06.1 Contact Offset Control domain smoke | valid=4 | deterministic-rejections=6");
    }

    private static void RunJointSmoke()
    {
        var expectedFailures = 0;
        var expectedMobility = new Dictionary<JointType, JointDegreeOfFreedom>
        {
            [JointType.Fixed] = JointDegreeOfFreedom.None,
            [JointType.Revolute] = JointDegreeOfFreedom.RotationZ,
            [JointType.Cylindrical] = JointDegreeOfFreedom.TranslationZ | JointDegreeOfFreedom.RotationZ,
            [JointType.Translational] = JointDegreeOfFreedom.TranslationZ,
            [JointType.Universal] = JointDegreeOfFreedom.RotationX | JointDegreeOfFreedom.RotationY,
            [JointType.Spherical] = JointDegreeOfFreedom.AllRotations,
            [JointType.Planar] = JointDegreeOfFreedom.TranslationX | JointDegreeOfFreedom.TranslationY | JointDegreeOfFreedom.RotationZ
        };

        foreach (var pair in expectedMobility)
        {
            var actual = JointDefinition.ExpectedMobility(pair.Key);
            if (actual != pair.Value)
                throw new InvalidOperationException($"{pair.Key} mobility mismatch: expected {pair.Value}, observed {actual}.");
        }

        var axialFrame = new JointAxisFrame(
            new JointVector3(0, 0, 0),
            new JointVector3(0, 0, 1),
            null);
        axialFrame.Validate("revolute-axis", secondaryAxisRequired: false);

        var planarFrame = new JointAxisFrame(
            new JointVector3(10, 20, 30),
            new JointVector3(0, 0, 1),
            new JointVector3(1, 0, 0));
        planarFrame.Validate("planar-frame", secondaryAxisRequired: true);

        new JointDofSetting(
            JointDegreeOfFreedom.RotationZ,
            ElasticStiffness: 25.0,
            LowerLimit: -0.5,
            UpperLimit: 0.5,
            StopStiffness: 10000.0).Validate(
                "revolute-limited",
                JointDefinition.ExpectedMobility(JointType.Revolute));

        new JointDofSetting(
            JointDegreeOfFreedom.TranslationZ,
            ElasticStiffness: 100.0,
            LowerLimit: null,
            UpperLimit: null,
            StopStiffness: 0.0).Validate(
                "translational-spring",
                JointDefinition.ExpectedMobility(JointType.Translational));

        ExpectInvalidOperation(
            () => new JointAxisFrame(
                new JointVector3(0, 0, 0),
                new JointVector3(0, 0, 0),
                null).Validate("zero-axis", false),
            "joint frame accepted a zero primary axis",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new JointAxisFrame(
                new JointVector3(0, 0, 0),
                new JointVector3(0, 0, 1),
                new JointVector3(0, 0, 2)).Validate("collinear-frame", true),
            "joint frame accepted collinear primary and secondary axes",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new JointDofSetting(
                JointDegreeOfFreedom.TranslationX,
                ElasticStiffness: 10.0,
                LowerLimit: null,
                UpperLimit: null,
                StopStiffness: 0.0).Validate(
                    "constrained-dof-data",
                    JointDefinition.ExpectedMobility(JointType.Revolute)),
            "joint accepted data on a constrained DOF",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new JointDofSetting(
                JointDegreeOfFreedom.RotationZ,
                ElasticStiffness: 0.0,
                LowerLimit: 1.0,
                UpperLimit: -1.0,
                StopStiffness: 1000.0).Validate(
                    "reversed-limits",
                    JointDefinition.ExpectedMobility(JointType.Revolute)),
            "joint accepted reversed travel limits",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new JointDofSetting(
                JointDegreeOfFreedom.RotationZ,
                ElasticStiffness: 0.0,
                LowerLimit: null,
                UpperLimit: null,
                StopStiffness: 1000.0).Validate(
                    "stop-without-limit",
                    JointDefinition.ExpectedMobility(JointType.Revolute)),
            "joint accepted stop stiffness without travel limits",
            ref expectedFailures);

        if (expectedFailures != 5)
            throw new InvalidOperationException($"WS06.2 expected 5 deterministic rejection fixtures, observed {expectedFailures}.");

        Console.WriteLine("PASS WS06.2 Joints domain smoke | joint-families=7 | valid-frames=2 | valid-dof-settings=2 | deterministic-rejections=5");
    }

    private static void RunRemoteBoundaryConditionSmoke()
    {
        var expectedFailures = 0;

        RemoteCoordinateFrame.Global.Validate("global-displacement");
        new RemoteCoordinateFrame(
            false,
            new RemoteVector3(1, 0, 0),
            new RemoteVector3(0, 1, 0)).Validate("local-frame");

        new RemoteComponents(0.0, null, null, null, null, 0.01)
            .Validate("remote-displacement", RemoteBoundaryConditionType.Displacement);
        new RemoteComponents(1000.0, -250.0, null, null, null, null)
            .Validate("remote-force", RemoteBoundaryConditionType.Force);
        new RemoteComponents(null, null, null, null, 5000.0, null)
            .Validate("remote-moment", RemoteBoundaryConditionType.Moment);

        new RemoteCouplingDefinition(RemoteCouplingBehavior.Rigid, RemoteWeightingMethod.Uniform, null)
            .Validate("rigid-coupling");
        new RemoteCouplingDefinition(RemoteCouplingBehavior.Deformable, RemoteWeightingMethod.AreaWeighted, null)
            .Validate("area-coupling");
        new RemoteCouplingDefinition(RemoteCouplingBehavior.Deformable, RemoteWeightingMethod.DistanceWeighted, 2.0)
            .Validate("distance-coupling");

        ExpectInvalidOperation(
            () => new RemoteCoordinateFrame(
                true,
                new RemoteVector3(1, 0, 0),
                null).Validate("global-with-local-axis"),
            "global remote frame accepted a local axis",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteCoordinateFrame(false, null, null).Validate("missing-local-axes"),
            "local remote frame accepted missing axes",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteCoordinateFrame(
                false,
                new RemoteVector3(1, 0, 0),
                new RemoteVector3(2, 0, 0)).Validate("collinear-local-axes"),
            "local remote frame accepted collinear axes",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteComponents(1000.0, null, null, null, 1.0, null)
                .Validate("force-with-moment", RemoteBoundaryConditionType.Force),
            "remote force accepted rotational components",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteComponents(1.0, null, null, null, 1000.0, null)
                .Validate("moment-with-force", RemoteBoundaryConditionType.Moment),
            "remote moment accepted translational components",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteComponents(0.0, 0.0, 0.0, null, null, null)
                .Validate("zero-force", RemoteBoundaryConditionType.Force),
            "remote force accepted an all-zero load",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteCouplingDefinition(
                RemoteCouplingBehavior.Deformable,
                RemoteWeightingMethod.DistanceWeighted,
                null).Validate("missing-distance-exponent"),
            "distance weighting accepted a missing exponent",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteCouplingDefinition(
                RemoteCouplingBehavior.Rigid,
                RemoteWeightingMethod.AreaWeighted,
                null).Validate("rigid-area-weighting"),
            "rigid coupling accepted deformable weighting",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new RemoteComponents(double.NaN, null, null, null, null, null)
                .Validate("nan-displacement", RemoteBoundaryConditionType.Displacement),
            "remote components accepted a non-finite value",
            ref expectedFailures);

        if (expectedFailures != 9)
            throw new InvalidOperationException($"WS06.3 expected 9 deterministic rejection fixtures, observed {expectedFailures}.");

        Console.WriteLine("PASS WS06.3 Remote Boundary Conditions domain smoke | valid-frames=2 | valid-component-sets=3 | valid-couplings=3 | deterministic-rejections=9");
    }

    private static void RunConstraintEquationSmoke()
    {
        var expectedFailures = 0;
        var node1X = new ConstraintEquationTerm(
            new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 1, null),
            ConstraintDegreeOfFreedom.TranslationX,
            1.0);
        var node2X = new ConstraintEquationTerm(
            new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 2, null),
            ConstraintDegreeOfFreedom.TranslationX,
            -1.0);

        var tie = new ConstraintEquationDefinition
        {
            Id = Guid.NewGuid(),
            Name = "Ux tie",
            Terms = new[] { node1X, node2X },
            RightHandSide = 0.0
        };
        tie.Validate();

        var remoteA = Guid.NewGuid();
        var remoteB = Guid.NewGuid();
        var remoteRotationTie = new ConstraintEquationDefinition
        {
            Id = Guid.NewGuid(),
            Name = "Remote Rz tie",
            Terms = new[]
            {
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.RemotePoint, null, remoteA),
                    ConstraintDegreeOfFreedom.RotationZ,
                    1.0),
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.RemotePoint, null, remoteB),
                    ConstraintDegreeOfFreedom.RotationZ,
                    -1.0)
            },
            RightHandSide = 0.0
        };
        remoteRotationTie.Validate();

        var mixed = new ConstraintEquationDefinition
        {
            Id = Guid.NewGuid(),
            Name = "Lever-arm compatibility",
            Terms = new[]
            {
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 3, null),
                    ConstraintDegreeOfFreedom.TranslationY,
                    1.0),
                new ConstraintEquationTerm(
                    new ConstraintTermTarget(ConstraintTargetKind.RemotePoint, null, remoteA),
                    ConstraintDegreeOfFreedom.RotationZ,
                    -1.0)
            },
            RightHandSide = 0.0,
            MixedDofLengthScale = 250.0
        };
        var scaled = mixed.BuildDimensionallyScaledTerms();
        if (Math.Abs(scaled[1].Coefficient + 250.0) > 1e-12)
            throw new InvalidOperationException("Mixed constraint equation did not apply the dimensional length scale to rotational terms.");

        ExpectInvalidOperation(
            () => new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "single-term",
                Terms = new[] { node1X },
                RightHandSide = 0.0
            }.Validate(),
            "constraint equation accepted a single term",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationTerm(
                new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 1, null),
                ConstraintDegreeOfFreedom.TranslationX,
                0.0).Validate("zero-coefficient"),
            "constraint equation accepted a zero coefficient",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "duplicate-term",
                Terms = new[] { node1X, node1X with { Coefficient = -1.0 } },
                RightHandSide = 0.0
            }.Validate(),
            "constraint equation accepted duplicate target/DOF terms",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationTerm(
                new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 1, null),
                ConstraintDegreeOfFreedom.RotationX,
                1.0).Validate("solid-node-rotation"),
            "constraint equation accepted rotational DOF on a solid mesh node",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "mixed-without-scale",
                Terms = new[]
                {
                    node1X,
                    new ConstraintEquationTerm(
                        new ConstraintTermTarget(ConstraintTargetKind.RemotePoint, null, remoteA),
                        ConstraintDegreeOfFreedom.RotationZ,
                        -1.0)
                },
                RightHandSide = 0.0
            }.Validate(),
            "mixed constraint equation accepted missing dimensional scale",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "scale-on-translation-only",
                Terms = new[] { node1X, node2X },
                RightHandSide = 0.0,
                MixedDofLengthScale = 100.0
            }.Validate(),
            "translation-only constraint equation accepted a mixed-DOF scale",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationTerm(
                new ConstraintTermTarget(ConstraintTargetKind.MeshNode, 0, null),
                ConstraintDegreeOfFreedom.TranslationX,
                1.0).Validate("invalid-node-id"),
            "constraint equation accepted an invalid mesh-node ID",
            ref expectedFailures);

        ExpectInvalidOperation(
            () => new ConstraintEquationDefinition
            {
                Id = Guid.NewGuid(),
                Name = "non-finite-rhs",
                Terms = new[] { node1X, node2X },
                RightHandSide = double.PositiveInfinity
            }.Validate(),
            "constraint equation accepted a non-finite right-hand side",
            ref expectedFailures);

        if (expectedFailures != 8)
            throw new InvalidOperationException($"WS06.4 expected 8 deterministic rejection fixtures, observed {expectedFailures}.");

        Console.WriteLine("PASS WS06.4 Constraint Equations domain smoke | valid-equations=3 | mixed-dimensional-scaling=1 | deterministic-rejections=8");
    }

    private static void ExpectInvalidOperation(Action action, string message, ref int counter)
    {
        try
        {
            action();
        }
        catch (InvalidOperationException)
        {
            counter++;
            return;
        }

        throw new InvalidOperationException(message);
    }
}
