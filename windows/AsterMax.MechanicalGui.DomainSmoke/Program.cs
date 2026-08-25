using AsterMax.MechanicalGui;

static class DomainSmoke
{
    private static int _expectedFailures;

    public static int Main()
    {
        try
        {
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

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.Preserve,
                    0.1,
                    null,
                    null).Validate("preserve-with-offset", 5.0),
                "preserve mode accepted a user offset");

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.UserDefinedOffset,
                    0.0,
                    null,
                    null).Validate("zero-offset", 5.0),
                "zero user offset was accepted");

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.UserDefinedOffset,
                    6.0,
                    null,
                    null).Validate("offset-outside-pinball", 5.0),
                "offset beyond pinball radius was accepted");

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.AdjustToTouch,
                    null,
                    null,
                    null).Validate("missing-adjustment", 5.0),
                "AdjustToTouch accepted a missing maximum adjustment");

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.AdjustToTouch,
                    null,
                    6.0,
                    null).Validate("adjustment-outside-pinball", 5.0),
                "adjustment beyond pinball radius was accepted");

            ExpectFailure(
                () => new ContactOffsetControl(
                    ContactInitialGapTreatment.UserDefinedOffset,
                    0.25,
                    null,
                    -0.01).Validate("negative-penetration-tolerance", 5.0),
                "negative penetration tolerance was accepted");

            if (_expectedFailures != 6)
                throw new InvalidOperationException($"Expected 6 deterministic rejection fixtures, observed {_expectedFailures}.");

            Console.WriteLine("PASS WS06.1 Contact Offset Control domain smoke | valid=4 | deterministic-rejections=6");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception);
            return 1;
        }
    }

    private static void ExpectFailure(Action action, string message)
    {
        try
        {
            action();
        }
        catch (InvalidOperationException)
        {
            _expectedFailures++;
            return;
        }

        throw new InvalidOperationException(message);
    }
}
