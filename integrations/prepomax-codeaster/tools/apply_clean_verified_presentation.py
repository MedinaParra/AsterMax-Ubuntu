#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

anchor = '''        private static PresentationReport ApplyPresentationMode(Controller controller)\n        {\n'''
helper = r'''        private static bool HideAsterMaxControl(Form mainForm, string fieldName, string token)
        {
            FieldInfo field = mainForm.GetType().GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) throw new InvalidOperationException("Presentation profile field not found: " + fieldName);
            Control control = field.GetValue(mainForm) as Control;
            if (control == null || control.IsDisposed) throw new InvalidOperationException("Presentation profile control unavailable: " + fieldName);
            control.Visible = false;
            Application.DoEvents();
            if (control.Visible) throw new InvalidOperationException("Presentation profile could not hide: " + token);
            return true;
        }

        private static int ApplyCleanPresentationProfile(Form mainForm, out string hiddenTokens)
        {
            List<string> tokens = new List<string>();
            if (HideAsterMaxControl(mainForm, "_asterMaxGlyphLayer", "ENGINEERING GLYPHS")) tokens.Add("ENGINEERING GLYPHS");
            if (HideAsterMaxControl(mainForm, "_asterMaxModelReadiness", "MODEL READINESS")) tokens.Add("MODEL READINESS");
            if (HideAsterMaxControl(mainForm, "_asterMaxResultsWorkspace", "RESULTS HUD")) tokens.Add("RESULTS HUD");
            if (HideAsterMaxControl(mainForm, "_asterMaxViewportHud", "VIEWPORT HUD")) tokens.Add("VIEWPORT HUD");
            if (HideAsterMaxControl(mainForm, "_asterMaxRegionBindingInspector", "REGION BINDING")) tokens.Add("REGION BINDING");
            if (HideAsterMaxControl(mainForm, "_asterMaxEngineeringTree", "ENGINEERING TREE")) tokens.Add("ENGINEERING TREE");
            hiddenTokens = String.Join("|", tokens.ToArray());
            mainForm.Refresh();
            Application.DoEvents();
            return tokens.Count;
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
new_after_output = '''            report.OutputPanelCollapsed = split2.Panel2Collapsed;\n\n            string hiddenTokens;\n            report.DiagnosticControlsHidden = ApplyCleanPresentationProfile(form, out hiddenTokens);\n            report.HiddenDiagnosticTokens = hiddenTokens;\n            report.CleanPresentationProfile = report.DiagnosticControlsHidden == 6 &&\n                hiddenTokens.IndexOf("ENGINEERING GLYPHS", StringComparison.OrdinalIgnoreCase) >= 0 &&\n                hiddenTokens.IndexOf("MODEL READINESS", StringComparison.OrdinalIgnoreCase) >= 0 &&\n                hiddenTokens.IndexOf("RESULTS HUD", StringComparison.OrdinalIgnoreCase) >= 0;\n            if (!report.CleanPresentationProfile)\n                throw new InvalidOperationException("Clean presentation profile gate failed. Hidden=" +\n                    report.DiagnosticControlsHidden + " Tokens=" + hiddenTokens);\n\n            FieldInfo zoomField = form.GetType().GetField("tsbZoomToFit", BindingFlags.Instance | BindingFlags.NonPublic);\n'''
if old_after_output not in text:
    raise SystemExit('Output panel anchor not found.')
text = text.replace(old_after_output, new_after_output, 1)

old_overlay = '''            overlay.Width = 365;\n            overlay.Height = 185;\n'''
new_overlay = '''            overlay.Width = 330;\n            overlay.Height = 150;\n'''
if old_overlay not in text:
    raise SystemExit('C8.67 overlay size anchor not found.')
text = text.replace(old_overlay, new_overlay, 1)
text = text.replace('            benchmark.Top = 130;\n', '            benchmark.Visible = false;\n            benchmark.Top = 130;\n', 1)
text = text.replace('            provenance.Top = 150;\n', '            provenance.Top = 120;\n', 1)
text = text.replace('            provenance.Text = "Solver verified | mm-N-MPa | fail-closed";\n',
                    '            provenance.Text = "SOLVER VERIFIED | mm-N-MPa";\n', 1)

old_gate = '''                if (!presentation.MainWindowMaximized || !presentation.LeftPanelCollapsed ||\n                    !presentation.OutputPanelCollapsed || !presentation.ZoomToFitInvoked)\n                    throw new InvalidOperationException("Professional presentation-mode gate failed.");\n'''
new_gate = '''                if (!presentation.MainWindowMaximized || !presentation.LeftPanelCollapsed ||\n                    !presentation.OutputPanelCollapsed || !presentation.ZoomToFitInvoked ||\n                    !presentation.CleanPresentationProfile || presentation.DiagnosticControlsHidden != 6)\n                    throw new InvalidOperationException("Clean professional presentation-mode gate failed.");\n'''
if old_gate not in text:
    raise SystemExit('C8.67 presentation gate anchor not found.')
text = text.replace(old_gate, new_gate, 1)

payload_anchor = '''                    "  \\\"verification_card_position\\\": \\\"top-right\\\"\\n" +'''
payload_new = '''                    "  \\\"verification_card_position\\\": \\\"top-right\\\",\\n" +\n                    "  \\\"clean_presentation_profile\\\": " + presentation.CleanPresentationProfile.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"diagnostic_controls_hidden\\\": " + presentation.DiagnosticControlsHidden.ToString(CultureInfo.InvariantCulture) + ",\\n" +\n                    "  \\\"hidden_diagnostic_tokens\\\": \\\"" + presentation.HiddenDiagnosticTokens + "\\\"\\n" +'''
if payload_anchor not in text:
    raise SystemExit('C8.67 READY payload anchor not found.')
text = text.replace(payload_anchor, payload_new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.68 explicit clean verified presentation profile')
