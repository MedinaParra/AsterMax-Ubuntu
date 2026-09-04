using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxWorkflowStrip : ToolStrip
    {
        public AsterMaxWorkflowStrip()
        {
            Name = "tsAsterMaxWorkflow";
            GripStyle = ToolStripGripStyle.Hidden;
            Dock = DockStyle.Top;
            BackColor = Color.White;
            Padding = new Padding(6, 3, 6, 3);
            AutoSize = true;
            RenderMode = ToolStripRenderMode.System;
            Items.Add(MakeStage("CAD / STEP", StageIcon.Geometry));
            Items.Add(MakeStage("Mesh", StageIcon.Mesh));
            Items.Add(MakeStage("Material", StageIcon.Material));
            Items.Add(MakeStage("BC", StageIcon.Boundary));
            Items.Add(MakeStage("Load", StageIcon.Load));
            Items.Add(MakeStage("Solve", StageIcon.Solve));
            Items.Add(MakeStage("Results", StageIcon.Results));
            Items.Add(new ToolStripSeparator());
            ToolStripLabel units = new ToolStripLabel("mm · N · MPa");
            units.ForeColor = AsterMaxUiTheme.TextSecondary;
            units.ToolTipText = "AsterMax engineering unit contract";
            Items.Add(units);
        }

        private static ToolStripButton MakeStage(string text, StageIcon icon)
        {
            ToolStripButton button = new ToolStripButton();
            button.Text = text;
            button.DisplayStyle = ToolStripItemDisplayStyle.ImageAndText;
            button.Image = CreateStageIcon(icon, 20);
            button.ImageScaling = ToolStripItemImageScaling.None;
            button.Margin = new Padding(2, 1, 2, 1);
            button.Padding = new Padding(4, 2, 4, 2);
            button.ToolTipText = "Engineering workflow: " + text;
            button.Tag = "astermax-workflow-stage";
            return button;
        }

        private enum StageIcon { Geometry, Mesh, Material, Boundary, Load, Solve, Results }

        private static Bitmap CreateStageIcon(StageIcon stage, int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (Pen p = new Pen(AsterMaxUiTheme.AccentDark, 1.7f))
                using (Brush b = new SolidBrush(AsterMaxUiTheme.Accent))
                using (Brush soft = new SolidBrush(Color.FromArgb(35, AsterMaxUiTheme.Accent)))
                {
                    switch (stage)
                    {
                        case StageIcon.Geometry:
                            g.FillRectangle(soft, 3, 5, 12, 10);
                            g.DrawRectangle(p, 3, 5, 12, 10);
                            g.DrawLine(p, 3, 5, 7, 2); g.DrawLine(p, 15, 5, 11, 2); g.DrawLine(p, 7, 2, 11, 2);
                            break;
                        case StageIcon.Mesh:
                            for (int x = 4; x <= 16; x += 6) g.DrawLine(p, x, 3, x, 17);
                            for (int y = 4; y <= 16; y += 6) g.DrawLine(p, 3, y, 17, y);
                            g.DrawLine(p, 3, 3, 17, 17); g.DrawLine(p, 17, 3, 3, 17);
                            break;
                        case StageIcon.Material:
                            g.FillEllipse(soft, 3, 3, 14, 14); g.DrawEllipse(p, 3, 3, 14, 14);
                            g.DrawLine(p, 6, 10, 14, 10); g.DrawLine(p, 10, 6, 10, 14);
                            break;
                        case StageIcon.Boundary:
                            g.DrawLine(p, 5, 3, 5, 17); g.DrawLine(p, 5, 4, 16, 4); g.DrawLine(p, 5, 16, 16, 16);
                            for (int y = 6; y <= 14; y += 4) g.DrawLine(p, 2, y, 5, y - 2);
                            break;
                        case StageIcon.Load:
                            g.DrawLine(p, 10, 2, 10, 15); g.DrawLine(p, 10, 15, 6, 11); g.DrawLine(p, 10, 15, 14, 11); g.FillEllipse(b, 8, 1, 4, 4);
                            break;
                        case StageIcon.Solve:
                            PointF[] tri = { new PointF(6, 3), new PointF(16, 10), new PointF(6, 17) };
                            g.FillPolygon(b, tri);
                            break;
                        case StageIcon.Results:
                            g.DrawRectangle(p, 3, 3, 14, 14);
                            g.FillRectangle(new SolidBrush(Color.FromArgb(80, 110, 190, 255)), 5, 11, 2, 4);
                            g.FillRectangle(new SolidBrush(Color.FromArgb(100, 80, 160, 230)), 9, 8, 2, 7);
                            g.FillRectangle(new SolidBrush(Color.FromArgb(120, 50, 130, 200)), 13, 5, 2, 10);
                            break;
                    }
                }
            }
            return bmp;
        }
    }
}
