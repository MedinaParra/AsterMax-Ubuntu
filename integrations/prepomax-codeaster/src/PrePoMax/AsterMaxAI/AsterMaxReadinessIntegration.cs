using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxModelReadiness _asterMaxModelReadiness;

        private void InstallAsterMaxModelReadiness()
        {
            if (_asterMaxModelReadiness != null) return;
            _asterMaxModelReadiness = new AsterMaxModelReadiness(_controller);
            Controls.Add(_asterMaxModelReadiness);
            _asterMaxModelReadiness.BringToFront();
            Shown += (s, e) => { if (_asterMaxModelReadiness != null && !_asterMaxModelReadiness.IsDisposed) { _asterMaxModelReadiness.BringToFront(); _asterMaxModelReadiness.RefreshReadiness(); } };
        }
    }
}
