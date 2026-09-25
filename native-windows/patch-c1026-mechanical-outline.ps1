param([string]$Root)
$ErrorActionPreference='Stop'

$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
$m = [regex]::Replace((Get-Content $modelTree -Raw), "\r\n?", "`n")

# Restore immutable lookup keys. Previous presentation patches translated some of these
# fields, but Nodes.Find() searches TreeNode.Name, whose designer keys remain English.
$keys = [ordered]@{
 'private string _geomPartsName = "Geometría";' = 'private string _geomPartsName = "Parts";'
 'private string _meshingParametersName = "Controles de malla";' = 'private string _meshingParametersName = "Meshing Parameters";'
 'private string _meshRefinementsName = "Controles locales de malla";' = 'private string _meshRefinementsName = "Mesh Refinements";'
 'private string _boundaryConditionsName = "Apoyos / CC";' = 'private string _boundaryConditionsName = "BCs";'
 'private string _loadsName = "Cargas";' = 'private string _loadsName = "Loads";'
 'private string _analysesName = "Solución";' = 'private string _analysesName = "Analyses";'
}
foreach($kv in $keys.GetEnumerator()){ if($m.Contains($kv.Key)){ $m=$m.Replace($kv.Key,$kv.Value) } }

# Add Details state fields.
$fieldAnchor = '        private Dictionary<CodersLabTreeView, bool[]> _prevStates;'
$fieldNew = @'
        private Dictionary<CodersLabTreeView, bool[]> _prevStates;
        private Panel _asterMaxDetailsPanel;
        private Label _asterMaxDetailsTitle;
        private Label _asterMaxDetailsType;
        private Label _asterMaxDetailsState;
        private Label _asterMaxDetailsHint;
'@
if(-not $m.Contains($fieldAnchor)){ throw 'C10.26 ModelTree field anchor missing.' }
$m=$m.Replace($fieldAnchor,$fieldNew)

# Activate presentation after the native static node references are fully resolved.
$ctorAnchor = '            _prevStates.Add(cltvResults, null);'
$ctorNew = @'
            _prevStates.Add(cltvResults, null);
            ApplyAsterMaxMechanicalOutline();
'@
if(-not $m.Contains($ctorAnchor)){ throw 'C10.26 constructor anchor missing.' }
$m=$m.Replace($ctorAnchor,$ctorNew)

# Keep Details synchronized with every normal tree selection.
$selectionAnchor = '            CodersLabTreeView tree = GetActiveTree();'
$selectionNew = @'
            CodersLabTreeView tree = GetActiveTree();
            AsterMaxUpdateDetails(tree);
'@
# Replace only first occurrence inside cltv_SelectionsChanged by finding the method first.
$methodPos=$m.IndexOf('private void cltv_SelectionsChanged')
if($methodPos -lt 0){ throw 'C10.26 selection method missing.' }
$tail=$m.Substring($methodPos)
$rel=$tail.IndexOf($selectionAnchor)
if($rel -lt 0){ throw 'C10.26 selection tree anchor missing.' }
$abs=$methodPos+$rel
$m=$m.Substring(0,$abs)+$selectionNew+$m.Substring($abs+$selectionAnchor.Length)

# Insert the Mechanical Outline presentation methods before the Geometry-Model-Results region.
$insertAnchor = '        #region Geometry-Model-Results'
$helpers = @'
        private void ApplyAsterMaxMechanicalOutline()
        {
            BackColor = Color.FromArgb(246, 247, 249);

            tcGeometryModelResults.Font = new Font("Segoe UI Semibold", 9.0f);
            tpGeometry.Text = "Geometría";
            tpModel.Text = "Modelo";
            tpResults.Text = "Resultados";
            tpGeometry.BackColor = Color.White;
            tpModel.BackColor = Color.White;
            tpResults.BackColor = Color.White;

            AsterMaxStyleTree(cltvGeometry);
            AsterMaxStyleTree(cltvModel);
            AsterMaxStyleTree(cltvResults);

            stbGeometry.Font = new Font("Segoe UI", 9.0f);
            stbModel.Font = new Font("Segoe UI", 9.0f);
            stbResults.Font = new Font("Segoe UI", 9.0f);

            // Visible labels only. TreeNode.Name and lookup fields stay untouched.
            _geomParts.Text = "Geometría";
            _meshingParameters.Text = "Controles de malla";
            _meshRefinements.Text = "Refinamientos locales";

            _model.Text = "Modelo";
            _modelMesh.Text = "Malla";
            _modelParts.Text = "Cuerpos / Partes";
            _modelNodeSets.Text = "Selecciones de nodos";
            _modelElementSets.Text = "Selecciones de elementos";
            _modelSurfaces.Text = "Superficies";
            _referencePoints.Text = "Puntos de referencia";
            _materials.Text = "Materiales";
            _sections.Text = "Secciones";
            _constraints.Text = "Conexiones / Restricciones";
            _contacts.Text = "Contactos";
            _surfaceInteractions.Text = "Interacciones";
            _contactPairs.Text = "Regiones de contacto";
            _amplitudes.Text = "Amplitudes";
            _initialConditions.Text = "Condiciones iniciales";
            _steps.Text = "Análisis estructural";
            _analyses.Text = "Solución / Ejecuciones";

            _resultMesh.Text = "Malla";
            _resultParts.Text = "Partes";
            _resultNodeSets.Text = "Selecciones de nodos";
            _resultElementSets.Text = "Selecciones de elementos";
            _resultSurfaces.Text = "Superficies";
            _results.Text = "Solución";
            _resultFieldOutputs.Text = "Resultados de campo";
            _resultHistoryOutputs.Text = "Resultados históricos";

            AsterMaxHeaderNode(_geomParts);
            AsterMaxHeaderNode(_model);
            AsterMaxHeaderNode(_modelMesh);
            AsterMaxHeaderNode(_materials);
            AsterMaxHeaderNode(_sections);
            AsterMaxHeaderNode(_constraints);
            AsterMaxHeaderNode(_contacts);
            AsterMaxHeaderNode(_steps);
            AsterMaxHeaderNode(_analyses);
            AsterMaxHeaderNode(_results);

            BuildAsterMaxDetailsPanel();

            cltvGeometry.ExpandAll();
            _model.Expand();
            _modelMesh.Expand();
            _contacts.Expand();
            _steps.Expand();
            _results.Expand();
        }

        private void AsterMaxStyleTree(CodersLabTreeView tree)
        {
            tree.BackColor = Color.White;
            tree.ForeColor = Color.FromArgb(42, 48, 56);
            tree.Font = new Font("Segoe UI", 9.1f);
            tree.BorderStyle = BorderStyle.None;
            tree.ItemHeight = 24;
            tree.Indent = 17;
            tree.FullRowSelect = true;
            tree.HideSelection = false;
            tree.HotTracking = true;
            tree.ShowLines = false;
            tree.ShowRootLines = false;
            tree.ShowPlusMinus = true;
            tree.SelectionBackColor = Color.FromArgb(218, 233, 246);
        }

        private void AsterMaxHeaderNode(TreeNode node)
        {
            if (node == null) return;
            node.NodeFont = new Font("Segoe UI Semibold", 9.1f, FontStyle.Bold);
            node.ForeColor = Color.FromArgb(40, 48, 58);
        }

        private void BuildAsterMaxDetailsPanel()
        {
            if (_asterMaxDetailsPanel != null) return;

            _asterMaxDetailsPanel = new Panel
            {
                Name = "asterMaxDetailsPanel",
                Dock = DockStyle.Bottom,
                Height = 132,
                BackColor = Color.FromArgb(248, 249, 251),
                Padding = new Padding(10, 8, 10, 8)
            };

            var header = new Label
            {
                Text = "DETAILS",
                Dock = DockStyle.Top,
                Height = 20,
                ForeColor = Color.FromArgb(94, 103, 114),
                Font = new Font("Segoe UI Semibold", 7.5f),
                TextAlign = ContentAlignment.MiddleLeft
            };

            _asterMaxDetailsTitle = new Label
            {
                Text = "Sin selección",
                Dock = DockStyle.Top,
                Height = 25,
                ForeColor = Color.FromArgb(32, 39, 48),
                Font = new Font("Segoe UI Semibold", 9.4f),
                TextAlign = ContentAlignment.MiddleLeft
            };

            _asterMaxDetailsType = new Label
            {
                Text = "Tipo: —",
                Dock = DockStyle.Top,
                Height = 19,
                ForeColor = Color.FromArgb(84, 94, 105),
                Font = new Font("Segoe UI", 8.3f),
                TextAlign = ContentAlignment.MiddleLeft
            };

            _asterMaxDetailsState = new Label
            {
                Text = "Estado: —",
                Dock = DockStyle.Top,
                Height = 19,
                ForeColor = Color.FromArgb(84, 94, 105),
                Font = new Font("Segoe UI", 8.3f),
                TextAlign = ContentAlignment.MiddleLeft
            };

            _asterMaxDetailsHint = new Label
            {
                Text = "Doble clic: editar   •   clic derecho: acciones",
                Dock = DockStyle.Bottom,
                Height = 22,
                ForeColor = Color.FromArgb(118, 126, 136),
                Font = new Font("Segoe UI", 7.8f),
                TextAlign = ContentAlignment.MiddleLeft
            };

            var accent = new Panel
            {
                Dock = DockStyle.Left,
                Width = 3,
                BackColor = Color.FromArgb(242, 181, 30)
            };

            _asterMaxDetailsPanel.Controls.Add(_asterMaxDetailsHint);
            _asterMaxDetailsPanel.Controls.Add(_asterMaxDetailsState);
            _asterMaxDetailsPanel.Controls.Add(_asterMaxDetailsType);
            _asterMaxDetailsPanel.Controls.Add(_asterMaxDetailsTitle);
            _asterMaxDetailsPanel.Controls.Add(header);
            _asterMaxDetailsPanel.Controls.Add(accent);

            Controls.Add(_asterMaxDetailsPanel);
            _asterMaxDetailsPanel.BringToFront();
        }

        private void AsterMaxUpdateDetails(CodersLabTreeView tree)
        {
            if (_asterMaxDetailsPanel == null || tree == null) return;

            if (tree.SelectedNodes == null || tree.SelectedNodes.Count == 0)
            {
                _asterMaxDetailsTitle.Text = "Sin selección";
                _asterMaxDetailsType.Text = "Tipo: —";
                _asterMaxDetailsState.Text = "Estado: —";
                return;
            }

            if (tree.SelectedNodes.Count > 1)
            {
                _asterMaxDetailsTitle.Text = tree.SelectedNodes.Count + " elementos seleccionados";
                _asterMaxDetailsType.Text = "Tipo: selección múltiple";
                _asterMaxDetailsState.Text = "Estado: listo para operaciones de conjunto";
                return;
            }

            TreeNode node = tree.SelectedNodes[0];
            _asterMaxDetailsTitle.Text = node.Text;

            NamedClass item = node.Tag as NamedClass;
            if (item == null)
            {
                _asterMaxDetailsType.Text = "Tipo: grupo / rama del proyecto";
                _asterMaxDetailsState.Text = node.Nodes.Count > 0
                    ? "Estado: " + node.Nodes.Count + " elemento(s)"
                    : "Estado: sin elementos";
            }
            else
            {
                _asterMaxDetailsType.Text = "Tipo: " + AsterMaxFriendlyType(item.GetType().Name);
                string state = "configurado";
                try
                {
                    if (!item.Active) state = "inactivo";
                    else if (!item.Valid) state = "requiere revisión";
                }
                catch { }
                _asterMaxDetailsState.Text = "Estado: " + state;
            }
        }

        private string AsterMaxFriendlyType(string typeName)
        {
            if (String.IsNullOrEmpty(typeName)) return "objeto";
            if (typeName.IndexOf("Material", StringComparison.OrdinalIgnoreCase) >= 0) return "material";
            if (typeName.IndexOf("Section", StringComparison.OrdinalIgnoreCase) >= 0) return "sección";
            if (typeName.IndexOf("Contact", StringComparison.OrdinalIgnoreCase) >= 0) return "contacto";
            if (typeName.IndexOf("Boundary", StringComparison.OrdinalIgnoreCase) >= 0) return "apoyo / condición de borde";
            if (typeName.IndexOf("Load", StringComparison.OrdinalIgnoreCase) >= 0) return "carga";
            if (typeName.IndexOf("Step", StringComparison.OrdinalIgnoreCase) >= 0) return "paso de análisis";
            if (typeName.IndexOf("Analysis", StringComparison.OrdinalIgnoreCase) >= 0) return "análisis";
            if (typeName.IndexOf("Part", StringComparison.OrdinalIgnoreCase) >= 0) return "cuerpo / parte";
            if (typeName.IndexOf("Mesh", StringComparison.OrdinalIgnoreCase) >= 0) return "malla";
            if (typeName.IndexOf("Field", StringComparison.OrdinalIgnoreCase) >= 0) return "resultado";
            return typeName.Replace("_", " ");
        }

'@
if(-not $m.Contains($insertAnchor)){ throw 'C10.26 helper insertion anchor missing.' }
$m=$m.Replace($insertAnchor,$helpers+$insertAnchor)

Set-Content $modelTree $m -Encoding UTF8
Write-Host 'C10.26: Mechanical Outline + Details workspace applied.' -ForegroundColor Green
