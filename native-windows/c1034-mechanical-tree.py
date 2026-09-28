import argparse,re,shutil,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args();root=Path(a.root);here=Path(__file__).parent

def replace(t,old,new):
 if old not in t: raise RuntimeError('C10.34 anchor missing: '+old[:100])
 return t.replace(old,new)
def method(t,signature,new):
 start=t.index(signature);brace=t.index('{',start);depth=1;end=brace+1
 while depth:
  if t[end]=='{':depth+=1
  if t[end]=='}':depth-=1
  end+=1
 return t[:start]+new+t[end:]
def edit(path,fn):
 p=root/path;p.write_text(fn(p.read_text(encoding='utf-8-sig')),encoding='utf-8-sig')

def outline(t):
 t=replace(t,'private TreeView _axOutline;','private CodersLabTreeView _axOutline;')
 t=replace(t,'_axOutline = new TreeView','_axOutline = new CodersLabTreeView')
 t=replace(t,'ForeColor = source.ForeColor','ForeColor = source.Tag is CaeGlobals.NamedClass && !((CaeGlobals.NamedClass)source.Tag).Active ? Color.Gray : Color.FromArgb(34,42,53)')
 t=replace(t,'Name = source.TreeView.Name + "/" + source.FullPath','Name = AxStableSourceKey(source)')
 start=t.index('            _axOutline.AfterSelect +=');end=t.index('            _axOutlineTimer =',start)
 t=t[:start]+'''            AxInitializeMechanical34();
            _axOutline.SelectionsChanged += (s,e) => AxMechanicalSelectionChanged();
            _axOutline.NodeMouseDoubleClick += (s,e) => AxEditMechanicalSelection();
            _axAnalysisMenu = AxCreateCommandMenu("Editar tipo de análisis…", () => AsterMaxAnalysisTypeRequested?.Invoke());
            _axSolutionMenu = AxCreateCommandMenu("Resolver con Code_Aster", () => AsterMaxSolveRequested?.Invoke());
            _axSolutionMenu.Items.Add("Ver información",null,(s,e)=>AsterMaxResultRequested?.Invoke("__information__"));
            _axAnalysisMenu.Items.Add("Resolver",null,(s,e)=>AsterMaxSolveRequested?.Invoke());
            _axOutline.NodeMouseClick += (s,e) => { if(e.Button==MouseButtons.Right) AxShowMechanicalMenu(e.Node,e.Location); };
            _axOutline.KeyDown += AxMechanicalKeyDown;
'''+t[end:]
 t=method(t,'        private bool SelectAsterMaxSource(TreeNode projected)', '''        private bool SelectAsterMaxSource(TreeNode projected)
        {
            if (_axRefreshing || _axSyncingSelection || _disableMouse || projected == null) return false;
            var source = projected.Tag as TreeNode;
            if (source == null || source.TreeView == null) return false;
            var tree = source.TreeView as CodersLabTreeView;
            _axSyncingSelection=true;
            bool prior=_disableSelectionsChanged;
            try {
                _disableSelectionsChanged=true;
                if (tree == cltvGeometry) { SetGeometryTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Geometry); }
                else if (tree == cltvModel) { SetModelTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Model); }
                else if (tree == cltvResults) { SetResultsTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Results); }
                else return false;
                tree.SelectedNodes.Clear();
                foreach(TreeNode selected in _axOutline.SelectedNodes) {
                    var native=selected.Tag as TreeNode;
                    if(native!=null && native.TreeView==tree) tree.SelectedNodes.Add(native);
                }
                if(tree.SelectedNodes.Count==0) tree.SelectedNodes.Add(source);
            }
            finally { _disableSelectionsChanged=prior; _axSyncingSelection=false; }
            cltv_SelectionsChanged(tree, EventArgs.Empty);
            return true;
        }''')
 t=replace(t,'string selected = _axOutline.SelectedNode == null ? null : _axOutline.SelectedNode.Name;', '''string selected = _axOutline.SelectedNode == null ? null : _axOutline.SelectedNode.Name;
            var selectedKeys=new List<string>();
            foreach(TreeNode node in _axOutline.SelectedNodes) selectedKeys.Add(node.Name);''')
 t=replace(t,'                _axOutline.Nodes.Clear();','                _axOutline.SelectedNodes.Clear();\n                _axOutline.Nodes.Clear();')
 for old,new in [('new TreeNode("Project")','new TreeNode("Proyecto")'),('new TreeNode("Model")','new TreeNode("Modelo")'),('new TreeNode("Coordinate Systems")','new TreeNode("Sistemas de coordenadas")'),('new TreeNode("Connections")','new TreeNode("Conexiones")'),('new TreeNode("Mesh")','new TreeNode("Malla")'),('new TreeNode("Named Selections")','new TreeNode("Selecciones nombradas")'),('new TreeNode("Type Analysis")','new TreeNode("Tipo de análisis")'),('new TreeNode("Solution")','new TreeNode("Solución")'),('new TreeNode("Solution Information")','new TreeNode("Información de la solución")')]: t=replace(t,old,new)
 t=replace(t,'                analysis.Nodes.Add(AxCopy(_steps, "Analysis Settings / Steps"));\n                analysis.Nodes.Add(AxCopy(_initialConditions));\n                analysis.Nodes.Add(AxCopy(_amplitudes));','                AxAddMechanicalAnalysisChildren(analysis);')
 t=replace(t,'                AxApplyNativeIcons(_axOutline.Nodes);','                AxApplyMechanicalIcons(_axOutline.Nodes);')
 t=replace(t,'                if (_axResultFields.Length>0) { analysis.Expand(); solution.Expand(); }','                if (first && _axResultFields.Length>0) { analysis.Expand(); solution.Expand(); }')
 t=replace(t,'                AxRestoreExpansion(_axOutline.Nodes, expanded, selected, first);\n                project.Expand(); model.Expand();','''                AxRestoreExpansion(_axOutline.Nodes, expanded, null, first);
                foreach(string key in selectedKeys) {
                    var restored=_axOutline.Nodes.Find(key,true);
                    if(restored.Length>0) _axOutline.SelectedNodes.Add(restored[0]);
                }
                if(first) { project.Expand(); model.Expand(); }''')
 t=replace(t,'if (model.Nodes.Count > 0) model.Nodes[0].Expand();','if (model.Nodes.Count>0 && model.Nodes[0].Nodes.Count>0 && !_axGeometryRevealed) { model.Nodes[0].ExpandAll(); _axGeometryRevealed=true; } else if(model.Nodes.Count>0 && model.Nodes[0].Nodes.Count==0) _axGeometryRevealed=false;')
 for old,new in [('Geometry','Geometría'),('Materials','Materiales'),('Material Assignments','Asignación de materiales'),('Mesh Controls','Controles de malla'),('Refinements','Refinamientos'),('Mesh Bodies','Cuerpos de malla'),('Solution Jobs','Ejecuciones')]:
  t=t.replace('"'+old+'"','"'+new+'"')
 # Status remains a compact badge; explanations live in Details, not dummy child nodes.
 start=t.index('                bool optional=key==');end=t.index('\n            }',start)
 t=t[:start]+t[end:]
 t=replace(t,'            if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();','            if (sourceChanged) AsterMaxModelTreeChanged?.Invoke();\n            AxUpdateMechanicalDetails(_axOutline.SelectedNode);')
 t=replace(t,'cmsTree.Visible ||','cmsTree.Visible || (_axMechanicalMenu != null && _axMechanicalMenu.Visible) || (_axMeshMenu != null && _axMeshMenu.Visible) ||')
 t=replace(t,".Append(node.ForeColor.ToArgb()).Append(';');",".Append(';');")
 return t
edit('UserControls/ModelTree.AsterMaxOutline.cs',outline)
shutil.copyfile(here/'ModelTree.Mechanical34.cs',root/'UserControls/ModelTree.Mechanical34.cs')
shutil.copyfile(here/'AsterMaxC1034Audit.cs',root/'PrePoMax/Forms/AsterMaxC1034Audit.cs')
edit('UserControls/UserControls.csproj',lambda t:replace(t,'<Compile Include="ModelTree.AsterMaxOutline.cs" />','<Compile Include="ModelTree.AsterMaxOutline.cs" />\n    <Compile Include="ModelTree.Mechanical34.cs" />'))
edit('PrePoMax/PrePoMax.csproj',lambda t:replace(t,'<Compile Include="Forms\\AsterMaxNativeUi.cs" />','<Compile Include="Forms\\AsterMaxNativeUi.cs" />\n    <Compile Include="Forms\\AsterMaxC1034Audit.cs" />'))
edit('PrePoMax/Forms/AsterMaxNativeUi.cs',lambda t:replace(t,'_modelTree.EnableAsterMaxOutline();','_modelTree.EnableAsterMaxOutline();\n                StartAsterMaxC1034OutlineAudit();\n                _modelTree.AsterMaxGenerateMeshRequested += () => tsmiCreateMesh_Click(null, EventArgs.Empty);'))
edit('PrePoMax/Forms/FrmMain.cs',lambda t:replace(t,'if (this == ActiveForm)','if (this == ActiveForm && !_modelTree.AsterMaxOutlineFocused)'))
edit('PrePoMax/Globals.cs',lambda t:replace(t,'AsterMax Mechanical C10.33','AsterMax Mechanical C10.34'))
edit('PrePoMax/Properties/AssemblyInfo.cs',lambda t:t.replace('10.33.0.0','10.34.0.0').replace('C10.33','C10.34'))
print('C10.34 mechanical tree, native multiselection, vector icons and details integrated.')

# Balance the existing native message-box hook before CLR teardown (real app and audits).
def shutdown(t):
 if 'MessageBoxManager.Unregister();' in t: return t
 return replace(t,'            Application.Run(new FrmMain(args));','            try { Application.Run(new FrmMain(args)); }\n            finally { MessageBoxManager.Unregister(); }')
edit('PrePoMax/Program.cs',shutdown)
