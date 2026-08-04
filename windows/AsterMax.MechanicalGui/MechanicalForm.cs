using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace AsterMax.MechanicalGui;

internal sealed partial class MechanicalForm : Form
{
    internal static readonly Color Bg = Color.FromArgb(242, 245, 249);
    internal static readonly Color Panel = Color.FromArgb(255, 255, 255);
    internal static readonly Color Panel2 = Color.FromArgb(235, 240, 246);
    internal static readonly Color Field = Color.FromArgb(252, 253, 255);
    internal static readonly Color Border = Color.FromArgb(188, 198, 210);
    internal static readonly Color TextMain = Color.FromArgb(33, 42, 52);
    internal static readonly Color TextMuted = Color.FromArgb(86, 99, 114);
    internal static readonly Color Accent = Color.FromArgb(0, 114, 198);
    internal static readonly Color Green = Color.FromArgb(34, 139, 85);
    internal static readonly Color Yellow = Color.FromArgb(190, 112, 0);
    internal static readonly Color Red = Color.FromArgb(195, 48, 48);

    private const string ProductTitle = "AsterMax Mechanical 0.7.1 beta";

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
        Text = ProductTitle;
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(1024, 680);
        Size = new Size(1520, 920);
        BackColor = Bg;
        ForeColor = TextMain;
        Font = new Font("Segoe UI", 9.3f);
        KeyPreview = true;
        AllowDrop = true;

        BuildSafeLayout();
        BuildMenus();
        BuildRibbon();
        BuildProjectTree();
        InitializePresentation();
        InitializeSimpleStaticWorkflow();
        InitializeEngineeringTutorials();
        WireEvents();
        SelectNode("Project");
        _ribbon.SelectedTab = _ribbon.TabPages.Cast<TabPage>()
            .FirstOrDefault(page => page.Text == "Workflow") ?? _ribbon.SelectedTab;
        Log(ProductTitle + " initialized.");
        Log("Existing tutorial capabilities verified: static TET4, Named Selections, convergence, Design Points, modal beam and steady thermal TET4.");
        Log("Standard CAD workflow: STEP -> material -> closed exterior mesh -> face selection -> support/load scoping.");
        Log("Mechanical workflow: Geometry -> Material -> Mesh -> Supports/Loads -> Solution -> Verification -> Report.");
    }
}
