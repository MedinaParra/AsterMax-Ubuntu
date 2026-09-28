using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;
using CaeGlobals;

namespace UserControls
{
    public partial class ModelTree
    {
        private ImageList _axObjectIcons;
        private DataGridView _axDetailsGrid;
        private Label _axDetailsCaption;
        private Button _axEditSelection;
        private TextBox _axFindBox;
        private ContextMenuStrip _axMechanicalMenu;
        private AxCommandMenu _axMeshMenu;
        private bool _axSyncingSelection;
        private SplitContainer _axTreeDetails;
        public bool AsterMaxOutlineFocused { get { return _axOutline != null && _axOutline.ContainsFocus; } }
        public event Action AsterMaxGenerateMeshRequested;

        private void AxInitializeMechanical34()
        {
            _axOutline.SelectionMode = TreeViewSelectionMode.MultiSelectSameParent;
            _axOutline.SelectionBackColor = Color.FromArgb(218,230,255);
            _axOutline.ShowLines = false;
            _axOutline.ShowRootLines = false;
            _axOutline.FullRowSelect = true;
            _axOutline.ItemHeight = 23;
            _axOutline.Indent = 18;
            _axOutline.HotTracking = false;
            _axObjectIcons = new ImageList { ImageSize = new Size(20,20), ColorDepth = ColorDepth.Depth32Bit };
            foreach (string key in new[] { "project", "model", "geometry", "body", "material", "assignment", "coordinates", "connections", "contact", "mesh", "mesh-control", "selection", "analysis", "settings", "support", "load", "solution", "result", "info", "folder" })
                _axObjectIcons.Images.Add(key, AxMechanicalIcon(key));
            _axOutline.ImageList = _axObjectIcons;
            Disposed += (s,e) => _axObjectIcons.Dispose();
            _asterMaxDetailsPanel.Visible = false;
            Controls.Remove(_axOutline);
            Controls.Remove(_axWorkflowHint);
            _axTreeDetails = new SplitContainer { Name="asterMaxTreeDetails", Dock=DockStyle.Fill,
                Orientation=Orientation.Horizontal, FixedPanel=FixedPanel.Panel2, SplitterWidth=5,
                BackColor=Color.FromArgb(215,223,236), Size=new Size(300,600) };
            _axTreeDetails.Panel1MinSize=100;
            _axTreeDetails.Panel2MinSize=90;
            _axTreeDetails.SplitterDistance=390;
            _axTreeDetails.Panel1.Controls.Add(_axOutline);
            var header = new Panel { Dock=DockStyle.Top, Height=59, Padding=new Padding(6), BackColor=Color.FromArgb(243,246,252) };
            var caption = new Label { Text="ÁRBOL DEL MODELO", Dock=DockStyle.Top, Height=20,
                ForeColor=Color.FromArgb(22,71,217), Font=new Font("Segoe UI",8,FontStyle.Bold) };
            _axFindBox = new TextBox { Name="asterMaxFindNode", Dock=DockStyle.Fill, BorderStyle=BorderStyle.FixedSingle };
            var findRow=new Panel { Dock=DockStyle.Fill };
            var findButton=new Button { Text="Buscar", Dock=DockStyle.Right, Width=58, FlatStyle=FlatStyle.Flat };
            findButton.Click += (s,e) => AxFindNext();
            _axFindBox.KeyDown += (s,e) => { if(e.KeyCode==Keys.Enter) { AxFindNext(); e.SuppressKeyPress=true; } };
            findRow.Controls.Add(_axFindBox); findRow.Controls.Add(findButton);
            header.Controls.Add(findRow); header.Controls.Add(caption);
            _axTreeDetails.Panel1.Controls.Add(header);
            _axOutline.BringToFront();
            _axDetailsCaption=new Label { Text="DETALLES", Dock=DockStyle.Top, Height=29, Padding=new Padding(7,5,0,0),
                BackColor=Color.FromArgb(236,242,253), ForeColor=Color.FromArgb(22,71,217), Font=new Font("Segoe UI",9,FontStyle.Bold) };
            _axDetailsGrid=new DataGridView { Dock=DockStyle.Fill, ReadOnly=true, AllowUserToAddRows=false,
                AllowUserToDeleteRows=false, AllowUserToResizeRows=false, RowHeadersVisible=false,
                ColumnHeadersVisible=false, BorderStyle=BorderStyle.None, BackgroundColor=Color.White,
                GridColor=Color.FromArgb(235,238,243), AutoSizeColumnsMode=DataGridViewAutoSizeColumnsMode.Fill,
                SelectionMode=DataGridViewSelectionMode.FullRowSelect, MultiSelect=false };
            _axDetailsGrid.Columns.Add("property","Propiedad"); _axDetailsGrid.Columns.Add("value","Valor");
            _axDetailsGrid.Columns[0].FillWeight=42; _axDetailsGrid.Columns[1].FillWeight=58;
            _axDetailsGrid.DefaultCellStyle.Font=new Font("Segoe UI",8.5f);
            _axDetailsGrid.DefaultCellStyle.SelectionBackColor=Color.FromArgb(231,238,252);
            _axDetailsGrid.DefaultCellStyle.SelectionForeColor=Color.FromArgb(34,42,53);
            _axEditSelection=new Button { Text="Editar objeto…", Dock=DockStyle.Bottom, Height=28, FlatStyle=FlatStyle.Flat };
            _axEditSelection.Click += (s,e) => AxEditMechanicalSelection();
            _axDetailsGrid.CellDoubleClick += (s,e) => AxEditMechanicalSelection();
            _axTreeDetails.Panel2.Controls.Add(_axDetailsGrid);
            _axTreeDetails.Panel2.Controls.Add(_axEditSelection);
            _axTreeDetails.Panel2.Controls.Add(_axDetailsCaption);
            _axDetailsGrid.BringToFront();
            Controls.Add(_axTreeDetails); _axTreeDetails.BringToFront();
            _axMeshMenu=AxCreateCommandMenu("Generar malla…",()=>AsterMaxGenerateMeshRequested?.Invoke());
            _axMeshMenu.Items.Add("Insertar control de malla…",null,(s,e)=> {
                var nodes=new List<TreeNode>();AxCollectMechanicalNodes(_axOutline.Nodes,nodes);
                var controls=nodes.Find(n=>Object.ReferenceEquals(n.Tag,_meshingParameters));
                if(controls!=null) { _axOutline.SelectedNode=controls;AxEditMechanicalSelection(); }
            });
            _axMechanicalMenu=new ContextMenuStrip(components);
            _axMechanicalMenu.Items.Add("Expandir rama",null,(s,e)=>{ if(_axOutline.SelectedNode!=null) _axOutline.SelectedNode.ExpandAll(); });
            _axMechanicalMenu.Items.Add("Contraer rama",null,(s,e)=>{ if(_axOutline.SelectedNode!=null) _axOutline.SelectedNode.Collapse(); });
        }

        private static string AxStableSourceKey(TreeNode source)
        {
            var names=new Stack<string>();
            for(var n=source;n!=null;n=n.Parent) names.Push(Uri.EscapeDataString(String.IsNullOrEmpty(n.Name)?n.Text:n.Name));
            return source.TreeView.Name+"/"+String.Join("/",names.ToArray());
        }

        private void AxMechanicalSelectionChanged()
        {
            if(_axRefreshing || _axSyncingSelection || _disableMouse) return;
            var projected=_axOutline.SelectedNode;

            if(projected==null) { AxUpdateMechanicalDetails(null); return; }
            if(_axOutline.SelectedNodes.Count==1 && projected.Name.StartsWith("ax-result/"))
                AsterMaxResultRequested?.Invoke(projected.Name.Substring("ax-result/".Length));
            else if(projected.Name=="ax-solution-info") AsterMaxResultRequested?.Invoke("__information__");
            else
            {
                var source=projected.Tag as TreeNode;
                var contact=source==null?null:source.Tag as CaeModel.ContactPair;
                if(contact!=null && _axOutline.SelectedNodes.Count==1) AsterMaxContactPairSelected?.Invoke(contact.Name);
                else { AsterMaxModelViewRequested?.Invoke(); SelectAsterMaxSource(projected); }
            }
            AxUpdateMechanicalDetails(projected);
            // Native source selection must not steal keyboard focus from the visible outline.
            ActiveControl=_axTreeDetails;
        }

        private void AxUpdateMechanicalDetails(TreeNode node)
        {
            if(_axDetailsGrid==null) return;
            _axDetailsGrid.Rows.Clear();
            int count=_axOutline.SelectedNodes.Count;
            _axDetailsCaption.Text=count>1?"DETALLES · "+count+" objetos":"DETALLES · "+(node==null?"Sin selección":node.Text);
            _axEditSelection.Enabled=count==1 && node!=null && (node.Tag is TreeNode || node.Name=="ax-analysis");
            if(node==null) return;
            if(count>1) { _axDetailsGrid.Rows.Add("Seleccionados",count); _axDetailsGrid.Rows.Add("Acciones","Clic derecho · Espacio · Supr"); return; }
            var source=node.Tag as TreeNode;
            var item=source==null?null:source.Tag as NamedClass;
            _axDetailsGrid.Rows.Add("Nombre",node.Text);
            _axDetailsGrid.Rows.Add("Tipo",item==null?"Grupo":AsterMaxFriendlyType(item.GetType().Name));
            if(item!=null)
            {
                _axDetailsGrid.Rows.Add("Estado",!item.Active?"Inactivo":item.Valid?"Configurado":"Requiere revisión");
                // Display only scalar properties. Native editors remain the validated mutation path.
                foreach(PropertyDescriptor property in TypeDescriptor.GetProperties(item))
                {
                    if(property.Name=="Name" || property.Name=="Active" || property.Name=="Valid" || !property.IsBrowsable) continue;
                    Type type=property.PropertyType;
                    if(!(type.IsPrimitive || type.IsEnum || type==typeof(string) || type==typeof(decimal))) continue;
                    try { var value=property.GetValue(item); if(value!=null) _axDetailsGrid.Rows.Add(property.DisplayName,Convert.ToString(value)); } catch { }
                    if(_axDetailsGrid.Rows.Count>=18) break;
                }
            }
            else _axDetailsGrid.Rows.Add("Elementos",node.Nodes.Count);
            if(!String.IsNullOrEmpty(node.ToolTipText)) _axDetailsGrid.Rows.Add("Información",node.ToolTipText);
        }

        private void AxEditMechanicalSelection()
        {
            if(_disableMouse || _axOutline.SelectedNodes.Count!=1) return;
            var node=_axOutline.SelectedNode;
            if(node==null) return;
            if(node.Name=="ax-analysis") { AsterMaxAnalysisTypeRequested?.Invoke(); return; }
            if(!SelectAsterMaxSource(node)) return;
            var source=node.Tag as TreeNode;
            if(source.Tag!=null) tsmiEdit_Click(null,EventArgs.Empty);
            else if(CanCreate(source)) tsmiCreate_Click(null,EventArgs.Empty);
        }

        private void AxMechanicalKeyDown(object sender,KeyEventArgs e)
        {
            if(_disableMouse) return;
            if(e.KeyCode==Keys.Enter || e.KeyCode==Keys.F2) { AxEditMechanicalSelection(); e.SuppressKeyPress=true; }
            else if(e.KeyCode==Keys.Delete || e.KeyCode==Keys.Space)
            { if(SelectAsterMaxSource(_axOutline.SelectedNode)) cltv_KeyDown(sender,e); e.SuppressKeyPress=true; }
            else if(e.Control && e.KeyCode==Keys.F) { _axFindBox.Focus(); e.SuppressKeyPress=true; }
        }

        private void AxFindNext()
        {
            string term=_axFindBox.Text.Trim(); if(term.Length==0) return;
            var all=new List<TreeNode>(); AxCollectMechanicalNodes(_axOutline.Nodes,all);
            int start=all.IndexOf(_axOutline.SelectedNode);
            for(int n=1;n<=all.Count;n++)
            {
                var node=all[(start+n+all.Count)%all.Count];
                if(node.Text.IndexOf(term,StringComparison.CurrentCultureIgnoreCase)<0) continue;
                _axOutline.SelectedNode=node; node.EnsureVisible(); _axOutline.Focus(); return;
            }
            _axDetailsCaption.Text="Sin coincidencias: "+term;
        }
        private static void AxCollectMechanicalNodes(TreeNodeCollection nodes,List<TreeNode> list)
        { foreach(TreeNode node in nodes) { list.Add(node); AxCollectMechanicalNodes(node.Nodes,list); } }

        private void AxShowMechanicalMenu(TreeNode node,Point location)
        {
            if(_disableMouse || node==null) return;
            if(!_axOutline.SelectedNodes.Contains(node)) _axOutline.SelectedNode=node;
            if(node.Name=="ax-mesh") { _axMeshMenu.Show(_axOutline,location); return; }
            if(node.Name=="ax-analysis") { _axAnalysisMenu.Show(_axOutline,location); return; }
            if(node.Name=="ax-solution") { _axSolutionMenu.Show(_axOutline,location); return; }
            if(!SelectAsterMaxSource(node)) { _axMechanicalMenu.Show(_axOutline,location); return; }
            PrepareToolStripItem(GetActiveTree());
            tsmiEditCalculiXKeywords.Visible=false; tsmiSpaceEditCalculiXKeywords.Visible=false;
            tsmiExpandAll.Visible=false; tsmiCollapseAll.Visible=false;
            cmsTree.Show(_axOutline,location);
        }

        private void AxAddMechanicalAnalysisChildren(TreeNode analysis)
        {
            var settings=AxCopy(_steps,"Configuración del análisis");
            settings.Nodes.Clear();
            analysis.Nodes.Add(settings);
            if(_steps.Nodes.Count==1)
            {
                var step=_steps.Nodes[0];
                settings.Tag=step;
                foreach(TreeNode child in step.Nodes) analysis.Nodes.Add(AxCopy(child));
            }
            else foreach(TreeNode step in _steps.Nodes) analysis.Nodes.Add(AxCopy(step));
            analysis.Nodes.Add(AxCopy(_initialConditions,"Condiciones iniciales"));
            analysis.Nodes.Add(AxCopy(_amplitudes,"Amplitudes"));
        }

        private string AxMechanicalIconKey(TreeNode node)
        {
            switch(node.Name) {
                case "ax-project": return "project"; case "ax-model": return "model";
                case "ax-coordinates": case "ax-global": return "coordinates";
                case "ax-connections": return "connections"; case "ax-mesh": return "mesh";
                case "ax-selections": return "selection"; case "ax-analysis": return "analysis";
                case "ax-solution": return "solution"; case "ax-solution-info": return "info";
            }
            if(node.Name.StartsWith("ax-result/")) return "result";
            var source=node.Tag as TreeNode;
            if(source==_geomParts) return "geometry"; if(source==_materials) return "material";
            if(source==_sections) return "assignment"; if(source==_steps) return "settings";
            if(source==_meshingParameters || source==_meshRefinements) return "mesh-control";
            if(source==_contactPairs || source==_surfaceInteractions || source==_constraints) return "contact";
            if(source!=null)
            {
                if(source.Name==_boundaryConditionsName) return "support";
                if(source.Name==_loadsName) return "load";
                string type=source.Tag==null?"":source.Tag.GetType().Name;
                if(type.Contains("Part")) return "body";
                if(type.Contains("Material")) return "material";
                if(type.Contains("Section")) return "assignment";
                if(type.Contains("Load") || type.Contains("Pressure")) return "load";
                if(type.Contains("Boundary") || type.Contains("Displacement") || type.Contains("Fixed")) return "support";
                if(type.Contains("Contact") || type.Contains("Constraint")) return "contact";
                if(type.Contains("Step")) return "settings";
                if(type.Contains("Set") || type.Contains("Surface")) return "selection";
                if(type.Contains("Mesh")) return "mesh-control";
            }
            return "folder";
        }
        private void AxApplyMechanicalIcons(TreeNodeCollection nodes)
        {
            foreach(TreeNode node in nodes)
            {
                node.ImageKey=AxMechanicalIconKey(node);node.SelectedImageKey=node.ImageKey;
                var source=node.Tag as TreeNode; var item=source==null?null:source.Tag as NamedClass;
                if(item!=null) node.StateImageKey=!item.Active?"info":item.Valid?"done":"pending";
                AxApplyMechanicalIcons(node.Nodes);
            }
        }
        private static Bitmap AxMechanicalIcon(string key)
        {
            var image=new Bitmap(40,40);
            using(var g=Graphics.FromImage(image))
            using(var blue=new Pen(Color.FromArgb(22,71,217),1.6f))
            using(var light=new SolidBrush(Color.FromArgb(217,231,255)))
            {
                g.ScaleTransform(2,2);g.SmoothingMode=SmoothingMode.AntiAlias;
                switch(key)
                {
                    case "geometry": case "body": case "model":
                        var cube=new[]{new Point(3,6),new Point(10,2),new Point(17,6),new Point(17,14),new Point(10,18),new Point(3,14)};
                        g.FillPolygon(light,cube);g.DrawPolygon(blue,cube);g.DrawLines(blue,new[]{new Point(3,6),new Point(10,10),new Point(17,6)});g.DrawLine(blue,10,10,10,18);break;
                    case "mesh": case "mesh-control":
                        g.FillRectangle(light,3,3,14,14);g.DrawRectangle(blue,3,3,14,14);
                        for(int i=3;i<=17;i+=7){g.DrawLine(blue,i,3,i,17);g.DrawLine(blue,3,i,17,i);}g.DrawLine(blue,3,3,17,17);g.DrawLine(blue,3,17,17,3);break;
                    case "material": case "assignment":
                        using(var gold=new SolidBrush(Color.FromArgb(224,171,55))){g.FillRectangle(gold,3,4,14,12);}g.DrawRectangle(blue,3,4,14,12);g.DrawLine(blue,3,8,17,8);g.DrawLine(blue,3,12,17,12);break;
                    case "coordinates":
                        g.DrawLine(Pens.Red,5,15,17,15);g.DrawLine(Pens.ForestGreen,5,15,5,2);g.DrawLine(blue,5,15,13,6);g.FillEllipse(Brushes.RoyalBlue,3,13,4,4);break;
                    case "contact": case "connections":
                        g.FillRectangle(light,2,3,7,13);g.FillRectangle(Brushes.LightCoral,11,3,7,13);g.DrawRectangle(blue,2,3,7,13);g.DrawLine(blue,10,2,10,18);break;
                    case "support":
                        g.DrawLine(blue,3,4,17,4);g.DrawPolygon(blue,new[]{new Point(10,5),new Point(4,14),new Point(16,14)});g.DrawLine(Pens.ForestGreen,2,17,18,17);for(int i=3;i<18;i+=4)g.DrawLine(Pens.ForestGreen,i,17,i-2,19);break;
                    case "load":
                        using(var red=new Pen(Color.Firebrick,2)){g.DrawLine(red,10,2,10,16);g.DrawLines(red,new[]{new Point(5,11),new Point(10,17),new Point(15,11)});}g.DrawLine(blue,2,18,18,18);break;
                    case "analysis": case "solution":
                        g.DrawEllipse(blue,2,2,16,16);g.FillPolygon(key=="solution"?Brushes.ForestGreen:Brushes.RoyalBlue,new[]{new Point(8,5),new Point(15,10),new Point(8,15)});break;
                    case "result":
                        g.FillRectangle(Brushes.RoyalBlue,3,11,4,6);g.FillRectangle(Brushes.MediumSeaGreen,8,7,4,10);g.FillRectangle(Brushes.OrangeRed,13,3,4,14);g.DrawLine(blue,2,18,18,18);break;
                    case "selection":
                        using(var dash=new Pen(Color.RoyalBlue,1.5f)){dash.DashStyle=DashStyle.Dash;g.DrawRectangle(dash,2,2,16,16);}g.FillEllipse(Brushes.RoyalBlue,8,8,4,4);break;
                    case "info":
                        g.DrawEllipse(blue,2,2,16,16);g.DrawLine(blue,10,8,10,15);g.FillEllipse(Brushes.RoyalBlue,9,4,2,2);break;
                    case "settings":
                        for(int i=5;i<=15;i+=5){g.DrawLine(blue,2,i,18,i);g.FillRectangle(Brushes.RoyalBlue,i-2,i-2,4,4);}break;
                    default:
                        g.FillRectangle(light,2,6,16,11);g.DrawRectangle(blue,2,6,16,11);g.DrawLines(blue,new[]{new Point(2,6),new Point(2,3),new Point(8,3),new Point(10,6)});break;
                }
            }
            var small=new Bitmap(image,new Size(20,20));image.Dispose();return small;
        }

        public Dictionary<string,object> AuditAsterMaxMechanicalOutline()
        {
            RefreshAsterMaxOutline();var result=new Dictionary<string,object>();
            var all=new List<TreeNode>();AxCollectMechanicalNodes(_axOutline.Nodes,all);
            var bodies=all.FindAll(n=>{var s=n.Tag as TreeNode;return s!=null && s.TreeView==cltvGeometry && s.Tag is CaeMesh.BasePart && s.Nodes.Count==0;});
            result["cad_leaf_body_count"]=bodies.Count;
            if(bodies.Count<2) {
                result["pass"]=false;result["error"]="Two CAD leaf bodies are required for the multiselection audit.";
                result["nodes"]=all.ConvertAll(n=>n.Name+" | "+n.Text+" | "+(n.Tag is TreeNode?(((TreeNode)n.Tag).Tag==null?"group":((TreeNode)n.Tag).Tag.GetType().FullName):"virtual"));
                return result;
            }
            _axOutline.SelectedNodes.Clear();_axOutline.SelectedNodes.Add(bodies[0]);_axOutline.SelectedNodes.Add(bodies[1]);
            AxMechanicalSelectionChanged();
            result["projected_multiselection"]= _axOutline.SelectedNodes.Count==2;
            result["native_multiselection"]=cltvGeometry.SelectedNodes.Count==2;
            var branch=_axOutline.Nodes.Find("ax-coordinates",true)[0];branch.Collapse();
            string first=bodies[0].Name,second=bodies[1].Name;
            _axOutlineStamp=null;RefreshAsterMaxOutline();
            result["selection_survives_refresh"]=_axOutline.SelectedNodes.Count==2 && _axOutline.SelectedNodes[0].Name==first && _axOutline.SelectedNodes[1].Name==second;
            result["collapse_survives_refresh"]=!_axOutline.Nodes.Find("ax-coordinates",true)[0].IsExpanded;
            result["object_icon_count"]=_axObjectIcons.Images.Count;
            result["context_menu_checks"]=AuditAsterMaxContextMenus();
            result["details_visible"]=_axDetailsGrid.Visible && _axDetailsGrid.Rows.Count>0;
            result["tree_visible"]=_axOutline.Visible && _axOutline.Height>100;
            result["pass"]=(bool)result["projected_multiselection"] && (bool)result["native_multiselection"] && (bool)result["selection_survives_refresh"] && (bool)result["collapse_survives_refresh"] && (bool)result["details_visible"] && (bool)result["tree_visible"];
            return result;
        }
    }
}
