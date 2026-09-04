using System;
using System.Collections.Generic;
using System.Drawing;
using System.Reflection;
using System.Windows.Forms;

namespace UserControls
{
    public partial class ModelTree
    {
        private sealed class AsterMaxOutlineLink
        {
            public TreeNode Source;
            public ViewType View;
            public string Category;

            public AsterMaxOutlineLink(TreeNode source, ViewType view, string category)
            {
                Source = source;
                View = view;
                Category = category;
            }
        }

        private Panel _asterMaxOutlineHost;
        private TreeView _asterMaxOutlineTree;
        private TextBox _asterMaxOutlineSearch;
        private Label _asterMaxDetailsName;
        private Label _asterMaxDetailsType;
        private Label _asterMaxDetailsView;
        private Label _asterMaxDetailsStatus;
        private Button _asterMaxDetailsEdit;
        private Font _asterMaxOutlineCategoryFont;
        private Dictionary<TreeNode, TreeNode> _asterMaxSourceToOutline;
        private bool _asterMaxOutlineInitialized;
        private bool _asterMaxSyncingOutline;

        private void InitializeAsterMaxOutline()
        {
            if (_asterMaxOutlineInitialized) return;

            _asterMaxSourceToOutline = new Dictionary<TreeNode, TreeNode>();
            _asterMaxOutlineCategoryFont = new Font("Segoe UI", 9F, FontStyle.Bold);

            _asterMaxOutlineHost = new Panel();
            _asterMaxOutlineHost.Name = "asterMaxOutlineHost";
            _asterMaxOutlineHost.Dock = DockStyle.Fill;
            _asterMaxOutlineHost.BackColor = Color.White;

            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 36;
            header.Padding = new Padding(7, 6, 7, 5);
            header.BackColor = Color.FromArgb(245, 247, 250);

            Label outlineLabel = new Label();
            outlineLabel.Text = "Outline";
            outlineLabel.Dock = DockStyle.Left;
            outlineLabel.Width = 62;
            outlineLabel.TextAlign = ContentAlignment.MiddleLeft;
            outlineLabel.Font = new Font("Segoe UI", 9F, FontStyle.Bold);

            _asterMaxOutlineSearch = new TextBox();
            _asterMaxOutlineSearch.Dock = DockStyle.Fill;
            _asterMaxOutlineSearch.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            _asterMaxOutlineSearch.BorderStyle = BorderStyle.FixedSingle;
            _asterMaxOutlineSearch.TextChanged += delegate { RefreshAsterMaxOutline(); };

            Button clearSearch = new Button();
            clearSearch.Text = "×";
            clearSearch.Dock = DockStyle.Right;
            clearSearch.Width = 28;
            clearSearch.FlatStyle = FlatStyle.Flat;
            clearSearch.FlatAppearance.BorderSize = 0;
            clearSearch.BackColor = header.BackColor;
            clearSearch.Font = new Font("Segoe UI", 10F, FontStyle.Bold);
            clearSearch.Click += delegate { _asterMaxOutlineSearch.Text = ""; };

            header.Controls.Add(_asterMaxOutlineSearch);
            header.Controls.Add(clearSearch);
            header.Controls.Add(outlineLabel);

            Panel detailsPanel = new Panel();
            detailsPanel.Dock = DockStyle.Bottom;
            detailsPanel.Height = 142;
            detailsPanel.Padding = new Padding(7, 5, 7, 6);
            detailsPanel.BackColor = Color.FromArgb(248, 249, 251);
            detailsPanel.BorderStyle = BorderStyle.FixedSingle;

            Label detailsHeader = new Label();
            detailsHeader.Text = "Details";
            detailsHeader.Dock = DockStyle.Top;
            detailsHeader.Height = 23;
            detailsHeader.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
            detailsHeader.TextAlign = ContentAlignment.MiddleLeft;

            TableLayoutPanel detailsTable = new TableLayoutPanel();
            detailsTable.Dock = DockStyle.Fill;
            detailsTable.ColumnCount = 2;
            detailsTable.RowCount = 4;
            detailsTable.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 64F));
            detailsTable.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100F));
            for (int i = 0; i < 4; i++) detailsTable.RowStyles.Add(new RowStyle(SizeType.Percent, 25F));

            _asterMaxDetailsName = CreateAsterMaxDetailsValue();
            _asterMaxDetailsType = CreateAsterMaxDetailsValue();
            _asterMaxDetailsView = CreateAsterMaxDetailsValue();
            _asterMaxDetailsStatus = CreateAsterMaxDetailsValue();

            AddAsterMaxDetailsRow(detailsTable, 0, "Name", _asterMaxDetailsName);
            AddAsterMaxDetailsRow(detailsTable, 1, "Type", _asterMaxDetailsType);
            AddAsterMaxDetailsRow(detailsTable, 2, "View", _asterMaxDetailsView);
            AddAsterMaxDetailsRow(detailsTable, 3, "Status", _asterMaxDetailsStatus);

            _asterMaxDetailsEdit = new Button();
            _asterMaxDetailsEdit.Text = "Edit";
            _asterMaxDetailsEdit.Dock = DockStyle.Bottom;
            _asterMaxDetailsEdit.Height = 27;
            _asterMaxDetailsEdit.FlatStyle = FlatStyle.Flat;
            _asterMaxDetailsEdit.Enabled = false;
            _asterMaxDetailsEdit.Click += delegate
            {
                AsterMaxOutlineLink link = GetSelectedAsterMaxOutlineLink();
                if (link == null || link.Source == null || link.Source.Tag == null) return;
                ActivateAsterMaxSource(link);
                tsmiEdit_Click(null, null);
            };

            detailsPanel.Controls.Add(detailsTable);
            detailsPanel.Controls.Add(_asterMaxDetailsEdit);
            detailsPanel.Controls.Add(detailsHeader);

            _asterMaxOutlineTree = new TreeView();
            _asterMaxOutlineTree.Name = "asterMaxOutlineTree";
            _asterMaxOutlineTree.Dock = DockStyle.Fill;
            _asterMaxOutlineTree.BorderStyle = BorderStyle.None;
            _asterMaxOutlineTree.BackColor = Color.White;
            _asterMaxOutlineTree.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            _asterMaxOutlineTree.HideSelection = false;
            _asterMaxOutlineTree.FullRowSelect = true;
            _asterMaxOutlineTree.ShowLines = true;
            _asterMaxOutlineTree.ShowRootLines = true;
            _asterMaxOutlineTree.ShowNodeToolTips = true;
            _asterMaxOutlineTree.Indent = 20;
            _asterMaxOutlineTree.ItemHeight = 24;
            _asterMaxOutlineTree.ImageList = ilIcons;
            _asterMaxOutlineTree.StateImageList = ilStatusIcons;
            _asterMaxOutlineTree.AfterSelect += AsterMaxOutline_AfterSelect;
            _asterMaxOutlineTree.NodeMouseDoubleClick += AsterMaxOutline_NodeMouseDoubleClick;
            _asterMaxOutlineTree.MouseUp += AsterMaxOutline_MouseUp;
            _asterMaxOutlineTree.KeyDown += AsterMaxOutline_KeyDown;

            _asterMaxOutlineHost.Controls.Add(_asterMaxOutlineTree);
            _asterMaxOutlineHost.Controls.Add(detailsPanel);
            _asterMaxOutlineHost.Controls.Add(header);

            tcGeometryModelResults.Visible = false;
            Controls.Add(_asterMaxOutlineHost);
            _asterMaxOutlineHost.BringToFront();

            cltvGeometry.SelectionsChanged += AsterMaxSource_SelectionsChanged;
            cltvModel.SelectionsChanged += AsterMaxSource_SelectionsChanged;
            cltvResults.SelectionsChanged += AsterMaxSource_SelectionsChanged;

            _asterMaxOutlineInitialized = true;
            RefreshAsterMaxOutline();
        }

        private Label CreateAsterMaxDetailsValue()
        {
            Label label = new Label();
            label.Dock = DockStyle.Fill;
            label.AutoEllipsis = true;
            label.TextAlign = ContentAlignment.MiddleLeft;
            label.Font = new Font("Segoe UI", 8.5F, FontStyle.Regular);
            label.ForeColor = Color.FromArgb(45, 50, 57);
            return label;
        }

        private void AddAsterMaxDetailsRow(TableLayoutPanel table, int row, string name, Label value)
        {
            Label key = new Label();
            key.Text = name;
            key.Dock = DockStyle.Fill;
            key.TextAlign = ContentAlignment.MiddleLeft;
            key.Font = new Font("Segoe UI", 8F, FontStyle.Bold);
            key.ForeColor = Color.FromArgb(80, 86, 94);
            table.Controls.Add(key, 0, row);
            table.Controls.Add(value, 1, row);
        }

        public void RefreshAsterMaxOutline()
        {
            if (!_asterMaxOutlineInitialized || _asterMaxOutlineTree == null || _asterMaxSyncingOutline) return;

            HashSet<string> expanded = GetAsterMaxExpandedPaths();
            string query = _asterMaxOutlineSearch == null ? "" : _asterMaxOutlineSearch.Text.Trim();

            _asterMaxSyncingOutline = true;
            _asterMaxOutlineTree.BeginUpdate();
            try
            {
                _asterMaxOutlineTree.Nodes.Clear();
                _asterMaxSourceToOutline.Clear();

                TreeNode project = CreateAsterMaxCategory("AsterMax Mechanical");
                project.NodeFont = _asterMaxOutlineCategoryFont;
                _asterMaxOutlineTree.Nodes.Add(project);

                TreeNode model = CreateAsterMaxLinkedNode(_model, ViewType.Model, "Model", "Model", false);
                if (model == null) model = CreateAsterMaxCategory("Model");
                model.NodeFont = _asterMaxOutlineCategoryFont;
                project.Nodes.Add(model);

                TreeNode geometry = CreateAsterMaxLinkedNode(_geomParts, ViewType.Geometry, "Geometry", "Geometry", true);
                if (geometry != null) model.Nodes.Add(geometry);

                TreeNode mesh = CreateAsterMaxLinkedNode(_modelMesh, ViewType.Model, "Mesh", "Mesh", true);
                if (mesh == null) mesh = CreateAsterMaxCategory("Mesh");
                TreeNode meshingParameters = CreateAsterMaxLinkedNode(_meshingParameters, ViewType.Geometry,
                                                                       "Meshing Controls", "Meshing Parameters", true);
                TreeNode meshRefinements = CreateAsterMaxLinkedNode(_meshRefinements, ViewType.Geometry,
                                                                     "Meshing Controls", "Mesh Refinements", true);
                if (meshingParameters != null) mesh.Nodes.Insert(0, meshingParameters);
                if (meshRefinements != null) mesh.Nodes.Insert(Math.Min(1, mesh.Nodes.Count), meshRefinements);
                model.Nodes.Add(mesh);

                AddAsterMaxLinkedIfNotNull(model, _materials, ViewType.Model, "Materials", "Materials", true);
                AddAsterMaxLinkedIfNotNull(model, _sections, ViewType.Model, "Sections", "Sections", true);

                TreeNode connections = CreateAsterMaxCategory("Connections");
                AddAsterMaxLinkedIfNotNull(connections, _constraints, ViewType.Model, "Connections", "Constraints", true);
                AddAsterMaxLinkedIfNotNull(connections, _contacts, ViewType.Model, "Connections", "Contacts", true);
                if (connections.Nodes.Count > 0) model.Nodes.Add(connections);

                AddAsterMaxLinkedIfNotNull(model, _amplitudes, ViewType.Model, "Amplitudes", "Amplitudes", true);
                AddAsterMaxLinkedIfNotNull(model, _initialConditions, ViewType.Model, "Initial Conditions",
                                           "Initial Conditions", true);

                TreeNode analysesRoot = CreateAsterMaxCategory("Analyses");
                analysesRoot.NodeFont = _asterMaxOutlineCategoryFont;
                project.Nodes.Add(analysesRoot);

                foreach (TreeNode step in _steps.Nodes)
                {
                    string label = GetAsterMaxAnalysisLabel(step);
                    TreeNode analysis = CreateAsterMaxLinkedNode(step, ViewType.Model, "Analysis", label, true);
                    if (analysis != null) analysesRoot.Nodes.Add(analysis);
                }

                TreeNode jobs = CreateAsterMaxLinkedNode(_analyses, ViewType.Model, "Solver Jobs", "Solver Jobs", true);
                if (jobs != null) analysesRoot.Nodes.Add(jobs);

                TreeNode solution = CreateAsterMaxCategory("Solution");
                solution.NodeFont = _asterMaxOutlineCategoryFont;
                project.Nodes.Add(solution);
                AddAsterMaxLinkedIfNotNull(solution, _resultFieldOutputs, ViewType.Results, "Solution",
                                           "Result Fields", true);
                AddAsterMaxLinkedIfNotNull(solution, _resultHistoryOutputs, ViewType.Results, "Solution",
                                           "History Results", true);
                AddAsterMaxLinkedIfNotNull(solution, _resultMesh, ViewType.Results, "Solution", "Result Mesh", true);

                if (!string.IsNullOrWhiteSpace(query)) PruneAsterMaxOutline(project, query);

                if (expanded.Count == 0)
                {
                    project.Expand();
                    model.Expand();
                    analysesRoot.Expand();
                    solution.Expand();
                    mesh.Expand();
                }
                else
                {
                    RestoreAsterMaxExpandedPaths(project, expanded);
                }
            }
            finally
            {
                _asterMaxOutlineTree.EndUpdate();
                _asterMaxSyncingOutline = false;
            }

            SyncAsterMaxOutlineSelectionFromSource();
        }

        private TreeNode CreateAsterMaxCategory(string text)
        {
            TreeNode node = new TreeNode(text);
            node.Name = text;
            node.ForeColor = Color.FromArgb(35, 42, 50);
            node.ToolTipText = text;
            return node;
        }

        private void AddAsterMaxLinkedIfNotNull(TreeNode parent, TreeNode source, ViewType view,
                                                string category, string text, bool includeChildren)
        {
            TreeNode node = CreateAsterMaxLinkedNode(source, view, category, text, includeChildren);
            if (node != null) parent.Nodes.Add(node);
        }

        private TreeNode CreateAsterMaxLinkedNode(TreeNode source, ViewType view, string category,
                                                  string text, bool includeChildren)
        {
            if (source == null) return null;

            TreeNode node = new TreeNode(string.IsNullOrWhiteSpace(text) ? GetAsterMaxSourceText(source) : text);
            node.Name = source.Name;
            node.Tag = new AsterMaxOutlineLink(source, view, category);
            node.ImageKey = source.ImageKey;
            node.SelectedImageKey = source.SelectedImageKey;
            node.StateImageKey = source.StateImageKey;
            node.ToolTipText = string.IsNullOrWhiteSpace(source.ToolTipText) ? node.Text : source.ToolTipText;
            _asterMaxSourceToOutline[source] = node;

            if (includeChildren)
            {
                foreach (TreeNode childSource in source.Nodes)
                {
                    TreeNode child = CreateAsterMaxLinkedNode(childSource, view, category,
                                                              GetAsterMaxSourceText(childSource), true);
                    if (child != null) node.Nodes.Add(child);
                }
            }
            return node;
        }

        private string GetAsterMaxSourceText(TreeNode source)
        {
            if (source == null) return "";
            if (source.Tag == null && !string.IsNullOrWhiteSpace(source.Name)) return source.Name;
            return source.Text;
        }

        private string GetAsterMaxAnalysisLabel(TreeNode step)
        {
            string typeName = step != null && step.Tag != null ? step.Tag.GetType().Name : "";
            string prefix = "Analysis";
            if (typeName.IndexOf("Static", StringComparison.OrdinalIgnoreCase) >= 0) prefix = "Static Structural";
            else if (typeName.IndexOf("Frequency", StringComparison.OrdinalIgnoreCase) >= 0 ||
                     typeName.IndexOf("Modal", StringComparison.OrdinalIgnoreCase) >= 0) prefix = "Modal";
            else if (typeName.IndexOf("Heat", StringComparison.OrdinalIgnoreCase) >= 0 ||
                     typeName.IndexOf("Thermal", StringComparison.OrdinalIgnoreCase) >= 0) prefix = "Thermal";
            else if (typeName.IndexOf("Dynamic", StringComparison.OrdinalIgnoreCase) >= 0) prefix = "Dynamic";
            else if (typeName.IndexOf("Buckling", StringComparison.OrdinalIgnoreCase) >= 0) prefix = "Buckling";

            string name = step == null ? "" : step.Text;
            return string.IsNullOrWhiteSpace(name) ? prefix : prefix + " — " + name;
        }

        private bool PruneAsterMaxOutline(TreeNode node, string query)
        {
            bool selfMatch = node.Text.IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0;
            for (int i = node.Nodes.Count - 1; i >= 0; i--)
            {
                if (!PruneAsterMaxOutline(node.Nodes[i], query)) node.Nodes.RemoveAt(i);
            }

            bool keep = selfMatch || node.Nodes.Count > 0 || node.Parent == null;
            if (keep && node.Nodes.Count > 0) node.Expand();
            return keep;
        }

        private HashSet<string> GetAsterMaxExpandedPaths()
        {
            HashSet<string> paths = new HashSet<string>(StringComparer.Ordinal);
            if (_asterMaxOutlineTree == null) return paths;
            foreach (TreeNode root in _asterMaxOutlineTree.Nodes) CollectAsterMaxExpandedPaths(root, paths);
            return paths;
        }

        private void CollectAsterMaxExpandedPaths(TreeNode node, HashSet<string> paths)
        {
            if (node.IsExpanded) paths.Add(node.FullPath);
            foreach (TreeNode child in node.Nodes) CollectAsterMaxExpandedPaths(child, paths);
        }

        private void RestoreAsterMaxExpandedPaths(TreeNode node, HashSet<string> paths)
        {
            if (paths.Contains(node.FullPath)) node.Expand();
            foreach (TreeNode child in node.Nodes) RestoreAsterMaxExpandedPaths(child, paths);
        }

        private AsterMaxOutlineLink GetSelectedAsterMaxOutlineLink()
        {
            if (_asterMaxOutlineTree == null || _asterMaxOutlineTree.SelectedNode == null) return null;
            return _asterMaxOutlineTree.SelectedNode.Tag as AsterMaxOutlineLink;
        }

        private void AsterMaxOutline_AfterSelect(object sender, TreeViewEventArgs e)
        {
            UpdateAsterMaxDetails(e.Node);
            if (_asterMaxSyncingOutline || _disableMouse) return;
            AsterMaxOutlineLink link = e.Node == null ? null : e.Node.Tag as AsterMaxOutlineLink;
            if (link != null) ActivateAsterMaxSource(link);
        }

        private void AsterMaxOutline_NodeMouseDoubleClick(object sender, TreeNodeMouseClickEventArgs e)
        {
            if (_disableMouse || e.Node == null) return;
            AsterMaxOutlineLink link = e.Node.Tag as AsterMaxOutlineLink;
            if (link == null || link.Source == null)
            {
                if (e.Node.IsExpanded) e.Node.Collapse();
                else e.Node.Expand();
                return;
            }

            ActivateAsterMaxSource(link);
            if (link.Source.Tag == null)
            {
                if (CanCreate(link.Source)) tsmiCreate_Click(null, null);
                else
                {
                    if (e.Node.IsExpanded) e.Node.Collapse();
                    else e.Node.Expand();
                }
            }
            else tsmiEdit_Click(null, null);
        }

        private void AsterMaxOutline_MouseUp(object sender, MouseEventArgs e)
        {
            if (_disableMouse || e.Button != MouseButtons.Right) return;
            TreeNode node = _asterMaxOutlineTree.GetNodeAt(e.Location);
            if (node == null) return;
            _asterMaxOutlineTree.SelectedNode = node;

            AsterMaxOutlineLink link = node.Tag as AsterMaxOutlineLink;
            if (link == null || link.Source == null) return;
            ActivateAsterMaxSource(link);
            CodersLabTreeView sourceTree = GetTree(link.View);
            PrepareToolStripItem(sourceTree);
            cmsTree.Show(_asterMaxOutlineTree, e.Location);
        }

        private void AsterMaxOutline_KeyDown(object sender, KeyEventArgs e)
        {
            if (_disableMouse) return;
            AsterMaxOutlineLink link = GetSelectedAsterMaxOutlineLink();
            if (link == null || link.Source == null) return;
            ActivateAsterMaxSource(link);
            cltv_KeyDown(GetTree(link.View), e);
        }

        private void ActivateAsterMaxSource(AsterMaxOutlineLink link)
        {
            if (link == null || link.Source == null) return;

            _asterMaxSyncingOutline = true;
            try
            {
                TabPage targetTab = link.View == ViewType.Geometry ? tpGeometry :
                                    link.View == ViewType.Model ? tpModel : tpResults;
                if (tcGeometryModelResults.SelectedTab != targetTab)
                    tcGeometryModelResults.SelectedTab = targetTab;

                CodersLabTreeView tree = GetTree(link.View);
                tree.SelectedNodes.Clear();
                tree.SelectedNodes.Add(link.Source);
                link.Source.EnsureVisible();
            }
            finally
            {
                _asterMaxSyncingOutline = false;
            }

            cltv_SelectionsChanged(GetTree(link.View), EventArgs.Empty);
        }

        private void AsterMaxSource_SelectionsChanged(object sender, EventArgs e)
        {
            if (_asterMaxSyncingOutline) return;
            SyncAsterMaxOutlineSelectionFromSource();
        }

        public void SyncAsterMaxOutlineSelectionFromSource()
        {
            if (!_asterMaxOutlineInitialized || _asterMaxOutlineTree == null || _asterMaxSyncingOutline) return;

            TreeNode source = null;
            CodersLabTreeView active = GetActiveTree();
            if (active != null && active.SelectedNodes.Count > 0) source = active.SelectedNodes[0];

            _asterMaxSyncingOutline = true;
            try
            {
                if (source != null && _asterMaxSourceToOutline.ContainsKey(source))
                {
                    TreeNode target = _asterMaxSourceToOutline[source];
                    _asterMaxOutlineTree.SelectedNode = target;
                    target.EnsureVisible();
                    UpdateAsterMaxDetails(target);
                }
            }
            finally
            {
                _asterMaxSyncingOutline = false;
            }
        }

        private void UpdateAsterMaxDetails(TreeNode outlineNode)
        {
            if (_asterMaxDetailsName == null) return;

            AsterMaxOutlineLink link = outlineNode == null ? null : outlineNode.Tag as AsterMaxOutlineLink;
            if (outlineNode == null)
            {
                _asterMaxDetailsName.Text = "";
                _asterMaxDetailsType.Text = "";
                _asterMaxDetailsView.Text = "";
                _asterMaxDetailsStatus.Text = "";
                _asterMaxDetailsEdit.Enabled = false;
                return;
            }

            _asterMaxDetailsName.Text = outlineNode.Text;
            if (link == null || link.Source == null)
            {
                _asterMaxDetailsType.Text = "Category";
                _asterMaxDetailsView.Text = "Project";
                _asterMaxDetailsStatus.Text = "Defined";
                _asterMaxDetailsEdit.Enabled = false;
                return;
            }

            object item = link.Source.Tag;
            _asterMaxDetailsType.Text = item == null ? "Container" : item.GetType().Name;
            _asterMaxDetailsView.Text = link.View.ToString();
            _asterMaxDetailsStatus.Text = GetAsterMaxNodeStatus(link.Source);
            _asterMaxDetailsEdit.Enabled = item != null;
        }

        private string GetAsterMaxNodeStatus(TreeNode source)
        {
            if (source == null) return "Unknown";
            object item = source.Tag;
            if (item != null)
            {
                try
                {
                    PropertyInfo active = item.GetType().GetProperty("Active", BindingFlags.Instance | BindingFlags.Public);
                    if (active != null && active.PropertyType == typeof(bool))
                    {
                        object value = active.GetValue(item, null);
                        if (value is bool && !(bool)value) return "Inactive";
                    }

                    PropertyInfo status = item.GetType().GetProperty("Status", BindingFlags.Instance | BindingFlags.Public);
                    if (status != null)
                    {
                        object value = status.GetValue(item, null);
                        if (value != null) return value.ToString();
                    }
                }
                catch { }
            }

            if (!string.IsNullOrWhiteSpace(source.StateImageKey))
                return source.StateImageKey.Replace("_", " ");
            return item == null ? "Container" : "Defined";
        }
    }
}
