namespace AsterMax.MechanicalGui;

internal static class MechanicalViewportTutorialExtensions
{
    public static void SetThermalSolution(
        this MechanicalViewport viewport,
        ThermalSolution solution,
        SimpleFace hotFace,
        SimpleFace coldFace)
    {
        viewport.ResultVisible = false;
        viewport.SupportVisible = false;
        viewport.ForceVisible = false;
        viewport.Caption = "Steady-State Thermal";
        viewport.SubCaption =
            $"{hotFace}: {solution.MaximumTemperatureC:0.###} °C · " +
            $"{coldFace}: {solution.MinimumTemperatureC:0.###} °C · " +
            $"Heat flow {solution.HeatFlowW:0.###} W";
        viewport.Invalidate();
    }
}
