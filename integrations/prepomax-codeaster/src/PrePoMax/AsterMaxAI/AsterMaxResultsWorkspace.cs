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
            Height = 92;
            MinimumSize = new Size(0, 82);
            BackColor = Color.White;
            Padding = new Padding(0);

            Panel topBorder = new Panel();
            topBorder.Dock = DockStyle.Top;
            topBorder.Height = 1;
            topBorder.BackColor = AsterMaxUiTheme.Border;

            Panel header = new Panel();
            header.Dock = DockStyle.Left;
            header.Width = 155;
            header.BackColor = AsterMaxUiTheme.SurfaceAlt;
            header.Padding = new Padding(12, 12, 10, 8);

            Label title = new Label();
            title.Dock = DockStyle.Top;
            title.Height = 24;
            title.Text = "RESULTS";
            title.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 10.5f, FontStyle.Bold);
            title.ForeColor = AsterMaxUiTheme.TextPrimary;
            header.Controls.Add(title);

            Label subtitle = new Label();
            subtitle.Dock = DockStyle.Fill;
            subtitle.Text = "Native postprocess\r\nevidence-aware";
            subtitle.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.1f, FontStyle.Regular);
            subtitle.ForeColor = AsterMaxUiTheme.TextSecondary;
            header.Controls.Add(subtitle);

            FlowLayoutPanel cards = new FlowLayoutPanel();
            cards.Dock = DockStyle.Fill;
            cards.FlowDirection = FlowDirection.LeftToRight;
            cards.WrapContents = false;
            cards.AutoScroll = true;
            cards.Padding = new Padding(8, 8, 8, 3);
            cards.BackColor = Color.White;

            _fieldValue = AddCard(cards, "ACTIVE FIELD", "—", 150);
            _componentValue = AddCard(cards, "COMPONENT", "—", 125);
            _unitsValue = AddCard(cards, "UNIT CONTRACT", "mm · N · MPa", 130);
            _resultValue = AddCard(cards, "RESULT OBJECT", "No results", 135);
            _evidenceValue = AddCard(cards, "EVIDENCE", "NO RESULTS", 150);

            Panel footer = new Panel();
            footer.Dock = DockStyle.Bottom;
            footer.Height = 22;
            footer.BackColor = AsterMaxUiTheme.Surface;
            footer.Padding = new Padding(8, 2, 8, 2);
            _provenance = new Label();
            _provenance.Dock = DockStyle.Fill;
            _provenance.Text = "Observed GUI state only · loaded results are not solver-verified until admitted by the Code_Aster evidence chain.";
            _provenance.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.8f, FontStyle.Regular);
            _provenance.ForeColor = AsterMaxUiTheme.TextSecondary;
            footer.Controls.Add(_provenance);

            Controls.Add(cards);
            Controls.Add(header);
            Controls.Add(footer);
            Controls.Add(topBorder);

            _timer = new Timer();
            _timer.Interval = 1000;
            _timer.Tick += (s, e) => RefreshObservedState();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();

            RefreshObservedState();
        }

        private static Label AddCard(FlowLayoutPanel host, string caption, string initialValue, int width)
        {
            Panel card = new Panel();
            card.Width = width;
            card.Height = 54;
            card.Margin = new Padding(4, 0, 4, 0);
            card.Padding = new Padding(8, 5, 8, 4);
            card.BackColor = AsterMaxUiTheme.Surface;

            Label cap = new Label();
            cap.Dock = DockStyle.Top;
            cap.Height = 18;
            cap.Text = caption;
            cap.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 7.6f, FontStyle.Bold);
            cap.ForeColor = AsterMaxUiTheme.TextSecondary;

            Label value = new Label();
            value.Dock = DockStyle.Fill;
            value.Text = initialValue;
            value.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9.3f, FontStyle.Bold);
            value.ForeColor = AsterMaxUiTheme.TextPrimary;
            value.AutoEllipsis = true;

            card.Controls.Add(value);
            card.Controls.Add(cap);
            host.Controls.Add(card);
            return value;
        }

        public void RefreshObservedState()
        {
            bool resultLoaded = false;
            string field = "—";
            string component = "—";

            try { resultLoaded = _controller != null && _controller.CurrentResult != null; }
            catch { resultLoaded = false; }

            try
            {
                if (_controller != null && _controller.CurrentFieldData != null)
                {
                    field = String.IsNullOrWhiteSpace(_controller.CurrentFieldData.Name) ? "—" : _controller.CurrentFieldData.Name;
                    component = String.IsNullOrWhiteSpace(_controller.CurrentFieldData.Component) ? "—" : _controller.CurrentFieldData.Component;
                }
            }
            catch
            {
                field = "Unknown";
                component = "Unknown";
            }

            _fieldValue.Text = field;
            _componentValue.Text = component;
            _unitsValue.Text = "mm · N · MPa";
            _resultValue.Text = resultLoaded ? "Loaded" : "No results";

            if (resultLoaded)
            {
                _resultValue.ForeColor = AsterMaxUiTheme.Success;
                _evidenceValue.Text = "UNVERIFIED";
                _evidenceValue.ForeColor = Color.FromArgb(177, 104, 24);
                _provenance.Text = "Result object observed · solver verification is intentionally withheld until admitted Code_Aster evidence is connected.";
            }
            else
            {
                _resultValue.ForeColor = AsterMaxUiTheme.TextSecondary;
                _evidenceValue.Text = "NO RESULTS";
                _evidenceValue.ForeColor = AsterMaxUiTheme.TextSecondary;
                _provenance.Text = "No result object observed · no numerical result is inferred or displayed by AsterMax.";
            }
        }
    }
}
