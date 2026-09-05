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
                // C8.75: the verified Results presentation has its own result/extrema widgets and does not
                // need the CAD/BC native-anchor harness layer. Keeping this unrelated layer alive during a
                // result-only demo increased native VTK teardown surface and previously caused a stale
                // vtkRenderer.RemoveActor call. Other harness modes retain the layer unchanged.
                if (IsAsterMaxResultsPresentationProcess()) return;

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

                FormClosing += (fs, fe) => AsterMaxPrepareNativeVtkAnchorShutdown();
            };
        }
    }
}
