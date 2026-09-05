#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'vtkControl' / 'vtkControl.Designer.cs'
text = path.read_text(encoding='utf-8-sig')

old = '''            if (this._renderWindowInteractor != null)\n            {\n                if (_coorSys != null) this._coorSys.SetInteractor(null);\n                //if (_statusBlockWidget != null) this._statusBlockWidget.SetInteractor(null, null);\n                //if (_minValueWidget != null) this._minValueWidget.SetInteractor(null, null);\n                //if (_maxValueWidget != null) this._maxValueWidget.SetInteractor(null, null);\n                //if (_probeWidget != null) this._probeWidget.SetInteractor(null, null);\n                //if (_scalarBarWidget != null) this._scalarBarWidget.SetInteractor(null, null);\n\n                this._renderWindowInteractor.Dispose();\n                this._renderWindowInteractor = null;\n            }\n'''
new = '''            if (this._renderWindowInteractor != null)\n            {\n                // AsterMax C8.75c: detach every live widget from the native interactor while\n                // renderers and the render window are still valid. The pinned upstream only\n                // detached the orientation marker and left the remaining teardown calls\n                // commented out, allowing widget finalization to race a disposed interactor.\n                if (_coorSys != null) _coorSys.SetInteractor(null);\n                if (_statusBlockWidget != null) _statusBlockWidget.SetInteractor(null, null);\n                if (_probeWidget != null) _probeWidget.SetInteractor(null, null);\n                if (_scalarBarWidget != null) _scalarBarWidget.SetInteractor(null, null);\n                if (_colorBarWidget != null) _colorBarWidget.SetInteractor(null, null);\n\n                this._renderWindowInteractor.SetRenderWindow(null);\n                this._renderWindow.SetInteractor(null);\n                this._renderWindowInteractor.Dispose();\n                this._renderWindowInteractor = null;\n            }\n'''
if old not in text:
    raise SystemExit('C8.75c vtkControl OnHandleDestroyed anchor not found; refusing partial patch.')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('Patched', path, 'to detach VTK widgets/interactor deterministically before native disposal')
