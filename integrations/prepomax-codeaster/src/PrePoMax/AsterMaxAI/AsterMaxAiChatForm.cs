using System;
using System.Collections.Generic;
using System.Drawing;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using Newtonsoft.Json.Linq;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxAiChatForm : Form
    {
        private readonly Controller _controller;
        private readonly RichTextBox _history;
        private readonly TextBox _input;
        private readonly Button _send;
        private readonly Button _clear;
        private readonly Label _status;
        private readonly Label _context;
        private readonly List<JObject> _messages = new List<JObject>();

        public AsterMaxAiChatForm(Controller controller)
        {
            _controller = controller;
            Text = "AsterMax AI — Engineering Copilot";
            Width = 620;
            Height = 780;
            MinimumSize = new Size(480, 580);
            StartPosition = FormStartPosition.CenterParent;
            BackColor = AsterMaxUiTheme.Background;
            ForeColor = AsterMaxUiTheme.TextPrimary;
            Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Regular);

            Panel header = new Panel { Dock = DockStyle.Top, Height = 88, Padding = new Padding(16, 11, 14, 8), BackColor = AsterMaxUiTheme.SurfaceAlt };
            PictureBox logo = new PictureBox { Width = 38, Height = 38, Left = 14, Top = 12, Image = AsterMaxUiTheme.CreateAiIcon(36), SizeMode = PictureBoxSizeMode.CenterImage };
            Label title = new Label { AutoSize = true, Left = 60, Top = 10, Text = "ASTERMAX AI", ForeColor = AsterMaxUiTheme.AccentGlow, Font = new Font(Font.FontFamily, 12.5f, FontStyle.Bold) };
            Label subtitle = new Label { AutoSize = true, Left = 61, Top = 37, Text = "Engineering Copilot · evidence-aware CAE assistant", ForeColor = AsterMaxUiTheme.TextSecondary };
            _status = new Label { AutoEllipsis = true, Left = 16, Top = 64, Height = 18, Width = 570, Text = ProviderStatus(), ForeColor = AsterMaxUiTheme.TextSecondary };
            header.Controls.Add(logo); header.Controls.Add(title); header.Controls.Add(subtitle); header.Controls.Add(_status);

            Panel contextBar = new Panel { Dock = DockStyle.Top, Height = 38, Padding = new Padding(14, 9, 12, 6), BackColor = AsterMaxUiTheme.Surface };
            _context = new Label { Dock = DockStyle.Fill, AutoEllipsis = true, ForeColor = AsterMaxUiTheme.Accent, Text = BuildContextBadge() };
            contextBar.Controls.Add(_context);

            _history = new RichTextBox { Dock = DockStyle.Fill, ReadOnly = true, BackColor = AsterMaxUiTheme.Background, ForeColor = AsterMaxUiTheme.TextPrimary, BorderStyle = BorderStyle.None, DetectUrls = false };
            Panel historyHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(16, 14, 16, 10), BackColor = AsterMaxUiTheme.Background };
            historyHost.Controls.Add(_history);

            Panel composer = new Panel { Dock = DockStyle.Bottom, Height = 130, Padding = new Padding(14, 10, 14, 12), BackColor = AsterMaxUiTheme.Surface };
            Panel inputHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(9), BackColor = AsterMaxUiTheme.SurfaceRaised };
            inputHost.Paint += (s, e) => ControlPaint.DrawBorder(e.Graphics, inputHost.ClientRectangle, AsterMaxUiTheme.Border, ButtonBorderStyle.Solid);
            _input = new TextBox { Multiline = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical, BorderStyle = BorderStyle.None, AcceptsReturn = true, BackColor = AsterMaxUiTheme.SurfaceRaised, ForeColor = AsterMaxUiTheme.TextPrimary };
            inputHost.Controls.Add(_input);

            Panel actions = new Panel { Dock = DockStyle.Right, Width = 120, Padding = new Padding(8, 0, 0, 0), BackColor = AsterMaxUiTheme.Surface };
            _send = new Button { Text = "ASK AI", Dock = DockStyle.Top, Height = 40 };
            AsterMaxUiTheme.StylePrimaryButton(_send);
            _clear = new Button { Text = "Clear", Dock = DockStyle.Top, Height = 34, Margin = new Padding(0, 8, 0, 0) };
            AsterMaxUiTheme.StyleSecondaryButton(_clear);
            actions.Controls.Add(_clear); actions.Controls.Add(_send);
            composer.Controls.Add(inputHost); composer.Controls.Add(actions);

            _send.Click += async (s, e) => await SendAsync();
            _clear.Click += (s, e) => ClearConversation();
            _input.KeyDown += async (s, e) => { if (e.Control && e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; await SendAsync(); } };

            Controls.Add(historyHost); Controls.Add(composer); Controls.Add(contextBar); Controls.Add(header);
            Append("AsterMax AI", "Ready. I can reason about the current model context, but Code_Aster remains solver authority. AI observations never become verified FEA evidence by themselves.");
        }

        private string ProviderStatus()
        {
            string endpoint = Environment.GetEnvironmentVariable("ASTERMAX_AI_ENDPOINT");
            string model = Environment.GetEnvironmentVariable("ASTERMAX_AI_MODEL");
            if (String.IsNullOrWhiteSpace(endpoint)) return "● AI offline · configure ASTERMAX_AI_ENDPOINT and ASTERMAX_AI_MODEL";
            return "● AI online · " + endpoint + " · model: " + (String.IsNullOrWhiteSpace(model) ? "default" : model);
        }

        private string BuildContextBadge()
        {
            string view = "—"; bool modelLoaded = false; bool resultLoaded = false;
            try { if (_controller != null) view = _controller.CurrentView.ToString(); } catch { }
            try { modelLoaded = _controller != null && _controller.Model != null; } catch { }
            try { resultLoaded = _controller != null && _controller.CurrentResult != null; } catch { }
            return "LIVE CONTEXT · " + view + "   |   model " + (modelLoaded ? "loaded" : "empty") + "   |   results " + (resultLoaded ? "loaded" : "empty") + "   |   mm-N-MPa";
        }

        private string BuildEngineeringContext()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("AsterMax Mechanical engineering context"); sb.AppendLine("Unit contract: mm-N-MPa"); sb.AppendLine("Solver authority: Code_Aster; never fabricate FEA results.");
            if (_controller != null)
            {
                try { sb.AppendLine("Current view: " + _controller.CurrentView); } catch { }
                try { sb.AppendLine("Model loaded: " + (_controller.Model != null)); } catch { }
                try { sb.AppendLine("Result loaded: " + (_controller.CurrentResult != null)); } catch { }
                try { if (_controller.CurrentFieldData != null) sb.AppendLine("Current result field: " + _controller.CurrentFieldData.Name + " / " + _controller.CurrentFieldData.Component); } catch { }
            }
            sb.AppendLine("Rules: distinguish observed model state, AI inference and solver-verified evidence. industrial_validation=false; ansys_equivalence=false unless independently demonstrated.");
            return sb.ToString();
        }

        private async Task SendAsync()
        {
            string text = _input.Text.Trim(); if (text.Length == 0) return; _input.Clear(); Append("You", text);
            string endpoint = Environment.GetEnvironmentVariable("ASTERMAX_AI_ENDPOINT");
            if (String.IsNullOrWhiteSpace(endpoint)) { Append("AsterMax AI", "AI provider is not configured. The panel and engineering-context reader are active, but no remote inference is being performed."); return; }
            _send.Enabled = false; _status.Text = "● AI reasoning…"; _context.Text = BuildContextBadge();
            try { Append("AsterMax AI", await Task.Run(() => CallProvider(endpoint, text))); }
            catch (Exception ex) { Append("AsterMax AI", "Provider error: " + ex.Message); }
            finally { _send.Enabled = true; _status.Text = ProviderStatus(); _context.Text = BuildContextBadge(); }
        }

        private void ClearConversation() { _messages.Clear(); _history.Clear(); Append("AsterMax AI", "Conversation cleared. Model context will be read again on the next request."); _input.Focus(); }

        private string CallProvider(string endpoint, string userText)
        {
            string model = Environment.GetEnvironmentVariable("ASTERMAX_AI_MODEL") ?? "default"; string key = Environment.GetEnvironmentVariable("ASTERMAX_AI_API_KEY"); string url = endpoint.TrimEnd('/') + "/v1/chat/completions";
            JArray messages = new JArray(); messages.Add(new JObject { ["role"] = "system", ["content"] = BuildEngineeringContext() }); foreach (JObject m in _messages) messages.Add(m); JObject user = new JObject { ["role"] = "user", ["content"] = userText }; messages.Add(user);
            JObject payload = new JObject { ["model"] = model, ["messages"] = messages, ["temperature"] = 0.2 };
            using (WebClient wc = new WebClient())
            {
                wc.Encoding = Encoding.UTF8; wc.Headers[HttpRequestHeader.ContentType] = "application/json"; if (!String.IsNullOrWhiteSpace(key)) wc.Headers[HttpRequestHeader.Authorization] = "Bearer " + key;
                JObject obj = JObject.Parse(wc.UploadString(url, "POST", payload.ToString())); JToken token = obj.SelectToken("choices[0].message.content"); if (token == null) throw new InvalidOperationException("Response missing choices[0].message.content");
                string answer = token.ToString(); _messages.Add(user); _messages.Add(new JObject { ["role"] = "assistant", ["content"] = answer }); return answer;
            }
        }

        private void Append(string who, string text)
        {
            if (_history.TextLength > 0) _history.AppendText(Environment.NewLine + Environment.NewLine);
            _history.SelectionStart = _history.TextLength; _history.SelectionFont = new Font(_history.Font, FontStyle.Bold); _history.SelectionColor = who == "AsterMax AI" ? AsterMaxUiTheme.AccentGlow : AsterMaxUiTheme.TextPrimary; _history.AppendText(who + Environment.NewLine);
            _history.SelectionFont = _history.Font; _history.SelectionColor = AsterMaxUiTheme.TextPrimary; _history.AppendText(text); _history.SelectionStart = _history.TextLength; _history.ScrollToCaret();
        }
    }
}
