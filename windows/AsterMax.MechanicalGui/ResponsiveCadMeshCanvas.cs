namespace AsterMax.MechanicalGui;

/// <summary>
/// Compatibility adapter retained so the existing AsterMax FEM/scoping model does not
/// need to change in the first FreeCAD viewer iteration.
///
/// IMPORTANT: when the official FreeCAD runtime is available this control does not paint
/// CAD at all. It delegates visualization to FreeCadNativeViewerHost, whose renderer lives
/// in the isolated FreeCAD Qt/Coin3D process. That removes the custom WinForms paint loop
/// that caused the physical Windows white-screen/Details regressions.
/// </summary>
internal sealed class ResponsiveCadMeshCanvas : Control
{
    private readonly Action<CadSurfaceSelection> _selectionCallback;
    private SimpleStepSolid? _envelope;
    private CadMesh? _mesh;
    private bool _volumeMesh;
    private bool _nativeMode;

    // Keep these fields for compatibility with the existing view-preset code, which still
    // reflects them during the POC. FreeCAD itself owns interactive orbit/pan/zoom.
    private float _zoom = 1f;
    private float _yaw = -.55f;
    private float _pitch = .45f;

    public ResponsiveCadMeshCanvas(Action<CadSurfaceSelection> selectionCallback)
    {
        _selectionCallback = selectionCallback;
        DoubleBuffered = true;
        ResizeRedraw = true;
        BackColor = Color.FromArgb(236, 242, 248);
        TabStop = false;
    }

    public void SetMesh(SimpleStepSolid envelope, CadMesh mesh, bool volumeMesh)
    {
        _envelope = envelope;
        _mesh = mesh;
        _volumeMesh = volumeMesh;
        _zoom = 1f;
        _yaw = -.55f;
        _pitch = .45f;

        if (FindForm() is MechanicalForm form && FreeCadNativeViewerHost.FindExecutable() is not null)
        {
            _nativeMode = true;
            // Never let this compatibility surface cover the native Qt child window.
            base.SetVisibleCore(false);
            Region = new Region(Rectangle.Empty);

            var native = form.RequireFreeCadNativeViewer();
            var required = string.Equals(
                Environment.GetEnvironmentVariable("ASTERMAX_REQUIRE_FREECAD_VIEWER"),
                "1",
                StringComparison.OrdinalIgnoreCase);

            if (required)
            {
                var ready = native.ShowStepBlocking(envelope.SourcePath, TimeSpan.FromSeconds(50));
                if (!native.IsReady)
                    throw new InvalidOperationException("FreeCAD viewer reached ready state but its HWND is not embedded in AsterMax.");
                if (!native.ScreenshotLooksRendered(out var diagnostic))
                    throw new InvalidOperationException("FreeCAD native screenshot gate failed: " + diagnostic);
                AppendEvidence(
                    $"native-gate-pass freecad={ready.FreeCadVersion} objects={ready.Objects} shapes={ready.ShapeObjects} {diagnostic}");
            }
            else
            {
                _ = LaunchNativeViewerAsync(native, envelope.SourcePath);
            }
            return;
        }

        _nativeMode = false;
        Region = null;
        Visible = true;
        Invalidate();
    }

    public void ClearModel()
    {
        _envelope = null;
        _mesh = null;
        _volumeMesh = false;
        try
        {
            if (FindForm() is MechanicalForm form)
                form.RequireFreeCadNativeViewer().StopViewer();
        }
        catch
        {
            // Form teardown can occur after the graphics host has already been disposed.
        }
        _nativeMode = false;
        Region = null;
        Visible = false;
        Invalidate();
    }

    public void SetView(float yaw, float pitch, float zoom, bool resetPan = true)
    {
        _yaw = yaw;
        _pitch = pitch;
        _zoom = zoom;
        if (FindForm() is MechanicalForm form)
        {
            try
            {
                var native = form.RequireFreeCadNativeViewer();
                if (native.IsReady)
                {
                    var command = Math.Abs(pitch) < .02f
                        ? Math.Abs(yaw) < .15f ? "front"
                        : Math.Abs(yaw - (float)(Math.PI / 2)) < .2f ? "right"
                        : Math.Abs(yaw + (float)(Math.PI / 2)) < .2f ? "left"
                        : Math.Abs(Math.Abs(yaw) - (float)Math.PI) < .2f ? "back"
                        : "iso"
                        : "iso";
                    native.SendCommand(command);
                    native.SendCommand("fit");
                }
            }
            catch { }
        }
        Invalidate();
    }

    public void FitView()
    {
        _yaw = -.55f;
        _pitch = .45f;
        _zoom = 1f;
        if (FindForm() is MechanicalForm form)
        {
            try
            {
                var native = form.RequireFreeCadNativeViewer();
                if (native.IsReady) native.SendCommand("fit");
            }
            catch { }
        }
        Invalidate();
    }

    public void SetScopeMarkers(IEnumerable<int> supportTags, IEnumerable<int> loadTags)
    {
        // Phase 1 intentionally leaves AsterMax/Gmsh scope metadata untouched. Mapping a
        // FreeCAD FaceN selection back to persistent Gmsh/OCC face tags is a separate gate.
        // Keeping this method makes current supports/loads data structures compatible.
    }

    public void SelectSurface(int? tag)
    {
        // Native FreeCAD selection synchronization is implemented in the next POC gate.
        // Do not manufacture a face selection here: that would create false FEM scoping.
    }

    protected override void SetVisibleCore(bool value)
    {
        // Existing AsterMax code still calls cad.Visible=true. In native mode that must not
        // resurrect a blank WinForms control above the embedded FreeCAD HWND.
        base.SetVisibleCore(_nativeMode ? false : value);
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        base.OnPaint(e);
        if (_nativeMode) return;

        e.Graphics.Clear(Color.FromArgb(236, 242, 248));
        using var title = new Font("Segoe UI Semibold", 12f);
        using var body = new Font("Segoe UI", 9.5f);
        using var titleBrush = new SolidBrush(MechanicalForm.TextMain);
        using var bodyBrush = new SolidBrush(MechanicalForm.TextMuted);
        e.Graphics.DrawString("FreeCAD native viewer runtime is not available", title, titleBrush, 28, 32);
        e.Graphics.DrawString(
            "Use the complete AsterMax FreeCAD-viewer package or configure ASTERMAX_FREECAD_EXE.\n" +
            "The old custom CAD painter is intentionally disabled in this POC.",
            body,
            bodyBrush,
            28,
            64);
        if (_mesh is not null && _envelope is not null)
        {
            e.Graphics.DrawString(
                $"STEP is loaded: {Path.GetFileName(_envelope.SourcePath)} · {_mesh.Nodes.Count:N0} nodes · " +
                $"{_mesh.SurfaceTriangles.Count:N0} surface triangles" + (_volumeMesh ? $" · {_mesh.Tetrahedra.Count:N0} TET4" : string.Empty),
                body,
                bodyBrush,
                28,
                118);
        }
    }

    private static async Task LaunchNativeViewerAsync(FreeCadNativeViewerHost native, string stepPath)
    {
        try
        {
            var ready = await native.ShowStepAsync(stepPath, TimeSpan.FromSeconds(50));
            if (!native.IsReady)
                throw new InvalidOperationException("FreeCAD HWND did not remain embedded after launch.");
            AppendEvidence(
                $"native-ready freecad={ready.FreeCadVersion} objects={ready.Objects} shapes={ready.ShapeObjects}");
        }
        catch (OperationCanceledException)
        {
            AppendEvidence("native-viewer-cancelled");
        }
        catch (Exception exception)
        {
            AppendEvidence("native-viewer-failed " + exception);
        }
    }

    private static void AppendEvidence(string text)
    {
        var path = Environment.GetEnvironmentVariable("ASTERMAX_FREECAD_EMBED_LOG");
        if (string.IsNullOrWhiteSpace(path)) return;
        try
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory)) Directory.CreateDirectory(directory);
            File.AppendAllText(path, $"{DateTimeOffset.Now:O} | {text}{Environment.NewLine}");
        }
        catch { }
    }
}