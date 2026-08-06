using System.Reflection;
using System.Runtime.CompilerServices;

namespace AsterMax.MechanicalGui;

internal static class MechanicalInterfaceRoadmapIteration
{
    private static readonly ConditionalWeakTable<AdvancedCadViewport, ViewportCommandBar> Bars = new();
    private static System.Windows.Forms.Timer? _monitor;
    private static bool _installed;

    [ModuleInitializer]
    internal static void Install()
    {
        if (_installed) return;
        _installed = true;
        Application.Idle += StartAfterMessageLoop;
    }

    private static void StartAfterMessageLoop(object? sender, EventArgs eventArgs)
    {
        Application.Idle -= StartAfterMessageLoop;
        if (_monitor is not null) return;

        _monitor = new System.Windows.Forms.Timer { Interval = 350 };
        _monitor.Tick += (_, _) =>
        {
            try
            {
                foreach (Form form in Application.OpenForms.Cast<Form>().ToArray())
                {
                    if (form.IsDisposed || !form.IsHandleCreated) continue;
                    form.KeyPreview = true;
                    foreach (var viewport in Descendants(form).OfType<AdvancedCadViewport>().ToArray())
                        EnsureCommandBar(viewport);
                }
            }
            catch
            {
                // Optional viewport productivity controls must never prevent application startup.
            }
        };
        _monitor.Start();
    }

    private static void EnsureCommandBar(AdvancedCadViewport viewport)
    {
        if (viewport.IsDisposed || !viewport.IsHandleCreated) return;
        if (!Bars.TryGetValue(viewport, out var bar))
        {
            bar = new ViewportCommandBar(viewport);
            viewport.Controls.Add(bar);
            bar.BringToFront();
            Bars.Add(viewport, bar);
            viewport.Resize += (_, _) => bar.Reposition();
            viewport.KeyDown += (_, e) => HandleShortcut(viewport, e);
            viewport.MouseDown += (_, _) => viewport.Focus();
        }
        bar.Reposition();
        bar.Visible = viewport.Visible;
    }

    private static void HandleShortcut(AdvancedCadViewport viewport, KeyEventArgs e)
    {
        var handled = true;
        switch (e.KeyCode)
        {
            case Keys.F:
                ApplyView(viewport, ViewCommand.Fit);
                break;
            case Keys.D0:
            case Keys.NumPad0:
                ApplyView(viewport, ViewCommand.Isometric);
                break;
            case Keys.D1:
            case Keys.NumPad1:
                ApplyView(viewport, ViewCommand.Front);
                break;
            case Keys.D2:
            case Keys.NumPad2:
                ApplyView(viewport, ViewCommand.Right);
                break;
            case Keys.D3:
            case Keys.NumPad3:
                ApplyView(viewport, ViewCommand.Top);
                break;
            case Keys.M:
                ApplyView(viewport, ViewCommand.ToggleMesh);
                break;
            case Keys.Escape:
                ApplyView(viewport, ViewCommand.ClearSelection);
                break;
            default:
                handled = false;
                break;
        }
        if (handled) e.Handled = e.SuppressKeyPress = true;
    }

    internal static void ApplyView(AdvancedCadViewport viewport, ViewCommand command)
    {
        switch (command)
        {
            case ViewCommand.Fit:
                Set(viewport, "_zoom", 1.0);
                Set(viewport, "_pan", PointF.Empty);
                break;
            case ViewCommand.Isometric:
                Set(viewport, "_yaw", -Math.PI / 4.0);
                Set(viewport, "_pitch", Math.PI / 7.0);
                Set(viewport, "_pan", PointF.Empty);
                break;
            case ViewCommand.Front:
                Set(viewport, "_yaw", 0.0);
                Set(viewport, "_pitch", 0.0);
                Set(viewport, "_pan", PointF.Empty);
                break;
            case ViewCommand.Right:
                Set(viewport, "_yaw", -Math.PI / 2.0);
                Set(viewport, "_pitch", 0.0);
                Set(viewport, "_pan", PointF.Empty);
                break;
            case ViewCommand.Top:
                Set(viewport, "_yaw", 0.0);
                Set(viewport, "_pitch", Math.PI / 2.0 - 0.001);
                Set(viewport, "_pan", PointF.Empty);
                break;
            case ViewCommand.ToggleMesh:
                Set(viewport, "_showMesh", !Get<bool>(viewport, "_showMesh"));
                break;
            case ViewCommand.ClearSelection:
                Set<int?>(viewport, "_selectedTag", null);
                var legacy = Get<SelectableCadMeshCanvas?>(viewport, "_legacy");
                legacy?.SelectSurface(null);
                break;
        }
        viewport.Invalidate();
    }

    private static T Get<T>(object target, string name)
    {
        var field = target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
        return field?.GetValue(target) is T value ? value : default!;
    }

    private static void Set<T>(object target, string name, T value)
    {
        target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)?.SetValue(target, value);
    }

    private static IEnumerable<Control> Descendants(Control root)
    {
        foreach (Control child in root.Controls)
        {
            yield return child;
            foreach (var nested in Descendants(child)) yield return nested;
        }
    }
}

internal enum ViewCommand
{
    Fit,
    Isometric,
    Front,
    Right,
    Top,
    ToggleMesh,
    ClearSelection
}

internal sealed class ViewportCommandBar : Panel
{
    private readonly AdvancedCadViewport _viewport;
    private readonly ToolTip _tips = new();

    public ViewportCommandBar(AdvancedCadViewport viewport)
    {
        _viewport = viewport;
        Height = 36;
        Width = 414;
        BackColor = Color.FromArgb(238, 250, 252, 254);
        BorderStyle = BorderStyle.FixedSingle;

        AddButton("Fit", ViewCommand.Fit, "Ajustar a pantalla (F)");
        AddButton("ISO", ViewCommand.Isometric, "Vista isométrica (0)");
        AddButton("Front", ViewCommand.Front, "Vista frontal (1)");
        AddButton("Right", ViewCommand.Right, "Vista derecha (2)");
        AddButton("Top", ViewCommand.Top, "Vista superior (3)");
        AddButton("Mesh", ViewCommand.ToggleMesh, "Mostrar u ocultar malla (M)");
        AddButton("Clear", ViewCommand.ClearSelection, "Limpiar selección (Esc)");
    }

    public void Reposition()
    {
        Left = 14;
        Top = Math.Max(104, _viewport.ClientSize.Height - Height - 14);
        BringToFront();
    }

    private void AddButton(string text, ViewCommand command, string tip)
    {
        var button = new Button
        {
            Text = text,
            Width = text == "Front" || text == "Right" || text == "Clear" ? 58 : 50,
            Height = 28,
            Left = Controls.Cast<Control>().Sum(control => control.Width) + 4,
            Top = 3,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(246, 249, 252),
            ForeColor = Color.FromArgb(42, 62, 78),
            Font = new Font("Segoe UI Semibold", 8.2f),
            TabStop = false
        };
        button.FlatAppearance.BorderColor = Color.FromArgb(156, 173, 186);
        button.Click += (_, _) => MechanicalInterfaceRoadmapIteration.ApplyView(_viewport, command);
        Controls.Add(button);
        _tips.SetToolTip(button, tip);
    }
}
