using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxNativeVtkAnchorLayer _asterMaxNativeVtkAnchorLayer;

        public void AsterMaxPrepareNativeVtkAnchorShutdown()
        {
            if (InvokeRequired)
            {
                Invoke(new System.Action(AsterMaxPrepareNativeVtkAnchorShutdown));
                return;
            }

            if (_asterMaxNativeVtkAnchorLayer != null)
            {
                _asterMaxNativeVtkAnchorLayer.Dispose();
                _asterMaxNativeVtkAnchorLayer = null;
            }
        }

        private static bool IsAsterMaxResultsPresentationProcess()
        {
            string[] args = System.Environment.GetCommandLineArgs();
            if (args == null) return false;
            foreach (string arg in args)
            {
                if (string.Equals(arg, "--astermax-results-demo", System.StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            return false;
        }

        private void InstallAsterMaxNativeVtkAnchorLayer()
        {
            Shown += (s, e) =>
            {
                if (IsAsterMaxResultsPresentationProcess()) return;
                if (_asterMaxNativeVtkAnchorLayer != null || _vtk == null) return;
                _asterMaxNativeVtkAnchorLayer = new AsterMaxNativeVtkAnchorLayer(_controller, _vtk);

                AsterMaxPmxRoundtripHarness pmxHarness = new AsterMaxPmxRoundtripHarness(_controller, _vtk, _asterMaxNativeVtkAnchorLayer);
                BeginInvoke((System.Action)(() => pmxHarness.RunIfRequested()));

                AsterMaxStepMmHarness stepHarness = new AsterMaxStepMmHarness(_controller);
                BeginInvoke((System.Action)(() => stepHarness.RunIfRequested()));

                AsterMaxStepMeshHarness meshHarness = new AsterMaxStepMeshHarness(_controller);
                BeginInvoke((System.Action)(() => meshHarness.RunIfRequested()));

                AsterMaxNativeRefinementPersistenceHarness refinementHarness = new AsterMaxNativeRefinementPersistenceHarness(_controller);
                BeginInvoke((System.Action)(() => refinementHarness.RunIfRequested()));

                // C8.89 standalone fixture: bind admitted physical ROI centroids to native CAD surfaces,
                // persist through PMX and prove the reloaded native NetGen path consumes the controls.
                AsterMaxNativeRoiConsumerHarness roiConsumerHarness = new AsterMaxNativeRoiConsumerHarness(_controller);
                BeginInvoke((System.Action)(() => roiConsumerHarness.RunIfRequested()));

                AsterMaxStructuralSetupHarness setupHarness = new AsterMaxStructuralSetupHarness(_controller);
                BeginInvoke((System.Action)(() => setupHarness.RunIfRequested()));

                AsterMaxCodeAsterGenerationHarness generationHarness = new AsterMaxCodeAsterGenerationHarness(_controller);
                BeginInvoke((System.Action)(() => generationHarness.RunIfRequested()));

                FormClosing += (fs, fe) => AsterMaxPrepareNativeVtkAnchorShutdown();
            };
        }
    }
}
