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

                AsterMaxPmxRoundtripHarness pmxHarness = new AsterMaxPmxRoundtripHarness(_controller, _vtk, _asterMaxNativeVtkAnchorLayer);
                BeginInvoke((System.Action)(() => pmxHarness.RunIfRequested()));

                AsterMaxStepMmHarness stepHarness = new AsterMaxStepMmHarness(_controller);
                BeginInvoke((System.Action)(() => stepHarness.RunIfRequested()));

                // C8.60 produces the real STEP/mm -> native NetGen FE mesh.
                AsterMaxStepMeshHarness meshHarness = new AsterMaxStepMeshHarness(_controller);
                BeginInvoke((System.Action)(() => meshHarness.RunIfRequested()));

                // C8.61/C8.62 consumes that exact FE mesh, locks mm/N/MPa, and configures the structural model.
                AsterMaxStructuralSetupHarness setupHarness = new AsterMaxStructuralSetupHarness(_controller);
                BeginInvoke((System.Action)(() => setupHarness.RunIfRequested()));

                // C8.62 runs after structural setup: native PMX roundtrip then Code_Aster study generation only.
                AsterMaxCodeAsterGenerationHarness generationHarness = new AsterMaxCodeAsterGenerationHarness(_controller);
                BeginInvoke((System.Action)(() => generationHarness.RunIfRequested()));

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
