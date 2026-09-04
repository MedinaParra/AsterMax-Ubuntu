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
        private AsterMaxEngineeringTree _asterMaxEngineeringTree;

        private void InstallAsterMaxAiChat()
        {
            InstallAsterMaxWorkflowStrip();
            InstallAsterMaxEngineeringTree();

            Bitmap icon16 = AsterMaxUiTheme.CreateAiIcon(16);
            Bitmap icon20 = AsterMaxUiTheme.CreateAiIcon(20);

            ToolStripButton aiButton = new ToolStripButton();
            aiButton.Name = "tsbAsterMaxAI";
            aiButton.Text = "AI Copilot";
            aiButton.Image = icon20;
            aiButton.ImageScaling = ToolStripItemImageScaling.None;
            aiButton.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            aiButton.AutoToolTip = false;
            aiButton.ToolTipText = "AsterMax AI Engineering Copilot (Ctrl+Shift+A)";
            aiButton.Margin = new Padding(3, 1, 3, 2);
            aiButton.Click += (s, e) => ShowAsterMaxAiChat();

            tsFile.Items.Add(new ToolStripSeparator());
            tsFile.Items.Add(aiButton);

            ToolStripMenuItem aiMenu = new ToolStripMenuItem("AsterMax AI Engineering Copilot");
            aiMenu.Name = "tsmiAsterMaxAI";
            aiMenu.Image = icon16;
            aiMenu.ShortcutKeys = Keys.Control | Keys.Shift | Keys.A;
            aiMenu.ToolTipText = "Asistente de ingeniería conectado al contexto actual del modelo.";
            aiMenu.Click += (s, e) => ShowAsterMaxAiChat();
            menuStripMain.Items.Add(aiMenu);
        }

        private void InstallAsterMaxWorkflowStrip()
        {
            if (_asterMaxWorkflowStrip != null) return;
            _asterMaxWorkflowStrip = new AsterMaxWorkflowStrip(_controller);
            Controls.Add(_asterMaxWorkflowStrip);
            _asterMaxWorkflowStrip.BringToFront();
        }

        private void InstallAsterMaxEngineeringTree()
        {
            if (_asterMaxEngineeringTree != null) return;
            _asterMaxEngineeringTree = new AsterMaxEngineeringTree(_controller);
            Controls.Add(_asterMaxEngineeringTree);
            _asterMaxEngineeringTree.BringToFront();
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
