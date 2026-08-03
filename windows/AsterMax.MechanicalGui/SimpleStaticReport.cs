using System.Net;

namespace AsterMax.MechanicalGui;

internal static class SimpleCalculationReport
{
    public static void Write(
        string htmlPath,
        SimpleStepSolid solid,
        TetMesh mesh,
        StaticMaterial material,
        SimpleStaticSetup setup,
        StaticSolution solution)
    {
        var title = Path.GetFileNameWithoutExtension(solid.SourcePath);
        var csvPath = Path.ChangeExtension(htmlPath, ".csv");
        var jsonPath = Path.ChangeExtension(htmlPath, ".json");
        File.WriteAllText(csvPath, BuildCsv(mesh, solution), new UTF8Encoding(false));
        File.WriteAllText(jsonPath, JsonSerializer.Serialize(new
        {
            schema = "astermax.simple-static.v1",
            generated = DateTimeOffset.Now,
            geometry = new
            {
                solid.SourcePath,
                solid.Min,
                solid.Max,
                solid.LengthX,
                solid.LengthY,
                solid.LengthZ,
                solid.Volume,
                solid.FidelityMessage
            },
            material,
            setup,
            mesh = new
            {
                nodes = mesh.Nodes.Count,
                elements = mesh.Elements.Count,
                mesh.DivisionsX,
                mesh.DivisionsY,
                mesh.DivisionsZ
            },
            results = new
            {
                solution.MaxDisplacementMm,
                solution.LoadedFaceAverageDisplacementMm,
                solution.MaxVonMisesMpa,
                solution.ReactionN,
                solution.AppliedForceN,
                solution.EquilibriumError,
                solution.BeamTheoryDisplacementMm,
                solution.BeamTheoryStressMpa
            }
        }, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));

        var safetyFactor = solution.MaxVonMisesMpa > 0
            ? material.YieldStrengthMpa / solution.MaxVonMisesMpa
            : double.PositiveInfinity;
        var equilibriumClass = solution.EquilibriumError < 1e-6 ? "ok" : "warnText";
        var html = new StringBuilder();
        html.AppendLine("<!doctype html>");
        html.AppendLine("<html lang=\"es\"><head><meta charset=\"utf-8\">");
        html.AppendLine($"<title>Memoria preliminar - {H(title)}</title>");
        html.AppendLine("<style>");
        html.AppendLine("body{font-family:Segoe UI,Arial,sans-serif;margin:38px;color:#23303d;line-height:1.45}");
        html.AppendLine("h1,h2{color:#075f9f} table{border-collapse:collapse;width:100%;margin:12px 0 24px}");
        html.AppendLine("th,td{border:1px solid #bcc8d4;padding:8px;text-align:left} th{background:#eaf2f8}");
        html.AppendLine(".notice{padding:12px;background:#fff3cd;border-left:5px solid #d99800}.ok{color:#147a42;font-weight:600}.warnText{color:#a65b00;font-weight:600}");
        html.AppendLine("code{background:#f2f5f8;padding:2px 4px}");
        html.AppendLine("</style></head><body>");
        html.AppendLine($"<h1>Memoria de cálculo preliminar — {H(title)}</h1>");
        html.AppendLine($"<p><b>Software:</b> AsterMax Mechanical 0.5 beta · <b>Fecha:</b> {DateTime.Now:yyyy-MM-dd HH:mm}</p>");
        html.AppendLine("<div class=\"notice\"><b>Alcance:</b> cálculo educativo y preliminar de un único prisma rectangular, material elástico lineal, pequeñas deformaciones y elementos tetraédricos TET4. La geometría STEP se representa mediante su envolvente rectangular. No reemplaza revisión de un ingeniero competente ni verificación reglamentaria.</div>");

        html.AppendLine("<h2>1. Modelo geométrico</h2><table>");
        Row(html, "Archivo", H(solid.SourcePath));
        Row(html, "Dimensiones X × Y × Z", $"{solid.LengthX:0.###} × {solid.LengthY:0.###} × {solid.LengthZ:0.###} mm");
        Row(html, "Volumen representado", $"{solid.Volume:0.###} mm³");
        Row(html, "Fidelidad", H(solid.FidelityMessage));
        html.AppendLine("</table>");

        html.AppendLine("<h2>2. Material</h2><table>");
        Row(html, "Nombre", H(material.Name));
        Row(html, "Módulo de Young", $"{material.YoungModulusMpa:0.###} MPa");
        Row(html, "Coeficiente de Poisson", material.PoissonRatio.ToString("0.####", CultureInfo.InvariantCulture));
        Row(html, "Límite elástico de referencia", $"{material.YieldStrengthMpa:0.###} MPa");
        html.AppendLine("</table>");

        html.AppendLine("<h2>3. Discretización y condiciones de borde</h2><table>");
        Row(html, "Malla", $"{mesh.Nodes.Count} nodos · {mesh.Elements.Count} TET4 · divisiones {mesh.DivisionsX} × {mesh.DivisionsY} × {mesh.DivisionsZ}");
        Row(html, "Apoyo fijo", setup.FixedFace.ToString());
        Row(html, "Cara cargada", setup.LoadFace.ToString());
        Row(html, "Fuerza total", $"{setup.ForceN} N");
        html.AppendLine("</table>");

        html.AppendLine("<h2>4. Método</h2>");
        html.AppendLine("<p>Se resuelve <code>[K]{u}={F}</code> con elasticidad isotrópica tridimensional. Cada tetraedro utiliza interpolación lineal y deformación constante. La fuerza total se distribuye entre los nodos de la cara cargada y los tres grados de libertad de la cara fija se anulan.</p>");

        html.AppendLine("<h2>5. Resultados</h2><table>");
        Row(html, "Desplazamiento máximo", $"{solution.MaxDisplacementMm:0.######} mm");
        Row(html, "Desplazamiento medio de la cara cargada", $"{solution.LoadedFaceAverageDisplacementMm} mm");
        Row(html, "von Mises máximo", $"{solution.MaxVonMisesMpa:0.######} MPa");
        Row(html, "Factor de seguridad simple", double.IsFinite(safetyFactor) ? safetyFactor.ToString("0.###", CultureInfo.InvariantCulture) : "No aplicable");
        Row(html, "Reacción total", $"{solution.ReactionN} N");
        html.AppendLine($"<tr><th>Error relativo de equilibrio</th><td class=\"{equilibriumClass}\">{solution.EquilibriumError:E3}</td></tr>");
        Row(html, "Tiempo de solución", $"{solution.Elapsed.TotalSeconds:0.###} s");
        html.AppendLine("</table>");

        html.AppendLine("<h2>6. Comparación analítica</h2><table>");
        Row(html, "Flecha de viga", Format(solution.BeamTheoryDisplacementMm, "mm"));
        Row(html, "Tensión de flexión", Format(solution.BeamTheoryStressMpa, "MPa"));
        html.AppendLine("</table>");

        html.AppendLine("<h2>7. Archivos anexos</h2>");
        html.AppendLine($"<p>Datos nodales y tensiones: <b>{H(Path.GetFileName(csvPath))}</b><br>Modelo y resultados JSON: <b>{H(Path.GetFileName(jsonPath))}</b></p>");
        html.AppendLine("<h2>8. Limitaciones obligatorias</h2>");
        html.AppendLine("<ul><li>Solo un prisma rectangular sin perforaciones, redondeos, superficies curvas ni ensamblajes.</li>");
        html.AppendLine("<li>Malla estructurada TET4 de primer orden; se requiere estudio de convergencia para uso ingenieril.</li>");
        html.AppendLine("<li>Sin plasticidad, contacto, pandeo, grandes deformaciones, fatiga ni dinámica.</li>");
        html.AppendLine("<li>Las tensiones cercanas al empotramiento pueden depender fuertemente de la malla.</li></ul>");
        html.AppendLine("</body></html>");
        File.WriteAllText(htmlPath, html.ToString(), new UTF8Encoding(false));
    }

    private static void Row(StringBuilder html, string label, string value) =>
        html.AppendLine($"<tr><th>{H(label)}</th><td>{value}</td></tr>");

    private static string BuildCsv(TetMesh mesh, StaticSolution solution)
    {
        var csv = new StringBuilder("type,id,x_mm,y_mm,z_mm,ux_mm,uy_mm,uz_mm,value_mpa\n");
        for (var index = 0; index < mesh.Nodes.Count; index++)
        {
            var point = mesh.Nodes[index];
            csv.AppendLine(FormattableString.Invariant(
                $"node,{index + 1},{point.X},{point.Y},{point.Z},{solution.Displacements[index * 3]},{solution.Displacements[index * 3 + 1]},{solution.Displacements[index * 3 + 2]},"));
        }
        for (var index = 0; index < mesh.Elements.Count; index++)
            csv.AppendLine(FormattableString.Invariant($"element,{index + 1},,,,,,,{solution.ElementVonMisesMpa[index]}"));
        return csv.ToString();
    }

    private static string H(string value) => WebUtility.HtmlEncode(value);
    private static string Format(double? value, string unit) =>
        value.HasValue ? $"{value.Value:0.######} {unit}" : "No aplicable";
}

internal sealed class SimpleStaticSetupDialog : Form
{
    private readonly NumericUpDown _young = Number(1, 1_000_000, 200000, 0);
    private readonly NumericUpDown _poisson = Number(-0.9m, 0.49m, 0.30m, 3);
    private readonly NumericUpDown _yield = Number(1, 10000, 250, 1);
    private readonly NumericUpDown _size = Number(0.1m, 100000, 25, 2);
    private readonly ComboBox _fixed = Faces();
    private readonly ComboBox _loaded = Faces();
    private readonly NumericUpDown _forceX = Number(-10_000_000, 10_000_000, 0, 2);
    private readonly NumericUpDown _forceY = Number(-10_000_000, 10_000_000, 0, 2);
    private readonly NumericUpDown _forceZ = Number(-10_000_000, 10_000_000, -1000, 2);

    public SimpleStaticSetupDialog(StaticMaterial material, SimpleStaticSetup setup)
    {
        Text = "Tutorial 01 — Linear Static Setup";
        StartPosition = FormStartPosition.CenterParent;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        ClientSize = new Size(500, 430);
        Font = new Font("Segoe UI", 9.2f);

        var table = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 9,
            Padding = new Padding(16, 14, 16, 58)
        };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 52));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 48));
        for (var index = 0; index < 9; index++) table.RowStyles.Add(new RowStyle(SizeType.Percent, 100f / 9f));
        Controls.Add(table);

        Add(table, 0, "Young modulus [MPa]", _young);
        Add(table, 1, "Poisson ratio", _poisson);
        Add(table, 2, "Yield strength [MPa]", _yield);
        Add(table, 3, "Target element size [mm]", _size);
        Add(table, 4, "Fixed face", _fixed);
        Add(table, 5, "Loaded face", _loaded);
        Add(table, 6, "Force X [N]", _forceX);
        Add(table, 7, "Force Y [N]", _forceY);
        Add(table, 8, "Force Z [N]", _forceZ);

        var buttons = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            Height = 50,
            FlowDirection = FlowDirection.RightToLeft,
            Padding = new Padding(8)
        };
        var accept = new Button { Text = "Accept", DialogResult = DialogResult.OK, Width = 100 };
        var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Width = 100 };
        buttons.Controls.Add(accept);
        buttons.Controls.Add(cancel);
        Controls.Add(buttons);
        AcceptButton = accept;
        CancelButton = cancel;

        _young.Value = Clamp(material.YoungModulusMpa, _young);
        _poisson.Value = Clamp(material.PoissonRatio, _poisson);
        _yield.Value = Clamp(material.YieldStrengthMpa, _yield);
        _size.Value = Clamp(setup.ElementSizeMm, _size);
        _fixed.SelectedItem = setup.FixedFace.ToString();
        _loaded.SelectedItem = setup.LoadFace.ToString();
        _forceX.Value = Clamp(setup.ForceN.X, _forceX);
        _forceY.Value = Clamp(setup.ForceN.Y, _forceY);
        _forceZ.Value = Clamp(setup.ForceN.Z, _forceZ);
    }

    public void Apply(StaticMaterial material, SimpleStaticSetup setup)
    {
        material.YoungModulusMpa = (double)_young.Value;
        material.PoissonRatio = (double)_poisson.Value;
        material.YieldStrengthMpa = (double)_yield.Value;
        setup.ElementSizeMm = (double)_size.Value;
        setup.FixedFace = Enum.Parse<SimpleFace>(_fixed.SelectedItem?.ToString() ?? nameof(SimpleFace.XMin));
        setup.LoadFace = Enum.Parse<SimpleFace>(_loaded.SelectedItem?.ToString() ?? nameof(SimpleFace.XMax));
        setup.ForceN = new Vec3((double)_forceX.Value, (double)_forceY.Value, (double)_forceZ.Value);
    }

    private static NumericUpDown Number(decimal minimum, decimal maximum, decimal value, int decimals) => new()
    {
        Minimum = minimum,
        Maximum = maximum,
        Value = value,
        DecimalPlaces = decimals,
        ThousandsSeparator = true,
        Dock = DockStyle.Fill
    };

    private static ComboBox Faces()
    {
        var combo = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill };
        combo.Items.AddRange(Enum.GetNames<SimpleFace>());
        return combo;
    }

    private static void Add(TableLayoutPanel table, int row, string label, Control control)
    {
        table.Controls.Add(new Label
        {
            Text = label,
            Dock = DockStyle.Fill,
            TextAlign = ContentAlignment.MiddleLeft
        }, 0, row);
        table.Controls.Add(control, 1, row);
    }

    private static decimal Clamp(double value, NumericUpDown control) =>
        Math.Clamp((decimal)value, control.Minimum, control.Maximum);
}
