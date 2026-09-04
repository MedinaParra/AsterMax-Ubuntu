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
            Width = 600;
            Height = 760;
            MinimumSize = new Size(470, 560);
            StartPosition = FormStartPosition.CenterParent;
            BackColor = AsterMaxUiTheme.Surface;
            Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Regular);

            Panel header = new Panel { Dock = DockStyle.Top, Height = 82, Padding = new Padding(14, 10, 14, 8), BackColor = Color.White };
            PictureBox logo = new PictureBox { Width = 34, Height = 34, Left = 14, Top = 12, Image = AsterMaxUiTheme.CreateAiIcon(32), SizeMode = PictureBoxSizeMode.CenterImage };
            Label title = new Label { AutoSize = true, Left = 58, Top = 11, Text = "AsterMax AI", ForeColor = AsterMaxUiTheme.TextPrimary, Font = new Font(Font.FontFamily, 12f, FontStyle.Bold) };
            Label subtitle = new Label { AutoSize = true, Left = 59, Top = 36, Text = "Engineering Copilot · Code_Aster remains solver authority", ForeColor = AsterMaxUiTheme.TextSecondary };
            _status = new Label { AutoEllipsis = true, Left = 14, Top = 60, Height = 18, Width = 545, Text = ProviderStatus(), ForeColor = AsterMaxUiTheme.TextSecondary };
            header.Controls.Add(logo);
            header.Controls.Add(title);
            header.Controls.Add(subtitle);
            header.Controls.Add(_status);

            Panel contextBar = new Panel { Dock = DockStyle.Top, Height = 36, Padding = new Padding(12, 8, 12, 6), BackColor = AsterMaxUiTheme.SurfaceAlt };
            _context = new Label { Dock = DockStyle.Fill, AutoEllipsis = true, ForeColor = AsterMaxUiTheme.TextSecondary, Text = BuildContextBadge() };
            contextBar.Controls.Add(_context);

            _history = new RichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                BackColor = Color.White,
                ForeColor = AsterMaxUiTheme.TextPrimary,
                BorderStyle = BorderStyle.None,
                Margin = new Padding(0),
                DetectUrls = false
            };

            Panel historyHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(14, 12, 14, 8), BackColor = Color.White };
            historyHost.Controls.Add(_history);

            Panel composer = new Panel { Dock = DockStyle.Bottom, Height = 126, Padding = new Padding(14, 10, 14, 12), BackColor = AsterMaxUiTheme.Surface };
            Panel inputHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(8), BackColor = Color.White };
            inputHost.Paint += (s, e) => ControlPaint.DrawBorder(e.Graphics, inputHost.ClientRectangle, AsterMaxUiTheme.Border, ButtonBorderStyle.Solid);
            _input = new TextBox { Multiline = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical, BorderStyle = BorderStyle.None, AcceptsReturn = true };
            inputHost.Controls.Add(_input);

            Panel actions = new Panel { Dock = DockStyle.Right, Width = 116, Padding = new Padding(8, 0, 0, 0), BackColor = AsterMaxUiTheme.Surface };
            _send = new Button { Text = "Enviar", Dock = DockStyle.Top, Height = 38 };
            AsterMaxUiTheme.StylePrimaryButton(_send);
            _clear = new Button { Text = "Limpiar", Dock = DockStyle.Top, Height = 34, Margin = new Padding(0, 8, 0, 0) };
            AsterMaxUiTheme.StyleSecondaryButton(_clear);
            actions.Controls.Add(_clear);
            actions.Controls.Add(_send);
            composer.Controls.Add(inputHost);
            composer.Controls.Add(actions);

            _send.Click += async (s, e) => await SendAsync();
            _clear.Click += (s, e) => ClearConversation();
            _input.KeyDown += async (s, e) =>
            {
                if (e.Control && e.KeyCode == Keys.Enter)
                {
                    e.SuppressKeyPress = true;
                    await SendAsync();
                }
            };

            Controls.Add(historyHost);
            Controls.Add(composer);
            Controls.Add(contextBar);
            Controls.Add(header);

            Append("AsterMax AI", "Listo. Puedo razonar sobre el contexto actual del modelo, pero no reemplazo al solver. Los resultados FEA sólo deben considerarse válidos cuando provengan de la cadena verificada de Code_Aster.");
        }

        private string ProviderStatus()
        {
            string endpoint = Environment.GetEnvironmentVariable("ASTERMAX_AI_ENDPOINT");
            string model = Environment.GetEnvironmentVariable("ASTERMAX_AI_MODEL");
            if (String.IsNullOrWhiteSpace(endpoint)) return "● IA sin configurar · define ASTERMAX_AI_ENDPOINT y ASTERMAX_AI_MODEL";
            return "● Conectado a " + endpoint + " · modelo: " + (String.IsNullOrWhiteSpace(model) ? "default" : model);
        }

        private string BuildContextBadge()
        {
            string view = "—";
            bool modelLoaded = false;
            bool resultLoaded = false;
            try { if (_controller != null) view = _controller.CurrentView.ToString(); } catch { }
            try { modelLoaded = _controller != null && _controller.Model != null; } catch { }
            try { resultLoaded = _controller != null && _controller.CurrentResult != null; } catch { }
            return "Contexto · vista " + view + "   |   modelo " + (modelLoaded ? "cargado" : "vacío") + "   |   resultados " + (resultLoaded ? "cargados" : "vacíos") + "   |   mm-N-MPa";
        }

        private string BuildEngineeringContext()
        {
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("AsterMax Mechanical engineering context");
            sb.AppendLine("Unit contract: mm-N-MPa");
            sb.AppendLine("Solver authority: Code_Aster; never fabricate FEA results.");
            if (_controller != null)
            {
                try { sb.AppendLine("Current view: " + _controller.CurrentView); } catch { }
                try { sb.AppendLine("Model loaded: " + (_controller.Model != null)); } catch { }
                try { sb.AppendLine("Result loaded: " + (_controller.CurrentResult != null)); } catch { }
                try
                {
                    if (_controller.CurrentFieldData != null)
                        sb.AppendLine("Current result field: " + _controller.CurrentFieldData.Name + " / " + _controller.CurrentFieldData.Component);
                }
                catch { }
            }
            sb.AppendLine("Rules: distinguish observed model state, inference and solver-verified evidence. industrial_validation=false; ansys_equivalence=false unless independently demonstrated.");
            return sb.ToString();
        }

        private async Task SendAsync()
        {
            string text = _input.Text.Trim();
            if (text.Length == 0) return;
            _input.Clear();
            Append("Tú", text);

            string endpoint = Environment.GetEnvironmentVariable("ASTERMAX_AI_ENDPOINT");
            if (String.IsNullOrWhiteSpace(endpoint))
            {
                Append("AsterMax AI", "Proveedor IA no configurado. Define ASTERMAX_AI_ENDPOINT y ASTERMAX_AI_MODEL. El panel y la lectura de contexto sí están activos.");
                return;
            }

            _send.Enabled = false;
            _status.Text = "● Consultando proveedor…";
            _context.Text = BuildContextBadge();
            try
            {
                string answer = await Task.Run(() => CallProvider(endpoint, text));
                Append("AsterMax AI", answer);
            }
            catch (Exception ex)
            {
                Append("AsterMax AI", "Error del proveedor: " + ex.Message);
            }
            finally
            {
                _send.Enabled = true;
                _status.Text = ProviderStatus();
                _context.Text = BuildContextBadge();
            }
        }

        private void ClearConversation()
        {
            _messages.Clear();
            _history.Clear();
            Append("AsterMax AI", "Conversación reiniciada. El contexto del modelo se volverá a leer en la siguiente consulta.");
            _input.Focus();
        }

        private string CallProvider(string endpoint, string userText)
        {
            string model = Environment.GetEnvironmentVariable("ASTERMAX_AI_MODEL") ?? "default";
            string key = Environment.GetEnvironmentVariable("ASTERMAX_AI_API_KEY");
            string url = endpoint.TrimEnd('/') + "/v1/chat/completions";

            JArray messages = new JArray();
            messages.Add(new JObject { ["role"] = "system", ["content"] = BuildEngineeringContext() });
            foreach (JObject m in _messages) messages.Add(m);
            JObject user = new JObject { ["role"] = "user", ["content"] = userText };
            messages.Add(user);

            JObject payload = new JObject { ["model"] = model, ["messages"] = messages, ["temperature"] = 0.2 };
            using (WebClient wc = new WebClient())
            {
                wc.Encoding = Encoding.UTF8;
                wc.Headers[HttpRequestHeader.ContentType] = "application/json";
                if (!String.IsNullOrWhiteSpace(key)) wc.Headers[HttpRequestHeader.Authorization] = "Bearer " + key;
                string raw = wc.UploadString(url, "POST", payload.ToString());
                JObject obj = JObject.Parse(raw);
                JToken token = obj.SelectToken("choices[0].message.content");
                if (token == null) throw new InvalidOperationException("Respuesta sin choices[0].message.content");
                string answer = token.ToString();
                _messages.Add(user);
                _messages.Add(new JObject { ["role"] = "assistant", ["content"] = answer });
                return answer;
            }
        }

        private void Append(string who, string text)
        {
            if (_history.TextLength > 0) _history.AppendText(Environment.NewLine + Environment.NewLine);
            _history.SelectionStart = _history.TextLength;
            _history.SelectionFont = new Font(_history.Font, FontStyle.Bold);
            _history.SelectionColor = who == "AsterMax AI" ? AsterMaxUiTheme.AccentDark : AsterMaxUiTheme.TextPrimary;
            _history.AppendText(who + Environment.NewLine);
            _history.SelectionFont = _history.Font;
            _history.SelectionColor = AsterMaxUiTheme.TextPrimary;
            _history.AppendText(text);
            _history.SelectionStart = _history.TextLength;
            _history.ScrollToCaret();
        }
    }
}
