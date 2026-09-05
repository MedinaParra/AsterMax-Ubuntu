#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

anchor = '''        private static PresentationReport ApplyPresentationMode(Controller controller)\n        {\n'''
helper = r'''        private static IEnumerable<Control> EnumerateControls(Control root)
        {
            foreach (Control child in root.Controls)
            {
                yield return child;
                foreach (Control nested in EnumerateControls(child)) yield return nested;
            }
        }

        private static bool ContainsDiagnosticToken(string text, out string token)
        {
            token = null;
            if (String.IsNullOrWhiteSpace(text)) return false;
            string upper = text.Trim().ToUpperInvariant();
            string[] tokens = new string[]
            {
                "ENGINEERING GLYPHS",
                "MODEL READINESS",
                "RESULTS HUD",
                "REGION",
                "BOUNDARY CONDITION"
            };
            foreach (string candidate in tokens)
            {
                if (upper.Contains(candidate))
                {
                    token = candidate;
                    return true;
                }
            }
            return false;
        }

        private static int ApplyCleanPresentationProfile(Form mainForm, out string hiddenTokens)
        {
            HashSet<Control> hidden = new HashSet<Control>();
            HashSet<string> tokens = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (Control control in EnumerateControls(mainForm).ToArray())
            {
                string token;
                if (!ContainsDiagnosticToken(control.Text, out token)) continue;
                Control candidate = control;
                Control parent = control.Parent;
                while (parent != null && parent != mainForm && parent.Width <= 520 && parent.Height <= 430)
                {
                    candidate = parent;
                    parent = parent.Parent;
                }
                if (candidate != null && candidate != mainForm && candidate.Visible)
                {
                    candidate.Visible = false;
                    hidden.Add(candidate);
                    tokens.Add(token);
                }
            }

            foreach (Form form in Application.OpenForms.Cast<Form>().ToArray())
            {
                if (form == mainForm || form.IsDisposed || !form.Visible) continue;
                string formText = form.Text ?? String.Empty;
                string token;
                if (ContainsDiagnosticToken(formText, out token) ||
                    EnumerateControls(form).Any(c => ContainsDiagnosticToken(c.Text, out token)))
                {
                    form.Hide();
                    tokens.Add(token ?? "AUXILIARY_DIAGNOSTIC_FORM");
                }
            }

            hiddenTokens = String.Join("|", tokens.OrderBy(x => x).ToArray());
            mainForm.Refresh();
            Application.DoEvents();
            return hidden.Count;
        }

'''
if helper not in text:
    if anchor not in text:
        raise SystemExit('C8.67 ApplyPresentationMode anchor not found; refusing partial C8.68 patch.')
    text = text.replace(anchor, helper + anchor, 1)

old_fields = '''            public bool ZoomToFitInvoked;\n        }\n'''
new_fields = '''            public bool ZoomToFitInvoked;\n            public bool CleanPresentationProfile;\n            public int DiagnosticControlsHidden;\n            public string HiddenDiagnosticTokens;\n        }\n'''
if old_fields not in text:
    raise SystemExit('PresentationReport field anchor not found.')
text = text.replace(old_fields, new_fields, 1)

old_after_output = '''            report.OutputPanelCollapsed = split2.Panel2Collapsed;\n\n            FieldInfo zoomField = form.GetType().GetField("tsbZoomToFit", BindingFlags.Instance | BindingFlags.NonPublic);\n'''
new_after_output = '''            report.OutputPanelCollapsed = split2.Panel2Collapsed;\n\n            string hiddenTokens;\n            report.DiagnosticControlsHidden = ApplyCleanPresentationProfile(form, out hiddenTokens);\n            report.HiddenDiagnosticTokens = hiddenTokens;\n            report.CleanPresentationProfile = report.DiagnosticControlsHidden >= 3 &&\n                hiddenTokens.IndexOf("ENGINEERING GLYPHS", StringComparison.OrdinalIgnoreCase) >= 0 &&\n                hiddenTokens.IndexOf("MODEL READINESS", StringComparison.OrdinalIgnoreCase) >= 0 &&\n                hiddenTokens.IndexOf("RESULTS HUD", StringComparison.OrdinalIgnoreCase) >= 0;\n            if (!report.CleanPresentationProfile)\n                throw new InvalidOperationException("Clean presentation profile gate failed. Hidden=" +\n                    report.DiagnosticControlsHidden + " Tokens=" + hiddenTokens);\n\n            FieldInfo zoomField = form.GetType().GetField("tsbZoomToFit", BindingFlags.Instance | BindingFlags.NonPublic);\n'''
if old_after_output not in text:
    raise SystemExit('Output panel anchor not found.')
text = text.replace(old_after_output, new_after_output, 1)

old_overlay = '''            overlay.Width = 365;\n            overlay.Height = 185;\n'''
new_overlay = '''            overlay.Width = 330;\n            overlay.Height = 150;\n'''
if old_overlay not in text:
    raise SystemExit('C8.67 overlay size anchor not found.')
text = text.replace(old_overlay, new_overlay, 1)

# Remove verbose benchmark/provenance rows from the clean presentation card; numerical Tag remains untouched.
text = text.replace('            benchmark.Visible = true;\n', '            benchmark.Visible = false;\n', 1) if '            benchmark.Visible = true;\n' in text else text
text = text.replace('            provenance.Top = 150;\n', '            provenance.Top = 125;\n', 1)
text = text.replace('            provenance.Text = "Solver verified | mm-N-MPa | fail-closed";\n',
                    '            provenance.Text = "SOLVER VERIFIED | mm-N-MPa";\n', 1)

old_gate = '''                if (!presentation.MainWindowMaximized || !presentation.LeftPanelCollapsed ||\n                    !presentation.OutputPanelCollapsed || !presentation.ZoomToFitInvoked)\n                    throw new InvalidOperationException("Professional presentation-mode gate failed.");\n'''
new_gate = '''                if (!presentation.MainWindowMaximized || !presentation.LeftPanelCollapsed ||\n                    !presentation.OutputPanelCollapsed || !presentation.ZoomToFitInvoked ||\n                    !presentation.CleanPresentationProfile || presentation.DiagnosticControlsHidden < 3)\n                    throw new InvalidOperationException("Clean professional presentation-mode gate failed.");\n'''
if old_gate not in text:
    raise SystemExit('C8.67 presentation gate anchor not found.')
text = text.replace(old_gate, new_gate, 1)

payload_anchor = '''                    "  \\\"verification_card_position\\\": \\\"top-right\\\"\\n" +'''
payload_new = '''                    "  \\\"verification_card_position\\\": \\\"top-right\\\",\\n" +\n                    "  \\\"clean_presentation_profile\\\": " + presentation.CleanPresentationProfile.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"diagnostic_controls_hidden\\\": " + presentation.DiagnosticControlsHidden.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"hidden_diagnostic_tokens\\\": \\\"" + presentation.HiddenDiagnosticTokens.Replace("\\\\", "\\\\\\\\").Replace("\\\"", "\\\\\\\"") + "\\\"\\n" +'''
if payload_anchor not in text:
    raise SystemExit('C8.67 READY payload anchor not found.')
text = text.replace(payload_anchor, payload_new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.68 clean verified presentation profile')
