using AsterMax.MechanicalGui;

static class DomainSmoke
{
    public static int Main()
    {
        try
        {
            RunContactOffsetSmoke();
            RunJointSmoke();
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
