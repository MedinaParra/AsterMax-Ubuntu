namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm
{
    private readonly System.Windows.Forms.Timer _productionUiTimer = new() { Interval = 120 };
    private Form? _operationOverlay;
    private Panel? _emptyViewportCover;
    private Control? _scopeLegend;
    private ToolStrip? _navigationStrip;
    private bool _productionInteractionsInitialized;

    private void InitializeProductionInteractionEnhancements()
    {
        if (_productionInteractionsInitialized) return;
        _productionInteractionsInitialized = true;

        InstallEmptyViewportCover();
        InstallScopeLegend();
        InstallNavigationControls();
        ConfigureDetailsSelectionExperience();

        _outline.AfterSelect += (_, _) => RefreshProductionSelectionFeedback();
        _productionUiTimer.Tick += (_, _) => RefreshProductionUiState();
        _productionUiTimer.Start();
        KeyDown += HandleNavigationShortcut;
        FormClosed += (_, _) =>
        {
            _productionUiTimer.Stop();
            CloseOperationOverlay();
        };
    }

    private void InstallEmptyViewportCover()
    {
        _emptyViewportCover = new Panel
        {
            Dock = DockStyle.Fill,
            BackColor = Color.FromArgb(236, 242, 248),
            TabStop = false
        };
        _viewport.Controls.Add(_emptyViewportCover);
        _emptyViewportCover.BringToFront();
    }

    private void InstallScopeLegend()
    {
        var legend = new FlowLayoutPanel
        {
            AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            BackColor = Color.FromArgb(232, 255, 255, 255),
            Padding = new Padding(8, 5, 8, 5),
            Margin = Padding.Empty
        };
        legend.Controls.Add(LegendItem(Color.FromArgb(255, 183, 48), "Selected face"));
        legend.Controls.Add(LegendItem(Color.FromArgb(0, 166, 160), "Fixed support"));
        legend.Controls.Add(LegendItem(Color.FromArgb(218, 61, 61), "Load / force"));
        _scopeLegend = legend;
    }

    private void InstallNavigationControls()
    {
        _navigationStrip = new ToolStrip
        {
            GripStyle = ToolStripGripStyle.Hidden,
            AutoSize = true,
            BackColor = Color.FromArgb(238, 247, 252),
            ForeColor = Color.FromArgb(38, 51, 63),
            RenderMode = ToolStripRenderMode.System,
            Padding = new Padding(3, 2, 3, 2)
        };
        _navigationStrip.Items.Add(new ToolStripLabel("View"));
        _navigationStrip.Items.Add(NavigationButton("Fit", "Fit model (F)", () => ApplyCadViewPreset(-.55f, 1f, "Fit / isometric")));
        _navigationStrip.Items.Add(NavigationButton("ISO", "Isometric view (0)", () => ApplyCadViewPreset(-.55f, 1f, "Isometric")));
        _navigationStrip.Items.Add(NavigationButton("Front", "Front view (1)", () => ApplyCadViewPreset(0f, 1f, "Front")));
        _navigationStrip.Items.Add(NavigationButton("Right", "Right view (2)", () => ApplyCadViewPreset((float)(Math.PI / 2), 1f, "Right")));
        _navigationStrip.Items.Add(NavigationButton("Back", "Back view (3)", () => ApplyCadViewPreset((float)Math.PI, 1f, "Back")));
        _navigationStrip.Items.Add(NavigationButton("Left", "Left view (4)", () => ApplyCadViewPreset((float)(-Math.PI / 2), 1f, "Left")));
        _navigationStrip.Items.Add(new ToolStripSeparator());
        _navigationStrip.Items.Add(new ToolStripLabel("MMB/Ctrl+drag: orbit · Wheel: zoom"));
    }

    private static ToolStripButton NavigationButton(string text, string toolTip, Action action)
    {
        var button = new ToolStripButton(text)
        {
            DisplayStyle = ToolStripItemDisplayStyle.Text,
            ToolTipText = toolTip,
            AutoSize = true
        };
        button.Click += (_, _) => action();
        return button;
    }

    private void ApplyCadViewPreset(float yaw, float zoom, string name)
    {
        if (_cadCanvas is null)
        {
            _viewport.Fit();
            _statusMain.Text = $"View: {name}";
            return;
        }

        var type = _cadCanvas.GetType();
        type.GetField("_yaw", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)?.SetValue(_cadCanvas, yaw);
        type.GetField("_zoom", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)?.SetValue(_cadCanvas, zoom);
        _cadCanvas.Invalidate();
        _statusMain.Text = $"View: {name}";
    }

    private void HandleNavigationShortcut(object? sender, KeyEventArgs eventArgs)
    {
        if (eventArgs.Modifiers != Keys.None) return;
        switch (eventArgs.KeyCode)
        {
            case Keys.F:
                ApplyCadViewPreset(-.55f, 1f, "Fit / isometric");
                break;
            case Keys.D0:
            case Keys.NumPad0:
                ApplyCadViewPreset(-.55f, 1f, "Isometric");
                break;
            case Keys.D1:
            case Keys.NumPad1:
                ApplyCadViewPreset(0f, 1f, "Front");
                break;
            case Keys.D2:
            case Keys.NumPad2:
                ApplyCadViewPreset((float)(Math.PI / 2), 1f, "Right");
                break;
            case Keys.D3:
            case Keys.NumPad3:
                ApplyCadViewPreset((float)Math.PI, 1f, "Back");
                break;
            case Keys.D4:
            case Keys.NumPad4:
                ApplyCadViewPreset((float)(-Math.PI / 2), 1f, "Left");
                break;
            default:
                return;
        }
        eventArgs.Handled = true;
        eventArgs.SuppressKeyPress = true;
    }

    private static Control LegendItem(Color color, string text)
    {
        var item = new FlowLayoutPanel
        {
            AutoSize = true,
            FlowDirection = FlowDirection.LeftToRight,
            WrapContents = false,
            Margin = new Padding(4, 0, 8, 0)
        };
        item.Controls.Add(new Panel
        {
            Width = 13,
            Height = 13,
            BackColor = color,
            Margin = new Padding(0, 3, 5, 0)
        });
        item.Controls.Add(new Label
        {
            AutoSize = true,
            Text = text,
            ForeColor = Color.FromArgb(45, 55, 66),
            Font = new Font("Segoe UI", 8.2f),
            Margin = new Padding(0, 1, 0, 0)
        });
        return item;
    }

    private void ConfigureDetailsSelectionExperience()
    {
        _details.CellFormatting += (_, eventArgs) =>
        {
            if (eventArgs.RowIndex < 0 || _outline.SelectedNode?.Tag is not ModelObject model) return;
            var property = _details.Rows[eventArgs.RowIndex].Cells[0].Value?.ToString();
            if (property is not ("Geometry" or "CadSurfaceTag" or "Scoping Method")) return;

            var color = model.Kind switch
            {
                ObjectKind.Support => Color.FromArgb(0, 143, 137),
                ObjectKind.Load => Color.FromArgb(198, 48, 48),
                _ => Accent
            };
            eventArgs.CellStyle.ForeColor = color;
            eventArgs.CellStyle.SelectionForeColor = Color.White;
            if (property == "Geometry")
                eventArgs.CellStyle.Font = new Font("Segoe UI Semibold", 9f);
        };

        _details.CellDoubleClick += (_, eventArgs) =>
        {
            if (eventArgs.RowIndex < 0 || _outline.SelectedNode?.Tag is not ModelObject model ||
                model.Kind is not (ObjectKind.Support or ObjectKind.Load)) return;
            var property = _details.Rows[eventArgs.RowIndex].Cells[0].Value?.ToString();
            if (property != "Geometry") return;

            if (_selectedCadSurfaceTag is int selectedTag)
            {
                ScopeCadObject(_outline.SelectedNode, model, selectedTag);
                UpdateDetails(_outline.SelectedNode);
                _statusSelection.Text = $"{model.Name}: Face {selectedTag} assigned";
            }
            else
            {
                _statusSelection.Text = $"Pick a face in the 3D view for {model.Name}";
                Log($"{model.Name}: double-clicked Geometry. Select a highlighted CAD face in the 3D workspace.");
            }
        };

        _details.CellToolTipTextNeeded += (_, eventArgs) =>
        {
            if (eventArgs.RowIndex < 0) return;
            var property = _details.Rows[eventArgs.RowIndex].Cells[0].Value?.ToString();
            if (property == "Geometry")
                eventArgs.ToolTipText = "Double-click to assign the currently selected 3D face, or select a new face in the viewport.";
        };
    }

    private void RefreshProductionSelectionFeedback()
    {
        if (_outline.SelectedNode?.Tag is not ModelObject model) return;
        if (model.Kind is ObjectKind.Support or ObjectKind.Load)
        {
            var symbol = model.Kind == ObjectKind.Support ? "▰" : "➜";
            var meaning = model.Kind == ObjectKind.Support ? "constraint" : "applied load";
            _statusSelection.Text = model.Properties.TryGetValue("CadSurfaceTag", out var tag)
                ? $"{symbol} {model.Name}: Face {tag} ({meaning})"
                : $"{symbol} {model.Name}: select a face ({meaning})";
        }
    }

    private void RefreshProductionUiState()
    {
        if (_emptyViewportCover is not null)
        {
            var shouldCover = string.IsNullOrWhiteSpace(_geometryPath) && _cadCanvas is null;
            _emptyViewportCover.Visible = shouldCover;
            if (shouldCover) _emptyViewportCover.BringToFront();
        }

        if (_cadCanvas is not null && _scopeLegend is not null)
        {
            if (_scopeLegend.Parent != _cadCanvas)
            {
                _scopeLegend.Left = 16;
                _scopeLegend.Top = 112;
                _cadCanvas.Controls.Add(_scopeLegend);
            }
            _scopeLegend.Visible = _cadCanvas.Visible;
            if (_scopeLegend.Visible) _scopeLegend.BringToFront();
        }

        if (_cadCanvas is not null && _navigationStrip is not null)
        {
            if (_navigationStrip.Parent != _cadCanvas)
            {
                _navigationStrip.Left = 16;
                _navigationStrip.Top = 154;
                _cadCanvas.Controls.Add(_navigationStrip);
            }
            _navigationStrip.Visible = _cadCanvas.Visible;
            if (_navigationStrip.Visible) _navigationStrip.BringToFront();
        }

        if (_busy)
            ShowOperationOverlay(CurrentOperationMessage());
        else
            CloseOperationOverlay();
    }

    private string CurrentOperationMessage()
    {
        var status = _statusMain.Text;
        if (status.Contains("STEP", StringComparison.OrdinalIgnoreCase) ||
            status.Contains("OpenCASCADE", StringComparison.OrdinalIgnoreCase))
            return "Importing STEP geometry\nReading topology and building selectable faces…";
        if (status.Contains("mesh", StringComparison.OrdinalIgnoreCase))
            return "Generating finite-element mesh…";
        if (status.Contains("solv", StringComparison.OrdinalIgnoreCase))
            return "Solving mechanical model…";
        return "Processing model…";
    }

    private void ShowOperationOverlay(string message)
    {
        if (_operationOverlay is null || _operationOverlay.IsDisposed)
        {
            var progress = new ProgressBar
            {
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 28,
                Dock = DockStyle.Bottom,
                Height = 8
            };
            var label = new Label
            {
                Name = "OperationMessage",
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = TextMain,
                Font = new Font("Segoe UI Semibold", 11f)
            };
            _operationOverlay = new Form
            {
                Text = "AsterMax",
                FormBorderStyle = FormBorderStyle.FixedToolWindow,
                StartPosition = FormStartPosition.CenterParent,
                ShowInTaskbar = false,
                ControlBox = false,
                Width = 440,
                Height = 145,
                BackColor = Panel,
                TopMost = false
            };
            _operationOverlay.Controls.Add(label);
            _operationOverlay.Controls.Add(progress);
            _operationOverlay.Show(this);
        }

        var messageLabel = _operationOverlay.Controls.Find("OperationMessage", true).FirstOrDefault() as Label;
        if (messageLabel is not null) messageLabel.Text = message;
        if (!_operationOverlay.Visible) _operationOverlay.Show(this);
        _operationOverlay.BringToFront();
    }

    private void CloseOperationOverlay()
    {
        if (_operationOverlay is null) return;
        try { _operationOverlay.Close(); } catch { }
        _operationOverlay.Dispose();
        _operationOverlay = null;
    }
}
