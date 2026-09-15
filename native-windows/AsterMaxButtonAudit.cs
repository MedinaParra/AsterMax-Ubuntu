using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private ToolTip _axCommandTips;
        private static readonly Dictionary<string,string> AxCommandIcons = new Dictionary<string,string> {
            {"New","New"},{"Open","Open"},{"Import Geometry","Import"},{"Import STEP","Import"},
            {"Save","Save"},{"Fit","ZoomToFit"},{"Isometric","Isometric"},{"Analyze Geometry","Query"},
            {"Edges","ModelEdges"},{"Model Properties","Part"},{"Materials","Material"},
            {"Biblioteca","Library"},{"Nuevo material","Material"},{"Editar material","Material"},
            {"Asignar seccion","Section"},{"Mesh Controls","Meshing_parameters"},{"Generate Mesh","ElementEdges"},
            {"Analysis Step","Step"},{"Supports","Bc"},{"Loads","Load"},
            {"Export Solver Contract","Export"},{"Export Code_Aster Deck","Export"},{"Runtime","Query"},
            {"Solve","Running"},{"Results Explorer","Field_output"},{"FEA Viewport","Color_contours"},
            {"Contours","Color_contours"},{"Deformed","Deformed"},{"Front","Front"},{"Top","Top"},{"Right","Right"},
            {"Auditoria","Query"}
        };

        private void ConfigureAsterMaxButton(Button button, string caption, string group, Action action)
        {
            string key;
            if (!AxCommandIcons.TryGetValue(caption, out key))
                throw new InvalidOperationException("Command icon mapping missing: " + caption);
            Image icon = Properties.Resources.ResourceManager.GetObject(key) as Image;
            if (icon == null) throw new InvalidOperationException("Native icon missing: " + key);
            button.Name = "axCommand_" + group + "_" + caption.Replace(" ", "_");
            button.Text = caption;
            button.Image = icon;
            button.ImageAlign = ContentAlignment.TopCenter;
            button.TextAlign = ContentAlignment.BottomCenter;
            button.TextImageRelation = TextImageRelation.ImageAboveText;
            button.Tag = action;
            button.AccessibleName = caption;
            button.AccessibleDescription = group + ": " + caption;
            if (_axCommandTips == null) {
                _axCommandTips = new ToolTip { ShowAlways = true, AutoPopDelay = 15000 };
                Disposed += (s,e) => _axCommandTips.Dispose();
            }
            string tip = group + " — " + caption;
            if (caption == "Solve") tip += "\nCode_Aster en WSL2; requiere material, sección, malla, apoyo y carga.";
            else if (caption == "Generate Mesh") tip += "\nSeleccione una pieza de Geometry; utiliza NetGen incluido.";
            else if (caption == "Asignar seccion") tip += "\nAsigna el material a una región de la malla.";
            else if (caption == "Supports" || caption == "Loads") tip += "\nRequiere un paso de análisis y una región válida.";
            _axCommandTips.SetToolTip(button, tip);
        }

        private void InvokeAsterMaxCommand(string caption, Action action)
        {
            try { action(); }
            catch (Exception ex) {
                tsslState.Text = "Command failed: " + caption;
                CaeGlobals.MessageBoxes.ShowError(caption + ": " + ex.Message);
            }
        }

        private void OpenAsterMaxButtonAuditReport()
        {
            string path = Path.Combine(Application.StartupPath, "Audit", "BUTTON_AUDIT.html");
            if (!File.Exists(path)) throw new FileNotFoundException("El informe de auditoría no está incluido en este paquete.", path);
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo { FileName=path, UseShellExecute=true });
        }

        private static IEnumerable<Button> AxButtons(Control root)
        {
            foreach (Control child in root.Controls) {
                Button button = child as Button;
                if (button != null) yield return button;
                foreach (Button nested in AxButtons(child)) yield return nested;
            }
        }

        private void AuditAsterMaxButtons(string reportPath)
        {
            var ribbon = Controls["asterMaxRibbon"] as TabControl;
            if (ribbon == null) throw new InvalidOperationException("Command ribbon missing.");
            var rows = new JArray();
            TabPage previous = ribbon.SelectedTab;
            try {
                foreach (TabPage page in ribbon.TabPages) {
                    ribbon.SelectedTab = page;
                    ribbon.PerformLayout(); page.PerformLayout();
                    int count = 0;
                    foreach (Button button in AxButtons(page)) {
                        count++;
                        bool bound = button.Tag is Action;
                        bool icon = button.Image != null;
                        if (!bound || !icon || String.IsNullOrEmpty(button.AccessibleName))
                            throw new InvalidOperationException("Unbound/iconless command: " + page.Text + "/" + button.Text);
                        rows.Add(new JObject { ["tab"] = page.Text, ["button"] = button.Text,
                            ["action_bound"] = bound, ["icon_present"] = icon,
                            ["execution"] = "NOT_INVOKED", ["reason"] = "This gate checks UI wiring; it does not execute editing commands." });
                    }
                    if (count > 0) {
                        using (var bitmap = new Bitmap(Width, Height)) {
                            DrawToBitmap(bitmap, new Rectangle(0,0,Width,Height));
                            bitmap.Save(reportPath + ".buttons-" + page.Text.Replace(" ","_") + ".png");
                        }
                    }
                }
            }
            finally { ribbon.SelectedTab = previous; }
            if (rows.Count < 30) throw new InvalidOperationException("Command inventory unexpectedly incomplete.");
            var workflowStates=BuildAsterMaxSectionStates();
            if (_controller.Model.Materials.Count==0 && workflowStates["materials"].State!=0)
                throw new InvalidOperationException("Missing material must never show a completion tick.");
            if (_controller.Model.Sections.Count==0 && workflowStates["assignments"].State!=0)
                throw new InvalidOperationException("Missing material assignment must never show a completion tick.");
            File.WriteAllText(reportPath + ".buttons.json", new JObject {
                ["release"] = "C10.10", ["checks_pass"] = true, ["buttons"] = rows,
                ["scope"] = "Live ribbon icon and delegate binding; no claim of end-to-end command success.",
                ["workflow_states"] = JObject.FromObject(workflowStates)
            }.ToString(Formatting.Indented));
        }
    }
}
