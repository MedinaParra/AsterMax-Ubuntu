namespace AsterMax.MechanicalGui;

/// <summary>
/// Compatibility shims for startup calls that existed before the responsive CAD canvas.
/// The old implementations used global WinForms timers and reflection to scan/reparent the
/// control tree every few hundred milliseconds. They are intentionally disabled: the
/// production MechanicalForm now owns its viewport and selection lifecycle directly.
/// </summary>
internal static class CadViewerQualityBootstrap
{
    internal static void Start()
    {
        // Intentionally no-op.
    }
}

internal static class MechanicalInterfaceRoadmapIteration
{
    internal static void Start()
    {
        // Intentionally no-op.
    }
}
