namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private Panel? _graphicsViewportHost;
    private FreeCadNativeViewerHostV4? _freeCadNativeViewer;

    /// <summary>
    /// Owns every graphics surface for the full form lifetime. The original viewport,
    /// compatibility CAD adapter and the official FreeCAD native viewer are siblings;
    /// no renderer is ever nested inside another renderer.
    /// </summary>
    private void InitializeDedicatedGraphicsHost()
    {
        if (_graphicsViewportHost is not null) return;
        var outer = _viewport.Parent;
        if (outer is null)
            throw new InvalidOperationException("Graphics viewport has no layout parent.");

        var originalIndex = outer.Controls.GetChildIndex(_viewport);
        var host = new Panel
        {
            Name = "GraphicsViewportHost",
            Dock = DockStyle.Fill,
            Margin = Padding.Empty,
            Padding = Padding.Empty,
            BackColor = Color.FromArgb(236, 242, 248),
            TabStop = false,
            Visible = true
        };

        // V4 is bootstrapped by FreeCAD's normal Mod/InitGui lifecycle, matching the
        // runtime strategy already proven in SolidFreeCAD. It is not a Workbench.
        var freeCad = new FreeCadNativeViewerHostV4();

        outer.SuspendLayout();
        try
        {
            outer.Controls.Remove(_viewport);
            _viewport.Dock = DockStyle.Fill;
            _viewport.Visible = true;
            host.Controls.Add(_viewport);
            host.Controls.Add(freeCad);
            freeCad.Visible = false;
            _viewport.BringToFront();

            host.ControlAdded += (_, eventArgs) =>
            {
                if (eventArgs.Control is not ResponsiveCadMeshCanvas cad) return;
                cad.Anchor = AnchorStyles.None;
                cad.Dock = DockStyle.Fill;
                host.PerformLayout();
            };

            outer.Controls.Add(host);
            outer.Controls.SetChildIndex(host, Math.Min(originalIndex, outer.Controls.Count - 1));
            _graphicsTools.BringToFront();
            _graphicsViewportHost = host;
            _freeCadNativeViewer = freeCad;
        }
        finally
        {
            outer.ResumeLayout(true);
        }

        host.PerformLayout();
        _viewport.BringToFront();
    }

    private Panel RequireGraphicsViewportHost()
    {
        InitializeDedicatedGraphicsHost();
        return _graphicsViewportHost
               ?? throw new InvalidOperationException("Dedicated graphics host was not initialized.");
    }

    internal FreeCadNativeViewerHostV4 RequireFreeCadNativeViewer()
    {
        InitializeDedicatedGraphicsHost();
        return _freeCadNativeViewer
               ?? throw new InvalidOperationException("FreeCAD native viewer host was not initialized.");
    }
}