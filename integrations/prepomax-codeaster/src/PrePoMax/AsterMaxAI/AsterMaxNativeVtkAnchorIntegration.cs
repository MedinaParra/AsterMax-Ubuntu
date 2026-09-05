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
