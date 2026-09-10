namespace PrePoMax
{
    public partial class FrmMain
    {
        private PrePoMax.AsterMaxAI.AsterMaxRegionBindingInspector _asterMaxRegionBindingInspector;

        private void InstallAsterMaxRegionBindingInspector()
        {
            if (_asterMaxRegionBindingInspector != null) return;
            _asterMaxRegionBindingInspector = new PrePoMax.AsterMaxAI.AsterMaxRegionBindingInspector(_controller);
            Controls.Add(_asterMaxRegionBindingInspector);
            _asterMaxRegionBindingInspector.BringToFront();
        }
    }
}
