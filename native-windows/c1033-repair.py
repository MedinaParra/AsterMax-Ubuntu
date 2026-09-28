"""C10.33: original branding, canonical operation state and localized GUI audit."""
import argparse,base64,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args()
root=Path(a.root);here=Path(__file__).parent

def edit(rel,fn):
 p=root/rel;t=p.read_text(encoding='utf-8-sig');n=fn(t);p.write_text(n,encoding='utf-8-sig')
def required(t,old,new):
 if old not in t: raise RuntimeError('C10.33 missing anchor: '+old[:120])
 return t.replace(old,new)

icon=base64.b64decode((here/'branding/astermax-royal-blue.ico.b64').read_text())
(root/'PrePoMax/main.ico').write_bytes(icon)
# WinForms stores a separate icon in each form resource. Replace these too.
for res in (root/'PrePoMax').rglob('*.resx'):
 t=res.read_text(encoding='utf-8-sig')
 n=re.sub(r'(<data\s+name="\$this.Icon"[^>]*>\s*<value>).*?(</value>)',lambda m:m[1]+base64.b64encode(icon).decode()+m[2],t,flags=re.S)
 if n!=t:res.write_text(n,encoding='utf-8-sig')
edit('PrePoMax/Globals.cs',lambda t:re.sub(r'public static string ProgramName = "[^"]*";', 'public static string ProgramName = "AsterMax Mechanical C10.33";',t))
def assembly(t):
 for attr,val in [('AssemblyTitle','AsterMax Mechanical'),('AssemblyProduct','AsterMax Mechanical C10.33'),('AssemblyVersion','10.33.0.0'),('AssemblyFileVersion','10.33.0.0')]:
  t=re.sub(r'(?m)^\[assembly: '+attr+r'\("[^"]*"\)\]', '[assembly: '+attr+'("'+val+'")]',t)
 return t
edit('PrePoMax/Properties/AssemblyInfo.cs',assembly)
edit('PrePoMax/Forms/AsterMaxSpanishChile.cs',lambda t:required(t,'private static string Translate(string input)','internal static string Translate(string input)'))
def main(t):
 # Operation identity must never depend on localized or informational UI text.
 t=required(t,'public void SetStateReady(string currentText)', 'private string _asterMaxOperationState = Globals.ReadyText;\n        public void SetStateReady(string currentText)')
 for old,new in [('tsslState.Text != Globals.RegeneratingText','_asterMaxOperationState != Globals.RegeneratingText'),('tsslState.Text != Globals.ReadyText','_asterMaxOperationState != Globals.ReadyText'),('tsslState.Text == Globals.ReadyText','_asterMaxOperationState == Globals.ReadyText'),('tsslState.Text == currentText','_asterMaxOperationState == currentText'),('tsslState.Text == Globals.OpeningText','_asterMaxOperationState == Globals.OpeningText')]:
  t=required(t,old,new)
 t=required(t,'tsslState.Text = text;', '_asterMaxOperationState = text;\n                tsslState.Text = AsterMaxSpanishChile.Translate(text);')
 return t
edit('PrePoMax/Forms/FrmMain.cs',main)
# Preserve canonical command names in evidence while resolving the actual C10.24 UI.
helper='''        private static string C1033CommandLabel(string text)
        {
            switch(text)
            {
                case "Materials": return "Material";
                case "Mesh Controls": return "Controles";
                case "Analysis Step": return "Paso";
                case "Supports": return "Apoyo";
                case "Loads": return "Carga";
                case "Solve": return "Ejecutar";
                case "Fit": return "Ajustar";
                case "Isometric": return "Isométrica";
                default: return AsterMaxSpanishChile.Translate(text);
            }
        }
'''
def audit(t):
 t=required(t, 'new SolidSection("B01_Steel", "Steel",', 'new SolidSection("B01_Steel", model.Materials.Keys.First(),')
 t=required(t,'        private void C10208ClickRibbonButton(string tab,string caption)',helper+'        private void C10208ClickRibbonButton(string tab,string caption)')
 t=required(t,'String.Equals(x.Text,tab,StringComparison.Ordinal)','String.Equals(x.Text,AsterMaxSpanishChile.Translate(tab),StringComparison.Ordinal)')
 t=required(t,'String.Equals(x.Text,caption,StringComparison.Ordinal)','String.Equals(x.Text,C1033CommandLabel(caption),StringComparison.Ordinal)')
 t=required(t,'String.Equals(button.Text, caption, StringComparison.Ordinal)','String.Equals(button.Text, C1033CommandLabel(caption), StringComparison.Ordinal)')
 t=required(t,'String.Equals(node.Text, text, StringComparison.OrdinalIgnoreCase)','String.Equals(AsterMaxSpanishChile.Translate(node.Text), AsterMaxSpanishChile.Translate(text), StringComparison.OrdinalIgnoreCase)')
 t=required(t,'(node.Text ?? "").IndexOf(text, StringComparison.OrdinalIgnoreCase)','AsterMaxSpanishChile.Translate(node.Text ?? "").IndexOf(AsterMaxSpanishChile.Translate(text), StringComparison.OrdinalIgnoreCase)')
 # Audit fixture is disposable. Suppress only its unsaved-file prompt after recording result.
 t=required(t,'_asterMaxUiAuditMode = false;','_asterMaxUiAuditMode = false;\n                    if (_controller != null) _controller.ModelChanged = false;')
 return t
edit('PrePoMax/Forms/AsterMaxWorkflowConformanceAudit.cs',audit)
print('C10.33: royal-blue icon, title/version, canonical operation state and localized command audit applied.')
