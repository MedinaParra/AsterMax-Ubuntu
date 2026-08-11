namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private Panel? _graphicsViewportHost;

    /// <summary>
    /// Installs one permanent graphics host before any STEP import occurs.
    ///
    /// The legacy MechanicalViewport and ResponsiveCadMeshCanvas must never be moved into
    /// unrelated layout parents after the form is already visible. Field testing showed
    /// that doing so could leave the CAD control alive but not painted, producing a blank
    /// white graphics area even though Geometry and Details were valid.
    ///
    /// This host owns the complete drawable area below the graphics toolbar for the lifetime
    /// of the form. Importing CAD only changes which renderer is visible/frontmost.
    /// </summary>
    private void InitializeDedicatedGraphicsHost()
    {
        if (_graphicsViewportHost is not null) return;
        var outer = _viewport.Parent;
        if (outer is null)
            throw new InvalidOperationException("Graphics viewport has no layout parent.");

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

        outer.SuspendLayout();
        try
        {
            outer.Controls.Remove(_viewport);
            _viewport.Dock = DockStyle.Fill;
            _viewport.Visible = true;
            host.Controls.Add(_viewport);

            // New CAD canvases are normalized immediately when StableInteraction promotes
            // them from the legacy viewport. This removes the fragile Dock=None/Anchor path.
            host.ControlAdded += (_, eventArgs) =>
            {
                if (eventArgs.Control is not ResponsiveCadMeshCanvas cad) return;
                cad.Anchor = AnchorStyles.None;
                cad.Dock = DockStyle.Fill;
                cad.Visible = true;
                cad.BringToFront();
                host.PerformLayout();
                cad.Invalidate();
            };

            outer.Controls.Add(host);
            host.SendToBack();
            _graphicsTools.BringToFront();
            _graphicsViewportHost = host;
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
}
