namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private System.Windows.Forms.Timer? _deferredCloseTimer;
    private bool _deferredCloseRequested;

    private void HandleFormClosingDuringOperation(object? sender, FormClosingEventArgs eventArgs)
    {
        if (_activeOperation is null || _deferredCloseRequested) return;

        eventArgs.Cancel = true;
        _deferredCloseRequested = true;
        _statusMain.Text = "Cancelling active geometry operation before exit…";
        Log("APPLICATION CLOSE: cancelling active geometry operation and waiting for child process cleanup.");
        _activeOperation.Cancel();

        _deferredCloseTimer ??= new System.Windows.Forms.Timer { Interval = 50 };
        _deferredCloseTimer.Tick -= DeferredCloseTick;
        _deferredCloseTimer.Tick += DeferredCloseTick;
        _deferredCloseTimer.Start();
    }

    private void DeferredCloseTick(object? sender, EventArgs eventArgs)
    {
        if (_activeOperation is not null) return;
        _deferredCloseTimer?.Stop();
        _deferredCloseTimer?.Dispose();
        _deferredCloseTimer = null;
        FormClosing -= HandleFormClosingDuringOperation;
        _deferredCloseRequested = false;
        Close();
    }
}
