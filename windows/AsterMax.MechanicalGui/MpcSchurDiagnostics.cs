namespace AsterMax.MechanicalGui;

/// <summary>
/// Scoped, async-flow-local observation of exact MPC solves. This lets higher-level
/// runtime adapters recover Schur equilibrium forces without global mutable state or
/// a second structural solve. Nested scopes restore the previous observer on dispose.
/// </summary>
internal static class MpcSchurDiagnostics
{
    private static readonly AsyncLocal<Action<MpcSchurSolveResult>?> Observer = new();

    public static IDisposable Capture(Action<MpcSchurSolveResult> observer)
    {
        ArgumentNullException.ThrowIfNull(observer);
        var previous = Observer.Value;
        Observer.Value = observer;
        return new CaptureScope(previous);
    }

    internal static void Publish(MpcSchurSolveResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        Observer.Value?.Invoke(result);
    }

    private sealed class CaptureScope(Action<MpcSchurSolveResult>? previous) : IDisposable
    {
        private Action<MpcSchurSolveResult>? _previous = previous;
        private bool _disposed;

        public void Dispose()
        {
            if (_disposed) return;
            Observer.Value = _previous;
            _previous = null;
            _disposed = true;
        }
    }
}
