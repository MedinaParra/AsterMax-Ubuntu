#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'Program.cs'
text = path.read_text(encoding='utf-8-sig')

anchor = '''            Application.Run(mainForm);\n'''
replacement = '''            mainForm.FormClosed += (sender, eventArgs) =>\n            {\n                MessageBoxManager.Unregister();\n                System.Console.WriteLine("C8.75d Program: MessageBoxManager unregistered on FormClosed");\n                System.Console.Out.Flush();\n            };\n            try\n            {\n                Application.Run(mainForm);\n                System.Console.WriteLine("C8.75d Program: Application.Run returned");\n                System.Console.Out.Flush();\n            }\n            finally\n            {\n                if (mainForm != null && !mainForm.IsDisposed) mainForm.Dispose();\n                System.Console.WriteLine("C8.75d Program: FrmMain disposed");\n                System.Console.Out.Flush();\n                MessageBoxManager.Unregister();\n                System.Console.WriteLine("C8.75d Program: MessageBoxManager unregister confirmed");\n                System.Console.Out.Flush();\n                GC.Collect();\n                GC.WaitForPendingFinalizers();\n                GC.Collect();\n                System.Console.WriteLine("C8.75d Program: finalizer drain complete");\n                System.Console.Out.Flush();\n            }\n'''
if anchor not in text:
    raise SystemExit('C8.75d generated Program.cs Application.Run(mainForm) anchor not found')
text = text.replace(anchor, replacement, 1)
path.write_text(text, encoding='utf-8-sig')
print('C8.75d patched generated Program.cs: FormClosed hook cleanup, deterministic disposal, finalizer drain')
