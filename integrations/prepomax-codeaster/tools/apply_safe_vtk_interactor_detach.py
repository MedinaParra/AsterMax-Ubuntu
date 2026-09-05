#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'vtkControl' / 'vtkControl.Designer.cs'
text = path.read_text(encoding='utf-8-sig')

class_anchor = '''    partial class vtkControl\n    {\n'''
trace_helper = '''    partial class vtkControl\n    {\n        private static void AsterMaxShutdownTrace(string message)\n        {\n            try\n            {\n                string trace = System.Environment.GetEnvironmentVariable("ASTERMAX_VTK_SHUTDOWN_TRACE");\n                if (!string.IsNullOrEmpty(trace))\n                    System.IO.File.AppendAllText(trace, System.DateTime.UtcNow.ToString("O") + " " + message + System.Environment.NewLine);\n            }\n            catch { }\n        }\n\n'''
if class_anchor not in text:
    raise SystemExit('C8.75c vtkControl class anchor not found.')
text = text.replace(class_anchor, trace_helper, 1)

old = '''            if (this._renderWindowInteractor != null)\n            {\n                if (_coorSys != null) this._coorSys.SetInteractor(null);\n                //if (_statusBlockWidget != null) this._statusBlockWidget.SetInteractor(null, null);\n                //if (_minValueWidget != null) this._minValueWidget.SetInteractor(null, null);\n                //if (_maxValueWidget != null) this._maxValueWidget.SetInteractor(null, null);\n                //if (_probeWidget != null) this._probeWidget.SetInteractor(null, null);\n                //if (_scalarBarWidget != null) this._scalarBarWidget.SetInteractor(null, null);\n\n                this._renderWindowInteractor.Dispose();\n                this._renderWindowInteractor = null;\n            }\n'''
new = '''            if (this._renderWindowInteractor != null)\n            {\n                AsterMaxShutdownTrace("interactor.begin");\n                if (_coorSys != null) { AsterMaxShutdownTrace("coorSys.detach.before"); _coorSys.SetInteractor(null); AsterMaxShutdownTrace("coorSys.detach.after"); }\n                if (_statusBlockWidget != null) { AsterMaxShutdownTrace("status.detach.before"); _statusBlockWidget.SetInteractor(null, null); AsterMaxShutdownTrace("status.detach.after"); }\n                if (_probeWidget != null) { AsterMaxShutdownTrace("probe.detach.before"); _probeWidget.SetInteractor(null, null); AsterMaxShutdownTrace("probe.detach.after"); }\n                if (_scalarBarWidget != null) { AsterMaxShutdownTrace("scalar.detach.before"); _scalarBarWidget.SetInteractor(null, null); AsterMaxShutdownTrace("scalar.detach.after"); }\n                if (_colorBarWidget != null) { AsterMaxShutdownTrace("color.detach.before"); _colorBarWidget.SetInteractor(null, null); AsterMaxShutdownTrace("color.detach.after"); }\n                AsterMaxShutdownTrace("interactor.setRenderWindowNull.before");\n                this._renderWindowInteractor.SetRenderWindow(null);\n                AsterMaxShutdownTrace("interactor.setRenderWindowNull.after");\n                if (this._renderWindow != null)\n                {\n                    AsterMaxShutdownTrace("renderWindow.setInteractorNull.before");\n                    this._renderWindow.SetInteractor(null);\n                    AsterMaxShutdownTrace("renderWindow.setInteractorNull.after");\n                }\n                AsterMaxShutdownTrace("interactor.dispose.before");\n                this._renderWindowInteractor.Dispose();\n                AsterMaxShutdownTrace("interactor.dispose.after");\n                this._renderWindowInteractor = null;\n            }\n'''
if old not in text:
    raise SystemExit('C8.75c vtkControl OnHandleDestroyed anchor not found; refusing partial patch.')
text = text.replace(old, new, 1)

repls = {
'''            if (this._renderer != null) this._renderer.SetRenderWindow(null);\n''': '''            AsterMaxShutdownTrace("handleDestroyed.begin");\n            if (this._renderer != null) { AsterMaxShutdownTrace("renderer.detach.before"); this._renderer.SetRenderWindow(null); AsterMaxShutdownTrace("renderer.detach.after"); }\n''',
'''            if (this._overlayRenderer != null) this._overlayRenderer.SetRenderWindow(null);\n''': '''            if (this._overlayRenderer != null) { AsterMaxShutdownTrace("overlayRenderer.detach.before"); this._overlayRenderer.SetRenderWindow(null); AsterMaxShutdownTrace("overlayRenderer.detach.after"); }\n''',
'''            if (this._selectionRenderer != null) this._selectionRenderer.SetRenderWindow(null);\n''': '''            if (this._selectionRenderer != null) { AsterMaxShutdownTrace("selectionRenderer.detach.before"); this._selectionRenderer.SetRenderWindow(null); AsterMaxShutdownTrace("selectionRenderer.detach.after"); }\n''',
'''                this._renderWindow.Dispose();\n''': '''                AsterMaxShutdownTrace("renderWindow.dispose.before");\n                this._renderWindow.Dispose();\n                AsterMaxShutdownTrace("renderWindow.dispose.after");\n''',
'''                this._renderer.Dispose();\n''': '''                AsterMaxShutdownTrace("renderer.dispose.before");\n                this._renderer.Dispose();\n                AsterMaxShutdownTrace("renderer.dispose.after");\n''',
'''                this._overlayRenderer.Dispose();\n''': '''                AsterMaxShutdownTrace("overlayRenderer.dispose.before");\n                this._overlayRenderer.Dispose();\n                AsterMaxShutdownTrace("overlayRenderer.dispose.after");\n''',
'''                this._selectionRenderer.Dispose();\n''': '''                AsterMaxShutdownTrace("selectionRenderer.dispose.before");\n                this._selectionRenderer.Dispose();\n                AsterMaxShutdownTrace("selectionRenderer.dispose.after");\n''',
'''            base.OnHandleDestroyed(e);\n''': '''            AsterMaxShutdownTrace("base.OnHandleDestroyed.before");\n            base.OnHandleDestroyed(e);\n            AsterMaxShutdownTrace("base.OnHandleDestroyed.after");\n'''
}
for a,b in repls.items():
    if a not in text:
        raise SystemExit('C8.75c diagnostic anchor missing: ' + a.strip())
    text = text.replace(a,b,1)

path.write_text(text, encoding='utf-8')
print('Patched', path, 'with deterministic widget detach and native teardown checkpoints')
