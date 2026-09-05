#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'CodeAster' / 'CodeAsterResultsDemo.cs'
text = path.read_text(encoding='utf-8')

if 'using System.Reflection;' not in text:
    text = text.replace('using System.Linq;\n', 'using System.Linq;\nusing System.Reflection;\n', 1)

anchor = '''        private static Form CreateVerificationOverlay(Controller controller, DemoCase demoCase, float min, float max, float dispMax)\n        {\n'''
helper = '''        private sealed class PresentationReport\n        {\n            public bool MainWindowMaximized;\n            public bool LeftPanelCollapsed;\n            public bool OutputPanelCollapsed;\n            public bool ZoomToFitInvoked;\n        }\n\n        private static PresentationReport ApplyPresentationMode(Controller controller)\n        {\n            PresentationReport report = new PresentationReport();\n            Form form = controller.Form;\n            if (form == null || form.IsDisposed)\n                throw new InvalidOperationException("Presentation mode requires a live native main form.");\n\n            form.WindowState = FormWindowState.Maximized;\n            Application.DoEvents();\n            report.MainWindowMaximized = form.WindowState == FormWindowState.Maximized;\n\n            FieldInfo split1Field = form.GetType().GetField("splitContainer1", BindingFlags.Instance | BindingFlags.NonPublic);\n            SplitContainer split1 = split1Field == null ? null : split1Field.GetValue(form) as SplitContainer;\n            if (split1 == null) throw new InvalidOperationException("Native splitContainer1 was not found.");\n            split1.Panel1Collapsed = true;\n            report.LeftPanelCollapsed = split1.Panel1Collapsed;\n\n            FieldInfo split2Field = form.GetType().GetField("splitContainer2", BindingFlags.Instance | BindingFlags.NonPublic);\n            SplitContainer split2 = split2Field == null ? null : split2Field.GetValue(form) as SplitContainer;\n            if (split2 == null) throw new InvalidOperationException("Native splitContainer2 was not found.");\n            split2.Panel2Collapsed = true;\n            report.OutputPanelCollapsed = split2.Panel2Collapsed;\n\n            FieldInfo zoomField = form.GetType().GetField("tsbZoomToFit", BindingFlags.Instance | BindingFlags.NonPublic);\n            ToolStripItem zoom = zoomField == null ? null : zoomField.GetValue(form) as ToolStripItem;\n            if (zoom == null) throw new InvalidOperationException("Native Zoom to fit toolbar item was not found.");\n            zoom.PerformClick();\n            Application.DoEvents();\n            report.ZoomToFitInvoked = true;\n\n            form.Refresh();\n            Application.DoEvents();\n            return report;\n        }\n\n'''
if helper not in text:
    if anchor not in text:
        raise SystemExit('Presentation helper anchor not found; refusing partial patch.')
    text = text.replace(anchor, helper + anchor, 1)

old_overlay = '''            overlay.Width = 430;\n            overlay.Height = 225;\n            overlay.Left = Math.Max(controller.Form.Left + 24, 0);\n            overlay.Top = Math.Max(controller.Form.Top + 72, 0);\n'''
new_overlay = '''            overlay.Width = 365;\n            overlay.Height = 185;\n            overlay.Left = Math.Max(controller.Form.Right - overlay.Width - 28, 0);\n            overlay.Top = Math.Max(controller.Form.Top + 76, 0);\n'''
if old_overlay in text:
    text = text.replace(old_overlay, new_overlay, 1)

# Compact the verification card so the contour remains the dominant visual object.
text = text.replace('            benchmark.Top = 135;\n', '            benchmark.Top = 130;\n', 1)
text = text.replace('            provenance.Top = 165;\n', '            provenance.Top = 150;\n', 1)
text = text.replace('            provenance.Text = "Provenance: genuine solver field  |  mm-N-MPa  |  fail-closed";\n',
                    '            provenance.Text = "Solver verified | mm-N-MPa | fail-closed";\n', 1)

old_gate = '''                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n                if (!scalarBarReport.ControlFound || !scalarBarReport.MethodFound ||\n                    !scalarBarReport.MethodInvoked || !scalarBarReport.InternalSpectrumAutomatic ||\n                    !scalarBarReport.ScalarBarWidgetFound || !scalarBarReport.LookupTableFound ||\n                    !scalarBarReport.LookupTableRangeReadable || !scalarBarReport.RangeMatchesField)\n                    throw new InvalidOperationException("Native scalar-bar numerical semantics gate failed: " + scalarBarReport.ToString());\n\n                controller.Form.Refresh();\n'''
new_gate = '''                NativeScalarBarGate.Report scalarBarReport = NativeScalarBarGate.Verify(controller, min, max);\n                if (!scalarBarReport.ControlFound || !scalarBarReport.MethodFound ||\n                    !scalarBarReport.MethodInvoked || !scalarBarReport.InternalSpectrumAutomatic ||\n                    !scalarBarReport.ScalarBarWidgetFound || !scalarBarReport.LookupTableFound ||\n                    !scalarBarReport.LookupTableRangeReadable || !scalarBarReport.RangeMatchesField)\n                    throw new InvalidOperationException("Native scalar-bar numerical semantics gate failed: " + scalarBarReport.ToString());\n\n                PresentationReport presentation = ApplyPresentationMode(controller);\n                if (!presentation.MainWindowMaximized || !presentation.LeftPanelCollapsed ||\n                    !presentation.OutputPanelCollapsed || !presentation.ZoomToFitInvoked)\n                    throw new InvalidOperationException("Professional presentation-mode gate failed.");\n\n                controller.Form.Refresh();\n'''
if old_gate not in text:
    raise SystemExit('Scalar-bar gate anchor not found; refusing partial presentation patch.')
text = text.replace(old_gate, new_gate, 1)

payload_anchor = '''                    "  \\\"native_scalar_bar_range_matches_field\\\": true,\\n" +\n                    "  \\\"native_scalar_bar_semantically_verified\\\": true\\n" +'''
payload_new = '''                    "  \\\"native_scalar_bar_range_matches_field\\\": true,\\n" +\n                    "  \\\"native_scalar_bar_semantically_verified\\\": true,\\n" +\n                    "  \\\"presentation_mode\\\": true,\\n" +\n                    "  \\\"main_window_maximized\\\": " + presentation.MainWindowMaximized.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"left_panel_collapsed\\\": " + presentation.LeftPanelCollapsed.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"output_panel_collapsed\\\": " + presentation.OutputPanelCollapsed.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"zoom_to_fit_invoked\\\": " + presentation.ZoomToFitInvoked.ToString().ToLowerInvariant() + ",\\n" +\n                    "  \\\"verification_card_position\\\": \\\"top-right\\\"\\n" +'''
if payload_anchor not in text:
    raise SystemExit('READY payload presentation anchor not found; refusing partial patch.')
text = text.replace(payload_anchor, payload_new, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path} with C8.67 professional verified Results presentation mode')
