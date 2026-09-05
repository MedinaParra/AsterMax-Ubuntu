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

                // C8.58 persistence proof remains opt-in and untouched.
                AsterMaxPmxRoundtripHarness pmxHarness = new AsterMaxPmxRoundtripHarness(_controller, _vtk, _asterMaxNativeVtkAnchorLayer);
                BeginInvoke((System.Action)(() => pmxHarness.RunIfRequested()));

                // C8.59 is a separate fail-closed CAD qualification path: a real STEP file is
                // imported through Controller.ImportFile and its known millimetre extents are
                // checked before any meshing or solver claim is allowed.
                AsterMaxStepMmHarness stepHarness = new AsterMaxStepMmHarness(_controller);
                BeginInvoke((System.Action)(() => stepHarness.RunIfRequested()));

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
