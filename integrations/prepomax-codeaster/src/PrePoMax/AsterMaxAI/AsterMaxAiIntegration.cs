using System;
using System.Drawing;
using System.Windows.Forms;
using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxAiChatForm _asterMaxAiChat;
        private AsterMaxWorkflowStrip _asterMaxWorkflowStrip;
        private AsterMaxViewportHud _asterMaxViewportHud;
        private AsterMaxEngineeringTree _asterMaxEngineeringTree;
        private AsterMaxResultsWorkspace _asterMaxResultsWorkspace;

        private void InstallAsterMaxAiChat()
        {
            ApplyAsterMaxDarkShell();
            InstallAsterMaxWorkflowStrip();
            InstallAsterMaxViewportHud();
            InstallAsterMaxEngineeringTree();
            InstallAsterMaxResultsWorkspace();
            Shown += (s, e) => ApplyAsterMaxDarkShell();

            Bitmap icon16 = AsterMaxUiTheme.CreateAiIcon(16);
            Bitmap icon20 = AsterMaxUiTheme.CreateAiIcon(20);

            ToolStripButton aiButton = new ToolStripButton();
            aiButton.Name = "tsbAsterMaxAI";
            aiButton.Text = "AI Copilot";
            aiButton.Image = icon20;
            aiButton.ImageScaling = ToolStripItemImageScaling.None;
            aiButton.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            aiButton.AutoToolTip = false;
            aiButton.ForeColor = AsterMaxUiTheme.AccentGlow;
            aiButton.BackColor = AsterMaxUiTheme.Surface;
            aiButton.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.5f, FontStyle.Bold);
            aiButton.ToolTipText = "AsterMax AI Engineering Copilot (Ctrl+Shift+A)";
            aiButton.Margin = new Padding(3, 1, 3, 2);
            aiButton.Click += (s, e) => ShowAsterMaxAiChat();

            tsFile.Items.Add(new ToolStripSeparator());
            tsFile.Items.Add(aiButton);

            ToolStripMenuItem aiMenu = new ToolStripMenuItem("AsterMax AI Engineering Copilot");
            aiMenu.Name = "tsmiAsterMaxAI";
            aiMenu.Image = icon16;
            aiMenu.ForeColor = AsterMaxUiTheme.AccentGlow;
            aiMenu.BackColor = AsterMaxUiTheme.Surface;
            aiMenu.ShortcutKeys = Keys.Control | Keys.Shift | Keys.A;
            aiMenu.ToolTipText = "Evidence-aware engineering assistant connected to the current model context.";
            aiMenu.Click += (s, e) => ShowAsterMaxAiChat();
            menuStripMain.Items.Add(aiMenu);
        }

        private void ApplyAsterMaxDarkShell()
        {
            BackColor = AsterMaxUiTheme.Background;
            ForeColor = AsterMaxUiTheme.TextPrimary;
            ThemeAsterMaxControlTree(this);
            AsterMaxUiTheme.StyleMenuStrip(menuStripMain);
            AsterMaxUiTheme.StyleToolStrip(tsFile);
        }

        private static void ThemeAsterMaxControlTree(Control root)
        {
            if (root == null) return;
            foreach (Control control in root.Controls)
            {
                ToolStrip strip = control as ToolStrip;
                if (strip != null) AsterMaxUiTheme.StyleToolStrip(strip);

                TreeView tree = control as TreeView;
                if (tree != null)
                {
                    tree.BackColor = AsterMaxUiTheme.Background;
                    tree.ForeColor = AsterMaxUiTheme.TextPrimary;
                    tree.LineColor = AsterMaxUiTheme.Border;
                    tree.BorderStyle = BorderStyle.FixedSingle;
                }

                ListView list = control as ListView;
                if (list != null)
                {
                    list.BackColor = AsterMaxUiTheme.Background;
                    list.ForeColor = AsterMaxUiTheme.TextPrimary;
                    list.BorderStyle = BorderStyle.FixedSingle;
                }

                PropertyGrid grid = control as PropertyGrid;
                if (grid != null)
                {
                    grid.BackColor = AsterMaxUiTheme.Background;
                    grid.ViewBackColor = AsterMaxUiTheme.Background;
                    grid.ViewForeColor = AsterMaxUiTheme.TextPrimary;
                    grid.HelpBackColor = AsterMaxUiTheme.Surface;
                    grid.HelpForeColor = AsterMaxUiTheme.TextSecondary;
                    grid.CommandsBackColor = AsterMaxUiTheme.Surface;
                    grid.CommandsForeColor = AsterMaxUiTheme.AccentGlow;
                    grid.LineColor = AsterMaxUiTheme.Border;
                    grid.CategoryForeColor = AsterMaxUiTheme.AccentGlow;
                }

                TextBox textBox = control as TextBox;
                if (textBox != null && !textBox.ReadOnly)
                {
                    textBox.BackColor = AsterMaxUiTheme.SurfaceRaised;
                    textBox.ForeColor = AsterMaxUiTheme.TextPrimary;
                    textBox.BorderStyle = BorderStyle.FixedSingle;
                }

                StatusStrip status = control as StatusStrip;
                if (status != null) AsterMaxUiTheme.StyleToolStrip(status);

                ThemeAsterMaxControlTree(control);
            }
        }

        private void InstallAsterMaxWorkflowStrip()
        {
            if (_asterMaxWorkflowStrip != null) return;
            _asterMaxWorkflowStrip = new AsterMaxWorkflowStrip(_controller);
            Controls.Add(_asterMaxWorkflowStrip);
            _asterMaxWorkflowStrip.BringToFront();
        }

        private void InstallAsterMaxViewportHud()
        {
            if (_asterMaxViewportHud != null) return;
            _asterMaxViewportHud = new AsterMaxViewportHud(_controller);
            Controls.Add(_asterMaxViewportHud);
            _asterMaxViewportHud.BringToFront();
        }

        private void InstallAsterMaxEngineeringTree()
        {
            if (_asterMaxEngineeringTree != null) return;
            _asterMaxEngineeringTree = new AsterMaxEngineeringTree(_controller);
            Controls.Add(_asterMaxEngineeringTree);
            _asterMaxEngineeringTree.BringToFront();
        }

        private void InstallAsterMaxResultsWorkspace()
        {
            if (_asterMaxResultsWorkspace != null) return;
            _asterMaxResultsWorkspace = new AsterMaxResultsWorkspace(_controller);
            Controls.Add(_asterMaxResultsWorkspace);
            _asterMaxResultsWorkspace.BringToFront();
        }

        private void ShowAsterMaxAiChat()
        {
            if (_asterMaxAiChat == null || _asterMaxAiChat.IsDisposed)
                _asterMaxAiChat = new AsterMaxAiChatForm(_controller);
            if (!_asterMaxAiChat.Visible) _asterMaxAiChat.Show(this);
            _asterMaxAiChat.BringToFront();
            _asterMaxAiChat.Focus();
        }
    }
}
