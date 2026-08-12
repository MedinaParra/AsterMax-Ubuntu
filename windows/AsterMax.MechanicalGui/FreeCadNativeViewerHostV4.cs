using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

/// <summary>
/// FreeCAD native viewer host v4.
///
/// The old POC invoked "FreeCAD.exe bridge.py". On physical Windows the official package
/// can use a short-lived launcher and the Python bridge never reaches the GUI process.
/// SolidFreeCAD's Windows runtime instead starts FreeCAD normally and relies on the native
/// Mod/InitGui lifecycle. V4 follows that proven lifecycle while keeping the module hidden:
/// no AsterMax Workbench is registered and AsterMax remains the product shell.
/// </summary>
internal sealed class FreeCadNativeViewerHostV4 : Panel
{
    private const int GwlStyle = -16;
    private const long WsChild = 0x40000000L;
    private const long WsVisible = 0x10000000L;
    private const long WsCaption = 0x00C00000L;
    private const long WsThickFrame = 0x00040000L;
    private const long WsMinimizeBox = 0x00020000L;
    private const long WsMaximizeBox = 0x00010000L;
    private const long WsSysMenu = 0x00080000L;
    private const uint SwpNoZOrder = 0x0004;
    private const uint SwpNoActivate = 0x0010;
    private const uint SwpFrameChanged = 0x0020;
    private const int SwHide = 0;
    private const int SwShow = 5;

    private readonly Label _state = new()
    {
        Dock = DockStyle.Fill,
        TextAlign = ContentAlignment.MiddleCenter,
        ForeColor = MechanicalForm.TextMuted,
        BackColor = Color.FromArgb(236, 242, 248),
        Text = "FreeCAD native CAD engine is idle."
    };

    private Process? _launcherProcess;
    private Process? _windowProcess;
    private CancellationTokenSource? _launchCancellation;
    private Task<string>? _stdoutTask;
    private Task<string>? _stderrTask;
    private IntPtr _embeddedWindow;
    private string? _sessionDirectory;
    private string? _commandPath;
    private string? _runtimeRoot;
    private ViewerReady? _lastReady;
    private readonly HashSet<int> _ownedProcessIds = new();
    private HashSet<int> _baselineFreeCadIds = new();
    private int _generation;

    public bool IsReady
    {
        get
        {
            if (_embeddedWindow == IntPtr.Zero || !IsHandleCreated) return false;
            try { return _windowProcess is { HasExited: false } && GetParent(_embeddedWindow) == Handle; }
            catch { return false; }
        }
    }

    public int? ViewerProcessId
    {
        get
        {
            try { return _windowProcess is { HasExited: false } ? _windowProcess.Id : null; }
            catch { return null; }
        }
    }

    public string? LastScreenshotPath => _lastReady?.Screenshot;
    public int LastShapeObjectCount => _lastReady?.ShapeObjects ?? 0;

    public FreeCadNativeViewerHostV4()
    {
        Name = "FreeCadNativeViewerHostV4";
        Dock = DockStyle.Fill;
        Margin = Padding.Empty;
        Padding = Padding.Empty;
        BackColor = Color.FromArgb(236, 242, 248);
        Visible = false;
        Controls.Add(_state);
        Resize += (_, _) => ResizeEmbeddedWindow();
    }

    /// <summary>
    /// Resolve a real FreeCAD engine executable. If an explicit path points to a package
    /// launcher, scan the same runtime and prefer Library/bin or bin, matching the Windows
    /// layout already used by SolidFreeCAD.
    /// </summary>
    public static string? FindExecutable()
    {
        var roots = new List<string>();
        var explicitExe = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EXE")
                          ?? Environment.GetEnvironmentVariable("FREECAD_EXE");
        if (!string.IsNullOrWhiteSpace(explicitExe) && File.Exists(explicitExe))
        {
            var explicitFull = Path.GetFullPath(explicitExe);
            roots.Add(ResolveRuntimeRoot(Path.GetDirectoryName(explicitFull)!));
        }

        var explicitRoot = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_ROOT");
        if (!string.IsNullOrWhiteSpace(explicitRoot) && Directory.Exists(explicitRoot))
            roots.Add(Path.GetFullPath(explicitRoot));

        var bundledRoot = Path.Combine(AppContext.BaseDirectory, "tools", "freecad");
        if (Directory.Exists(bundledRoot)) roots.Add(bundledRoot);

        foreach (var programRoot in new[]
                 {
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD 1.1"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD")
                 })
            if (Directory.Exists(programRoot)) roots.Add(programRoot);

        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(explicitExe) && File.Exists(explicitExe))
            candidates.Add(Path.GetFullPath(explicitExe));

        foreach (var root in roots.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                candidates.AddRange(Directory.EnumerateFiles(root, "FreeCAD.exe", SearchOption.AllDirectories));
            }
            catch (UnauthorizedAccessException) { }
            catch (DirectoryNotFoundException) { }
        }

        return candidates
            .Where(File.Exists)
            .Where(path => !path.Contains("uninstall", StringComparison.OrdinalIgnoreCase))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderByDescending(ScoreExecutable)
            .ThenBy(path => path.Length)
            .FirstOrDefault();
    }

    private static int ScoreExecutable(string path)
    {
        var normalized = path.Replace('/', '\\');
        var score = 0;
        if (normalized.Contains("\\Library\\bin\\", StringComparison.OrdinalIgnoreCase)) score += 500;
        else if (normalized.Contains("\\bin\\", StringComparison.OrdinalIgnoreCase)) score += 400;
        if (normalized.Contains("\\tools\\freecad\\", StringComparison.OrdinalIgnoreCase)) score += 80;
        if (string.Equals(Path.GetFileName(path), "FreeCAD.exe", StringComparison.OrdinalIgnoreCase)) score += 20;

        // A root-level executable in the official portable package may be a launcher. It is
        // retained as fallback but deliberately ranked below the engine binaries.
        var root = ResolveRuntimeRoot(Path.GetDirectoryName(path)!);
        if (string.Equals(Path.GetDirectoryName(path), root, StringComparison.OrdinalIgnoreCase)) score -= 100;
        return score;
    }

    public async Task<ViewerReady> ShowStepAsync(
        string stepPath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var generation = Interlocked.Increment(ref _generation);
        StopViewerCore(incrementGeneration: false);
        ShowLoadingState();
        _launchCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        try
        {
            var ready = await Task.Run(
                () => LaunchAndWait(stepPath, timeout ?? TimeSpan.FromSeconds(50), _launchCancellation.Token),
                _launchCancellation.Token);
            _launchCancellation.Token.ThrowIfCancellationRequested();
            if (generation != _generation)
                throw new OperationCanceledException("A newer FreeCAD viewer session replaced this one.");
            CompleteEmbedding(ready);
            return ready;
        }
        catch (Exception exception)
        {
            WriteEvidence("viewer-v4-failed " + exception);
            SetState("FreeCAD native viewer failed to start.\n\n" + exception.Message);
            StopOwnedProcesses();
            throw;
        }
    }

    public ViewerReady ShowStepBlocking(
        string stepPath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var generation = Interlocked.Increment(ref _generation);
        StopViewerCore(incrementGeneration: false);
        ShowLoadingState();
        _launchCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        try
        {
            var ready = LaunchAndWait(stepPath, timeout ?? TimeSpan.FromSeconds(50), _launchCancellation.Token);
            if (generation != _generation)
                throw new OperationCanceledException("A newer FreeCAD viewer session replaced this one.");
            CompleteEmbedding(ready);
            return ready;
        }
        catch
        {
            StopOwnedProcesses();
            throw;
        }
    }

    public void SendCommand(string command)
    {
        if (!IsReady || string.IsNullOrWhiteSpace(_commandPath)) return;
        try
        {
            var temporary = _commandPath + ".tmp";
            File.WriteAllText(temporary, command.Trim());
            File.Move(temporary, _commandPath, true);
        }
        catch (Exception exception)
        {
            WriteEvidence($"command-v4-failed command={command} error={exception.Message}");
        }
    }

    public void StopViewer() => StopViewerCore(incrementGeneration: true);

    public bool ScreenshotLooksRendered(out string diagnostic)
    {
        var path = LastScreenshotPath;
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
        {
            diagnostic = "FreeCAD did not produce its native 3D screenshot.";
            return false;
        }
        try
        {
            using var bitmap = new Bitmap(path);
            if (bitmap.Width < 320 || bitmap.Height < 200)
            {
                diagnostic = $"Screenshot dimensions are too small: {bitmap.Width}x{bitmap.Height}.";
                return false;
            }
            var colors = new HashSet<int>();
            var minLuma = 255;
            var maxLuma = 0;
            var stepX = Math.Max(1, bitmap.Width / 64);
            var stepY = Math.Max(1, bitmap.Height / 36);
            for (var y = 0; y < bitmap.Height; y += stepY)
            for (var x = 0; x < bitmap.Width; x += stepX)
            {
                var color = bitmap.GetPixel(x, y);
                colors.Add(color.ToArgb());
                var luma = (color.R * 299 + color.G * 587 + color.B * 114) / 1000;
                minLuma = Math.Min(minLuma, luma);
                maxLuma = Math.Max(maxLuma, luma);
            }
            var dynamicRange = maxLuma - minLuma;
            var rendered = colors.Count >= 8 && dynamicRange >= 18 && LastShapeObjectCount > 0;
            diagnostic = $"screenshot={bitmap.Width}x{bitmap.Height}, sampledColors={colors.Count}, lumaRange={dynamicRange}, shapeObjects={LastShapeObjectCount}";
            return rendered;
        }
        catch (Exception exception)
        {
            diagnostic = "Unable to inspect FreeCAD screenshot: " + exception.Message;
            return false;
        }
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) StopViewer();
        base.Dispose(disposing);
    }

    private ViewerReady LaunchAndWait(string stepPath, TimeSpan timeout, CancellationToken token)
    {
        var freeCad = FindExecutable()
                      ?? throw new FileNotFoundException(
                          "Official FreeCAD runtime was not found. Use the complete package or configure ASTERMAX_FREECAD_ROOT.");
        if (!File.Exists(stepPath)) throw new FileNotFoundException("STEP file does not exist.", stepPath);

        _runtimeRoot = ResolveRuntimeRoot(Path.GetDirectoryName(freeCad)!);
        _baselineFreeCadIds = EnumerateFreeCadProcessIds();
        _ownedProcessIds.Clear();

        var evidenceRoot = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EVIDENCE_DIR");
        var preserveEvidence = !string.IsNullOrWhiteSpace(evidenceRoot);
        var root = preserveEvidence
            ? Path.GetFullPath(evidenceRoot!)
            : Path.Combine(Path.GetTempPath(), "AsterMax", "freecad-viewer-v4", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        _sessionDirectory = preserveEvidence ? null : root;
        var unique = preserveEvidence ? Guid.NewGuid().ToString("N")[..8] : "session";
        var readyPath = Path.Combine(root, $"freecad-viewer-{unique}.json");
        var bootstrapPath = Path.Combine(root, $"freecad-bootstrap-{unique}.json");
        var screenshotPath = Path.Combine(root, $"freecad-viewer-{unique}.png");
        _commandPath = Path.Combine(root, $"freecad-command-{unique}.txt");

        var userRoot = Path.Combine(root, "user");
        Directory.CreateDirectory(userRoot);
        StageBridgeModule(userRoot, _runtimeRoot);

        var startInfo = new ProcessStartInfo(freeCad)
        {
            UseShellExecute = false,
            CreateNoWindow = false,
            WorkingDirectory = Path.GetDirectoryName(freeCad) ?? _runtimeRoot,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        // No .py argument. InitGui.py is discovered through FreeCAD's normal module loader.
        startInfo.Environment["ASTERMAX_VIEWER_STEP"] = Path.GetFullPath(stepPath);
        startInfo.Environment["ASTERMAX_VIEWER_READY"] = readyPath;
        startInfo.Environment["ASTERMAX_VIEWER_BOOTSTRAP"] = bootstrapPath;
        startInfo.Environment["ASTERMAX_VIEWER_SCREENSHOT"] = screenshotPath;
        startInfo.Environment["ASTERMAX_VIEWER_COMMAND"] = _commandPath;
        startInfo.Environment["FREECAD_USER_HOME"] = userRoot;
        startInfo.Environment["FREECAD_USER_DATA"] = userRoot;
        ConfigureRuntimeEnvironment(startInfo, freeCad);
        if (Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_FORCE_SOFTWARE_OPENGL") == "1")
            startInfo.Environment["QT_OPENGL"] = "software";

        _launcherProcess = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!_launcherProcess.Start()) throw new InvalidOperationException("Windows could not start the FreeCAD engine.");
        _ownedProcessIds.Add(_launcherProcess.Id);
        _stdoutTask = _launcherProcess.StandardOutput.ReadToEndAsync();
        _stderrTask = _launcherProcess.StandardError.ReadToEndAsync();
        WriteEvidence($"v4-start pid={_launcherProcess.Id} exe={freeCad} runtime={_runtimeRoot} step={stepPath}");

        var watch = Stopwatch.StartNew();
        var lastBootstrap = "not-entered";
        while (watch.Elapsed < timeout)
        {
            token.ThrowIfCancellationRequested();
            CaptureNewRuntimeProcesses();

            if (File.Exists(bootstrapPath))
            {
                var text = SafeReadText(bootstrapPath);
                if (!string.IsNullOrWhiteSpace(text) && !string.Equals(text, lastBootstrap, StringComparison.Ordinal))
                {
                    lastBootstrap = text;
                    WriteEvidence("v4-bootstrap " + OneLine(text));
                }
            }

            if (File.Exists(readyPath))
            {
                var ready = ReadReadyFile(readyPath);
                if (!ready.Ok)
                    throw new InvalidOperationException(
                        $"FreeCAD bridge reached phase '{ready.Phase ?? "unknown"}' but failed: {ready.Error ?? "unknown error"}. " +
                        $"Traceback: {OneLine(ready.Traceback)}");
                if (ready.Hwnd == 0) throw new InvalidDataException("FreeCAD returned a zero QMainWindow HWND.");
                if (ready.Objects <= 0 || ready.ShapeObjects <= 0)
                    throw new InvalidDataException($"FreeCAD imported no drawable shape (objects={ready.Objects}, shapes={ready.ShapeObjects}).");
                if (string.IsNullOrWhiteSpace(ready.Screenshot) || !File.Exists(ready.Screenshot))
                    throw new InvalidDataException("FreeCAD did not save native viewer PNG evidence.");

                BindWindowOwnerProcess(new IntPtr(ready.Hwnd));
                CaptureNewRuntimeProcesses();
                WriteEvidence(
                    $"v4-ready hwnd=0x{ready.Hwnd:X} ownerPid={ViewerProcessId} phase={ready.Phase} ownedPids={string.Join(',', _ownedProcessIds.Order())}");
                return ready;
            }

            Thread.Sleep(70);
        }

        var launcherState = _launcherProcess is null
            ? "launcher unavailable"
            : SafeHasExited(_launcherProcess)
                ? $"starter exited code {SafeExitCode(_launcherProcess)}"
                : "starter still running";
        var runtimeProcesses = DescribeOwnedProcesses();
        throw new TimeoutException(
            $"FreeCAD did not publish a native viewer within {timeout.TotalSeconds:0} s ({launcherState}). " +
            $"Bootstrap={OneLine(lastBootstrap)}. Engine={freeCad}. RuntimeProcesses={runtimeProcesses}. " +
            $"STDOUT: {OneLine(SafeTaskResult(_stdoutTask))} STDERR: {OneLine(SafeTaskResult(_stderrTask))}");
    }

    private void StageBridgeModule(string userRoot, string runtimeRoot)
    {
        var source = Path.Combine(AppContext.BaseDirectory, "FreeCAD", "AsterMaxBridge");
        if (!Directory.Exists(source))
            throw new DirectoryNotFoundException("AsterMax FreeCAD InitGui bridge is missing: " + source);

        // User module location is session-isolated and writable even for Program Files installs.
        CopyModule(source, Path.Combine(userRoot, "Mod", "AsterMaxBridge"));

        // Dedicated bundled runtimes are writable. Staging here as well makes startup robust
        // across FreeCAD distributions that differ in their FREECAD_USER_HOME scan order.
        try { CopyModule(source, Path.Combine(runtimeRoot, "Mod", "AsterMaxBridge")); }
        catch (UnauthorizedAccessException) { }
        catch (IOException) { }
    }

    private static void CopyModule(string source, string target)
    {
        Directory.CreateDirectory(target);
        foreach (var file in Directory.EnumerateFiles(source, "*.py", SearchOption.TopDirectoryOnly))
            File.Copy(file, Path.Combine(target, Path.GetFileName(file)), true);
    }

    private ViewerReady ReadReadyFile(string path)
    {
        for (var retry = 0; retry < 10; retry++)
        {
            try
            {
                var ready = JsonSerializer.Deserialize<ViewerReady>(File.ReadAllText(path));
                if (ready is not null) return ready;
            }
            catch (IOException) { }
            catch (JsonException) { }
            Thread.Sleep(40);
        }
        throw new InvalidDataException("FreeCAD ready JSON could not be parsed.");
    }

    private void BindWindowOwnerProcess(IntPtr hwnd)
    {
        GetWindowThreadProcessId(hwnd, out var processId);
        if (processId == 0) throw new InvalidOperationException("Unable to resolve the process that owns the FreeCAD QMainWindow.");
        _ownedProcessIds.Add((int)processId);
        try
        {
            _windowProcess?.Dispose();
            _windowProcess = Process.GetProcessById((int)processId);
        }
        catch (Exception exception)
        {
            throw new InvalidOperationException($"FreeCAD window owner PID {processId} is not alive.", exception);
        }
    }

    private void CompleteEmbedding(ViewerReady ready)
    {
        EmbedWindow(new IntPtr(ready.Hwnd));
        _lastReady = ready;
        _state.Visible = false;
        Visible = true;
        BringToFront();
        WriteEvidence(
            $"v4-embedded hwnd=0x{ready.Hwnd:X} pid={ViewerProcessId} objects={ready.Objects} shapes={ready.ShapeObjects} screenshot={ready.Screenshot}");
    }

    private void ShowLoadingState()
    {
        Visible = true;
        BringToFront();
        SetState("Starting native CAD engine…\nFreeCAD is booting through Mod/InitGui (SolidFreeCAD runtime strategy).\nAsterMax remains the application shell.");
    }

    private void StopViewerCore(bool incrementGeneration)
    {
        if (incrementGeneration) Interlocked.Increment(ref _generation);
        try { _launchCancellation?.Cancel(); } catch { }
        _launchCancellation?.Dispose();
        _launchCancellation = null;
        if (_embeddedWindow != IntPtr.Zero)
        {
            try { ShowWindow(_embeddedWindow, SwHide); } catch { }
            _embeddedWindow = IntPtr.Zero;
        }
        StopOwnedProcesses();
        _lastReady = null;
        _commandPath = null;
        Visible = false;
        _state.Visible = true;
        _state.Text = "FreeCAD native CAD engine is idle.";
        CleanupSessionDirectory();
    }

    private void StopOwnedProcesses()
    {
        CaptureNewRuntimeProcesses();
        var ids = _ownedProcessIds.OrderDescending().ToArray();
        foreach (var id in ids)
        {
            if (_baselineFreeCadIds.Contains(id)) continue;
            try
            {
                using var process = Process.GetProcessById(id);
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
            catch { }
        }
        foreach (var id in ids)
        {
            if (_baselineFreeCadIds.Contains(id)) continue;
            try
            {
                using var process = Process.GetProcessById(id);
                process.WaitForExit(3000);
            }
            catch { }
        }
        try { _windowProcess?.Dispose(); } catch { }
        try { _launcherProcess?.Dispose(); } catch { }
        _windowProcess = null;
        _launcherProcess = null;
        _stdoutTask = null;
        _stderrTask = null;
        _ownedProcessIds.Clear();
    }

    private void CaptureNewRuntimeProcesses()
    {
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                if (!process.ProcessName.Contains("freecad", StringComparison.OrdinalIgnoreCase)) continue;
                if (_baselineFreeCadIds.Contains(process.Id)) continue;
                var path = TryGetExecutablePath(process);
                if (!string.IsNullOrWhiteSpace(_runtimeRoot) && !string.IsNullOrWhiteSpace(path) &&
                    !path.StartsWith(_runtimeRoot, StringComparison.OrdinalIgnoreCase))
                    continue;
                _ownedProcessIds.Add(process.Id);
            }
            catch { }
            finally { process.Dispose(); }
        }
    }

    private static HashSet<int> EnumerateFreeCadProcessIds()
    {
        var ids = new HashSet<int>();
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                if (process.ProcessName.Contains("freecad", StringComparison.OrdinalIgnoreCase)) ids.Add(process.Id);
            }
            catch { }
            finally { process.Dispose(); }
        }
        return ids;
    }

    private string DescribeOwnedProcesses()
    {
        var values = new List<string>();
        foreach (var id in _ownedProcessIds.Order())
        {
            try
            {
                using var process = Process.GetProcessById(id);
                values.Add($"{id}:{process.ProcessName}:{TryGetExecutablePath(process) ?? "?"}");
            }
            catch { values.Add($"{id}:exited"); }
        }
        return values.Count == 0 ? "none" : string.Join(" | ", values);
    }

    private static string? TryGetExecutablePath(Process process)
    {
        try { return process.MainModule?.FileName; }
        catch { return null; }
    }

    private void ConfigureRuntimeEnvironment(ProcessStartInfo startInfo, string freeCad)
    {
        var runtimeRoot = _runtimeRoot ?? ResolveRuntimeRoot(Path.GetDirectoryName(freeCad)!);
        var entries = new[]
        {
            Path.GetDirectoryName(freeCad)!,
            runtimeRoot,
            Path.Combine(runtimeRoot, "bin"),
            Path.Combine(runtimeRoot, "Scripts"),
            Path.Combine(runtimeRoot, "lib"),
            Path.Combine(runtimeRoot, "lib", "qt6", "bin"),
            Path.Combine(runtimeRoot, "Library", "bin"),
            Path.Combine(runtimeRoot, "Library", "usr", "bin")
        }.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase);
        var currentPath = startInfo.Environment.TryGetValue("PATH", out var path)
            ? path
            : Environment.GetEnvironmentVariable("PATH");
        startInfo.Environment["PATH"] = string.Join(";", entries.Concat(new[] { currentPath ?? string.Empty }));

        // SolidFreeCAD's proven portable Windows launcher explicitly sets PYTHONHOME to the
        // environment root. Apply it only when the runtime actually resembles a Python root.
        if (Directory.Exists(Path.Combine(runtimeRoot, "Lib")) ||
            Directory.EnumerateFiles(runtimeRoot, "python*.dll", SearchOption.TopDirectoryOnly).Any())
            startInfo.Environment["PYTHONHOME"] = runtimeRoot;

        try
        {
            var qwindows = Directory.EnumerateFiles(runtimeRoot, "qwindows.dll", SearchOption.AllDirectories).FirstOrDefault();
            if (qwindows is not null)
            {
                var platform = Path.GetDirectoryName(qwindows)!;
                startInfo.Environment["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform;
                var plugins = Directory.GetParent(platform)?.FullName;
                if (!string.IsNullOrWhiteSpace(plugins)) startInfo.Environment["QT_PLUGIN_PATH"] = plugins;
                startInfo.Environment["QT_QPA_PLATFORM"] = "windows";
            }

            if (Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_FORCE_SOFTWARE_OPENGL") == "1")
            {
                var softwareGl = Directory.EnumerateFiles(runtimeRoot, "opengl32sw.dll", SearchOption.AllDirectories).FirstOrDefault();
                if (softwareGl is not null)
                    startInfo.Environment["QT_OPENGL_DLL"] = softwareGl;
            }
        }
        catch (UnauthorizedAccessException) { }
    }

    internal static string ResolveRuntimeRoot(string exeDirectory)
    {
        var current = new DirectoryInfo(exeDirectory);
        for (var i = 0; i < 6; i++)
        {
            if (Directory.Exists(Path.Combine(current.FullName, "Mod")) ||
                Directory.Exists(Path.Combine(current.FullName, "lib")) ||
                Directory.Exists(Path.Combine(current.FullName, "Library")))
                return current.FullName;
            if (current.Parent is null) break;
            current = current.Parent;
        }
        return exeDirectory;
    }

    private void EmbedWindow(IntPtr window)
    {
        if (window == IntPtr.Zero) throw new ArgumentException("Cannot embed a zero HWND.", nameof(window));
        if (!IsHandleCreated) CreateControl();
        ShowWindow(window, SwHide);
        SetLastError(0);
        var previousParent = SetParent(window, Handle);
        var error = Marshal.GetLastWin32Error();
        if (previousParent == IntPtr.Zero && error != 0)
            throw new System.ComponentModel.Win32Exception(error, "SetParent failed for the FreeCAD QMainWindow.");

        var style = GetWindowLongPtr(window, GwlStyle).ToInt64();
        style &= ~(WsCaption | WsThickFrame | WsMinimizeBox | WsMaximizeBox | WsSysMenu);
        style |= WsChild | WsVisible;
        SetWindowLongPtr(window, GwlStyle, new IntPtr(style));
        SetWindowPos(window, IntPtr.Zero, 0, 0, Math.Max(1, ClientSize.Width), Math.Max(1, ClientSize.Height),
            SwpNoZOrder | SwpNoActivate | SwpFrameChanged);
        ShowWindow(window, SwShow);
        _embeddedWindow = window;
        ResizeEmbeddedWindow();
        if (GetParent(window) != Handle)
            throw new InvalidOperationException("FreeCAD HWND was not parented to the AsterMax graphics host.");
    }

    private void ResizeEmbeddedWindow()
    {
        if (_embeddedWindow == IntPtr.Zero || !IsHandleCreated) return;
        MoveWindow(_embeddedWindow, 0, 0, Math.Max(1, ClientSize.Width), Math.Max(1, ClientSize.Height), true);
    }

    private void CleanupSessionDirectory()
    {
        if (string.IsNullOrWhiteSpace(_sessionDirectory)) return;
        try { if (Directory.Exists(_sessionDirectory)) Directory.Delete(_sessionDirectory, true); }
        catch { }
        _sessionDirectory = null;
    }

    private void SetState(string text)
    {
        _state.Text = text;
        _state.Visible = true;
        Visible = true;
        BringToFront();
        Invalidate();
    }

    private static string SafeReadText(string path)
    {
        try { return File.ReadAllText(path); }
        catch { return string.Empty; }
    }

    private static string OneLine(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return string.Empty;
        var text = value.Replace('\r', ' ').Replace('\n', ' ').Trim();
        return text.Length <= 900 ? text : text[..900] + "…";
    }

    private static bool SafeHasExited(Process? process)
    {
        try { return process is null || process.HasExited; }
        catch { return true; }
    }

    private static int? SafeExitCode(Process? process)
    {
        try { return process is { HasExited: true } ? process.ExitCode : null; }
        catch { return null; }
    }

    private static string SafeTaskResult(Task<string>? task)
    {
        if (task is null) return string.Empty;
        try { return task.IsCompletedSuccessfully ? task.Result : string.Empty; }
        catch { return string.Empty; }
    }

    private static void WriteEvidence(string line)
    {
        var path = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EMBED_LOG");
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            File.AppendAllText(path, $"{DateTimeOffset.Now:O} | {line}{Environment.NewLine}");
        }
        catch { }
    }

    [DllImport("kernel32.dll")]
    private static extern void SetLastError(uint errorCode);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetParent(IntPtr child, IntPtr newParent);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr GetParent(IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr GetWindowLongPtr(IntPtr window, int index);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr window, int index, IntPtr value);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool MoveWindow(IntPtr window, int x, int y, int width, int height, bool repaint);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(IntPtr window, IntPtr insertAfter, int x, int y, int width, int height, uint flags);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr window, int command);

    internal sealed class ViewerReady
    {
        [JsonPropertyName("ok")] public bool Ok { get; set; }
        [JsonPropertyName("phase")] public string? Phase { get; set; }
        [JsonPropertyName("pid")] public int Pid { get; set; }
        [JsonPropertyName("hwnd")] public long Hwnd { get; set; }
        [JsonPropertyName("document")] public string? Document { get; set; }
        [JsonPropertyName("objects")] public int Objects { get; set; }
        [JsonPropertyName("visible_objects")] public int VisibleObjects { get; set; }
        [JsonPropertyName("shape_objects")] public int ShapeObjects { get; set; }
        [JsonPropertyName("step")] public string? Step { get; set; }
        [JsonPropertyName("screenshot")] public string? Screenshot { get; set; }
        [JsonPropertyName("freecad_version")] public string? FreeCadVersion { get; set; }
        [JsonPropertyName("error")] public string? Error { get; set; }
        [JsonPropertyName("traceback")] public string? Traceback { get; set; }
    }
}