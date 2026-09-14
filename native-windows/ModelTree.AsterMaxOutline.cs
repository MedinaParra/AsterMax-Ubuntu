using System;
using System.Collections.Generic;
using System.Drawing;
using System.Text;
using System.Windows.Forms;

namespace UserControls
{
    public partial class ModelTree
    {
        private TreeView _axOutline;
        private Timer _axOutlineTimer;
        private string _axOutlineStamp;
        private bool _axRefreshing;
        public event Action AsterMaxSolveRequested;

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
            _axOutline.AfterSelect += (s,e) => SelectAsterMaxSource(e.Node);
            _axOutline.NodeMouseDoubleClick += (s,e) => {
                if (!SelectAsterMaxSource(e.Node)) return;
                var source = e.Node.Tag as TreeNode;
                if (source.Tag != null) tsmiEdit_Click(null, EventArgs.Empty);
                else if (CanCreate(source)) tsmiCreate_Click(null, EventArgs.Empty);
            };
            _axOutline.NodeMouseClick += (s,e) => {
                if (e.Button != MouseButtons.Right || _disableMouse) return;
                _axOutline.SelectedNode = e.Node;
                if (e.Node.Name == "ax-solution") {
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
                var analysis = new TreeNode("Static Structural") { Name = "ax-analysis", Tag = _steps };
                analysis.Nodes.Add(AxCopy(_steps, "Analysis Settings / Steps"));
                analysis.Nodes.Add(AxCopy(_initialConditions));
                analysis.Nodes.Add(AxCopy(_amplitudes));
                var solution = new TreeNode("Solution") { Name = "ax-solution" };
                solution.Nodes.Add(AxCopy(_analyses, "Solution Jobs"));
                foreach (TreeNode node in cltvResults.Nodes) solution.Nodes.Add(AxCopy(node));
                analysis.Nodes.Add(solution);
                model.Nodes.Add(analysis);
                _axOutline.Nodes.Add(project);
                AxRestoreExpansion(_axOutline.Nodes, expanded, selected, first);
                project.Expand(); model.Expand();
                // Keep the imported-body branch discoverable after a previously empty project is filled.
                if (model.Nodes.Count > 0) model.Nodes[0].Expand();
            }
            finally { _axOutline.EndUpdate(); _axRefreshing = false; }
        }

        private static void AxRememberExpansion(TreeNodeCollection nodes, HashSet<string> expanded)
        {
            foreach (TreeNode node in nodes) { if (node.IsExpanded) expanded.Add(node.Name); AxRememberExpansion(node.Nodes, expanded); }
        }
        private void AxRestoreExpansion(TreeNodeCollection nodes, HashSet<string> expanded, string selected, bool first)
        {
            foreach (TreeNode node in nodes) {
                if (first || expanded.Contains(node.Name)) node.Expand();
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
