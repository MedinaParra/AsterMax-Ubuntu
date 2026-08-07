using System.Drawing.Drawing2D;
using System.Globalization;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace AsterMax.MechanicalGui;

internal static class SvgIconRenderer
{
    private const float ViewBoxSize = 24f;
    private static readonly Lazy<XDocument> IconDocument = new(LoadIconDocument);
    private static readonly Dictionary<string, Bitmap> Cache = new(StringComparer.OrdinalIgnoreCase);
    private static readonly object CacheLock = new();

    public static Bitmap Render(string iconId, int pixelSize, Color foreground, Color accent)
    {
        var cacheKey = $"{iconId}|{pixelSize}|{foreground.ToArgb()}|{accent.ToArgb()}";
        lock (CacheLock)
        {
            if (Cache.TryGetValue(cacheKey, out var cached)) return (Bitmap)cached.Clone();
        }

        var group = IconDocument.Value.Descendants()
            .FirstOrDefault(element => element.Name.LocalName == "g" &&
                                       string.Equals((string?)element.Attribute("id"), iconId, StringComparison.OrdinalIgnoreCase));

        var bitmap = new Bitmap(pixelSize, pixelSize, System.Drawing.Imaging.PixelFormat.Format32bppPArgb);
        bitmap.SetResolution(96, 96);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
        graphics.CompositingQuality = CompositingQuality.HighQuality;
        graphics.Clear(Color.Transparent);
        graphics.ScaleTransform(pixelSize / ViewBoxSize, pixelSize / ViewBoxSize);

        if (group is not null)
        {
            var inherited = SvgStyle.Default;
            DrawElement(graphics, group, inherited, foreground, accent);
        }
        else
        {
            using var pen = new Pen(foreground, 1.8f);
            graphics.DrawRectangle(pen, 4, 4, 16, 16);
        }

        lock (CacheLock) Cache[cacheKey] = (Bitmap)bitmap.Clone();
        return bitmap;
    }

    public static void ClearCache()
    {
        lock (CacheLock)
        {
            foreach (var bitmap in Cache.Values) bitmap.Dispose();
            Cache.Clear();
        }
    }

    private static XDocument LoadIconDocument()
    {
        var assembly = Assembly.GetExecutingAssembly();
        var resourceName = assembly.GetManifestResourceNames()
            .FirstOrDefault(name => name.EndsWith("Icons.AsterMaxIconSet.svg", StringComparison.OrdinalIgnoreCase));
        if (resourceName is null) throw new InvalidOperationException("Embedded AsterMax SVG icon set was not found.");
        using var stream = assembly.GetManifestResourceStream(resourceName)
            ?? throw new InvalidOperationException("Unable to open embedded AsterMax SVG icon set.");
        return XDocument.Load(stream);
    }

    private static void DrawElement(Graphics graphics, XElement element, SvgStyle inherited, Color foreground, Color accent)
    {
        var style = inherited.Merge(element, foreground, accent);
        var localName = element.Name.LocalName;

        if (localName is "svg" or "g")
        {
            foreach (var child in element.Elements()) DrawElement(graphics, child, style, foreground, accent);
            return;
        }

        using var pen = CreatePen(style);
        using var brush = CreateBrush(style);

        switch (localName)
        {
            case "line":
                if (pen is not null)
                    graphics.DrawLine(pen, F(element, "x1"), F(element, "y1"), F(element, "x2"), F(element, "y2"));
                break;
            case "rect":
            {
                var rectangle = new RectangleF(F(element, "x"), F(element, "y"), F(element, "width"), F(element, "height"));
                var radius = F(element, "rx", 0);
                if (radius > 0)
                {
                    using var path = RoundedRectangle(rectangle, radius);
                    if (brush is not null) graphics.FillPath(brush, path);
                    if (pen is not null) graphics.DrawPath(pen, path);
                }
                else
                {
                    if (brush is not null) graphics.FillRectangle(brush, rectangle);
                    if (pen is not null) graphics.DrawRectangle(pen, rectangle.X, rectangle.Y, rectangle.Width, rectangle.Height);
                }
                break;
            }
            case "circle":
            {
                var cx = F(element, "cx");
                var cy = F(element, "cy");
                var radius = F(element, "r");
                var rectangle = new RectangleF(cx - radius, cy - radius, radius * 2, radius * 2);
                if (brush is not null) graphics.FillEllipse(brush, rectangle);
                if (pen is not null) graphics.DrawEllipse(pen, rectangle);
                break;
            }
            case "ellipse":
            {
                var cx = F(element, "cx");
                var cy = F(element, "cy");
                var rx = F(element, "rx");
                var ry = F(element, "ry");
                var rectangle = new RectangleF(cx - rx, cy - ry, rx * 2, ry * 2);
                if (brush is not null) graphics.FillEllipse(brush, rectangle);
                if (pen is not null) graphics.DrawEllipse(pen, rectangle);
                break;
            }
            case "polyline":
            case "polygon":
            {
                var points = ParsePoints((string?)element.Attribute("points"));
                if (points.Length < 2) break;
                if (brush is not null && localName == "polygon") graphics.FillPolygon(brush, points);
                if (pen is not null)
                {
                    if (localName == "polygon") graphics.DrawPolygon(pen, points);
                    else graphics.DrawLines(pen, points);
                }
                break;
            }
            case "path":
            {
                using var path = ParsePath((string?)element.Attribute("d"));
                if (brush is not null) graphics.FillPath(brush, path);
                if (pen is not null) graphics.DrawPath(pen, path);
                break;
            }
        }
    }

    private static Pen? CreatePen(SvgStyle style)
    {
        if (!style.HasStroke) return null;
        var pen = new Pen(style.Stroke, style.StrokeWidth)
        {
            StartCap = LineCap.Round,
            EndCap = LineCap.Round,
            LineJoin = LineJoin.Round
        };
        if (style.DashPattern.Length > 0) pen.DashPattern = style.DashPattern;
        return pen;
    }

    private static Brush? CreateBrush(SvgStyle style) => style.HasFill ? new SolidBrush(style.Fill) : null;

    private static GraphicsPath RoundedRectangle(RectangleF rectangle, float radius)
    {
        var diameter = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(rectangle.X, rectangle.Y, diameter, diameter, 180, 90);
        path.AddArc(rectangle.Right - diameter, rectangle.Y, diameter, diameter, 270, 90);
        path.AddArc(rectangle.Right - diameter, rectangle.Bottom - diameter, diameter, diameter, 0, 90);
        path.AddArc(rectangle.X, rectangle.Bottom - diameter, diameter, diameter, 90, 90);
        path.CloseFigure();
        return path;
    }

    private static PointF[] ParsePoints(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return [];
        var numbers = Regex.Matches(value, @"-?(?:\d+\.?\d*|\.\d+)")
            .Select(match => float.Parse(match.Value, CultureInfo.InvariantCulture))
            .ToArray();
        var points = new List<PointF>();
        for (var index = 0; index + 1 < numbers.Length; index += 2)
            points.Add(new PointF(numbers[index], numbers[index + 1]));
        return points.ToArray();
    }

    private static GraphicsPath ParsePath(string? data)
    {
        var path = new GraphicsPath();
        if (string.IsNullOrWhiteSpace(data)) return path;

        var tokens = Regex.Matches(data, @"[A-Za-z]|-?(?:\d+\.?\d*|\.\d+)")
            .Select(match => match.Value)
            .ToList();
        var index = 0;
        var command = ' ';
        var current = new PointF();
        var subpathStart = new PointF();
        var previousControl = new PointF();
        var hasPreviousControl = false;

        float Number() => float.Parse(tokens[index++], CultureInfo.InvariantCulture);
        bool HasNumber() => index < tokens.Count && !char.IsLetter(tokens[index][0]);

        while (index < tokens.Count)
        {
            if (char.IsLetter(tokens[index][0])) command = tokens[index++][0];
            var relative = char.IsLower(command);
            var upper = char.ToUpperInvariant(command);

            switch (upper)
            {
                case 'M':
                {
                    var first = true;
                    while (HasNumber())
                    {
                        var point = new PointF(Number(), Number());
                        if (relative) point = new PointF(current.X + point.X, current.Y + point.Y);
                        if (first)
                        {
                            path.StartFigure();
                            current = subpathStart = point;
                            first = false;
                        }
                        else
                        {
                            path.AddLine(current, point);
                            current = point;
                        }
                    }
                    hasPreviousControl = false;
                    break;
                }
                case 'L':
                    while (HasNumber())
                    {
                        var point = new PointF(Number(), Number());
                        if (relative) point = new PointF(current.X + point.X, current.Y + point.Y);
                        path.AddLine(current, point);
                        current = point;
                    }
                    hasPreviousControl = false;
                    break;
                case 'H':
                    while (HasNumber())
                    {
                        var x = Number();
                        if (relative) x += current.X;
                        var point = new PointF(x, current.Y);
                        path.AddLine(current, point);
                        current = point;
                    }
                    hasPreviousControl = false;
                    break;
                case 'V':
                    while (HasNumber())
                    {
                        var y = Number();
                        if (relative) y += current.Y;
                        var point = new PointF(current.X, y);
                        path.AddLine(current, point);
                        current = point;
                    }
                    hasPreviousControl = false;
                    break;
                case 'C':
                    while (HasNumber())
                    {
                        var c1 = new PointF(Number(), Number());
                        var c2 = new PointF(Number(), Number());
                        var end = new PointF(Number(), Number());
                        if (relative)
                        {
                            c1 = new PointF(current.X + c1.X, current.Y + c1.Y);
                            c2 = new PointF(current.X + c2.X, current.Y + c2.Y);
                            end = new PointF(current.X + end.X, current.Y + end.Y);
                        }
                        path.AddBezier(current, c1, c2, end);
                        current = end;
                        previousControl = c2;
                        hasPreviousControl = true;
                    }
                    break;
                case 'S':
                    while (HasNumber())
                    {
                        var c1 = hasPreviousControl
                            ? new PointF(current.X * 2 - previousControl.X, current.Y * 2 - previousControl.Y)
                            : current;
                        var c2 = new PointF(Number(), Number());
                        var end = new PointF(Number(), Number());
                        if (relative)
                        {
                            c2 = new PointF(current.X + c2.X, current.Y + c2.Y);
                            end = new PointF(current.X + end.X, current.Y + end.Y);
                        }
                        path.AddBezier(current, c1, c2, end);
                        current = end;
                        previousControl = c2;
                        hasPreviousControl = true;
                    }
                    break;
                case 'Z':
                    path.CloseFigure();
                    current = subpathStart;
                    hasPreviousControl = false;
                    break;
                default:
                    index++;
                    break;
            }
        }
        return path;
    }

    private static float F(XElement element, string attribute, float fallback = 0)
    {
        var value = (string?)element.Attribute(attribute);
        return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsed) ? parsed : fallback;
    }

    private readonly record struct SvgStyle(bool HasStroke, Color Stroke, float StrokeWidth, bool HasFill, Color Fill, float[] DashPattern)
    {
        public static SvgStyle Default => new(true, Color.Black, 1.5f, false, Color.Transparent, []);

        public SvgStyle Merge(XElement element, Color foreground, Color accent)
        {
            var strokeText = (string?)element.Attribute("stroke");
            var fillText = (string?)element.Attribute("fill");
            var widthText = (string?)element.Attribute("stroke-width");
            var dashText = (string?)element.Attribute("stroke-dasharray");

            var hasStroke = strokeText is null ? HasStroke : !strokeText.Equals("none", StringComparison.OrdinalIgnoreCase);
            var stroke = strokeText is null ? Stroke : ResolveColor(strokeText, foreground, accent, Stroke);
            var hasFill = fillText is null ? HasFill : !fillText.Equals("none", StringComparison.OrdinalIgnoreCase);
            var fill = fillText is null ? Fill : ResolveColor(fillText, foreground, accent, Fill);
            var width = widthText is not null && float.TryParse(widthText, NumberStyles.Float, CultureInfo.InvariantCulture, out var parsedWidth)
                ? parsedWidth
                : StrokeWidth;
            var dash = dashText is null
                ? DashPattern
                : dashText.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries)
                    .Select(value => float.Parse(value, CultureInfo.InvariantCulture))
                    .ToArray();
            return new SvgStyle(hasStroke, stroke, width, hasFill, fill, dash);
        }

        private static Color ResolveColor(string value, Color foreground, Color accent, Color fallback)
        {
            if (value.Equals("currentColor", StringComparison.OrdinalIgnoreCase)) return foreground;
            if (value.Equals("accent", StringComparison.OrdinalIgnoreCase)) return accent;
            if (value.StartsWith('#'))
            {
                try { return ColorTranslator.FromHtml(value); }
                catch { return fallback; }
            }
            return Color.FromName(value);
        }
    }
}
