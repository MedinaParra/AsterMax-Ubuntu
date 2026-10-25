using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;

namespace AsterMax.WindowsNative;

internal static class ProgramV2
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainFormV2());
    }
}

internal sealed class MainFormV2 : Form
{
    private readonly TextBox _launcher = new();
    private readonly TextBox _export = new();
    private readonly RichTextBox _log = new();
    private readonly Label _status = new();
    private readonly Label _version = new();
    private readonly Label _messageSummary = new();
    private readonly Button _detect = new();
    private readonly Button _diagnose = new();
    private readonly Button _validate = new();
    private readonly Button _run = new();
    private readonly Button _cancel = new();
    private readonly ProgressBar _progress = new();
    private readonly AppSettings _settings;
    private CancellationTokenSource? _cancellation;
    private string? _lastWorkspace;

    private static readonly Color Bg = Color.FromArgb(22, 25, 30);
    private static readonly Color Card = Color.FromArgb(34, 39, 47);
    private static readonly Color Input = Color.FromArgb(17, 20, 25);
    private static readonly Color TextColor = Color.FromArgb(236, 239, 244);
    private static readonly Color Muted = Color.FromArgb(159, 168, 182);
    private static readonly Color Blue = Color.FromArgb(51, 142, 255);
    private static readonly Color Green = Color.FromArgb(63, 196, 126);
    private static readonly Color Amber = Color.FromArgb(255, 184, 77);
    private static readonly Color Red = Color.FromArgb(235, 92, 92);

    public MainFormV2()
    {
        _settings = AppSettings.Load();
        Text = "AsterMax Windows Native 0.2 — Code_Aster Validation";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(980, 720);
        Size = new Size(1160, 820);
        BackColor = Bg;
        ForeColor = TextColor;
        Font = new Font("Segoe UI", 10F);
        AllowDrop = true;

        BuildUi();
        Load += async (_, _) => await InitializeAsync();
        FormClosing += (_, _) => Save();
        DragEnter += OnDragEnter;
        DragDrop += OnDragDrop;
    }

    private void BuildUi()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 5,
            Padding = new Padding(24),
            BackColor = Bg
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 86));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 148));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 106));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 58));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        Controls.Add(root);

        var header = new Panel { Dock = DockStyle.Fill, BackColor = Bg };
        header.Controls.Add(new Label
        {
            Text = "ASTERMAX  WINDOWS NATIVE",
            AutoSize = true,
            Location = new Point(0, 2),
            Font = new Font("Segoe UI Semibold", 22F, FontStyle.Bold),
            ForeColor = TextColor
        });
        header.Controls.Add(new Label
        {
            Text = "Iteración 0.2 · detección, smoke test real, lectura de .mess y ejecución de .export",
            AutoSize = true,
            Location = new Point(2, 48),
            Font = new Font("Segoe UI", 10.5F),
            ForeColor = Muted
        });
        root.Controls.Add(header, 0, 0);

        var paths = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 4,
            RowCount = 3,
            Padding = new Padding(16, 12, 16, 12),
            BackColor = Card
        };
        paths.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 148));
        paths.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        paths.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 112));
        paths.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 112));
        paths.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        paths.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        paths.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        root.Controls.Add(paths, 0, 1);

        paths.Controls.Add(MakeLabel("Code_Aster:"), 0, 0);
        ConfigureTextBox(_launcher);
        paths.Controls.Add(_launcher, 1, 0);
        paths.Controls.Add(MakeButton("Examinar", (_, _) => BrowseLauncher()), 2, 0);
        _detect.Text = "Detectar";
        ConfigureButton(_detect);
        _detect.Click += async (_, _) => await DetectAsync(true);
        paths.Controls.Add(_detect, 3, 0);

        paths.Controls.Add(MakeLabel("Trabajo .export:"), 0, 1);
        ConfigureTextBox(_export);
        paths.Controls.Add(_export, 1, 1);
        paths.SetColumnSpan(_export, 2);
        paths.Controls.Add(MakeButton("Examinar", (_, _) => BrowseExport()), 3, 1);

        paths.Controls.Add(MakeLabel("Estado:"), 0, 2);
        _status.Text = "Pendiente de diagnóstico";
        _status.Dock = DockStyle.Fill;
        _status.TextAlign = ContentAlignment.MiddleLeft;
        _status.ForeColor = Amber;
        _status.AutoEllipsis = true;
        paths.Controls.Add(_status, 1, 2);
        paths.SetColumnSpan(_status, 3);

        var summary = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 3,
            RowCount = 2,
            Padding = new Padding(16, 12, 16, 12),
            BackColor = Card
        };
        summary.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33F));
        summary.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33F));
        summary.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.34F));
        summary.RowStyles.Add(new RowStyle(SizeType.Absolute, 26));
        summary.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.Controls.Add(summary, 0, 2);

        summary.Controls.Add(MakeCaption("VERSIÓN DETECTADA"), 0, 0);
        summary.Controls.Add(MakeCaption("ÚLTIMA VALIDACIÓN"), 1, 0);
        summary.Controls.Add(MakeCaption("ARCHIVO DE MENSAJES"), 2, 0);

        _version.Text = "No identificada";
        _version.ForeColor = TextColor;
        _version.Dock = DockStyle.Fill;
        _version.TextAlign = ContentAlignment.MiddleLeft;
        summary.Controls.Add(_version, 0, 1);

        _messageSummary.Text = "No ejecutada";
        _messageSummary.ForeColor = Muted;
        _messageSummary.Dock = DockStyle.Fill;
        _messageSummary.TextAlign = ContentAlignment.MiddleLeft;
        _messageSummary.AutoEllipsis = true;
        summary.Controls.Add(_messageSummary, 1, 1);

        var openWorkspace = MakeButton("Abrir carpeta", (_, _) => OpenLastWorkspace());
        openWorkspace.Dock = DockStyle.Left;
        summary.Controls.Add(openWorkspace, 2, 1);

        var actions = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Padding = new Padding(0, 11, 0, 7),
            BackColor = Bg
        };
        root.Controls.Add(actions, 0, 3);

        _diagnose.Text = "Diagnóstico";
        ConfigureButton(_diagnose);
        _diagnose.Click += async (_, _) => await DiagnoseAsync();
        actions.Controls.Add(_diagnose);

        _validate.Text = "Validación automática";
        ConfigureButton(_validate, primary: true, width: 178);
        _validate.Click += async (_, _) => await ValidateInstallationAsync();
        actions.Controls.Add(_validate);

        _run.Text = "Ejecutar .export";
        ConfigureButton(_run, width: 150);
        _run.Click += async (_, _) => await RunSelectedExportAsync();
        actions.Controls.Add(_run);

        _cancel.Text = "Cancelar";
        ConfigureButton(_cancel, width: 112);
        _cancel.Enabled = false;
        _cancel.Click += (_, _) => _cancellation?.Cancel();
        actions.Controls.Add(_cancel);

        actions.Controls.Add(MakeButton("Logs", (_, _) => OpenFolder(CodeAsterRunner.LogDirectory), width: 92));

        _progress.Style = ProgressBarStyle.Marquee;
        _progress.MarqueeAnimationSpeed = 35;
        _progress.Width = 170;
        _progress.Height = 28;
        _progress.Margin = new Padding(16, 4, 0, 0);
        _progress.Visible = false;
        actions.Controls.Add(_progress);

        _log.Dock = DockStyle.Fill;
        _log.ReadOnly = true;
        _log.BackColor = Input;
        _log.ForeColor = Color.FromArgb(210, 219, 231);
        _log.BorderStyle = BorderStyle.FixedSingle;
        _log.Font = new Font("Cascadia Mono", 9.4F);
        _log.WordWrap = false;
        _log.DetectUrls = true;
        root.Controls.Add(_log, 0, 4);
    }

    private async Task InitializeAsync()
    {
        _launcher.Text = _settings.CodeAsterLauncher ?? string.Empty;
        _export.Text = _settings.LastExportFile ?? string.Empty;
        Append("AsterMax Windows Native 0.2.0-beta");
        Append($"Windows: {Environment.OSVersion}");
        Append("Puede arrastrar un archivo .export sobre esta ventana.");

        if (!File.Exists(_launcher.Text))
        {
            await DetectAsync(false);
        }
        else
        {
            SetStatus($"Configurado: {Path.GetFileName(_launcher.Text)}", Green);
        }
    }

    private async Task DetectAsync(bool showDialog)
    {
        SetBusy(true);
        SetStatus("Buscando Code_Aster y Salome-Meca...", Amber);
        try
        {
            var found = await Task.Run(CodeAsterLocator.FindInstallations);
            if (found.Count == 0)
            {
                SetStatus("No detectado; seleccione el lanzador manualmente.", Amber);
                Append("No se encontró un lanzador compatible.");
                if (showDialog)
                {
                    MessageBox.Show(this,
                        "No se detectó Code_Aster automáticamente. Seleccione run_aster.bat, as_run.bat, python.exe o el lanzador de su distribución.",
                        "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                return;
            }

            _launcher.Text = found[0].LauncherPath;
            SetStatus($"Detectado: {found[0].Kind} ({found[0].Source})", Green);
            Append($"Lanzador seleccionado: {found[0].LauncherPath}");
            foreach (var alternative in found.Skip(1).Take(8))
            {
                Append($"Alternativa: {alternative.LauncherPath}");
            }
            Save();
        }
        catch (Exception ex)
        {
            SetStatus("La detección falló.", Red);
            Append($"ERROR detección: {ex.Message}");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task DiagnoseAsync()
    {
        var launcher = GetLauncher();
        if (launcher is null) return;

        SetBusy(true);
        _log.Clear();
        Append($"> Diagnóstico: {launcher}");
        var captured = new StringBuilder();
        try
        {
            var result = await CodeAsterRunner.TestAsync(
                launcher,
                line => { captured.AppendLine(line); Append(line); },
                CancellationToken.None);

            var detected = CodeAsterOutputParser.DetectVersion(captured.ToString());
            _version.Text = detected ?? "No informada por el lanzador";
            if (result.Success)
            {
                SetStatus("El lanzador respondió correctamente.", Green);
            }
            else
            {
                SetStatus($"El diagnóstico terminó con código {result.ExitCode}.", Amber);
            }
        }
        catch (Exception ex)
        {
            SetStatus("No fue posible iniciar el lanzador.", Red);
            Append($"ERROR: {ex}");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task ValidateInstallationAsync()
    {
        var launcher = GetLauncher();
        if (launcher is null) return;

        var smoke = CodeAsterSmokeTest.Create();
        _lastWorkspace = smoke.Workspace;
        _export.Text = smoke.ExportFile;
        Save();

        _cancellation = new CancellationTokenSource();
        SetBusy(true, solving: true);
        _log.Clear();
        Append("VALIDACIÓN AUTOMÁTICA DE INSTALACIÓN");
        Append($"Workspace: {smoke.Workspace}");
        Append($"Comando: {smoke.CommandFile}");
        Append($"Export: {smoke.ExportFile}");
        Append("El caso mínimo ejecuta DEBUT(); FIN(); sin malla ni modelo.");
        SetStatus("Ejecutando smoke test real...", Blue);

        try
        {
            var result = await CodeAsterRunner.RunExportAsync(
                launcher,
                smoke.ExportFile,
                Append,
                _cancellation.Token);

            var report = CodeAsterMessageParser.Analyze(smoke.MessageFile, result.ExitCode);
            ApplyReport(report);
            Append(report.Details);
            Append($"Log del puente: {result.LogFile}");
            if (File.Exists(smoke.MessageFile))
            {
                Append($"Mensaje Code_Aster: {smoke.MessageFile}");
            }
        }
        catch (OperationCanceledException)
        {
            SetStatus("Validación cancelada.", Amber);
            _messageSummary.Text = "Cancelada";
        }
        catch (Exception ex)
        {
            SetStatus("Falló la ejecución de la validación.", Red);
            _messageSummary.Text = ex.Message;
            Append($"ERROR: {ex}");
        }
        finally
        {
            _cancellation.Dispose();
            _cancellation = null;
            SetBusy(false);
        }
    }

    private async Task RunSelectedExportAsync()
    {
        var launcher = GetLauncher();
        if (launcher is null) return;

        var exportFile = _export.Text.Trim();
        if (!File.Exists(exportFile) || !exportFile.EndsWith(".export", StringComparison.OrdinalIgnoreCase))
        {
            MessageBox.Show(this, "Seleccione un archivo .export existente.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        _lastWorkspace = Path.GetDirectoryName(exportFile);
        Save();
        _cancellation = new CancellationTokenSource();
        SetBusy(true, solving: true);
        _log.Clear();
        Append($"> Ejecutando: {exportFile}");
        SetStatus("Code_Aster está resolviendo...", Blue);

        try
        {
            var result = await CodeAsterRunner.RunExportAsync(launcher, exportFile, Append, _cancellation.Token);
            var mess = CodeAsterExportParser.FindMessageFile(exportFile);
            var report = CodeAsterMessageParser.Analyze(mess, result.ExitCode);
            ApplyReport(report);
            Append(report.Details);
            Append($"Log del puente: {result.LogFile}");
        }
        catch (OperationCanceledException)
        {
            SetStatus("Ejecución cancelada.", Amber);
            _messageSummary.Text = "Cancelada";
        }
        catch (Exception ex)
        {
            SetStatus("Error al ejecutar Code_Aster.", Red);
            _messageSummary.Text = ex.Message;
            Append($"ERROR: {ex}");
        }
        finally
        {
            _cancellation.Dispose();
            _cancellation = null;
            SetBusy(false);
        }
    }

    private void ApplyReport(CodeAsterRunReport report)
    {
        _messageSummary.Text = report.Summary;
        _messageSummary.ForeColor = report.Success ? Green : Red;
        SetStatus(report.Success ? "Validación aprobada." : "Validación rechazada; revise el .mess.", report.Success ? Green : Red);
    }

    private string? GetLauncher()
    {
        var launcher = _launcher.Text.Trim();
        if (!File.Exists(launcher))
        {
            MessageBox.Show(this, "Seleccione un lanzador existente de Code_Aster.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return null;
        }
        return launcher;
    }

    private void BrowseLauncher()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Seleccione el lanzador de Code_Aster",
            Filter = "Lanzadores (*.bat;*.cmd;*.exe)|*.bat;*.cmd;*.exe|Todos los archivos (*.*)|*.*",
            CheckFileExists = true
        };
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            _launcher.Text = dialog.FileName;
            SetStatus("Lanzador seleccionado; ejecute Diagnóstico o Validación automática.", Blue);
            Save();
        }
    }

    private void BrowseExport()
    {
        using var dialog = new OpenFileDialog
        {
            Title = "Seleccione un trabajo Code_Aster",
            Filter = "Code_Aster export (*.export)|*.export|Todos los archivos (*.*)|*.*",
            CheckFileExists = true
        };
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            _export.Text = dialog.FileName;
            _lastWorkspace = Path.GetDirectoryName(dialog.FileName);
            Save();
        }
    }

    private void OnDragEnter(object? sender, DragEventArgs e)
    {
        if (e.Data?.GetData(DataFormats.FileDrop) is string[] files && files.Any(f => f.EndsWith(".export", StringComparison.OrdinalIgnoreCase)))
        {
            e.Effect = DragDropEffects.Copy;
        }
    }

    private void OnDragDrop(object? sender, DragEventArgs e)
    {
        if (e.Data?.GetData(DataFormats.FileDrop) is not string[] files) return;
        var exportFile = files.FirstOrDefault(f => f.EndsWith(".export", StringComparison.OrdinalIgnoreCase));
        if (exportFile is null) return;
        _export.Text = exportFile;
        _lastWorkspace = Path.GetDirectoryName(exportFile);
        SetStatus("Archivo .export cargado; listo para ejecutar.", Blue);
        Save();
    }

    private void OpenLastWorkspace()
    {
        var path = _lastWorkspace;
        if (string.IsNullOrWhiteSpace(path) || !Directory.Exists(path))
        {
            path = Path.GetDirectoryName(_export.Text.Trim());
        }
        if (!string.IsNullOrWhiteSpace(path) && Directory.Exists(path))
        {
            OpenFolder(path);
        }
        else
        {
            MessageBox.Show(this, "Todavía no existe una carpeta de trabajo.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
    }

    private static void OpenFolder(string path)
    {
        Directory.CreateDirectory(path);
        Process.Start(new ProcessStartInfo("explorer.exe", path) { UseShellExecute = true });
    }

    private void Save()
    {
        _settings.CodeAsterLauncher = _launcher.Text.Trim();
        _settings.LastExportFile = _export.Text.Trim();
        _settings.Save();
    }

    private void SetBusy(bool busy, bool solving = false)
    {
        _detect.Enabled = !busy;
        _diagnose.Enabled = !busy;
        _validate.Enabled = !busy;
        _run.Enabled = !busy;
        _cancel.Enabled = busy && solving;
        _progress.Visible = busy;
        UseWaitCursor = busy;
    }

    private void SetStatus(string text, Color color)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => SetStatus(text, color));
            return;
        }
        _status.Text = text;
        _status.ForeColor = color;
    }

    private void Append(string text)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => Append(text));
            return;
        }
        _log.AppendText($"[{DateTime.Now:HH:mm:ss}] {text}{Environment.NewLine}");
        _log.SelectionStart = _log.TextLength;
        _log.ScrollToCaret();
    }

    private static Label MakeLabel(string text) => new()
    {
        Text = text,
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft,
        ForeColor = TextColor,
        Font = new Font("Segoe UI Semibold", 10F)
    };

    private static Label MakeCaption(string text) => new()
    {
        Text = text,
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleLeft,
        ForeColor = Muted,
        Font = new Font("Segoe UI Semibold", 8.5F)
    };

    private static void ConfigureTextBox(TextBox box)
    {
        box.Dock = DockStyle.Fill;
        box.Margin = new Padding(0, 5, 8, 5);
        box.BackColor = Input;
        box.ForeColor = TextColor;
        box.BorderStyle = BorderStyle.FixedSingle;
    }

    private static Button MakeButton(string text, EventHandler click, int width = 128)
    {
        var button = new Button { Text = text };
        ConfigureButton(button, width: width);
        button.Click += click;
        return button;
    }

    private static void ConfigureButton(Button button, bool primary = false, int width = 132)
    {
        button.AutoSize = false;
        button.Width = width;
        button.Height = 34;
        button.Margin = new Padding(5, 2, 5, 2);
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = 1;
        button.FlatAppearance.BorderColor = primary ? Blue : Color.FromArgb(80, 89, 102);
        button.BackColor = primary ? Blue : Card;
        button.ForeColor = Color.White;
        button.Cursor = Cursors.Hand;
    }
}

internal sealed record CodeAsterSmokeTest(
    string Workspace,
    string CommandFile,
    string ExportFile,
    string MessageFile)
{
    public static CodeAsterSmokeTest Create()
    {
        var publicRoot = Environment.GetEnvironmentVariable("PUBLIC");
        var root = !string.IsNullOrWhiteSpace(publicRoot)
            ? Path.Combine(publicRoot, "AsterMaxRuns")
            : Path.Combine(Path.GetTempPath(), "AsterMaxRuns");
        var workspace = Path.Combine(root, $"smoke-{DateTime.Now:yyyyMMdd-HHmmss}");
        Directory.CreateDirectory(workspace);

        var comm = Path.Combine(workspace, "astermax_smoke.comm");
        var export = Path.Combine(workspace, "astermax_smoke.export");
        var mess = Path.Combine(workspace, "astermax_smoke.mess");

        File.WriteAllText(comm,
            "# AsterMax Windows native smoke test\r\n" +
            "# Validates that the solver can initialize and terminate normally.\r\n" +
            "DEBUT();\r\n" +
            "FIN();\r\n",
            new UTF8Encoding(false));

        static string ExportPath(string path) => path.Replace('\\', '/');
        File.WriteAllText(export,
            "P actions make_etude\r\n" +
            "P version stable\r\n" +
            "P mode interactif\r\n" +
            "P time_limit 120\r\n" +
            "P memory_limit 512\r\n" +
            "P ncpus 1\r\n" +
            $"F comm {ExportPath(comm)} D 1\r\n" +
            $"F mess {ExportPath(mess)} R 6\r\n",
            new UTF8Encoding(false));

        return new CodeAsterSmokeTest(workspace, comm, export, mess);
    }
}

internal static class CodeAsterOutputParser
{
    private static readonly Regex[] VersionPatterns =
    [
        new(@"code[_\s-]*aster[^0-9]*(?<version>\d{2}\.\d+(?:\.\d+)?)", RegexOptions.IgnoreCase),
        new(@"version[^0-9]*(?<version>\d{2}\.\d+(?:\.\d+)?)", RegexOptions.IgnoreCase),
        new(@"\bASTER\s+(?<version>\d{2}\.\d+(?:\.\d+)?)", RegexOptions.IgnoreCase)
    ];

    public static string? DetectVersion(string output)
    {
        foreach (var pattern in VersionPatterns)
        {
            var match = pattern.Match(output);
            if (match.Success) return match.Groups["version"].Value;
        }
        return null;
    }
}

internal static class CodeAsterExportParser
{
    private static readonly Regex MessageLine = new(
        @"^\s*[FR]\s+mess\s+(?<path>.+?)\s+[DRC]\s+\d+\s*$",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    public static string? FindMessageFile(string exportFile)
    {
        try
        {
            foreach (var line in File.ReadLines(exportFile))
            {
                var match = MessageLine.Match(line);
                if (!match.Success) continue;
                var raw = match.Groups["path"].Value.Trim().Trim('"');
                var path = raw.Replace('/', Path.DirectorySeparatorChar);
                if (!Path.IsPathRooted(path))
                {
                    path = Path.Combine(Path.GetDirectoryName(exportFile) ?? Environment.CurrentDirectory, path);
                }
                return Path.GetFullPath(path);
            }
        }
        catch
        {
            // A malformed export is reported through the process log.
        }
        return null;
    }
}

internal sealed record CodeAsterRunReport(bool Success, string Summary, string Details);

internal static class CodeAsterMessageParser
{
    private static readonly string[] FatalMarkers =
    [
        "<F>",
        "FATAL_ERROR",
        "EXECUTION_CODE_ASTER_EXIT_",
        "ARRET PAR MANQUE",
        "ERREUR FATALE",
        "Traceback (most recent call last)"
    ];

    public static CodeAsterRunReport Analyze(string? messageFile, int exitCode)
    {
        if (string.IsNullOrWhiteSpace(messageFile) || !File.Exists(messageFile))
        {
            var successWithoutMess = exitCode == 0;
            return new CodeAsterRunReport(
                successWithoutMess,
                successWithoutMess ? "Proceso finalizado; no se localizó .mess" : $"Código {exitCode}; no se localizó .mess",
                "No fue posible leer un archivo .mess. Revise la declaración F/R mess del archivo .export y el log del puente.");
        }

        string text;
        try
        {
            text = File.ReadAllText(messageFile);
        }
        catch (Exception ex)
        {
            return new CodeAsterRunReport(false, "No se pudo leer el .mess", ex.Message);
        }

        var fatalLines = text
            .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries)
            .Where(line => IsFatalLine(line))
            .Take(12)
            .ToList();

        var alarms = Regex.Matches(text, @"<A>", RegexOptions.IgnoreCase).Count;
        var fatals = Regex.Matches(text, @"<F>", RegexOptions.IgnoreCase).Count;
        var normalTermination = text.Contains("TOTAL_JOB", StringComparison.OrdinalIgnoreCase)
            || text.Contains("EXECUTION_CODE_ASTER_EXIT_0000", StringComparison.OrdinalIgnoreCase)
            || text.Contains("DIAGNOSTIC JOB : <I>", StringComparison.OrdinalIgnoreCase);
        var success = exitCode == 0 && fatals == 0 && fatalLines.Count == 0 && normalTermination;

        var summary = success
            ? $"Aprobada · {alarms} alarma(s), 0 fatal(es)"
            : $"Rechazada · código {exitCode}, {alarms} alarma(s), {Math.Max(fatals, fatalLines.Count)} fatal(es)";

        var details = new StringBuilder();
        details.AppendLine($"Resumen .mess: {summary}");
        details.AppendLine($"Archivo: {messageFile}");
        if (!normalTermination) details.AppendLine("No se encontró un marcador inequívoco de terminación normal.");
        if (fatalLines.Count > 0)
        {
            details.AppendLine("Líneas críticas detectadas:");
            foreach (var line in fatalLines) details.AppendLine("  " + line.Trim());
        }
        return new CodeAsterRunReport(success, summary, details.ToString().TrimEnd());
    }

    private static bool IsFatalLine(string line)
    {
        if (line.Contains("EXECUTION_CODE_ASTER_EXIT_0000", StringComparison.OrdinalIgnoreCase)) return false;
        return FatalMarkers.Any(marker => line.Contains(marker, StringComparison.OrdinalIgnoreCase));
    }
}
