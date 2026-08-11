using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterMax.MechanicalGui;

/// <summary>
/// Hosts the official FreeCAD Qt/Coin3D viewer as an isolated native child window.
/// FreeCAD keeps its own Qt event loop and OpenGL/Coin3D rendering process; AsterMax
/// only owns the Win32 parent surface. This prevents custom WinForms painting from
/// monopolizing or corrupting the Mechanical UI message loop.
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

    private Process? _process;
    private CancellationTokenSource? _launchCancellation;
    private Task<string>? _stdoutTask;
    private Task<string>? _stderrTask;
    private IntPtr _embeddedWindow;
    private string? _sessionDirectory;
    private string? _commandPath;
    private ViewerReady? _lastReady;
    private int _generation;

    public bool IsReady =>
        _embeddedWindow != IntPtr.Zero &&
        _process is { HasExited: false } &&
        GetParent(_embeddedWindow) == Handle;

    public IntPtr EmbeddedWindow => _embeddedWindow;
    public int? ViewerProcessId => _process is { HasExited: false } ? _process.Id : null;
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
                var bundled = Directory.EnumerateFiles(
                        bundledRoot,
                        "FreeCAD.exe",
                        SearchOption.AllDirectories)
                    .FirstOrDefault(path => !path.Contains("uninstall", StringComparison.OrdinalIgnoreCase));
                if (bundled is not null) return bundled;
            }
            catch (UnauthorizedAccessException)
            {
                // Keep searching normal installed locations.
            }
        }

        foreach (var candidate in new[]
                 {
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD 1.1", "bin", "FreeCAD.exe"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD 1.1", "FreeCAD.exe"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FreeCAD", "bin", "FreeCAD.exe")
                 })
        {
            if (File.Exists(candidate)) return candidate;
        }

        return null;
    }

    public async Task<ViewerReady> ShowStepAsync(
        string stepPath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var generation = Interlocked.Increment(ref _generation);
        StopViewer();
        Visible = true;
        BringToFront();
        SetState("Starting official FreeCAD 1.1.3 viewer…\nQt/Coin3D/OpenCASCADE rendering is isolated from the AsterMax UI thread.");

        _launchCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var token = _launchCancellation.Token;
        try
        {
            var ready = await Task.Run(
                () => LaunchAndWait(stepPath, timeout ?? TimeSpan.FromSeconds(45), token),
                token);
            token.ThrowIfCancellationRequested();
            if (generation != _generation)
                throw new OperationCanceledException("A newer FreeCAD viewer session replaced this one.");

            EmbedWindow(new IntPtr(ready.Hwnd));
            _lastReady = ready;
            _state.Visible = false;
            Visible = true;
            BringToFront();
            WriteEvidence(
                $"embedded-pass hwnd=0x{ready.Hwnd:X} pid={ViewerProcessId} objects={ready.Objects} shapes={ready.ShapeObjects} screenshot={ready.Screenshot}");
            return ready;
        }
        catch (Exception exception)
        {
            WriteEvidence("viewer-failed " + exception);
            SetState("FreeCAD native viewer failed to start.\n\n" + exception.Message);
            StopProcessOnly();
            throw;
        }
    }

    /// <summary>
    /// Used by the Windows CI gate so the existing real TreeView/Details smoke cannot race
    /// ahead and delete the STEP before FreeCAD has actually rendered and been embedded.
    /// </summary>
    public ViewerReady ShowStepBlocking(
        string stepPath,
        TimeSpan? timeout = null,
        CancellationToken cancellationToken = default)
    {
        var generation = Interlocked.Increment(ref _generation);
        StopViewer();
        Visible = true;
        BringToFront();
        SetState("Starting official FreeCAD 1.1.3 viewer…");
        _launchCancellation = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        var ready = LaunchAndWait(
            stepPath,
            timeout ?? TimeSpan.FromSeconds(45),
            _launchCancellation.Token);
        if (generation != _generation)
            throw new OperationCanceledException("A newer FreeCAD viewer session replaced this one.");
        EmbedWindow(new IntPtr(ready.Hwnd));
        _lastReady = ready;
        _state.Visible = false;
        Visible = true;
        BringToFront();
        WriteEvidence(
            $"embedded-pass hwnd=0x{ready.Hwnd:X} pid={ViewerProcessId} objects={ready.Objects} shapes={ready.ShapeObjects} screenshot={ready.Screenshot}");
        return ready;
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

    public void StopViewer()
    {
        Interlocked.Increment(ref _generation);
        try { _launchCancellation?.Cancel(); } catch { }
        _launchCancellation?.Dispose();
        _launchCancellation = null;

        if (_embeddedWindow != IntPtr.Zero)
        {
            try { ShowWindow(_embeddedWindow, SwHide); } catch { }
            _embeddedWindow = IntPtr.Zero;
        }

        StopProcessOnly();
        _lastReady = null;
        _commandPath = null;
        Visible = false;
        _state.Visible = true;
        _state.Text = "FreeCAD native viewer is idle.";
        CleanupSessionDirectory();
    }

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
            diagnostic =
                $"screenshot={bitmap.Width}x{bitmap.Height}, sampledColors={colors.Count}, lumaRange={dynamicRange}, shapeObjects={LastShapeObjectCount}";
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
                          "Official FreeCAD runtime was not found. The complete AsterMax package must include tools\\freecad, or ASTERMAX_FREECAD_EXE must point to FreeCAD.exe.");
        var script = Path.Combine(AppContext.BaseDirectory, "FreeCAD", "astermax_freecad_viewer.py");
        if (!File.Exists(script))
            throw new FileNotFoundException("AsterMax FreeCAD viewer script is missing from the application package.", script);
        if (!File.Exists(stepPath))
            throw new FileNotFoundException("STEP file passed to FreeCAD does not exist.", stepPath);

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

        if (string.Equals(
                Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_FORCE_SOFTWARE_OPENGL"),
                "1",
                StringComparison.OrdinalIgnoreCase))
            startInfo.Environment["QT_OPENGL"] = "software";

        _process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!_process.Start())
            throw new InvalidOperationException("Windows could not start FreeCAD.exe.");
        _stdoutTask = _process.StandardOutput.ReadToEndAsync();
        _stderrTask = _process.StandardError.ReadToEndAsync();
        WriteEvidence($"process-start pid={_process.Id} exe={freeCad} step={stepPath}");

        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < timeout)
        {
            token.ThrowIfCancellationRequested();
            if (_process.HasExited)
            {
                var stdout = SafeTaskResult(_stdoutTask);
                var stderr = SafeTaskResult(_stderrTask);
                throw new InvalidOperationException(
                    $"FreeCAD exited before the viewer became ready (code {_process.ExitCode}).\nSTDOUT: {stdout}\nSTDERR: {stderr}");
            }

            if (File.Exists(readyPath))
            {
                ViewerReady? ready = null;
                for (var retry = 0; retry < 8 && ready is null; retry++)
                {
                    try
                    {
                        var json = File.ReadAllText(readyPath);
                        ready = JsonSerializer.Deserialize<ViewerReady>(json);
                    }
                    catch (IOException) { Thread.Sleep(40); }
                    catch (JsonException) { Thread.Sleep(40); }
                }

                if (ready is null)
                    throw new InvalidDataException("FreeCAD ready file could not be parsed.");
                if (!ready.Ok)
                    throw new InvalidOperationException(
                        "FreeCAD viewer reported an import/render error: " + (ready.Error ?? "unknown error"));
                if (ready.Hwnd == 0)
                    throw new InvalidDataException("FreeCAD returned a zero main-window handle.");
                if (ready.Objects <= 0 || ready.ShapeObjects <= 0)
                    throw new InvalidDataException(
                        $"FreeCAD imported no drawable STEP shape (objects={ready.Objects}, shapes={ready.ShapeObjects}).");
                if (string.IsNullOrWhiteSpace(ready.Screenshot) || !File.Exists(ready.Screenshot))
                    throw new InvalidDataException("FreeCAD did not save native viewer evidence PNG.");
                return ready;
            }

            Thread.Sleep(60);
        }

        throw new TimeoutException($"FreeCAD native viewer did not become ready within {timeout.TotalSeconds:0} seconds.");
    }

    private void ConfigureRuntimeEnvironment(ProcessStartInfo startInfo, string freeCad)
    {
        var exeDirectory = Path.GetDirectoryName(freeCad)!;
        var runtimeRoot = ResolveRuntimeRoot(exeDirectory);
        var pathEntries = new List<string>
        {
            exeDirectory,
            runtimeRoot,
            Path.Combine(runtimeRoot, "bin"),
            Path.Combine(runtimeRoot, "Library", "bin"),
            Path.Combine(runtimeRoot, "Library", "usr", "bin")
        };
        pathEntries = pathEntries.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        var currentPath = startInfo.Environment.TryGetValue("PATH", out var existing) ? existing : Environment.GetEnvironmentVariable("PATH");
        startInfo.Environment["PATH"] = string.Join(";", pathEntries.Concat(new[] { currentPath ?? string.Empty }));

        try
        {
            var qwindows = Directory.EnumerateFiles(runtimeRoot, "qwindows.dll", SearchOption.AllDirectories).FirstOrDefault();
            if (qwindows is not null)
            {
                var platform = Path.GetDirectoryName(qwindows)!;
                startInfo.Environment["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform;
                var plugins = Directory.GetParent(platform)?.FullName;
                if (!string.IsNullOrWhiteSpace(plugins))
                    startInfo.Environment["QT_PLUGIN_PATH"] = plugins;
                startInfo.Environment["QT_QPA_PLATFORM"] = "windows";
            }
        }
        catch (UnauthorizedAccessException)
        {
            // FreeCAD can still resolve its own Qt plugins from its normal runtime paths.
        }
    }

    private static string ResolveRuntimeRoot(string exeDirectory)
    {
        var current = new DirectoryInfo(exeDirectory);
        for (var i = 0; i < 4 && current.Parent is not null; i++, current = current.Parent)
        {
            if (Directory.Exists(Path.Combine(current.FullName, "Mod")) ||
                Directory.Exists(Path.Combine(current.FullName, "Library")) ||
                Directory.Exists(Path.Combine(current.FullName, "Ext")))
                return current.FullName;
        }
        return exeDirectory;
    }

    private void EmbedWindow(IntPtr window)
    {
        if (window == IntPtr.Zero) throw new ArgumentException("Cannot embed a zero HWND.", nameof(window));
        if (!IsHandleCreated) CreateControl();
        ShowWindow(window, SwHide);

        var previousParent = SetParent(window, Handle);
        var error = Marshal.GetLastWin32Error();
        if (previousParent == IntPtr.Zero && error != 0)
            throw new System.ComponentModel.Win32Exception(error, "SetParent failed for the FreeCAD main window.");

        var style = GetWindowLongPtr(window, GwlStyle).ToInt64();
        style &= ~(WsCaption | WsThickFrame | WsMinimizeBox | WsMaximizeBox | WsSysMenu);
        style |= WsChild | WsVisible;
        SetWindowLongPtr(window, GwlStyle, new IntPtr(style));
        SetWindowPos(
            window,
            IntPtr.Zero,
            0,
            0,
            Math.Max(1, ClientSize.Width),
            Math.Max(1, ClientSize.Height),
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
        MoveWindow(
            _embeddedWindow,
            0,
            0,
            Math.Max(1, ClientSize.Width),
            Math.Max(1, ClientSize.Height),
            true);
    }

    private void StopProcessOnly()
    {
        if (_process is null) return;
        try
        {
            if (!_process.HasExited)
            {
                try { _process.Kill(entireProcessTree: true); } catch { }
                try { _process.WaitForExit(4000); } catch { }
            }
        }
        finally
        {
            try { _process.Dispose(); } catch { }
            _process = null;
            _stdoutTask = null;
            _stderrTask = null;
        }
    }

    private void CleanupSessionDirectory()
    {
        if (string.IsNullOrWhiteSpace(_sessionDirectory)) return;
        try
        {
            if (Directory.Exists(_sessionDirectory)) Directory.Delete(_sessionDirectory, true);
        }
        catch
        {
            // Temp cleanup is best effort; process termination is the critical invariant.
        }
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

    private static string SafeTaskResult(Task<string>? task)
    {
        if (task is null) return string.Empty;
        try
        {
            return task.IsCompletedSuccessfully ? task.Result : string.Empty;
        }
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

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetParent(IntPtr child, IntPtr newParent);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr GetParent(IntPtr window);

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr GetWindowLongPtr(IntPtr window, int index);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr window, int index, IntPtr value);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool MoveWindow(IntPtr window, int x, int y, int width, int height, bool repaint);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetWindowPos(
        IntPtr window,
        IntPtr insertAfter,
        int x,
        int y,
        int width,
        int height,
        uint flags);

    [DllImport("user32.dll")]
    private static extern bool ShowWindow(IntPtr window, int command);

    internal sealed class ViewerReady
    {
        [JsonPropertyName("ok")]
        public bool Ok { get; set; }

        [JsonPropertyName("hwnd")]
        public long Hwnd { get; set; }

        [JsonPropertyName("document")]
        public string? Document { get; set; }

        [JsonPropertyName("objects")]
        public int Objects { get; set; }

        [JsonPropertyName("visible_objects")]
        public int VisibleObjects { get; set; }

        [JsonPropertyName("shape_objects")]
        public int ShapeObjects { get; set; }

        [JsonPropertyName("step")]
        public string? Step { get; set; }

        [JsonPropertyName("screenshot")]
        public string? Screenshot { get; set; }

        [JsonPropertyName("freecad_version")]
        public string? FreeCadVersion { get; set; }

        [JsonPropertyName("error")]
        public string? Error { get; set; }

        [JsonPropertyName("traceback")]
        public string? Traceback { get; set; }
    }
}