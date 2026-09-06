#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path('build/PrePoMax-CodeAster').resolve()
path = root / 'PrePoMax' / 'Program.cs'
text = path.read_text(encoding='utf-8-sig')

old = '''            Application.EnableVisualStyles();\n            Application.SetCompatibleTextRenderingDefault(false);\n            Application.Run(new FrmMain(args));\n'''
new = '''            Application.EnableVisualStyles();\n            Application.SetCompatibleTextRenderingDefault(false);\n            try\n            {\n                using (FrmMain mainForm = new FrmMain(args))\n                {\n                    Application.Run(mainForm);\n                }\n                System.Console.WriteLine("C8.75d Program: Application.Run returned; FrmMain disposed");\n                System.Console.Out.Flush();\n            }\n            finally\n            {\n                MessageBoxManager.Unregister();\n                System.Console.WriteLine("C8.75d Program: MessageBoxManager unregistered");\n                System.Console.Out.Flush();\n                GC.Collect();\n                GC.WaitForPendingFinalizers();\n                GC.Collect();\n                System.Console.WriteLine("C8.75d Program: finalizer drain complete");\n                System.Console.Out.Flush();\n            }\n'''
if old not in text:
    raise SystemExit('C8.75d Program.cs application-run anchor not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8-sig')
print('C8.75d patched Program.cs: deterministic FrmMain disposal, hook unregister, finalizer drain')
