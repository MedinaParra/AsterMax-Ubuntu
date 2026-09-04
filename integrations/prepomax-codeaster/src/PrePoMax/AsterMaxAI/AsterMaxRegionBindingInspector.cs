using System;
using System.Collections;
using System.Drawing;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace PrePoMax.AsterMaxAI
{
    public sealed class AsterMaxRegionBindingInspector : UserControl
    {
        private readonly Controller _controller;
        private readonly TextBox _report;
        private readonly Timer _timer;

        public AsterMaxRegionBindingInspector(Controller controller)
        {
            _controller = controller;
            Name = "ucAsterMaxRegionBindingInspector";
            Dock = DockStyle.Bottom;
            Height = 118;
            BackColor = AsterMaxUiTheme.SurfaceRaised;
            Padding = new Padding(8, 5, 8, 5);

            Label title = new Label();
            title.Dock = DockStyle.Top;
            title.Height = 22;
            title.Text = "REGION BINDING INSPECTOR · BC/LOAD → REGION → ENTITY REFERENCES";
            title.ForeColor = AsterMaxUiTheme.AccentGlow;
            title.Font = new Font(SystemFonts.MessageBoxFont.FontFamily, 8.2f, FontStyle.Bold);

            _report = new TextBox();
            _report.Dock = DockStyle.Fill;
            _report.Multiline = true;
            _report.ReadOnly = true;
            _report.ScrollBars = ScrollBars.Vertical;
            _report.BackColor = AsterMaxUiTheme.Background;
            _report.ForeColor = AsterMaxUiTheme.TextSecondary;
            _report.BorderStyle = BorderStyle.FixedSingle;
            _report.Font = new Font(FontFamily.GenericMonospace, 7.7f, FontStyle.Regular);

            Controls.Add(_report);
            Controls.Add(title);

            _timer = new Timer();
            _timer.Interval = 1500;
            _timer.Tick += (s, e) => RefreshReport();
            _timer.Start();
            Disposed += (s, e) => _timer.Dispose();
            RefreshReport();
        }

        public void RefreshReport()
        {
            object model = null;
            try { if (_controller != null) model = _controller.Model; } catch { }
            StringBuilder sb = new StringBuilder();
            sb.AppendLine("Observed only. No viewport anchoring or solver verification is inferred.");
            if (model == null) { sb.Append("MODEL: MISSING"); _report.Text = sb.ToString(); return; }
            InspectCollection(model, "BoundaryConditions", "BC", sb);
            InspectCollection(model, "Loads", "LOAD", sb);
            _report.Text = sb.ToString();
        }

        private static void InspectCollection(object model, string propertyName, string kind, StringBuilder sb)
        {
            try
            {
                PropertyInfo pi = model.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (pi == null) { sb.AppendLine(kind + ": COLLECTION API UNKNOWN"); return; }
                object value = pi.GetValue(model, null);
                IEnumerable enumerable = value as IEnumerable;
                if (enumerable == null) { sb.AppendLine(kind + ": NONE/UNREADABLE"); return; }
                int count = 0;
                foreach (object item in enumerable)
                {
                    if (item == null) continue;
                    count++;
                    object target = UnwrapDictionaryEntry(item);
                    Type t = target.GetType();
                    string name = ReadFirst(target, new[] { "Name", "RegionName" });
                    string region = ReadFirst(target, new[] { "RegionName", "CreationData", "Region" });
                    string regionType = ReadFirst(target, new[] { "RegionType", "SelectionType" });
                    string entityIds = ReadFirst(target, new[] { "CreationIds", "GeometryIds", "NodeIds", "ElementIds", "Ids" });
                    sb.AppendLine(kind + "[" + count + "] type=" + t.Name + " name=" + Safe(name) + " region=" + Safe(region) + " regionType=" + Safe(regionType) + " entityRefs=" + Safe(entityIds));
                }
                if (count == 0) sb.AppendLine(kind + ": NONE");
            }
            catch (Exception ex) { sb.AppendLine(kind + ": INSPECTION UNKNOWN (" + ex.GetType().Name + ")"); }
        }

        private static object UnwrapDictionaryEntry(object item)
        {
            Type t = item.GetType();
            PropertyInfo v = t.GetProperty("Value", BindingFlags.Public | BindingFlags.Instance);
            if (v != null) { try { object x = v.GetValue(item, null); if (x != null) return x; } catch { } }
            return item;
        }

        private static string ReadFirst(object target, string[] names)
        {
            foreach (string name in names)
            {
                try
                {
                    PropertyInfo pi = target.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pi == null) continue;
                    object v = pi.GetValue(target, null);
                    if (v == null) continue;
                    IEnumerable e = v as IEnumerable;
                    if (e != null && !(v is string))
                    {
                        StringBuilder b = new StringBuilder(); int n = 0;
                        foreach (object x in e) { if (n++ > 0) b.Append(','); b.Append(x); if (n >= 8) { b.Append("…"); break; } }
                        return b.ToString();
                    }
                    return v.ToString();
                }
                catch { }
            }
            return "?";
        }

        private static string Safe(string s) { return String.IsNullOrWhiteSpace(s) ? "?" : s; }
    }
}
