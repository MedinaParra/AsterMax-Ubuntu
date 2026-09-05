using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxViewportProjectionOverlay _asterMaxViewportProjectionOverlay;

        private void InstallAsterMaxViewportProjectionOverlay()
        {
            Shown += (s, e) =>
            {
                if (_asterMaxViewportProjectionOverlay != null && !_asterMaxViewportProjectionOverlay.IsDisposed)
                    return;

                AsterMaxViewportProjectionOverlay overlay;
                if (AsterMaxViewportProjectionOverlay.TryCreate(_controller, this, out overlay))
                {
                    _asterMaxViewportProjectionOverlay = overlay;
                    _asterMaxViewportProjectionOverlay.BringToFront();
                    _asterMaxViewportProjectionOverlay.RefreshProjectedAnchors();
                }
            };
        }
    }
}
