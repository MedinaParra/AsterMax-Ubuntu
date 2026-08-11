using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

/// <summary>
/// Embeds the official FreeCAD Qt/Coin3D viewer as a native child window.
/// The Windows FreeCAD package can start through a short-lived launcher, so ownership is
/// bound to the process that actually owns the QMainWindow HWND returned by the bridge.
/// </summary>
internal sealed class FreeCadNativeViewerHost : Panel
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
        Text = "FreeCAD native viewer is idle."
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
            try
            {
                return _windowProcess is { HasExited: false } && GetParent(_embeddedWindow) == Handle;
            }
            catch { return false; }
        }
    }

    public IntPtr EmbeddedWindow => _embeddedWindow;
    public int? ViewerProcessId
    {
        get
        {
            try { return _windowProcess is { HasExited: false } ? _windowProcess.Id : null; }
            catch { return null; }
        }
    }
    public string? LastScreenshotPath => _lastReady?.Screenshot;
    public int LastObjectCount => _lastReady?.Objects ?? 0;
    public int LastShapeObjectCount => _lastReady?.ShapeObjects ?? 0;

    public FreeCadNativeViewerHost()
    {
        Name = "FreeCadNativeViewerHost";
        Dock = DockStyle.Fill;
        Margin = Padding.Empty;
        Padding = Padding.Empty;
        BackColor = Color.FromArgb(236, 242, 248);
        Visible = false;
        Controls.Add(_state);
        Resize += (_, _) => ResizeEmbeddedWindow();
    }

    public static string? FindExecutable()
    {
        foreach (var explicitPath in new[]
                 {
                     Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EXE"),
                     Environment.GetEnvironmentVariable("FREECAD_EXE")
                 })
        {
            if (!string.IsNullOrWhiteSpace(explicitPath) && File.Exists(explicitPath))
                return Path.GetFullPath(explicitPath);
        }

        var bundledRoot = Path.Combine(AppContext.BaseDirectory, "tools", "freecad");
        if (Directory.Exists(bundledRoot))
        {
            try
            {
                var bundled = Directory.EnumerateFiles(bundledRoot, "FreeCAD.exe", SearchOption.AllDirectories)
                    .FirstOrDefault(path => !path.Contains("uninstall", StringComparison.OrdinalIgnoreCase));
                if (bundled is not null) return bundled;
            }
            catch (UnauthorizedAccessException) { }
        }

        foreach (var candidate in new[]
                 {
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD 1.1", "FreeCAD.exe"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD 1.1", "bin", "FreeCAD.exe"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD", "bin", "FreeCAD.exe")
                 })
            if (File.Exists(candidate)) return candidate;
        return null;
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
            WriteEvidence("viewer-failed " + exception);
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
            var ready = LaunchAndWait(
                stepPath,
                timeout ?? TimeSpan.FromSeconds(50),
                _launchCancellation.Token);
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
            WriteEvidence($"command-failed command={command} error={exception.Message}");
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
            var minimumLuma = 255;
            var maximumLuma = 0;
            var stepX = Math.Max(1, bitmap.Width / 64);
            var stepY = Math.Max(1, bitmap.Height / 36);
            for (var y = 0; y < bitmap.Height; y += stepY)
            for (var x = 0; x < bitmap.Width; x += stepX)
            {
                var color = bitmap.GetPixel(x, y);
                colors.Add(color.ToArgb());
                var luma = (color.R * 299 + color.G * 587 + color.B * 114) / 1000;
                minimumLuma = Math.Min(minimumLuma, luma);
                maximumLuma = Math.Max(maximumLuma, luma);
            }
            var dynamicRange = maximumLuma - minimumLuma;
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
                          "Official FreeCAD runtime was not found. Use the complete package or set ASTERMAX_FREECAD_EXE.");
        var script = Path.Combine(AppContext.BaseDirectory, "FreeCAD", "astermax_freecad_viewer.py");
        if (!File.Exists(script)) throw new FileNotFoundException("FreeCAD viewer bridge script is missing.", script);
        if (!File.Exists(stepPath)) throw new FileNotFoundException("STEP file does not exist.", stepPath);

        _runtimeRoot = ResolveRuntimeRoot(Path.GetDirectoryName(freeCad)!);
        _baselineFreeCadIds = EnumerateFreeCadProcessIds();
        _ownedProcessIds.Clear();

        var evidenceRoot = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EVIDENCE_DIR");
        var preserveEvidence = !string.IsNullOrWhiteSpace(evidenceRoot);
        var root = preserveEvidence
            ? Path.GetFullPath(evidenceRoot!)
            : Path.Combine(Path.GetTempPath(), "AsterMax", "freecad-viewer", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        _sessionDirectory = preserveEvidence ? null : root;
        var unique = preserveEvidence ? Guid.NewGuid().ToString("N")[..8] : "session";
        var readyPath = Path.Combine(root, $"freecad-viewer-{unique}.json");
        var screenshotPath = Path.Combine(root, $"freecad-viewer-{unique}.png");
        _commandPath = Path.Combine(root, $"freecad-command-{unique}.txt");

        var startInfo = new ProcessStartInfo(freeCad)
        {
            UseShellExecute = false,
            CreateNoWindow = false,
            WorkingDirectory = Path.GetDirectoryName(freeCad) ?? AppContext.BaseDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        startInfo.ArgumentList.Add(script);
        startInfo.Environment["ASTERMAX_VIEWER_STEP"] = Path.GetFullPath(stepPath);
        startInfo.Environment["ASTERMAX_VIEWER_READY"] = readyPath;
        startInfo.Environment["ASTERMAX_VIEWER_SCREENSHOT"] = screenshotPath;
        startInfo.Environment["ASTERMAX_VIEWER_COMMAND"] = _commandPath;
        var userRoot = Path.Combine(root, "user");
        Directory.CreateDirectory(userRoot);
        startInfo.Environment["FREECAD_USER_HOME"] = userRoot;
        startInfo.Environment["FREECAD_USER_DATA"] = userRoot;
        ConfigureRuntimeEnvironment(startInfo, freeCad);
        if (Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_FORCE_SOFTWARE_OPENGL") == "1")
            startInfo.Environment["QT_OPENGL"] = "software";

        _launcherProcess = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!_launcherProcess.Start()) throw new InvalidOperationException("Windows could not start FreeCAD.exe.");
        _ownedProcessIds.Add(_launcherProcess.Id);
        _stdoutTask = _launcherProcess.StandardOutput.ReadToEndAsync();
        _stderrTask = _launcherProcess.StandardError.ReadToEndAsync();
        WriteEvidence($"launcher-start pid={_launcherProcess.Id} exe={freeCad} step={stepPath}");

        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < timeout)
        {
            token.ThrowIfCancellationRequested();
            CaptureNewRuntimeProcesses();

            if (File.Exists(readyPath))
            {
                var ready = ReadReadyFile(readyPath);
                if (!ready.Ok)
                    throw new InvalidOperationException("FreeCAD viewer reported: " + (ready.Error ?? "unknown error"));
                if (ready.Hwnd == 0) throw new InvalidDataException("FreeCAD returned a zero QMainWindow HWND.");
                if (ready.Objects <= 0 || ready.ShapeObjects <= 0)
                    throw new InvalidDataException($"FreeCAD imported no drawable shape (objects={ready.Objects}, shapes={ready.ShapeObjects}).");
                if (string.IsNullOrWhiteSpace(ready.Screenshot) || !File.Exists(ready.Screenshot))
                    throw new InvalidDataException("FreeCAD did not save native viewer PNG evidence.");

                BindWindowOwnerProcess(new IntPtr(ready.Hwnd));
                CaptureNewRuntimeProcesses();
                WriteEvidence(
                    $"ready-pass hwnd=0x{ready.Hwnd:X} ownerPid={ViewerProcessId} launcherExited={SafeHasExited(_launcherProcess)} ownedPids={string.Join(',', _ownedProcessIds.Order())}");
                return ready;
            }

            // FreeCAD's official Windows package is allowed to replace its launcher with
            // the real GUI process. Do not treat launcher exit code 0 as application exit.
            Thread.Sleep(70);
        }

        var launcherState = _launcherProcess is null
            ? "launcher unavailable"
            : SafeHasExited(_launcherProcess)
                ? $"launcher exited code {SafeExitCode(_launcherProcess)}"
                : "launcher still running";
        throw new TimeoutException(
            $"FreeCAD native viewer did not become ready within {timeout.TotalSeconds:0} s ({launcherState}). " +
            $"STDOUT: {SafeTaskResult(_stdoutTask)} STDERR: {SafeTaskResult(_stderrTask)}");
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

    private void CaptureNewRuntimeProcesses()
    {
        foreach (var process in Process.GetProcesses())
        {
            try
            {
                if (!process.ProcessName.Contains("freecad", StringComparison.OrdinalIgnoreCase)) continue;
                if (_baselineFreeCadIds.Contains(process.Id)) continue;
                var path = TryGetExecutablePath(process);
                if (!string.IsNullOrWhiteSpace(_runtimeRoot) &&
                    !string.IsNullOrWhiteSpace(path) &&
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

    private static string? TryGetExecutablePath(Process process)
    {
        try { return process.MainModule?.FileName; }
        catch { return null; }
    }

    private void CompleteEmbedding(ViewerReady ready)
    {
        EmbedWindow(new IntPtr(ready.Hwnd));
        _lastReady = ready;
        _state.Visible = false;
        Visible = true;
        BringToFront();
        WriteEvidence(
            $"embedded-pass hwnd=0x{ready.Hwnd:X} pid={ViewerProcessId} objects={ready.Objects} shapes={ready.ShapeObjects} screenshot={ready.Screenshot}");
    }

    private void ShowLoadingState()
    {
        Visible = true;
        BringToFront();
        SetState("Starting official FreeCAD 1.1.3 viewer…\nQt/Coin3D/OpenCASCADE rendering is isolated from the AsterMax UI thread.");
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
        _state.Text = "FreeCAD native viewer is idle.";
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

    private void ConfigureRuntimeEnvironment(ProcessStartInfo startInfo, string freeCad)
    {
        var runtimeRoot = _runtimeRoot ?? ResolveRuntimeRoot(Path.GetDirectoryName(freeCad)!);
        var entries = new[]
        {
            Path.GetDirectoryName(freeCad)!,
            runtimeRoot,
            Path.Combine(runtimeRoot, "bin"),
            Path.Combine(runtimeRoot, "lib"),
            Path.Combine(runtimeRoot, "lib", "qt6", "bin"),
            Path.Combine(runtimeRoot, "Library", "bin"),
            Path.Combine(runtimeRoot, "Library", "usr", "bin")
        }.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase);
        var currentPath = startInfo.Environment.TryGetValue("PATH", out var path)
            ? path
            : Environment.GetEnvironmentVariable("PATH");
        startInfo.Environment["PATH"] = string.Join(";", entries.Concat(new[] { currentPath ?? string.Empty }));

        try
        {
            var qwindows = Directory.EnumerateFiles(runtimeRoot, "qwindows.dll", SearchOption.AllDirectories).FirstOrDefault();
            if (qwindows is null) return;
            var platform = Path.GetDirectoryName(qwindows)!;
            startInfo.Environment["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform;
            var plugins = Directory.GetParent(platform)?.FullName;
            if (!string.IsNullOrWhiteSpace(plugins)) startInfo.Environment["QT_PLUGIN_PATH"] = plugins;
            startInfo.Environment["QT_QPA_PLATFORM"] = "windows";
        }
        catch (UnauthorizedAccessException) { }
    }

    private static string ResolveRuntimeRoot(string exeDirectory)
    {
        var current = new DirectoryInfo(exeDirectory);
        for (var i = 0; i < 4; i++)
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