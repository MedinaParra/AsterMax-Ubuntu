using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm : Form
{
    internal static readonly Color Bg = Color.FromArgb(27, 30, 35);
    internal static readonly Color Panel = Color.FromArgb(39, 43, 50);
    internal static readonly Color Panel2 = Color.FromArgb(49, 54, 63);
    internal static readonly Color Field = Color.FromArgb(24, 27, 32);
    internal static readonly Color Border = Color.FromArgb(72, 79, 90);
    internal static readonly Color TextMain = Color.FromArgb(235, 238, 242);
    internal static readonly Color TextMuted = Color.FromArgb(164, 174, 187);
    internal static readonly Color Accent = Color.FromArgb(38, 143, 255);
    internal static readonly Color Green = Color.FromArgb(74, 200, 126);
    internal static readonly Color Yellow = Color.FromArgb(245, 187, 70);
    internal static readonly Color Red = Color.FromArgb(235, 86, 86);

    private readonly MenuStrip _menu = new();
    private readonly TabControl _ribbon = new();
    private readonly FlowLayoutPanel _workflow = new();
    private readonly TreeView _outline = new();
    private readonly DataGridView _details = new();
    private readonly MechanicalViewport _viewport = new();
    private readonly ToolStrip _graphicsTools = new();
    private readonly TabControl _lowerTabs = new();
    private readonly DataGridView _worksheet = new();
    private readonly DataGridView _tabular = new();
    private readonly Panel _graph = new();
    private readonly RichTextBox _messages = new();
    private readonly StatusStrip _status = new();
    private readonly ToolStripStatusLabel _statusMain = new("Ready");
    private readonly ToolStripStatusLabel _statusSelection = new("No selection");
    private readonly ToolStripStatusLabel _statusSolver = new("Solver: not configured");
    private readonly Label _contextTitle = new();
    private readonly FlowLayoutPanel _contextButtons = new();
    private readonly Dictionary<string, TreeNode> _nodes = new(StringComparer.OrdinalIgnoreCase);

    private string? _projectPath;
    private string? _geometryPath;
    private string? _codeAsterLauncher;
    private string _units = "Metric (mm, kg, N, s)";
    private bool _meshGenerated;
    private bool _solved;
    private bool _busy;
    private int _loadCount;
    private int _supportCount;
    private int _resultCount;

    public MechanicalForm()
    {
        Text = "AsterMax Mechanical 0.3 beta";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(1180, 760);
        Size = new Size(1520, 920);
        BackColor = Bg;
        ForeColor = TextMain;
        Font = new Font("Segoe UI", 9.3f);
        KeyPreview = true;
        AllowDrop = true;

        BuildLayout();
        BuildMenus();
        BuildRibbon();
        BuildProjectTree();
        WireEvents();
        SelectNode("Project");
        Log("AsterMax Mechanical 0.3 beta initialized.");
        Log("Workflow loaded from the Mechanical training methodology: Preliminary Decisions -> Preprocessing -> Solution -> Postprocessing.");
    }
}
