using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.Win32;

namespace AsterMax.WindowsNative;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }
}

internal sealed class MainForm : Form
{
    private readonly TextBox _launcherText = new();
    private readonly TextBox _exportText = new();
    private readonly RichTextBox _log = new();
    private readonly Label _status = new();
    private readonly Button _detectButton = new();
    private readonly Button _testButton = new();
    private readonly Button _runButton = new();
    private readonly Button _cancelButton = new();
    private readonly ProgressBar _progress = new();
    private readonly AppSettings _settings;
    private CancellationTokenSource? _runCancellation;

    private static readonly Color Background = Color.FromArgb(24, 27, 32);
    private static readonly Color Panel = Color.FromArgb(35, 39, 46);
    private static readonly Color Field = Color.FromArgb(19, 22, 27);
    private static readonly Color Foreground = Color.FromArgb(235, 238, 242);
    private static readonly Color Muted = Color.FromArgb(160, 168, 180);
    private static readonly Color Accent = Color.FromArgb(44, 145, 255);
    private static readonly Color Success = Color.FromArgb(70, 190, 120);
    private static readonly Color Warning = Color.FromArgb(255, 184, 77);

    public MainForm()
    {
        _settings = AppSettings.Load();

        Text = "AsterMax Windows Native — Code_Aster Bridge";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(900, 650);
        Size = new Size(1080, 760);
        BackColor = Background;
        ForeColor = Foreground;
        Font = new Font("Segoe UI", 10F);

        BuildInterface();
        Load += async (_, _) => await InitializeAsync();
        FormClosing += (_, _) => SaveSettings();
    }

    private void BuildInterface()
    {
        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 4,
            Padding = new Padding(24),
            BackColor = Background
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 92));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 184));
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 62));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        Controls.Add(root);

        var titlePanel = new Panel { Dock = DockStyle.Fill, BackColor = Background };
        var title = new Label
        {
            Text = "ASTERMAX  WINDOWS NATIVE",
            AutoSize = true,
            Font = new Font("Segoe UI Semibold", 22F, FontStyle.Bold),
            ForeColor = Foreground,
            Location = new Point(0, 4)
        };
        var subtitle = new Label
        {
            Text = "Puente beta para ejecutar Code_Aster nativo con archivos .export",
            AutoSize = true,
            Font = new Font("Segoe UI", 10.5F),
            ForeColor = Muted,
            Location = new Point(2, 50)
        };
        titlePanel.Controls.Add(title);
        titlePanel.Controls.Add(subtitle);
        root.Controls.Add(titlePanel, 0, 0);

        var configuration = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 4,
            RowCount = 4,
            Padding = new Padding(18, 14, 18, 14),
            BackColor = Panel
        };
        configuration.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 150));
        configuration.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        configuration.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 112));
        configuration.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 112));
        configuration.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        configuration.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        configuration.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        configuration.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        root.Controls.Add(configuration, 0, 1);

        configuration.Controls.Add(MakeLabel("Code_Aster:"), 0, 0);
        ConfigureTextBox(_launcherText, "Ruta a as_run.bat, run_aster.bat, python.exe o ejecutable equivalente");
        configuration.Controls.Add(_launcherText, 1, 0);
        configuration.SetColumnSpan(_launcherText, 1);

        var browseLauncher = MakeButton("Examinar", (_, _) => BrowseLauncher());
        configuration.Controls.Add(browseLauncher, 2, 0);
        _detectButton.Text = "Detectar";
        ConfigureButton(_detectButton);
        _detectButton.Click += async (_, _) => await DetectAsync(showDialog: true);
        configuration.Controls.Add(_detectButton, 3, 0);

        configuration.Controls.Add(MakeLabel("Trabajo .export:"), 0, 1);
        ConfigureTextBox(_exportText, "Seleccione el archivo de ejecución generado por AsterMax");
        configuration.Controls.Add(_exportText, 1, 1);
        configuration.SetColumnSpan(_exportText, 2);
        configuration.Controls.Add(MakeButton("Examinar", (_, _) => BrowseExport()), 3, 1);

        configuration.Controls.Add(MakeLabel("Estado:"), 0, 2);
        _status.Text = "Sin comprobar";
        _status.AutoEllipsis = true;
        _status.Dock = DockStyle.Fill;
        _status.TextAlign = ContentAlignment.MiddleLeft;
        _status.ForeColor = Warning;
        configuration.Controls.Add(_status, 1, 2);
        configuration.SetColumnSpan(_status, 3);

        var hint = new Label
        {
            Text = "Funciona sin permisos de administrador. La configuración se guarda en LocalAppData\\AsterMax.",
            Dock = DockStyle.Fill,
            ForeColor = Muted,
            Font = new Font("Segoe UI", 8.8F),
            TextAlign = ContentAlignment.MiddleLeft
        };
        configuration.Controls.Add(hint, 1, 3);
        configuration.SetColumnSpan(hint, 3);

        var actions = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Padding = new Padding(0, 12, 0, 8),
            BackColor = Background
        };
        root.Controls.Add(actions, 0, 2);

        _testButton.Text = "Probar Code_Aster";
        ConfigureButton(_testButton);
        _testButton.Click += async (_, _) => await TestAsync();
        actions.Controls.Add(_testButton);

        _runButton.Text = "Ejecutar análisis";
        ConfigureButton(_runButton, primary: true);
        _runButton.Click += async (_, _) => await RunAnalysisAsync();
        actions.Controls.Add(_runButton);

        _cancelButton.Text = "Cancelar";
        ConfigureButton(_cancelButton);
        _cancelButton.Enabled = false;
        _cancelButton.Click += (_, _) => _runCancellation?.Cancel();
        actions.Controls.Add(_cancelButton);

        actions.Controls.Add(MakeButton("Abrir carpeta de logs", (_, _) => OpenLogsFolder()));

        _progress.Style = ProgressBarStyle.Marquee;
        _progress.MarqueeAnimationSpeed = 35;
        _progress.Width = 170;
        _progress.Height = 28;
        _progress.Margin = new Padding(16, 5, 0, 0);
        _progress.Visible = false;
        actions.Controls.Add(_progress);

        _log.Dock = DockStyle.Fill;
        _log.ReadOnly = true;
        _log.BackColor = Field;
        _log.ForeColor = Color.FromArgb(210, 218, 228);
        _log.BorderStyle = BorderStyle.FixedSingle;
        _log.Font = new Font("Cascadia Mono", 9.5F);
        _log.WordWrap = false;
        _log.DetectUrls = true;
        root.Controls.Add(_log, 0, 3);
    }

    private async Task InitializeAsync()
    {
        _launcherText.Text = _settings.CodeAsterLauncher ?? string.Empty;
        _exportText.Text = _settings.LastExportFile ?? string.Empty;
        AppendLog("AsterMax Windows Native Bridge 0.1.0-beta");
        AppendLog($"Windows: {Environment.OSVersion}");
        AppendLog($"Configuración: {AppSettings.SettingsPath}");

        if (string.IsNullOrWhiteSpace(_launcherText.Text) || !File.Exists(_launcherText.Text))
        {
            await DetectAsync(showDialog: false);
        }
        else
        {
            SetStatus($"Configurado: {Path.GetFileName(_launcherText.Text)}", Success);
        }
    }

    private async Task DetectAsync(bool showDialog)
    {
        SetBusy(true);
        SetStatus("Buscando instalaciones de Code_Aster...", Warning);
        AppendLog("Buscando Code_Aster en variables de entorno, registro y carpetas conocidas...");

        try
        {
            var installations = await Task.Run(CodeAsterLocator.FindInstallations);
            if (installations.Count == 0)
            {
                SetStatus("Code_Aster no fue detectado. Seleccione el lanzador manualmente.", Warning);
                AppendLog("No se encontró una instalación compatible.");
                if (showDialog)
                {
                    MessageBox.Show(
                        this,
                        "No se detectó Code_Aster. Puede seleccionar manualmente as_run.bat, run_aster.bat, python.exe o el lanzador suministrado por la distribución Windows.",
                        "AsterMax",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
                return;
            }

            var selected = installations[0];
            _launcherText.Text = selected.LauncherPath;
            SetStatus($"Detectado: {selected.Kind} ({selected.Source})", Success);
            AppendLog($"Detectado: {selected.LauncherPath}");

            if (installations.Count > 1)
            {
                AppendLog("Otras instalaciones encontradas:");
                foreach (var installation in installations.Skip(1))
                {
                    AppendLog($"  - {installation.LauncherPath}");
                }
            }

            SaveSettings();
        }
        catch (Exception ex)
        {
            SetStatus("Falló la detección automática.", Color.IndianRed);
            AppendLog($"ERROR detección: {ex.Message}");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task TestAsync()
    {
        var launcher = ValidateLauncher();
        if (launcher is null)
        {
            return;
        }

        SetBusy(true);
        _log.Clear();
        AppendLog($"> Diagnóstico de {launcher}");

        try
        {
            var result = await CodeAsterRunner.TestAsync(launcher, AppendLog, CancellationToken.None);
            if (result.Success)
            {
                SetStatus("Code_Aster respondió correctamente.", Success);
                AppendLog("DIAGNÓSTICO: compatible para la integración beta.");
            }
            else
            {
                SetStatus($"El lanzador respondió con código {result.ExitCode}.", Warning);
                AppendLog("DIAGNÓSTICO: revise el log y, si corresponde, seleccione otro lanzador.");
            }
        }
        catch (Exception ex)
        {
            SetStatus("No fue posible iniciar Code_Aster.", Color.IndianRed);
            AppendLog($"ERROR: {ex}");
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task RunAnalysisAsync()
    {
        var launcher = ValidateLauncher();
        if (launcher is null)
        {
            return;
        }

        var exportFile = _exportText.Text.Trim();
        if (!File.Exists(exportFile) || !string.Equals(Path.GetExtension(exportFile), ".export", StringComparison.OrdinalIgnoreCase))
        {
            MessageBox.Show(this, "Seleccione un archivo .export existente.", "AsterMax", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        SaveSettings();
        _runCancellation = new CancellationTokenSource();
        SetBusy(true, solving: true);
        _log.Clear();
        AppendLog($"> {launcher} {exportFile}");
        SetStatus("Code_Aster está resolviendo...", Accent);

        try
        {
            var result = await CodeAsterRunner.RunExportAsync(launcher, exportFile, AppendLog, _runCancellation.Token);
            if (result.Success)
            {
                SetStatus($"Análisis finalizado correctamente. Log: {Path.GetFileName(result.LogFile)}", Success);
                AppendLog($"FINALIZADO: código 0");
                AppendLog($"Log guardado en: {result.LogFile}");
            }
            else
            {
                SetStatus($"Code_Aster terminó con código {result.ExitCode}.", Color.IndianRed);
                AppendLog($"FALLO: código {result.ExitCode}");
                AppendLog($"Log guardado en: {result.LogFile}");
            }
        }
        catch (OperationCanceledException)
        {
            SetStatus("Ejecución cancelada.", Warning);
            AppendLog("CANCELADO por el usuario.");
        }
        catch (Exception ex)
        {
            SetStatus("Error al ejecutar Code_Aster.", Color.IndianRed);
            AppendLog($"ERROR: {ex}");
        }
        finally
        {
            _runCancellation.Dispose();
            _runCancellation = null;
            SetBusy(false);
        }
    }

    private string? ValidateLauncher()
    {
        var launcher = _launcherText.Text.Trim();
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
            _launcherText.Text = dialog.FileName;
            SetStatus("Lanzador seleccionado; ejecute la prueba.", Accent);
            SaveSettings();
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
            _exportText.Text = dialog.FileName;
            SaveSettings();
        }
    }

    private void OpenLogsFolder()
    {
        Directory.CreateDirectory(CodeAsterRunner.LogDirectory);
        Process.Start(new ProcessStartInfo("explorer.exe", CodeAsterRunner.LogDirectory) { UseShellExecute = true });
    }

    private void SaveSettings()
    {
        _settings.CodeAsterLauncher = _launcherText.Text.Trim();
        _settings.LastExportFile = _exportText.Text.Trim();
        _settings.Save();
    }

    private void SetBusy(bool busy, bool solving = false)
    {
        _detectButton.Enabled = !busy;
        _testButton.Enabled = !busy;
        _runButton.Enabled = !busy;
        _cancelButton.Enabled = busy && solving;
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

    private void AppendLog(string text)
    {
        if (InvokeRequired)
        {
            BeginInvoke(() => AppendLog(text));
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
        ForeColor = Foreground,
        Font = new Font("Segoe UI Semibold", 10F)
    };

    private static void ConfigureTextBox(TextBox box, string accessibleDescription)
    {
        box.Dock = DockStyle.Fill;
        box.Margin = new Padding(0, 5, 8, 5);
        box.BackColor = Field;
        box.ForeColor = Foreground;
        box.BorderStyle = BorderStyle.FixedSingle;
        box.AccessibleDescription = accessibleDescription;
    }

    private static Button MakeButton(string text, EventHandler click)
    {
        var button = new Button { Text = text };
        ConfigureButton(button);
        button.Click += click;
        return button;
    }

    private static void ConfigureButton(Button button, bool primary = false)
    {
        button.AutoSize = false;
        button.Width = primary ? 150 : 136;
        button.Height = 34;
        button.Margin = new Padding(5, 2, 5, 2);
        button.FlatStyle = FlatStyle.Flat;
        button.FlatAppearance.BorderSize = 1;
        button.FlatAppearance.BorderColor = primary ? Accent : Color.FromArgb(80, 88, 100);
        button.BackColor = primary ? Accent : Panel;
        button.ForeColor = Color.White;
        button.Cursor = Cursors.Hand;
    }
}

internal sealed class AppSettings
{
    public string? CodeAsterLauncher { get; set; }
    public string? LastExportFile { get; set; }

    public static string SettingsDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AsterMax");

    public static string SettingsPath => Path.Combine(SettingsDirectory, "windows-native.json");

    public static AppSettings Load()
    {
        try
        {
            if (File.Exists(SettingsPath))
            {
                return JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(SettingsPath)) ?? new AppSettings();
            }
        }
        catch
        {
            // A malformed user configuration must never prevent startup.
        }
        return new AppSettings();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(SettingsDirectory);
            var json = JsonSerializer.Serialize(this, new JsonSerializerOptions { WriteIndented = true });
            File.WriteAllText(SettingsPath, json, Encoding.UTF8);
        }
        catch
        {
            // Configuration persistence is best effort in the beta.
        }
    }
}

internal sealed record SolverInstallation(string LauncherPath, string Kind, string Source);

internal static class CodeAsterLocator
{
    private static readonly string[] LauncherNames =
    [
        "as_run.bat",
        "run_aster.bat",
        "code_aster.bat",
        "as_run.exe",
        "run_aster.exe",
        "python.exe"
    ];

    public static IReadOnlyList<SolverInstallation> FindInstallations()
    {
        var results = new List<SolverInstallation>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        void AddFile(string? file, string source)
        {
            if (string.IsNullOrWhiteSpace(file)) return;
            string full;
            try { full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(file)); }
            catch { return; }
            if (!File.Exists(full) || !seen.Add(full)) return;
            results.Add(new SolverInstallation(full, Describe(full), source));
        }

        void AddRoot(string? root, string source)
        {
            if (string.IsNullOrWhiteSpace(root)) return;
            var expanded = Environment.ExpandEnvironmentVariables(root);
            if (File.Exists(expanded))
            {
                AddFile(expanded, source);
                return;
            }
            if (!Directory.Exists(expanded)) return;

            foreach (var name in LauncherNames)
            {
                foreach (var relative in KnownRelativePaths(name))
                {
                    AddFile(Path.Combine(expanded, relative), source);
                }
            }

            SearchTargeted(expanded, source, AddFile);
        }

        foreach (var variable in new[] { "ASTERMAX_CODE_ASTER", "CODE_ASTER_HOME", "ASTER_ROOT", "ASTER_HOME", "SALOME_ROOT" })
        {
            AddRoot(Environment.GetEnvironmentVariable(variable), $"variable {variable}");
        }

        foreach (var registryRoot in ReadRegistryInstallLocations())
        {
            AddRoot(registryRoot, "registro de Windows");
        }

        AddRoot(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Program Files");
        AddRoot(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Program Files (x86)");
        AddRoot(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "LocalAppData");
        AddRoot(@"C:\Code_Aster", "ruta conocida");
        AddRoot(@"C:\code_aster", "ruta conocida");
        AddRoot(@"C:\Salome-Meca", "ruta conocida");

        return results
            .OrderBy(x => Rank(x.LauncherPath))
            .ThenBy(x => x.LauncherPath, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static IEnumerable<string> KnownRelativePaths(string name)
    {
        yield return name;
        yield return Path.Combine("bin", name);
        yield return Path.Combine("tools", name);
        yield return Path.Combine("code_aster", "bin", name);
        yield return Path.Combine("Python", name);
        yield return Path.Combine("python", name);
        yield return Path.Combine("bin", "python", name);
    }

    private static void SearchTargeted(string root, string source, Action<string?, string> addFile)
    {
        IEnumerable<string> firstLevel;
        try { firstLevel = Directory.EnumerateDirectories(root); }
        catch { return; }

        foreach (var directory in firstLevel)
        {
            var name = Path.GetFileName(directory);
            if (!ContainsProductName(name)) continue;
            SearchProductTree(directory, source, addFile, maximumDepth: 5);
        }

        if (ContainsProductName(Path.GetFileName(root)))
        {
            SearchProductTree(root, source, addFile, maximumDepth: 5);
        }
    }

    private static void SearchProductTree(string root, string source, Action<string?, string> addFile, int maximumDepth)
    {
        var queue = new Queue<(string Directory, int Depth)>();
        queue.Enqueue((root, 0));
        var visited = 0;

        while (queue.Count > 0 && visited < 2500)
        {
            var current = queue.Dequeue();
            visited++;

            foreach (var launcher in LauncherNames)
            {
                addFile(Path.Combine(current.Directory, launcher), source);
            }

            if (current.Depth >= maximumDepth) continue;
            try
            {
                foreach (var child in Directory.EnumerateDirectories(current.Directory))
                {
                    queue.Enqueue((child, current.Depth + 1));
                }
            }
            catch
            {
                // Access denied or transient directories are ignored.
            }
        }
    }

    private static IEnumerable<string> ReadRegistryInstallLocations()
    {
        var locations = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var hive in new[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
        {
            foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
            {
                try
                {
                    using var baseKey = RegistryKey.OpenBaseKey(hive, view);
                    using var uninstall = baseKey.OpenSubKey(@"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall");
                    if (uninstall is null) continue;
                    foreach (var subKeyName in uninstall.GetSubKeyNames())
                    {
                        using var subKey = uninstall.OpenSubKey(subKeyName);
                        var displayName = subKey?.GetValue("DisplayName") as string;
                        if (!ContainsProductName(displayName)) continue;
                        var location = subKey?.GetValue("InstallLocation") as string;
                        if (!string.IsNullOrWhiteSpace(location)) locations.Add(location);
                        var icon = subKey?.GetValue("DisplayIcon") as string;
                        if (!string.IsNullOrWhiteSpace(icon))
                        {
                            locations.Add(icon.Split(',')[0].Trim('"'));
                        }
                    }
                }
                catch
                {
                    // Registry access varies between Windows editions.
                }
            }
        }
        return locations;
    }

    private static bool ContainsProductName(string? value) =>
        !string.IsNullOrWhiteSpace(value) &&
        (value.Contains("aster", StringComparison.OrdinalIgnoreCase) ||
         value.Contains("salome", StringComparison.OrdinalIgnoreCase));

    private static string Describe(string path)
    {
        var file = Path.GetFileName(path);
        if (file.Equals("python.exe", StringComparison.OrdinalIgnoreCase)) return "Python run_aster";
        if (file.Contains("as_run", StringComparison.OrdinalIgnoreCase)) return "as_run";
        if (file.Contains("run_aster", StringComparison.OrdinalIgnoreCase)) return "run_aster";
        return "Code_Aster launcher";
    }

    private static int Rank(string path)
    {
        var file = Path.GetFileName(path);
        if (file.Equals("run_aster.bat", StringComparison.OrdinalIgnoreCase)) return 0;
        if (file.Equals("as_run.bat", StringComparison.OrdinalIgnoreCase)) return 1;
        if (file.Equals("run_aster.exe", StringComparison.OrdinalIgnoreCase)) return 2;
        if (file.Equals("as_run.exe", StringComparison.OrdinalIgnoreCase)) return 3;
        if (file.Equals("code_aster.bat", StringComparison.OrdinalIgnoreCase)) return 4;
        return 5;
    }
}

internal sealed record SolverRunResult(bool Success, int ExitCode, string LogFile);

internal static class CodeAsterRunner
{
    public static string LogDirectory => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "AsterMax",
        "logs");

    public static async Task<SolverRunResult> TestAsync(
        string launcher,
        Action<string> output,
        CancellationToken cancellationToken)
    {
        var logFile = CreateLogFile("diagnostic");
        var startInfo = BuildStartInfo(launcher, null, diagnostic: true);
        return await ExecuteAsync(startInfo, logFile, output, cancellationToken, TimeSpan.FromSeconds(30));
    }

    public static async Task<SolverRunResult> RunExportAsync(
        string launcher,
        string exportFile,
        Action<string> output,
        CancellationToken cancellationToken)
    {
        var logFile = CreateLogFile(Path.GetFileNameWithoutExtension(exportFile));
        var startInfo = BuildStartInfo(launcher, exportFile, diagnostic: false);
        return await ExecuteAsync(startInfo, logFile, output, cancellationToken, timeout: null);
    }

    private static ProcessStartInfo BuildStartInfo(string launcher, string? exportFile, bool diagnostic)
    {
        var extension = Path.GetExtension(launcher).ToLowerInvariant();
        var fileName = launcher;
        var arguments = new List<string>();

        if (extension is ".bat" or ".cmd")
        {
            fileName = Environment.GetEnvironmentVariable("ComSpec") ?? "cmd.exe";
            arguments.Add("/d");
            arguments.Add("/s");
            arguments.Add("/c");
            var commandArgument = diagnostic ? "--help" : Quote(exportFile!);
            arguments.Add($"\"{Quote(launcher)} {commandArgument}\"");
        }
        else if (Path.GetFileName(launcher).Equals("python.exe", StringComparison.OrdinalIgnoreCase))
        {
            arguments.Add("-m");
            arguments.Add("run_aster");
            arguments.Add(diagnostic ? "--help" : exportFile!);
        }
        else
        {
            arguments.Add(diagnostic ? "--help" : exportFile!);
        }

        var info = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = exportFile is null
                ? Path.GetDirectoryName(launcher) ?? Environment.CurrentDirectory
                : Path.GetDirectoryName(exportFile) ?? Environment.CurrentDirectory,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };

        foreach (var argument in arguments)
        {
            info.ArgumentList.Add(argument);
        }

        var launcherDirectory = Path.GetDirectoryName(launcher);
        if (!string.IsNullOrWhiteSpace(launcherDirectory))
        {
            var currentPath = info.Environment.TryGetValue("PATH", out var path) ? path : Environment.GetEnvironmentVariable("PATH");
            info.Environment["PATH"] = launcherDirectory + Path.PathSeparator + currentPath;
        }
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        info.Environment["ASTERMAX_HOST"] = "windows-native-bridge";

        return info;
    }

    private static async Task<SolverRunResult> ExecuteAsync(
        ProcessStartInfo startInfo,
        string logFile,
        Action<string> output,
        CancellationToken cancellationToken,
        TimeSpan? timeout)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(logFile)!);
        await using var log = new StreamWriter(logFile, append: false, new UTF8Encoding(false)) { AutoFlush = true };
        using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };

        output($"Iniciando: {startInfo.FileName} {string.Join(' ', startInfo.ArgumentList.Select(QuoteForDisplay))}");
        await log.WriteLineAsync($"AsterMax Windows Native Bridge {DateTimeOffset.Now:O}");
        await log.WriteLineAsync($"Command: {startInfo.FileName} {string.Join(' ', startInfo.ArgumentList.Select(QuoteForDisplay))}");
        await log.WriteLineAsync($"WorkingDirectory: {startInfo.WorkingDirectory}");
        await log.WriteLineAsync(new string('-', 80));

        if (!process.Start())
        {
            throw new InvalidOperationException("Windows no pudo iniciar el proceso de Code_Aster.");
        }

        async Task PumpAsync(StreamReader reader, string prefix)
        {
            while (await reader.ReadLineAsync(cancellationToken) is { } line)
            {
                output(prefix + line);
                await log.WriteLineAsync(prefix + line);
            }
        }

        var stdout = PumpAsync(process.StandardOutput, string.Empty);
        var stderr = PumpAsync(process.StandardError, "ERR | ");

        using var timeoutCancellation = timeout.HasValue ? new CancellationTokenSource(timeout.Value) : null;
        using var linked = timeoutCancellation is null
            ? CancellationTokenSource.CreateLinkedTokenSource(cancellationToken)
            : CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeoutCancellation.Token);

        try
        {
            await process.WaitForExitAsync(linked.Token);
            await Task.WhenAll(stdout, stderr);
        }
        catch (OperationCanceledException)
        {
            try
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
            catch
            {
                // The process may have exited between checks.
            }

            if (timeoutCancellation?.IsCancellationRequested == true && !cancellationToken.IsCancellationRequested)
            {
                output("La prueba alcanzó el límite de 30 segundos; el proceso fue detenido.");
                await log.WriteLineAsync("TIMEOUT");
                return new SolverRunResult(false, -2, logFile);
            }
            throw;
        }

        await log.WriteLineAsync(new string('-', 80));
        await log.WriteLineAsync($"ExitCode: {process.ExitCode}");
        return new SolverRunResult(process.ExitCode == 0, process.ExitCode, logFile);
    }

    private static string CreateLogFile(string stem)
    {
        Directory.CreateDirectory(LogDirectory);
        var safeStem = string.Concat(stem.Select(ch => Path.GetInvalidFileNameChars().Contains(ch) ? '_' : ch));
        return Path.Combine(LogDirectory, $"{DateTime.Now:yyyyMMdd-HHmmss}-{safeStem}.log");
    }

    private static string Quote(string value) => $"\"{value.Replace("\"", "\\\"")}\"";

    private static string QuoteForDisplay(string value) =>
        value.Any(char.IsWhiteSpace) ? Quote(value) : value;
}
