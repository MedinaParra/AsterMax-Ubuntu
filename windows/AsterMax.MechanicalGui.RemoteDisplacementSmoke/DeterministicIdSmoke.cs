using System.Reflection;
using System.Runtime.CompilerServices;
using AsterMax.MechanicalGui;

internal static class DeterministicIdSmoke
{
    [ModuleInitializer]
    internal static void Run()
    {
        var method = typeof(RigidRemoteDisplacementRuntime).GetMethod(
            "StableEquationId",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Stable Remote Displacement MPC ID generator was not found.");

        var remoteId = Guid.Parse("3e62af49-0fb2-4f7f-b8f9-2d46a5d6c2bb");
        var first = (Guid)(method.Invoke(null, new object[]
        {
            remoteId,
            42,
            ConstraintDegreeOfFreedom.TranslationY
        }) ?? throw new InvalidOperationException("Stable ID generator returned null."));
        var repeat = (Guid)(method.Invoke(null, new object[]
        {
            remoteId,
            42,
            ConstraintDegreeOfFreedom.TranslationY
        }) ?? throw new InvalidOperationException("Stable ID generator returned null."));
        var differentNode = (Guid)(method.Invoke(null, new object[]
        {
            remoteId,
            43,
            ConstraintDegreeOfFreedom.TranslationY
        }) ?? throw new InvalidOperationException("Stable ID generator returned null."));
        var differentDof = (Guid)(method.Invoke(null, new object[]
        {
            remoteId,
            42,
            ConstraintDegreeOfFreedom.TranslationZ
        }) ?? throw new InvalidOperationException("Stable ID generator returned null."));

        if (first == Guid.Empty || first != repeat || first == differentNode || first == differentDof)
            throw new InvalidOperationException("Rigid Remote Displacement deterministic MPC identity gate failed.");

        Console.WriteLine("PASS Rigid Remote Displacement deterministic MPC identifiers");
    }
}
