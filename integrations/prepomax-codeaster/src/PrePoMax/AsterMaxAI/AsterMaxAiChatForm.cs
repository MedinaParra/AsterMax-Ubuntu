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
        private readonly Label _status;
        private readonly List<JObject> _messages = new List<JObject>();

        public AsterMaxAiChatForm(Controller controller)
        {
            _controller = controller;
            Text = "AsterMax AI | Engineering Copilot";
            Width = 520;
            Height = 720;
            MinimumSize = new Size(420, 520);
            StartPosition = FormStartPosition.CenterParent;

            _status = new Label { Dock = DockStyle.Top, Height = 42, Padding = new Padding(10), Text = ProviderStatus() };
            _history = new RichTextBox { Dock = DockStyle.Fill, ReadOnly = true, BackColor = SystemColors.Window, BorderStyle = BorderStyle.FixedSingle };
            Panel bottom = new Panel { Dock = DockStyle.Bottom, Height = 105, Padding = new Padding(8) };
            _input = new TextBox { Multiline = true, Dock = DockStyle.Fill, ScrollBars = ScrollBars.Vertical };
            _send = new Button { Text = "Enviar", Dock = DockStyle.Right, Width = 95 };
            _send.Click += async (s, e) => await SendAsync();
            _input.KeyDown += async (s, e) => { if (e.Control && e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; await SendAsync(); } };
            bottom.Controls.Add(_input);
            bottom.Controls.Add(_send);
            Controls.Add(_history);
            Controls.Add(bottom);
            Controls.Add(_status);

            Append("AsterMax AI", "Listo. Puedo razonar sobre el contexto actual del modelo, pero no reemplazo al solver. Los resultados FEA sólo deben considerarse válidos cuando provengan de la cadena verificada de Code_Aster.");
        }

        private string ProviderStatus()
        {
            string endpoint = Environment.GetEnvironmentVariable("ASTERMAX_AI_ENDPOINT");
            string model = Environment.GetEnvironmentVariable("ASTERMAX_AI_MODEL");
            if (String.IsNullOrWhiteSpace(endpoint)) return "AI: sin configurar | define ASTERMAX_AI_ENDPOINT, ASTERMAX_AI_MODEL y opcionalmente ASTERMAX_AI_API_KEY";
            return "AI: " + endpoint + " | model: " + (String.IsNullOrWhiteSpace(model) ? "default" : model);
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
            _status.Text = "AI: consultando proveedor...";
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
            }
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
            _history.AppendText(who + ":" + Environment.NewLine + text);
            _history.SelectionStart = _history.TextLength;
            _history.ScrollToCaret();
        }
    }
}
