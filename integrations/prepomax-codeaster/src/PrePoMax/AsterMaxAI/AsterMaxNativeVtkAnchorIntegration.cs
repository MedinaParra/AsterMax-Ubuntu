using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxNativeVtkAnchorLayer _asterMaxNativeVtkAnchorLayer;

        private void InstallAsterMaxNativeVtkAnchorLayer()
        {
            Shown += (s, e) =>
            {
                if (_asterMaxNativeVtkAnchorLayer != null || _vtk == null) return;
                _asterMaxNativeVtkAnchorLayer = new AsterMaxNativeVtkAnchorLayer(_controller, _vtk);

                // C8.58: opt-in CI harness only. Build real CaeModel/CaeMesh objects, persist them
                // through Controller.SaveToPmx, reopen through Controller.Open(.pmx), then reuse
                // the production region resolver + native VTK anchor layer for verification.
                AsterMaxPmxRoundtripHarness pmxHarness = new AsterMaxPmxRoundtripHarness(_controller, _vtk, _asterMaxNativeVtkAnchorLayer);
                BeginInvoke((System.Action)(() => pmxHarness.RunIfRequested()));

                FormClosed += (fs, fe) =>
                {
                    if (_asterMaxNativeVtkAnchorLayer != null)
                    {
                        _asterMaxNativeVtkAnchorLayer.Dispose();
                        _asterMaxNativeVtkAnchorLayer = null;
                    }
                };
            };
        }
    }
}
