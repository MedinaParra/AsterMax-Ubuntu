namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private Panel? _graphicsViewportHost;
    private FreeCadNativeViewerHost? _freeCadNativeViewer;

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

        // Preserve the exact original z-order occupied by MechanicalViewport. Re-adding a
        // Dock=Fill control at a different z-order was the source of the previous white
        // workspace regression on physical Windows even though structural CI still passed.
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

        var freeCad = new FreeCadNativeViewerHost();

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

            // The legacy compatibility adapter can still be promoted here by the existing
            // interaction controller, but when FreeCAD is available it deliberately has an
            // empty region and never paints over the native Qt/Coin3D child window.
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

    internal FreeCadNativeViewerHost RequireFreeCadNativeViewer()
    {
        InitializeDedicatedGraphicsHost();
        return _freeCadNativeViewer
               ?? throw new InvalidOperationException("FreeCAD native viewer host was not initialized.");
    }
}