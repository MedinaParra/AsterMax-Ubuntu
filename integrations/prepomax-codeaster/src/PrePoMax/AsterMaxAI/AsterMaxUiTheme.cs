using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public static class AsterMaxUiTheme
    {
        public static readonly Color Accent = Color.FromArgb(34, 110, 220);
        public static readonly Color AccentDark = Color.FromArgb(24, 78, 156);
        public static readonly Color Surface = Color.FromArgb(248, 249, 251);
        public static readonly Color SurfaceAlt = Color.FromArgb(238, 241, 246);
        public static readonly Color Border = Color.FromArgb(205, 211, 220);
        public static readonly Color TextPrimary = Color.FromArgb(31, 38, 48);
        public static readonly Color TextSecondary = Color.FromArgb(92, 101, 114);
        public static readonly Color Success = Color.FromArgb(38, 130, 79);

        public static Bitmap CreateAiIcon(int size)
        {
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                RectangleF body = new RectangleF(1.5f, 1.5f, size - 3f, size - 3f);
                using (Brush b = new SolidBrush(Accent)) g.FillEllipse(b, body);
                float c = size / 2f;
                using (Pen p = new Pen(Color.White, Math.Max(1.4f, size / 9f)))
                {
                    p.StartCap = LineCap.Round;
                    p.EndCap = LineCap.Round;
                    g.DrawLine(p, c, size * 0.23f, c, size * 0.77f);
                    g.DrawLine(p, size * 0.23f, c, size * 0.77f, c);
                    g.DrawLine(p, size * 0.31f, size * 0.31f, size * 0.69f, size * 0.69f);
                    g.DrawLine(p, size * 0.69f, size * 0.31f, size * 0.31f, size * 0.69f);
                }
                using (Brush dot = new SolidBrush(Color.White)) g.FillEllipse(dot, c - 1.6f, c - 1.6f, 3.2f, 3.2f);
            }
            return bmp;
        }

        public static void StylePrimaryButton(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderSize = 0;
            button.BackColor = Accent;
            button.ForeColor = Color.White;
            button.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 9f, FontStyle.Bold);
            button.Cursor = Cursors.Hand;
        }

        public static void StyleSecondaryButton(Button button)
        {
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Border;
            button.BackColor = Color.White;
            button.ForeColor = TextPrimary;
            button.Cursor = Cursors.Hand;
        }
    }
}
