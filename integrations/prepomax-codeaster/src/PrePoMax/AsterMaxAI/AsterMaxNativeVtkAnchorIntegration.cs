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

                // C8.59 fail-closed CAD-only STEP/mm qualification path.
                AsterMaxStepMmHarness stepHarness = new AsterMaxStepMmHarness(_controller);
                BeginInvoke((System.Action)(() => stepHarness.RunIfRequested()));

                // C8.60 independently starts from a clean model, imports the same real STEP/mm fixture,
                // invokes Controller.CreateMesh (native NetGen BREP route), and qualifies the resulting FE mesh.
                AsterMaxStepMeshHarness meshHarness = new AsterMaxStepMeshHarness(_controller);
                BeginInvoke((System.Action)(() => meshHarness.RunIfRequested()));

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
