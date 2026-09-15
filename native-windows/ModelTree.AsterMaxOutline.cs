using System;
using System.Collections.Generic;
using System.Drawing;
using System.Text;
using System.Windows.Forms;

namespace UserControls
{
    public sealed class AsterMaxSectionState
    {
        public int State; // 0: mandatory missing, 1: information/incomplete, 2: validated configuration
        public string Message;
        public AsterMaxSectionState(int state, string message) { State=state; Message=message; }
    }
    public partial class ModelTree
    {
        private TreeView _axOutline;
        private Timer _axOutlineTimer;
        private string _axOutlineStamp;
        private bool _axRefreshing;
        public event Action AsterMaxSolveRequested;
        public event Action AsterMaxAnalysisTypeRequested;
        public Func<Dictionary<string,AsterMaxSectionState>> AsterMaxSectionStates;
        private ImageList _axSectionIcons;
        private Label _axWorkflowHint;

        public void EnableAsterMaxOutline()
        {
            if (_axOutline != null) return;
            _axOutline = new TreeView { Name = "asterMaxOutline", Dock = DockStyle.Fill,
                HideSelection = false, ShowLines = true, ShowRootLines = true,
                BackColor = Color.White, ForeColor = Color.FromArgb(34,42,53),
                Font = new Font("Segoe UI", 9), BorderStyle = BorderStyle.None };
            // Keep the original nodes and event routing alive; only their presentation is replaced.
            tcGeometryModelResults.Visible = false;
            Controls.Add(_axOutline);
            _axOutline.BringToFront();
            _axWorkflowHint = new Label { Name="asterMaxWorkflowHint", Dock=DockStyle.Bottom, Height=88,
                Padding=new Padding(8), BackColor=Color.FromArgb(239,246,252),
                Text="? Pendiente   i Revisar   ✓ Completo\n\nSeleccione una sección para ver qué falta completar.",
                Font=new Font("Segoe UI",9), AutoEllipsis=true };
            Controls.Add(_axWorkflowHint);
            _axWorkflowHint.SendToBack();
            _axOutline.ShowNodeToolTips = true;
            _axSectionIcons = new ImageList { ImageSize=new Size(16,16), ColorDepth=ColorDepth.Depth32Bit };
            _axSectionIcons.Images.Add("pending", AxStatusIcon("?", Color.FromArgb(198,139,0)));
            _axSectionIcons.Images.Add("info", AxStatusIcon("i", Color.FromArgb(35,116,180)));
            _axSectionIcons.Images.Add("done", AxStatusIcon("", Color.FromArgb(30,145,70)));
            _axOutline.StateImageList = _axSectionIcons;
            Disposed += (s,e) => _axSectionIcons.Dispose();
            _axOutline.AfterSelect += (s,e) => {
                TreeNode info=e.Node;
                while(info!=null && String.IsNullOrEmpty(info.ToolTipText)) info=info.Parent;
                if(info!=null) {
                    _axWorkflowHint.Text=info.ToolTipText;
                    _axWorkflowHint.BackColor=info.BackColor.IsEmpty?Color.FromArgb(239,246,252):info.BackColor;
                }
                SelectAsterMaxSource(e.Node);
            };
            _axOutline.NodeMouseDoubleClick += (s,e) => {
                if (e.Node.Name == "ax-analysis") { AsterMaxAnalysisTypeRequested?.Invoke(); return; }
                if (!SelectAsterMaxSource(e.Node)) return;
                var source = e.Node.Tag as TreeNode;
                if (source.Tag != null) tsmiEdit_Click(null, EventArgs.Empty);
                else if (CanCreate(source)) tsmiCreate_Click(null, EventArgs.Empty);
            };
            _axOutline.NodeMouseClick += (s,e) => {
                if (e.Button != MouseButtons.Right || _disableMouse) return;
                _axOutline.SelectedNode = e.Node;
                if (e.Node.Name == "ax-analysis") {
                    var menu = new ContextMenuStrip();
                    menu.Items.Add("Select analysis type / edit study", null, (a,b) => AsterMaxAnalysisTypeRequested?.Invoke());
                    menu.Closed += (a,b) => menu.Dispose(); menu.Show(_axOutline,e.Location);
                }
                else if (e.Node.Name == "ax-solution") {
                    var menu = new ContextMenuStrip();
                    menu.Items.Add("Solve — Code_Aster", null, (a,b) => AsterMaxSolveRequested?.Invoke());
                    menu.Closed += (a,b) => menu.Dispose();
                    menu.Show(_axOutline, e.Location);
                }
                else if (SelectAsterMaxSource(e.Node)) {
                    PrepareToolStripItem(GetActiveTree());
                    tsmiEditCalculiXKeywords.Visible = false;
                    tsmiSpaceEditCalculiXKeywords.Visible = false;
                    cmsTree.Show(_axOutline, e.Location);
                }
            };
            _axOutline.KeyDown += (s,e) => {
                if (SelectAsterMaxSource(_axOutline.SelectedNode) &&
                    (e.KeyCode == Keys.Delete || e.KeyCode == Keys.Enter || e.KeyCode == Keys.Space))
                    cltv_KeyDown(s,e);
            };
            _axOutlineTimer = new Timer { Interval = 300 };
            _axOutlineTimer.Tick += (s,e) => RefreshAsterMaxOutline();
            Disposed += (s,e) => { _axOutlineTimer.Stop(); _axOutlineTimer.Dispose(); };
            RefreshAsterMaxOutline();
            _axOutlineTimer.Start();
        }

        private bool SelectAsterMaxSource(TreeNode projected)
        {
            if (_axRefreshing || _disableMouse || projected == null) return false;
            var source = projected.Tag as TreeNode;
            if (source == null || source.TreeView == null) return false;
            var tree = source.TreeView as CodersLabTreeView;
            if (tree == cltvGeometry) { SetGeometryTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Geometry); }
            else if (tree == cltvModel) { SetModelTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Model); }
            else if (tree == cltvResults) { SetResultsTab(); GeometryMeshResultsEvent?.Invoke(ViewType.Results); }
            else return false;
            tree.SelectedNodes.Clear();
            tree.SelectedNodes.Add(source);
            cltv_SelectionsChanged(tree, EventArgs.Empty);
            return true;
        }

        private TreeNode AxCopy(TreeNode source, string caption = null)
        {
            var node = new TreeNode(caption ?? source.Text) {
                Name = source.TreeView.Name + "/" + source.FullPath, Tag = source,
                ForeColor = source.ForeColor };
            foreach (TreeNode child in source.Nodes) node.Nodes.Add(AxCopy(child));
            return node;
        }

        private static void AxStamp(TreeNode node, StringBuilder stamp)
        {
            var item=node.Tag as CaeGlobals.NamedClass;
            if(item!=null) stamp.Append(item.GetHashCode()).Append(item.Valid).Append(item.Active);
            stamp.Append(node.Name).Append(':').Append(node.Text).Append(':')
                .Append(System.Runtime.CompilerServices.RuntimeHelpers.GetHashCode(node)).Append(':')
                .Append(node.ForeColor.ToArgb()).Append(';');
            foreach (TreeNode child in node.Nodes) AxStamp(child, stamp);
        }

        public void RefreshAsterMaxOutline()
        {
            if (_axOutline == null || _disableMouse || !_screenUpdating || cmsTree.Visible) return;
            var stamp = new StringBuilder();
            foreach (TreeView tree in new TreeView[] { cltvGeometry, cltvModel, cltvResults })
                foreach (TreeNode node in tree.Nodes) AxStamp(node,stamp);
            if (_axOutlineStamp == stamp.ToString()) return;
            _axOutlineStamp = stamp.ToString();
            var expanded = new HashSet<string>();
            AxRememberExpansion(_axOutline.Nodes, expanded);
            string selected = _axOutline.SelectedNode == null ? null : _axOutline.SelectedNode.Name;
            string topName = _axOutline.TopNode == null ? null : _axOutline.TopNode.Name;
            bool first = _axOutline.Nodes.Count == 0;
            _axRefreshing = true;
            _axOutline.BeginUpdate();
            try {
                _axOutline.Nodes.Clear();
                var project = new TreeNode("Project") { Name = "ax-project" };
                var model = new TreeNode("Model") { Name = "ax-model", Tag = _model };
                project.Nodes.Add(model);
                model.Nodes.Add(AxCopy(_geomParts, "Geometry"));
                var materials = AxCopy(_materials, "Materials");
                materials.Nodes.Add(AxCopy(_sections, "Material Assignments"));
                model.Nodes.Add(materials);
                var coordinates = new TreeNode("Coordinate Systems") { Name = "ax-coordinates" };
                coordinates.Nodes.Add(new TreeNode("Global Cartesian (X, Y, Z)") { Name = "ax-global" });
                model.Nodes.Add(coordinates);
                var connections = new TreeNode("Connections") { Name = "ax-connections", Tag = _contacts };
                connections.Nodes.Add(AxCopy(_constraints));
                foreach (TreeNode node in _contacts.Nodes) connections.Nodes.Add(AxCopy(node));
                model.Nodes.Add(connections);
                var mesh = new TreeNode("Mesh") { Name = "ax-mesh", Tag = _modelMesh };
                mesh.Nodes.Add(AxCopy(_meshingParameters, "Mesh Controls"));
                mesh.Nodes.Add(AxCopy(_meshRefinements, "Refinements"));
                mesh.Nodes.Add(AxCopy(_modelParts, "Mesh Bodies"));
                model.Nodes.Add(mesh);
                var selections = new TreeNode("Named Selections") { Name = "ax-selections" };
                selections.Nodes.Add(AxCopy(_modelNodeSets));
                selections.Nodes.Add(AxCopy(_modelElementSets));
                selections.Nodes.Add(AxCopy(_modelSurfaces));
                selections.Nodes.Add(AxCopy(_referencePoints));
                model.Nodes.Add(selections);
                var analysis = new TreeNode("Type Analysis") { Name = "ax-analysis", Tag = _steps };
                analysis.Nodes.Add(AxCopy(_steps, "Analysis Settings / Steps"));
                analysis.Nodes.Add(AxCopy(_initialConditions));
                analysis.Nodes.Add(AxCopy(_amplitudes));
                var solution = new TreeNode("Solution") { Name = "ax-solution" };
                solution.Nodes.Add(AxCopy(_analyses, "Solution Jobs"));
                foreach (TreeNode node in cltvResults.Nodes) solution.Nodes.Add(AxCopy(node));
                analysis.Nodes.Add(solution);
                model.Nodes.Add(analysis);
                _axOutline.Nodes.Add(project);
                if (AsterMaxSectionStates != null) AxApplySectionStates(_axOutline.Nodes, AsterMaxSectionStates());
                AxRestoreExpansion(_axOutline.Nodes, expanded, selected, first);
                project.Expand(); model.Expand();
                // Keep the imported-body branch discoverable after a previously empty project is filled.
                if (model.Nodes.Count > 0) model.Nodes[0].Expand();
                if (first) analysis.Expand();
                TreeNode[] previousTop = topName == null ? new TreeNode[0] : _axOutline.Nodes.Find(topName, true);
                _axOutline.TopNode = previousTop.Length > 0 ? previousTop[0] : project;
            }
            finally { _axOutline.EndUpdate(); _axRefreshing = false; }
        }

        private static void AxRememberExpansion(TreeNodeCollection nodes, HashSet<string> expanded)
        {
            foreach (TreeNode node in nodes) { if (node.IsExpanded) expanded.Add(node.Name); AxRememberExpansion(node.Nodes, expanded); }
        }

        private static Bitmap AxStatusIcon(string text, Color color)
        {
            var bitmap=new Bitmap(16,16);
            using(var g=Graphics.FromImage(bitmap)) {
                g.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                using(var brush=new SolidBrush(color)) g.FillEllipse(brush,1,1,14,14);
                if(text.Length==0) {
                    using(var pen=new Pen(Color.White,2)) g.DrawLines(pen,new Point[]{new Point(4,8),new Point(7,11),new Point(12,5)});
                } else using(var font=new Font("Segoe UI",9,FontStyle.Bold))
                    g.DrawString(text,font,Brushes.White,new RectangleF(0,0,16,16),new StringFormat{Alignment=StringAlignment.Center,LineAlignment=StringAlignment.Center});
            }
            return bitmap;
        }

        private void AxApplySectionStates(TreeNodeCollection nodes, Dictionary<string,AsterMaxSectionState> states)
        {
            foreach(TreeNode node in nodes) AxApplySectionStatesSingle(node,states);
        }
        private void AxApplySectionStatesSingle(TreeNode node, Dictionary<string,AsterMaxSectionState> states)
        {
            // Process a subtree without moving its native/projection nodes.
            TreeNode source=node.Tag as TreeNode;
            string key=node.Name;
            if(source==_geomParts) key="geometry";
            else if(source==_materials) key="materials";
            else if(source==_sections) key="assignments";
            else if(source!=null && source.Name==_boundaryConditionsName) key="supports";
            else if(source!=null && source.Name==_loadsName) key="loads";
            AsterMaxSectionState state;
            if(states.TryGetValue(key,out state)) {
                node.StateImageKey=state.State==2?"done":state.State==0?"pending":"info";
                node.ToolTipText=state.Message;
                bool optional=key=="ax-coordinates"||key=="ax-connections"||key=="ax-selections";
                if(state.State!=2&&!optional) node.BackColor=Color.FromArgb(255,244,184);
                if(state.State!=2&&!optional) node.Nodes.Add(new TreeNode("Revisar campos") {
                    Name="ax-info-"+key, StateImageKey="info", BackColor=Color.FromArgb(255,244,184),ToolTipText=state.Message });
            }
            foreach(TreeNode child in node.Nodes) if(!child.Name.StartsWith("ax-info-")) AxApplySectionStatesSingle(child,states);
        }
        private void AxRestoreExpansion(TreeNodeCollection nodes, HashSet<string> expanded, string selected, bool first)
        {
            foreach (TreeNode node in nodes) {
                if (expanded.Contains(node.Name)) node.Expand();
                if (node.Name == selected) _axOutline.SelectedNode = node;
                AxRestoreExpansion(node.Nodes,expanded,selected,first);
            }
        }

        public bool AsterMaxOutlineHasGeometry(string partName)
        {
            RefreshAsterMaxOutline();
            return _axOutline != null && _axOutline.Visible && _axOutline.Width > 100 &&
                _axOutline.Height > 100 && AxFindSource(_axOutline.Nodes, partName);
        }
        private bool AxFindSource(TreeNodeCollection nodes, string partName)
        {
            foreach (TreeNode node in nodes) {
                var source = node.Tag as TreeNode;
                if (source != null && source.TreeView == cltvGeometry && source.Name == partName) return true;
                if (AxFindSource(node.Nodes, partName)) return true;
            }
            return false;
        }
    }
}
