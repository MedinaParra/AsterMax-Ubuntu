using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public static class AsterMaxUiTheme
    {
        public static readonly Color Accent = Color.FromArgb(0, 214, 255);
        public static readonly Color AccentDark = Color.FromArgb(0, 154, 204);
        public static readonly Color AccentGlow = Color.FromArgb(46, 232, 255);
        public static readonly Color Background = Color.FromArgb(9, 13, 20);
        public static readonly Color Surface = Color.FromArgb(15, 21, 31);
        public static readonly Color SurfaceAlt = Color.FromArgb(20, 29, 42);
        public static readonly Color SurfaceRaised = Color.FromArgb(25, 36, 52);
        public static readonly Color Border = Color.FromArgb(46, 63, 83);
        public static readonly Color TextPrimary = Color.FromArgb(232, 241, 248);
        public static readonly Color TextSecondary = Color.FromArgb(145, 164, 184);
        public static readonly Color Success = Color.FromArgb(63, 214, 147);
        public static readonly Color Warning = Color.FromArgb(244, 180, 74);
        public static readonly Color Danger = Color.FromArgb(247, 94, 105);

        public static Bitmap CreateAiIcon(int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                RectangleF outer = new RectangleF(1.5f, 1.5f, size - 3f, size - 3f);
                using (Brush glow = new SolidBrush(Color.FromArgb(58, Accent))) g.FillEllipse(glow, outer);
                RectangleF body = new RectangleF(3f, 3f, size - 6f, size - 6f);
                using (Brush b = new LinearGradientBrush(body, AccentGlow, AccentDark, 45f)) g.FillEllipse(b, body);
                float c = size / 2f;
                using (Pen p = new Pen(Color.White, Math.Max(1.2f, size / 10f)))
                {
                    p.StartCap = LineCap.Round;
                    p.EndCap = LineCap.Round;
                    g.DrawLine(p, c, size * 0.27f, c, size * 0.73f);
                    g.DrawLine(p, size * 0.27f, c, size * 0.73f, c);
                    g.DrawLine(p, size * 0.34f, size * 0.34f, size * 0.66f, size * 0.66f);
                    g.DrawLine(p, size * 0.66f, size * 0.34f, size * 0.34f, size * 0.66f);
                }
            }
            return bmp;
        }

        public static Bitmap CreateAnalysisIcon(int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                using (Pen p = new Pen(Accent, Math.Max(1.4f, size / 10f)))
                {
                    g.DrawRectangle(p, 2, 2, size - 5, size - 5);
                    g.DrawLine(p, size * 0.25f, size * 0.68f, size * 0.43f, size * 0.46f);
                    g.DrawLine(p, size * 0.43f, size * 0.46f, size * 0.58f, size * 0.58f);
                    g.DrawLine(p, size * 0.58f, size * 0.58f, size * 0.78f, size * 0.29f);
                }
            }
            return bmp;
        }

        public static void StylePrimaryButton(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.FlatAppearance.MouseOverBackColor = AccentGlow;
            button.BackColor = AccentDark;
            button.ForeColor = Color.White;
            button.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Bold);
            button.Cursor = Cursors.Hand;
        }

        public static void StyleSecondaryButton(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Border;
            button.FlatAppearance.MouseOverBackColor = SurfaceRaised;
            button.BackColor = SurfaceAlt;
            button.ForeColor = TextPrimary;
            button.Cursor = Cursors.Hand;
        }

        public static void StyleToolStrip(ToolStrip strip)
        {
            if (strip == null) return;
            strip.BackColor = Surface;
            strip.ForeColor = TextPrimary;
            strip.RenderMode = ToolStripRenderMode.System;
            foreach (ToolStripItem item in strip.Items)
            {
                item.BackColor = Surface;
                item.ForeColor = TextPrimary;
            }
        }

        public static void StyleMenuStrip(MenuStrip strip)
        {
            if (strip == null) return;
            strip.BackColor = Surface;
            strip.ForeColor = TextPrimary;
            foreach (ToolStripItem item in strip.Items)
            {
                item.BackColor = Surface;
                item.ForeColor = TextPrimary;
            }
        }
    }
}
