using System;
using System.Windows.Forms;
using PrePoMax.AsterMaxAI;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private AsterMaxAiChatForm _asterMaxAiChat;

        private void InstallAsterMaxAiChat()
        {
            ToolStripButton aiButton = new ToolStripButton();
            aiButton.Name = "tsbAsterMaxAI";
            aiButton.Text = "AsterMax AI";
            aiButton.DisplayStyle = ToolStripItemDisplayStyle.Text;
            aiButton.ToolTipText = "Abrir AsterMax AI Engineering Copilot";
            aiButton.Click += (s, e) => ShowAsterMaxAiChat();
            tsFile.Items.Add(new ToolStripSeparator());
            tsFile.Items.Add(aiButton);
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
