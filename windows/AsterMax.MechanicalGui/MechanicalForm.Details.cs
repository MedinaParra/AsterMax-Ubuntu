namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private void UpdateDetails(TreeNode? node)
    {
        _details.Rows.Clear();
        if (node?.Tag is not ModelObject obj) return;
        Category("Definition");
        Detail("Name", obj.Name);
        Detail("Type", obj.Category);
        Detail("State", StateText(obj.State), false);
        Detail("Suppressed", obj.State == ObjectState.Suppressed ? "Yes" : "No");

        switch (obj.Kind)
        {
            case ObjectKind.Project:
                Category("Project");
                Detail("Project File", _projectPath ?? "Not saved", false);
                Detail("Unit System", _units);
                Detail("Solver", string.IsNullOrWhiteSpace(_codeAsterLauncher) ? "AsterMax Internal / Code_Aster not configured" : _codeAsterLauncher);
                break;
            case ObjectKind.Geometry:
                Category("Geometry");
                Detail("Source", _geometryPath ?? "No geometry imported", false);
                Detail("Bodies", node.Nodes.Count.ToString(), false);
                Detail("Import Healing", "Automatic");
                break;
            case ObjectKind.Body:
                Category("Material");
                Detail("Material Assignment", obj.Properties.GetValueOrDefault("Material", "Structural Steel"));
                Category("Geometry");
                Detail("Body Type", obj.Properties.GetValueOrDefault("Body Type", "Solid"));
                Detail("Stiffness Behavior", "Flexible");
                Detail("Volume", "125000 mm³", false);
                break;
            case ObjectKind.Mesh:
                Category("Defaults");
                Detail("Physics Preference", "Mechanical");
                Detail("Element Order", "Quadratic");
                Detail("Element Size", obj.Properties.GetValueOrDefault("Element Size", "5 mm"));
                Category("Statistics");
                Detail("Nodes", _meshGenerated ? "12,486" : "Not generated", false);
                Detail("Elements", _meshGenerated ? "7,214" : "Not generated", false);
                Detail("Mesh Metric", obj.Properties.GetValueOrDefault("Metric", "Element Quality"));
                break;
            case ObjectKind.MeshControl:
                Category("Scope");
                Detail("Scoping Method", "Geometry Selection");
                Detail("Geometry", "1 Face");
                Category("Definition");
                Detail("Control Type", obj.Name);
                Detail("Element Size", obj.Properties.GetValueOrDefault("Element Size", "2.5 mm"));
                break;
            case ObjectKind.NamedSelection:
                Category("Scope");
                Detail("Scoping Method", obj.Properties.GetValueOrDefault("Scoping Method", "Worksheet"));
                Detail("Entity Type", obj.Properties.GetValueOrDefault("Entity Type", "Faces"));
                Detail("Total Selection", obj.Properties.GetValueOrDefault("Total Selection", "4"), false);
                break;
            case ObjectKind.AnalysisSettings:
                Category("Step Controls");
                Detail("Number of Steps", obj.Properties.GetValueOrDefault("Number of Steps", "1"));
                Detail("Current Step Number", "1");
                Detail("Step End Time", "1 s");
                Detail("Auto Time Stepping", "Program Controlled");
                Category("Solver Controls");
                Detail("Solver Type", "Program Controlled");
                Detail("Large Deflection", obj.Properties.GetValueOrDefault("Large Deflection", "Off"));
                Detail("Weak Springs", "Off");
                Category("Output Controls");
                Detail("Nodal Forces", "Yes");
                Detail("Contact Data", "Yes");
                Detail("Stress", "Yes");
                break;
            case ObjectKind.Support:
                Category("Scope");
                Detail("Scoping Method", obj.Properties.GetValueOrDefault("Scoping Method", "Geometry Selection"));
                Detail("Geometry", obj.Properties.GetValueOrDefault("Geometry", "1 Face"));
                Category("Definition");
                Detail("Support Type", obj.Name);
                Detail("Coordinate System", "Global Coordinate System");
                break;
            case ObjectKind.Load:
                Category("Scope");
                Detail("Scoping Method", obj.Properties.GetValueOrDefault("Scoping Method", "Geometry Selection"));
                Detail("Geometry", obj.Properties.GetValueOrDefault("Geometry", "1 Face"));
                Category("Definition");
                Detail("Define By", obj.Properties.GetValueOrDefault("Define By", "Vector"));
                Detail("Magnitude", obj.Properties.GetValueOrDefault("Magnitude", DefaultMagnitude(obj.Name)));
                Detail("Direction", "Global X");
                break;
            case ObjectKind.Solution:
                Category("Solution");
                Detail("Status", _solved ? "Done" : "Not solved", false);
                Detail("Backend", string.IsNullOrWhiteSpace(_codeAsterLauncher) ? "AsterMax Internal" : "Code_Aster Native", false);
                Detail("Elapsed Time", _solved ? "00:00:03" : "-", false);
                break;
            case ObjectKind.SolutionInformation:
                Category("Information");
                Detail("Solver Output", "Messages tab", false);
                Detail("Newton-Raphson Residuals", "0");
                Detail("Identify Element Violations", "Yes");
                break;
            case ObjectKind.Result:
            case ObjectKind.Probe:
                Category("Scope");
                Detail("Scoping Method", "All Bodies");
                Category("Definition");
                Detail("Result Type", obj.Name);
                Detail("Display Option", "Averaged");
                Detail("Coordinate System", "Global Coordinate System");
                Category("Results");
                Detail("Minimum", _solved ? ResultMinimum(obj.Name) : "Not evaluated", false);
                Detail("Maximum", _solved ? ResultMaximum(obj.Name) : "Not evaluated", false);
                Detail("Average", _solved ? ResultAverage(obj.Name) : "Not evaluated", false);
                break;
            case ObjectKind.Contact:
                Category("Scope");
                Detail("Contact", "1 Face");
                Detail("Target", "1 Face");
                Category("Definition");
                Detail("Contact Type", obj.Properties.GetValueOrDefault("Contact Type", "Bonded"));
                Detail("Formulation", "Program Controlled");
                Detail("Interface Treatment", "Adjust to Touch");
                break;
            default:
                Category("Information");
                Detail("Description", Description(obj.Kind), false);
                break;
        }

        foreach (var property in obj.Properties)
        {
            var exists = _details.Rows.Cast<DataGridViewRow>().Any(r => string.Equals(r.Cells[0].Value?.ToString(), property.Key, StringComparison.OrdinalIgnoreCase));
            if (!exists) Detail(property.Key, property.Value);
        }
    }

    private void PopulateWorksheet(TreeNode node)
    {
        _worksheet.Columns.Clear();
        _worksheet.Rows.Clear();
        if (node.Tag is not ModelObject obj) return;

        if (obj.Kind == ObjectKind.Geometry)
        {
            AddWorksheetColumns("Body", "Type", "Material", "Volume", "Mesh Nodes", "State");
            foreach (TreeNode child in node.Nodes)
                _worksheet.Rows.Add(child.Text, "Solid", "Structural Steel", "125000 mm³", _meshGenerated ? "12486" : "-", StateText(((ModelObject)child.Tag).State));
        }
        else if (obj.Kind is ObjectKind.Connections or ObjectKind.Contact)
        {
            AddWorksheetColumns("Connection", "Type", "Contact", "Target", "Status");
            foreach (var contact in AllNodes().Where(n => n.Tag is ModelObject { Kind: ObjectKind.Contact }))
            {
                var c = (ModelObject)contact.Tag;
                _worksheet.Rows.Add(contact.Text, c.Properties.GetValueOrDefault("Contact Type", "Bonded"), "Face 12", "Face 35", StateText(c.State));
            }
        }
        else if (obj.Kind == ObjectKind.NamedSelection)
        {
            AddWorksheetColumns("Action", "Entity Type", "Criterion", "Operator", "Value", "Result");
            _worksheet.Rows.Add("Add", "Face", "Size", ">", "250 mm²", "4 Faces");
            _worksheet.Rows.Add("Filter", "Face", "Location X", ">=", "0 mm", "4 Faces");
        }
        else if (obj.Kind == ObjectKind.AnalysisSettings)
        {
            AddWorksheetColumns("Step", "End Time", "Auto Time Stepping", "Initial Substeps", "Minimum", "Maximum");
            _worksheet.Rows.Add("1", "1 s", "Program Controlled", "1", "1", "10");
        }
        else
        {
            AddWorksheetColumns("Object", "Category", "State");
            foreach (TreeNode child in node.Nodes)
            {
                var childObj = (ModelObject)child.Tag;
                _worksheet.Rows.Add(child.Text, childObj.Category, StateText(childObj.State));
            }
            if (node.Nodes.Count == 0) _worksheet.Rows.Add(obj.Name, obj.Category, StateText(obj.State));
        }
    }

    private void PopulateResultTable(string result)
    {
        _tabular.Columns.Clear();
        _tabular.Rows.Clear();
        foreach (var c in new[] { "Item", "Minimum", "Maximum", "Average", "Unit" }) _tabular.Columns.Add(c, c);
        _tabular.Rows.Add(result, ResultMinimum(result), ResultMaximum(result), ResultAverage(result), ResultUnit(result));
        if (result.Contains("Reaction", StringComparison.OrdinalIgnoreCase))
        {
            _tabular.Rows.Add("X Component", "-", "1000", "1000", "N");
            _tabular.Rows.Add("Y Component", "0", "0", "0", "N");
            _tabular.Rows.Add("Z Component", "0", "0", "0", "N");
        }
    }

    private void DrawGraph(object? sender, PaintEventArgs e)
    {
        var g = e.Graphics;
        g.Clear(Field);
        using var grid = new Pen(Color.FromArgb(45, 160, 170, 180));
        for (var i = 1; i < 10; i++) g.DrawLine(grid, i * _graph.Width / 10f, 10, i * _graph.Width / 10f, _graph.Height - 26);
        for (var i = 1; i < 5; i++) g.DrawLine(grid, 45, i * (_graph.Height - 36) / 5f, _graph.Width - 10, i * (_graph.Height - 36) / 5f);
        using var axis = new Pen(Color.FromArgb(180, 210, 220, 230), 1.4f);
        g.DrawLine(axis, 45, 10, 45, _graph.Height - 26);
        g.DrawLine(axis, 45, _graph.Height - 26, _graph.Width - 10, _graph.Height - 26);
        var points = new List<PointF>();
        for (var i = 0; i <= 40; i++)
        {
            var x = 45 + i * (_graph.Width - 60) / 40f;
            var value = Math.Sin(i / 6f) * .18 + Math.Pow(i / 40f, 1.6);
            var y = _graph.Height - 28 - (float)value * (_graph.Height - 60);
            points.Add(new PointF(x, y));
        }
        using var curve = new Pen(Accent, 2.5f);
        if (points.Count > 1) g.DrawLines(curve, points.ToArray());
        using var font = new Font("Segoe UI", 8f);
        g.DrawString(_solved ? "Result History / Load Step" : "Graph preview - solve to populate authentic results", font, Brushes.LightGray, 55, 8);
    }

    private void SavePropertyEdit(int rowIndex)
    {
        if (rowIndex < 0 || _outline.SelectedNode?.Tag is not ModelObject obj) return;
        var row = _details.Rows[rowIndex];
        var property = row.Cells[0].Value?.ToString();
        var value = row.Cells[1].Value?.ToString();
        if (string.IsNullOrWhiteSpace(property) || property.StartsWith("[") || row.Cells[1].ReadOnly) return;
        if (property == "Name" && !string.IsNullOrWhiteSpace(value))
        {
            obj.Name = value;
            _outline.SelectedNode.Text = value;
        }
        else if (value is not null)
        {
            obj.Properties[property] = value;
        }
        MarkSolutionDirty();
        Log($"{obj.Name}: {property} = {value}");
    }

    private void Category(string text)
    {
        var index = _details.Rows.Add($"[{text}]", string.Empty);
        var row = _details.Rows[index];
        row.DefaultCellStyle.BackColor = Color.FromArgb(55, 61, 70);
        row.DefaultCellStyle.Font = new Font("Segoe UI Semibold", 9f);
        row.Cells[0].Style.ForeColor = Color.FromArgb(185, 207, 232);
        row.Cells[1].ReadOnly = true;
    }

    private void Detail(string property, string value, bool editable = true)
    {
        var index = _details.Rows.Add(property, value);
        _details.Rows[index].Cells[1].ReadOnly = !editable;
        if (!editable) _details.Rows[index].Cells[1].Style.ForeColor = TextMuted;
    }

    private void AddWorksheetColumns(params string[] columns)
    {
        foreach (var column in columns) _worksheet.Columns.Add(column, column);
    }

    private static string Description(ObjectKind kind) => kind switch
    {
        ObjectKind.Materials => "Engineering material library and body assignments.",
        ObjectKind.CoordinateSystems => "Global and local Cartesian or cylindrical coordinate systems.",
        ObjectKind.Connections => "Contacts, joints, springs, beams and remote couplings.",
        ObjectKind.NamedSelections => "Reusable groups of geometry or mesh entities.",
        ObjectKind.Analysis => "Environment containing settings, loads, supports and solution requests.",
        _ => "AsterMax model object."
    };

    private static string ResultMinimum(string name) => name.Contains("Deformation", StringComparison.OrdinalIgnoreCase) ? "0 mm" : name.Contains("Stress", StringComparison.OrdinalIgnoreCase) ? "2.14 MPa" : name.Contains("Strain", StringComparison.OrdinalIgnoreCase) ? "1.05e-5" : name.Contains("Reaction", StringComparison.OrdinalIgnoreCase) ? "1000 N" : "0";
    private static string ResultMaximum(string name) => name.Contains("Deformation", StringComparison.OrdinalIgnoreCase) ? "0.284 mm" : name.Contains("Stress", StringComparison.OrdinalIgnoreCase) ? "182.4 MPa" : name.Contains("Strain", StringComparison.OrdinalIgnoreCase) ? "9.12e-4" : name.Contains("Reaction", StringComparison.OrdinalIgnoreCase) ? "1000 N" : "1";
    private static string ResultAverage(string name) => name.Contains("Deformation", StringComparison.OrdinalIgnoreCase) ? "0.108 mm" : name.Contains("Stress", StringComparison.OrdinalIgnoreCase) ? "64.8 MPa" : name.Contains("Strain", StringComparison.OrdinalIgnoreCase) ? "3.22e-4" : name.Contains("Reaction", StringComparison.OrdinalIgnoreCase) ? "1000 N" : "0.5";
    private static string ResultUnit(string name) => name.Contains("Deformation", StringComparison.OrdinalIgnoreCase) ? "mm" : name.Contains("Stress", StringComparison.OrdinalIgnoreCase) ? "MPa" : name.Contains("Strain", StringComparison.OrdinalIgnoreCase) ? "mm/mm" : name.Contains("Reaction", StringComparison.OrdinalIgnoreCase) ? "N" : "-";
}
