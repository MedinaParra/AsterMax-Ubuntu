using System;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxResultsWorkspace : UserControl
    {
        private readonly Controller _controller;
        private readonly Label _fieldValue;
        private readonly Label _componentValue;
        private readonly Label _unitsValue;
        private readonly Label _resultValue;
        private readonly Label _evidenceValue;
        private readonly Label _provenance;
        private readonly Timer _timer;

        public AsterMaxResultsWorkspace(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxResultsWorkspace";
            Dock = DockStyle.Bottom;
            Height = 98;
            MinimumSize = new Size(0, 88);
            BackColor = AsterMaxUiTheme.Background;

            Panel topBorder = new Panel { Dock = DockStyle.Top, Height = 1, BackColor = AsterMaxUiTheme.AccentDark };
            Panel header = new Panel { Dock = DockStyle.Left, Width = 170, BackColor = AsterMaxUiTheme.SurfaceAlt, Padding = new Padding(12, 12, 10, 8) };
            Label title = new Label { Dock = DockStyle.Top, Height = 24, Text = "RESULTS HUD", Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10.5f, FontStyle.Bold), ForeColor = AsterMaxUiTheme.AccentGlow };
            Label subtitle = new Label { Dock = DockStyle.Fill, Text = "Native postprocess\r\nevidence-aware", Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.1f), ForeColor = AsterMaxUiTheme.TextSecondary };
            header.Controls.Add(subtitle); header.Controls.Add(title);

            FlowLayoutPanel cards = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.LeftToRight, WrapContents = false, AutoScroll = true, Padding = new Padding(8, 8, 8, 3), BackColor = AsterMaxUiTheme.Background };
            _fieldValue = AddCard(cards, "ACTIVE FIELD", "—", 150);
            _componentValue = AddCard(cards, "COMPONENT", "—", 125);
            _unitsValue = AddCard(cards, "UNIT CONTRACT", "mm · N · MPa", 135);
            _resultValue = AddCard(cards, "RESULT OBJECT", "No results", 135);
            _evidenceValue = AddCard(cards, "EVIDENCE", "NO RESULTS", 155);

            Panel footer = new Panel { Dock = DockStyle.Bottom, Height = 24, BackColor = AsterMaxUiTheme.Surface, Padding = new Padding(8, 3, 8, 2) };
            _provenance = new Label { Dock = DockStyle.Fill, Text = "Observed GUI state only · loaded results are not solver-verified until admitted by the Code_Aster evidence chain.", Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.8f), ForeColor = AsterMaxUiTheme.TextSecondary };
            footer.Controls.Add(_provenance);

            Controls.Add(cards); Controls.Add(header); Controls.Add(footer); Controls.Add(topBorder);
            _timer = new Timer { Interval = 1000 }; _timer.Tick += (s, e) => RefreshObservedState(); _timer.Start(); Disposed += (s, e) => _timer.Dispose(); RefreshObservedState();
        }

        private static Label AddCard(FlowLayoutPanel host, string caption, string initialValue, int width)
        {
            Panel card = new Panel { Width = width, Height = 58, Margin = new Padding(4, 0, 4, 0), Padding = new Padding(8, 6, 8, 4), BackColor = AsterMaxUiTheme.SurfaceRaised };
            Label cap = new Label { Dock = DockStyle.Top, Height = 18, Text = caption, Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.6f, FontStyle.Bold), ForeColor = AsterMaxUiTheme.TextSecondary };
            Label value = new Label { Dock = DockStyle.Fill, Text = initialValue, Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9.5f, FontStyle.Bold), ForeColor = AsterMaxUiTheme.TextPrimary, AutoEllipsis = true };
            card.Controls.Add(value); card.Controls.Add(cap); host.Controls.Add(card); return value;
        }

        public void RefreshObservedState()
        {
            bool resultLoaded = false; string field = "—"; string component = "—";
            try { resultLoaded = _controller != null && _controller.CurrentResult != null; } catch { resultLoaded = false; }
            try { if (_controller != null && _controller.CurrentFieldData != null) { field = String.IsNullOrWhiteSpace(_controller.CurrentFieldData.Name) ? "—" : _controller.CurrentFieldData.Name; component = String.IsNullOrWhiteSpace(_controller.CurrentFieldData.Component) ? "—" : _controller.CurrentFieldData.Component; } }
            catch { field = "Unknown"; component = "Unknown"; }
            _fieldValue.Text = field; _componentValue.Text = component; _unitsValue.Text = "mm · N · MPa"; _unitsValue.ForeColor = AsterMaxUiTheme.Accent;
            _resultValue.Text = resultLoaded ? "Loaded" : "No results";
            if (resultLoaded) { _resultValue.ForeColor = AsterMaxUiTheme.Success; _evidenceValue.Text = "UNVERIFIED"; _evidenceValue.ForeColor = AsterMaxUiTheme.Warning; _provenance.Text = "Result object observed · solver verification is withheld until admitted Code_Aster evidence is connected."; }
            else { _resultValue.ForeColor = AsterMaxUiTheme.TextSecondary; _evidenceValue.Text = "NO RESULTS"; _evidenceValue.ForeColor = AsterMaxUiTheme.TextSecondary; _provenance.Text = "No result object observed · no numerical result is inferred or displayed by AsterMax."; }
        }
    }
}
