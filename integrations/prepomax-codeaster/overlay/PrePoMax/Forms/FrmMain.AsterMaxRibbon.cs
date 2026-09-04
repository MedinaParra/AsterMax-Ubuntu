using System;
using System.Collections.Generic;
using System.Drawing;
using System.Windows.Forms;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private Panel _asterMaxRibbonHost;
        private TabControl _asterMaxRibbonTabs;
        private ToolTip _asterMaxRibbonToolTip;
        private bool _asterMaxRibbonEnabled = true;
        private bool _asterMaxShowClassicToolbars = false;
        private bool _asterMaxWorkspaceLayoutApplied = false;

        private void InitializeAsterMaxRibbon()
        {
            _asterMaxRibbonToolTip = new ToolTip();
            _asterMaxRibbonToolTip.ShowAlways = true;
            _asterMaxRibbonToolTip.AutoPopDelay = 12000;
            _asterMaxRibbonToolTip.InitialDelay = 450;
            _asterMaxRibbonToolTip.ReshowDelay = 100;

            _asterMaxRibbonHost = new Panel();
            _asterMaxRibbonHost.Name = "asterMaxRibbonHost";
            _asterMaxRibbonHost.Dock = DockStyle.Top;
            _asterMaxRibbonHost.Height = 132;
            _asterMaxRibbonHost.BackColor = Color.FromArgb(244, 247, 250);
            _asterMaxRibbonHost.Padding = new Padding(0, 1, 0, 1);

            _asterMaxRibbonTabs = new TabControl();
            _asterMaxRibbonTabs.Name = "asterMaxRibbonTabs";
            _asterMaxRibbonTabs.Dock = DockStyle.Fill;
            _asterMaxRibbonTabs.Font = new Font("Segoe UI", 8.75F, FontStyle.Regular);
            _asterMaxRibbonTabs.Padding = new Point(11, 5);
            _asterMaxRibbonTabs.SizeMode = TabSizeMode.Normal;
            _asterMaxRibbonTabs.Multiline = false;

            BuildHomeRibbonTab();
            BuildMirroredMenuRibbonTabs();
            BuildAsterMaxRibbonTab();

            _asterMaxRibbonHost.Controls.Add(_asterMaxRibbonTabs);
            Controls.Add(_asterMaxRibbonHost);
            _asterMaxRibbonHost.BringToFront();

            ConfigureAsterMaxWorkspaceLayout(false);
            Shown += delegate { ConfigureAsterMaxWorkspaceLayout(true); };

            ApplyAsterMaxRibbonVisibility();
        }

        private string CleanRibbonText(string text)
        {
            if (text == null) return "";
            return text.Replace("&", "").Trim();
        }

        private TabPage CreateRibbonTab(string title)
        {
            TabPage page = new TabPage(title);
            page.BackColor = Color.FromArgb(248, 249, 251);
            page.Padding = new Padding(6, 4, 6, 3);
            page.UseVisualStyleBackColor = false;
            return page;
        }

        private FlowLayoutPanel CreateRibbonRow(TabPage page)
        {
            FlowLayoutPanel row = new FlowLayoutPanel();
            row.Dock = DockStyle.Fill;
            row.FlowDirection = FlowDirection.LeftToRight;
            row.WrapContents = false;
            row.AutoScroll = true;
            row.Padding = new Padding(2, 2, 2, 0);
            row.BackColor = page.BackColor;
            page.Controls.Add(row);
            return row;
        }

        private Panel CreateRibbonGroup(string title, IList<Control> controls)
        {
            int width = 116;
            foreach (Control control in controls) width += control.Width + 4;
            width = Math.Max(116, width);

            Panel group = new Panel();
            group.Width = width;
            group.Height = 86;
            group.Margin = new Padding(2, 0, 5, 0);
            group.BackColor = Color.White;
            group.BorderStyle = BorderStyle.FixedSingle;

            FlowLayoutPanel buttons = new FlowLayoutPanel();
            buttons.Dock = DockStyle.Fill;
            buttons.FlowDirection = FlowDirection.LeftToRight;
            buttons.WrapContents = false;
            buttons.AutoScroll = false;
            buttons.Padding = new Padding(4, 3, 4, 18);
            buttons.BackColor = Color.White;
            foreach (Control control in controls) buttons.Controls.Add(control);

            Label label = new Label();
            label.Text = title;
            label.Dock = DockStyle.Bottom;
            label.Height = 17;
            label.TextAlign = ContentAlignment.MiddleCenter;
            label.Font = new Font("Segoe UI", 7.5F, FontStyle.Regular);
            label.ForeColor = Color.FromArgb(82, 89, 98);
            label.BackColor = Color.FromArgb(241, 244, 247);

            group.Controls.Add(buttons);
            group.Controls.Add(label);
            return group;
        }

        private int GetRibbonButtonWidth(string text)
        {
            string clean = CleanRibbonText(text);
            int measured = TextRenderer.MeasureText(clean, new Font("Segoe UI", 8.25F)).Width + 20;
            return Math.Max(78, Math.Min(132, measured));
        }

        private Button CreateRibbonButtonBase(string text)
        {
            Button button = new Button();
            button.Text = CleanRibbonText(text);
            button.Width = GetRibbonButtonWidth(text);
            button.Height = 59;
            button.Margin = new Padding(2, 1, 2, 1);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = Color.White;
            button.ForeColor = Color.FromArgb(30, 37, 45);
            button.Font = new Font("Segoe UI", 8.25F, FontStyle.Regular);
            button.TextImageRelation = TextImageRelation.ImageAboveText;
            button.ImageAlign = ContentAlignment.MiddleCenter;
            button.TextAlign = ContentAlignment.BottomCenter;
            button.AutoEllipsis = true;
            button.MouseEnter += delegate { if (button.Enabled) button.BackColor = Color.FromArgb(229, 239, 250); };
            button.MouseLeave += delegate { SyncRibbonButtonAppearance(button); };
            return button;
        }

        private void SyncRibbonButtonAppearance(Button button)
        {
            ToolStripMenuItem source = button.Tag as ToolStripMenuItem;
            if (source == null)
            {
                button.BackColor = Color.White;
                return;
            }
            button.Enabled = source.Enabled && source.Visible;
            button.BackColor = source.Checked ? Color.FromArgb(214, 231, 249) : Color.White;
        }

        private Button RibbonCommand(ToolStripMenuItem command)
        {
            Button button = CreateRibbonButtonBase(command == null ? "Command" : command.Text);
            if (command == null) return button;

            button.Tag = command;
            button.Image = command.Image;
            button.Click += delegate { command.PerformClick(); };
            command.EnabledChanged += delegate { SyncRibbonButtonAppearance(button); };
            command.AvailableChanged += delegate { SyncRibbonButtonAppearance(button); };
            command.CheckedChanged += delegate { SyncRibbonButtonAppearance(button); };
            SyncRibbonButtonAppearance(button);
            _asterMaxRibbonToolTip.SetToolTip(button, GetRibbonToolTip(command));
            return button;
        }

        private Button RibbonDropDown(ToolStripMenuItem command)
        {
            Button button = CreateRibbonButtonBase(CleanRibbonText(command.Text) + "  ▼");
            button.Tag = command;
            button.Image = command.Image;
            button.Click += delegate(object sender, EventArgs e)
            {
                ShowRibbonDropDown((Control)sender, command);
            };
            command.EnabledChanged += delegate { SyncRibbonButtonAppearance(button); };
            command.AvailableChanged += delegate { SyncRibbonButtonAppearance(button); };
            command.CheckedChanged += delegate { SyncRibbonButtonAppearance(button); };
            SyncRibbonButtonAppearance(button);
            _asterMaxRibbonToolTip.SetToolTip(button, GetRibbonToolTip(command));
            return button;
        }

        private string GetRibbonToolTip(ToolStripMenuItem command)
        {
            string tip = CleanRibbonText(command.Text);
            if (!string.IsNullOrWhiteSpace(command.ToolTipText)) tip += Environment.NewLine + command.ToolTipText;
            if (!string.IsNullOrWhiteSpace(command.ShortcutKeyDisplayString)) tip += Environment.NewLine + command.ShortcutKeyDisplayString;
            else if (command.ShortcutKeys != Keys.None) tip += Environment.NewLine + command.ShortcutKeys.ToString();
            return tip;
        }

        private Button RibbonAction(string text, EventHandler click)
        {
            Button button = CreateRibbonButtonBase(text);
            button.Click += click;
            return button;
        }

        private void ShowRibbonDropDown(Control anchor, ToolStripMenuItem source)
        {
            ContextMenuStrip menu = new ContextMenuStrip();
            CopyMenuItems(menu.Items, source.DropDownItems);
            menu.Closed += delegate { menu.Dispose(); };
            menu.Show(anchor, new Point(0, anchor.Height));
        }

        private void CopyMenuItems(ToolStripItemCollection target, ToolStripItemCollection source)
        {
            foreach (ToolStripItem item in source)
            {
                if (item is ToolStripSeparator)
                {
                    target.Add(new ToolStripSeparator());
                    continue;
                }

                ToolStripMenuItem sourceItem = item as ToolStripMenuItem;
                if (sourceItem == null) continue;

                ToolStripMenuItem clone = new ToolStripMenuItem();
                clone.Text = CleanRibbonText(sourceItem.Text);
                clone.Image = sourceItem.Image;
                clone.Enabled = sourceItem.Enabled && sourceItem.Visible;
                clone.Checked = sourceItem.Checked;
                clone.CheckState = sourceItem.CheckState;
                clone.ShortcutKeyDisplayString = sourceItem.ShortcutKeyDisplayString;
                clone.ToolTipText = sourceItem.ToolTipText;

                if (sourceItem.DropDownItems.Count > 0)
                {
                    CopyMenuItems(clone.DropDownItems, sourceItem.DropDownItems);
                }
                else
                {
                    ToolStripMenuItem captured = sourceItem;
                    clone.Click += delegate { captured.PerformClick(); };
                }
                target.Add(clone);
            }
        }

        private Control CreateRibbonControlForMenuItem(ToolStripMenuItem item)
        {
            if (item.DropDownItems.Count > 0) return RibbonDropDown(item);
            return RibbonCommand(item);
        }

        private void AddRibbonGroup(FlowLayoutPanel row, string title, IList<Control> controls)
        {
            if (controls == null || controls.Count == 0) return;
            row.Controls.Add(CreateRibbonGroup(title, controls));
        }

        private void BuildHomeRibbonTab()
        {
            TabPage page = CreateRibbonTab("Home");
            FlowLayoutPanel row = CreateRibbonRow(page);

            AddRibbonGroup(row, "Project", new List<Control>
            {
                RibbonCommand(tsmiNew), RibbonCommand(tsmiOpen), RibbonCommand(tsmiImportFile), RibbonCommand(tsmiSave)
            });
            AddRibbonGroup(row, "History", new List<Control>
            {
                RibbonCommand(tsmiUndo), RibbonCommand(tsmiRedo)
            });
            AddRibbonGroup(row, "View", new List<Control>
            {
                RibbonCommand(tsmiZoomToFit), RibbonCommand(tsmiIsometricView)
            });
            AddRibbonGroup(row, "Interface", new List<Control>
            {
                RibbonAction("Classic UI", delegate
                {
                    _asterMaxShowClassicToolbars = !_asterMaxShowClassicToolbars;
                    ApplyAsterMaxRibbonVisibility();
                })
            });
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void BuildMirroredMenuRibbonTabs()
        {
            if (menuStripMain == null) return;

            foreach (ToolStripItem rawTopItem in menuStripMain.Items)
            {
                ToolStripMenuItem topMenu = rawTopItem as ToolStripMenuItem;
                if (topMenu == null) continue;

                string tabTitle = CleanRibbonText(topMenu.Text);
                if (string.IsNullOrWhiteSpace(tabTitle)) continue;

                TabPage page = CreateRibbonTab(tabTitle);
                FlowLayoutPanel row = CreateRibbonRow(page);
                BuildRibbonGroupsFromMenu(row, topMenu);
                _asterMaxRibbonTabs.TabPages.Add(page);
            }
        }

        private void BuildRibbonGroupsFromMenu(FlowLayoutPanel row, ToolStripMenuItem topMenu)
        {
            List<Control> general = new List<Control>();
            int generalIndex = 1;

            foreach (ToolStripItem rawItem in topMenu.DropDownItems)
            {
                if (rawItem is ToolStripSeparator)
                {
                    if (general.Count > 0)
                    {
                        AddRibbonGroup(row, generalIndex == 1 ? "Commands" : "Commands " + generalIndex.ToString(), general);
                        general = new List<Control>();
                        generalIndex++;
                    }
                    continue;
                }

                ToolStripMenuItem item = rawItem as ToolStripMenuItem;
                if (item == null) continue;

                if (item.DropDownItems.Count > 0)
                {
                    if (general.Count > 0)
                    {
                        AddRibbonGroup(row, generalIndex == 1 ? "Commands" : "Commands " + generalIndex.ToString(), general);
                        general = new List<Control>();
                        generalIndex++;
                    }

                    List<Control> nestedControls = new List<Control>();
                    foreach (ToolStripItem childRaw in item.DropDownItems)
                    {
                        if (childRaw is ToolStripSeparator) continue;
                        ToolStripMenuItem child = childRaw as ToolStripMenuItem;
                        if (child != null) nestedControls.Add(CreateRibbonControlForMenuItem(child));
                    }
                    if (nestedControls.Count == 0) nestedControls.Add(RibbonDropDown(item));
                    AddRibbonGroup(row, CleanRibbonText(item.Text), nestedControls);
                }
                else
                {
                    general.Add(RibbonCommand(item));
                }
            }

            if (general.Count > 0)
                AddRibbonGroup(row, generalIndex == 1 ? "Commands" : "Commands " + generalIndex.ToString(), general);
        }

        private void BuildAsterMaxRibbonTab()
        {
            TabPage page = CreateRibbonTab("AsterMax");
            FlowLayoutPanel row = CreateRibbonRow(page);
            AddRibbonGroup(row, "Solver", new List<Control>
            {
                RibbonCommand(tsmiSettings), RibbonCommand(tsmiCheckModel), RibbonCommand(tsmiRunAnalysis)
            });
            AddRibbonGroup(row, "Engineering", new List<Control>
            {
                RibbonCommand(tsmiMaterialLibrary), RibbonCommand(tsmiQuery)
            });
            AddRibbonGroup(row, "Interface", new List<Control>
            {
                RibbonAction("Classic UI", delegate
                {
                    _asterMaxShowClassicToolbars = !_asterMaxShowClassicToolbars;
                    ApplyAsterMaxRibbonVisibility();
                })
            });
            _asterMaxRibbonTabs.TabPages.Add(page);
        }

        private void ConfigureAsterMaxWorkspaceLayout(bool finalLayout)
        {
            if (splitContainer1 == null) return;
            if (_asterMaxWorkspaceLayoutApplied && finalLayout) return;

            int panel1Min = 285;
            int panel2Min = 420;
            int splitterWidth = 6;
            int available = splitContainer1.Width > 0 ? splitContainer1.Width : ClientSize.Width;
            int desired = (int)(available * 0.22);
            desired = Math.Max(330, Math.Min(380, desired));
            int maximum = available - panel2Min - splitterWidth;

            splitContainer1.Panel1MinSize = 0;
            splitContainer1.Panel2MinSize = 0;
            splitContainer1.SplitterWidth = splitterWidth;
            splitContainer1.FixedPanel = FixedPanel.Panel1;
            if (maximum >= panel1Min)
                splitContainer1.SplitterDistance = Math.Max(panel1Min, Math.Min(desired, maximum));
            splitContainer1.Panel1MinSize = panel1Min;
            splitContainer1.Panel2MinSize = panel2Min;

            if (finalLayout) _asterMaxWorkspaceLayoutApplied = true;
        }

        private void ApplyAsterMaxRibbonVisibility()
        {
            if (!_asterMaxRibbonEnabled) return;

            bool showClassic = _asterMaxShowClassicToolbars;
            if (menuStripMain != null) menuStripMain.Visible = showClassic;
            if (toolStripContainer1 != null) toolStripContainer1.TopToolStripPanelVisible = showClassic;
            if (tsFile != null) tsFile.Visible = showClassic;
            if (tsViews != null) tsViews.Visible = showClassic;
            if (tsModel != null) tsModel.Visible = showClassic;
            if (tsDeformationFactor != null) tsDeformationFactor.Visible = showClassic;
            if (tsResults != null) tsResults.Visible = showClassic;
            if (_asterMaxRibbonHost != null) _asterMaxRibbonHost.Visible = true;
        }
    }
}
