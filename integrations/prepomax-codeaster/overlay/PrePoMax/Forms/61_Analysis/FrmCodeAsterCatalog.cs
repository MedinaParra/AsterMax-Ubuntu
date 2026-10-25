using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using PrePoMax.CodeAster;

namespace PrePoMax
{
    /// <summary>
    /// Lightweight browser for the command catalog discovered from the local
    /// Code_Aster installation. It intentionally does not hard-code a release.
    /// </summary>
    public sealed class FrmCodeAsterCatalog : Form
    {
        private readonly CodeAsterCatalog _catalog;
        private readonly TextBox _search;
        private readonly ListBox _commands;
        private readonly Label _status;
        private readonly Button _copy;

        public string SelectedCommand
        {
            get
            {
                CodeAsterCommandInfo item = _commands.SelectedItem as CodeAsterCommandInfo;
                return item == null ? null : item.Name;
            }
        }

        public FrmCodeAsterCatalog(CodeAsterCatalog catalog)
        {
            if (catalog == null) throw new ArgumentNullException("catalog");
            _catalog = catalog;

            Text = "Code_Aster command catalog";
            StartPosition = FormStartPosition.CenterParent;
            MinimumSize = new Size(520, 520);
            Size = new Size(680, 700);

            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.Padding = new Padding(8);
            root.ColumnCount = 1;
            root.RowCount = 4;
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            Controls.Add(root);

            _search = new TextBox();
            _search.Dock = DockStyle.Top;
            _search.Margin = new Padding(0, 0, 0, 8);
            _search.TextChanged += delegate { RefreshList(); };
            root.Controls.Add(_search, 0, 0);

            _commands = new ListBox();
            _commands.Dock = DockStyle.Fill;
            _commands.Font = new Font(FontFamily.GenericMonospace, Font.Size);
            _commands.DoubleClick += delegate
            {
                if (SelectedCommand != null)
                {
                    DialogResult = DialogResult.OK;
                    Close();
                }
            };
            root.Controls.Add(_commands, 0, 1);

            _status = new Label();
            _status.AutoSize = true;
            _status.Margin = new Padding(0, 8, 0, 8);
            root.Controls.Add(_status, 0, 2);

            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.AutoSize = true;
            buttons.FlowDirection = FlowDirection.RightToLeft;
            buttons.Dock = DockStyle.Fill;

            Button close = new Button();
            close.Text = "Close";
            close.AutoSize = true;
            close.Click += delegate { Close(); };
            buttons.Controls.Add(close);

            _copy = new Button();
            _copy.Text = "Copy command";
            _copy.AutoSize = true;
            _copy.Click += delegate
            {
                if (!String.IsNullOrWhiteSpace(SelectedCommand)) Clipboard.SetText(SelectedCommand);
            };
            buttons.Controls.Add(_copy);

            root.Controls.Add(buttons, 0, 3);

            RefreshList();
            _search.Focus();
        }

        private void RefreshList()
        {
            string needle = (_search.Text ?? String.Empty).Trim();
            IEnumerable<CodeAsterCommandInfo> items = _catalog.Commands;
            if (needle.Length > 0)
            {
                items = items.Where(x => x.Name.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0);
            }

            CodeAsterCommandInfo[] visible = items.OrderBy(x => x.Name).ToArray();
            _commands.BeginUpdate();
            try
            {
                _commands.Items.Clear();
                _commands.Items.AddRange(visible);
            }
            finally
            {
                _commands.EndUpdate();
            }

            string version = String.IsNullOrWhiteSpace(_catalog.Version) ? "unknown version" : _catalog.Version;
            _status.Text = String.Format("{0} of {1} commands | Code_Aster {2}",
                                         visible.Length,
                                         _catalog.Commands.Count,
                                         version);
            _copy.Enabled = visible.Length > 0;
        }
    }
}
