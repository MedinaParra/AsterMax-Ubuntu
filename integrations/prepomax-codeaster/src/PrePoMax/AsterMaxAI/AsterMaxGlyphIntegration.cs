using System.Drawing;
using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxGlyphLayer _asterMaxGlyphLayer;

        private void InstallAsterMaxGlyphLayer()
        {
            if (_asterMaxGlyphLayer != null) return;
            _asterMaxGlyphLayer = new AsterMaxGlyphLayer(_controller);
            _asterMaxGlyphLayer.Location = new Point(310, 112);
            Controls.Add(_asterMaxGlyphLayer);
            _asterMaxGlyphLayer.BringToFront();

            Shown += (s, e) =>
            {
                if (_asterMaxGlyphLayer == null || _asterMaxGlyphLayer.IsDisposed) return;
                _asterMaxGlyphLayer.Location = new Point(310, 112);
                _asterMaxGlyphLayer.BringToFront();
                _asterMaxGlyphLayer.RefreshObservedState();
            };
        }
    }
}
