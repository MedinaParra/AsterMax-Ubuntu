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
        private static readonly Dictionary<string,string[]> AxExpectedCommandsByTab = new Dictionary<string,string[]> {
            {"Inicio",new[]{"Nuevo","Abrir","Importar","Guardar","Deshacer","Rehacer","Ajustar","Isométrica"}},
            {"Geometría",new[]{"Importar STEP","Analizar","Ajustar","Isométrica","Aristas"}},
            {"Modelo",new[]{"Propiedades","Material","Sección"}},
            {"Malla",new[]{"Controles","Refinamiento","Generar malla"}},
            {"Entorno",new[]{"Paso","Apoyo","Carga"}},
            {"Solución",new[]{"Verificar","Contrato","Deck Aster","Ejecutar","Cancelar"}},
            {"Resultados",new[]{"Explorador","Viewport FEA","Contornos","Deformada","Original"}},
            {"Vista",new[]{"Auditoría","Ajustar","Frontal","Superior","Derecha","Isométrica","Aristas"}}
        };

        private void ConfigureAsterMaxButton(Button button, string caption, string group, Action action)
        {
            // C10.27: captions are presentation text, never runtime keys.
            // C10.25 already assigns the original AsterMax engineering icon in CommandTile.
            // Keep that image. Fall back to a native resource only when no generated icon exists.
            if (button.Image == null)
            {
                string key;
                Image icon = null;
                if (AxCommandIcons.TryGetValue(caption, out key))
                    icon = Properties.Resources.ResourceManager.GetObject(key) as Image;
                if (icon == null)
                    icon = Properties.Resources.ResourceManager.GetObject("Query") as Image;
                if (icon != null)
                    button.Image = CreateAsterMaxCommandIcon(icon, caption, group);
            }

            button.Name = "axCommand_" + AsterMaxSafeControlToken(group) + "_" + AsterMaxSafeControlToken(caption);
            button.Text = caption;
            button.ImageAlign = ContentAlignment.TopCenter;
            button.TextAlign = ContentAlignment.BottomCenter;
            button.TextImageRelation = TextImageRelation.ImageAboveText;
            button.Tag = action;
            button.AccessibleName = caption;
            button.AccessibleDescription = group + ": " + caption;

            if (_axCommandTips == null)
            {
                _axCommandTips = new ToolTip { ShowAlways = true, AutoPopDelay = 15000 };
                Disposed += (s,e) => _axCommandTips.Dispose();
            }

            string tip = group + " — " + caption;
            if (caption == "Ejecutar") tip += "\nCode_Aster nativo de Windows; requiere material, sección, malla, apoyo, carga y preflight válido.";
            else if (caption == "Generar malla") tip += "\nSeleccione una pieza de Geometría; utiliza NetGen incluido.";
            else if (caption == "Sección") tip += "\nAsigna material y propiedades de sección a una región válida.";
            else if (caption == "Apoyo" || caption == "Carga") tip += "\nRequiere un paso de análisis y una región válida.";
            _axCommandTips.SetToolTip(button, tip);
        }

        private static string AsterMaxSafeControlToken(string value)
        {
            if (String.IsNullOrEmpty(value)) return "Command";
            var chars = value.Normalize(System.Text.NormalizationForm.FormD)
                .Where(ch => System.Globalization.CharUnicodeInfo.GetUnicodeCategory(ch) != System.Globalization.UnicodeCategory.NonSpacingMark)
                .Select(ch => Char.IsLetterOrDigit(ch) ? ch : '_')
                .ToArray();
            return new string(chars);
        }

        private static Image CreateAsterMaxCommandIcon(Image source,string caption,string group)
        {
            Color accent=Color.FromArgb(32,116,190);
            if(group.Contains("CAD")||group.Contains("MESH")) accent=Color.FromArgb(210,117,18);
            if(group.Contains("MODEL")||caption.Contains("material")||caption=="Biblioteca") accent=Color.FromArgb(142,68,173);
            if(caption=="Open") accent=Color.FromArgb(192,135,0);
            if(caption=="New"||caption=="Solve"||caption=="Generate Mesh") accent=Color.FromArgb(32,145,84);
            if(caption=="Loads"||caption=="Supports") accent=Color.FromArgb(211,72,58);
            if(caption=="Runtime"||caption=="Auditoria") accent=Color.FromArgb(27,143,157);
            if(group.Contains("RESULT")||caption=="Contours"||caption=="Deformed") accent=Color.FromArgb(180,64,121);
            var bitmap=new Bitmap(32,32);
            using(var graphics=Graphics.FromImage(bitmap)) {
                graphics.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                graphics.InterpolationMode=System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                using(var brush=new SolidBrush(Color.FromArgb(35,accent))) graphics.FillEllipse(brush,0,0,31,31);
                using(var attributes=new System.Drawing.Imaging.ImageAttributes()) {
                    var matrix=new System.Drawing.Imaging.ColorMatrix();
                    matrix.Matrix00=matrix.Matrix11=matrix.Matrix22=0.5f;
                    matrix.Matrix40=accent.R/510f;matrix.Matrix41=accent.G/510f;matrix.Matrix42=accent.B/510f;
                    attributes.SetColorMatrix(matrix);
                    graphics.DrawImage(source,new Rectangle(6,6,20,20),0,0,source.Width,source.Height,GraphicsUnit.Pixel,attributes);
                }
            }
            return bitmap;
        }

        private void InvokeAsterMaxCommand(string caption, Action action)
        {
            try { action(); }
            catch (Exception ex) when (
                ex is InvalidOperationException || ex is NotSupportedException || ex is ArgumentException ||
                ex is IOException || ex is UnauthorizedAccessException || ex is System.ComponentModel.Win32Exception) {
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
            _modelTree.RefreshAsterMaxOutline();
            var rows = new JArray();
            var validations = new JArray();
            var missingCommands = new List<string>();
            bool checksPass = true;
            Action<string,bool,string> check = (name,pass,evidence) => {
                validations.Add(new JObject { ["check"]=name,["pass"]=pass,["evidence"]=evidence });
                checksPass &= pass;
            };
            bool canCapture = WindowState != FormWindowState.Minimized && Width > 0 && Height > 0;
            check("screenshot_dimensions_positive",canCapture,
                "WindowState="+WindowState+" Width="+Width+" Height="+Height);
            TabPage previous = ribbon.SelectedTab;
            try {
                foreach (TabPage page in ribbon.TabPages) {
                    ribbon.SelectedTab = page;
                    ribbon.PerformLayout(); page.PerformLayout();
                    var actualCommands = new HashSet<string>(StringComparer.Ordinal);
                    foreach (Button button in AxButtons(page)) {
                        bool bound = button.Tag is Action;
                        bool icon = button.Image != null;
                        bool accessible = !String.IsNullOrEmpty(button.AccessibleName);
                        actualCommands.Add(button.Text);
                        check("button_wiring:"+page.Text+"/"+button.Text,bound&&icon&&accessible,
                            "action_bound="+bound+" icon_present="+icon+" accessible_name="+accessible);
                        rows.Add(new JObject { ["tab"] = page.Text, ["button"] = button.Text,
                            ["action_bound"] = bound, ["icon_present"] = icon, ["accessible_name"] = accessible,
                            ["execution"] = "NOT_INVOKED", ["reason"] = "This gate checks UI wiring; it does not execute editing commands." });
                    }
                    string[] expected;
                    if (AxExpectedCommandsByTab.TryGetValue(page.Text,out expected)) {
                        foreach (string command in expected) {
                            bool present=actualCommands.Contains(command);
                            check("expected_command:"+page.Text+"/"+command,present,present?"present":"missing");
                            if(!present) missingCommands.Add(page.Text+"/"+command);
                        }
                    }
                    if (actualCommands.Count > 0 && canCapture) {
                        using (var bitmap = new Bitmap(Width, Height)) {
                            DrawToBitmap(bitmap, new Rectangle(0,0,Width,Height));
                            bitmap.Save(reportPath + ".buttons-" + page.Text.Replace(" ","_") + ".png");
                        }
                    }
                }
            }
            finally { ribbon.SelectedTab = previous; }
            var workflowStates=BuildAsterMaxSectionStates();
            check("missing_material_not_complete",
                !(_controller.Model.Materials.Count==0 && workflowStates["materials"].State!=0),
                "materials="+_controller.Model.Materials.Count+" state="+workflowStates["materials"].State);
            check("missing_assignment_not_complete",
                !(_controller.Model.Sections.Count==0 && workflowStates["assignments"].State!=0),
                "sections="+_controller.Model.Sections.Count+" state="+workflowStates["assignments"].State);
            var contextMenuChecks=_modelTree.AuditAsterMaxContextMenus();
            var configurationRegressions=AuditAsterMaxWorkflowStates();
            var materialLibrary=AuditAsterMaxMaterialLibrary(reportPath);
            File.WriteAllText(reportPath + ".buttons.json", new JObject {
                ["release"] = "C10.10.1", ["checks_pass"] = checksPass, ["buttons"] = rows,
                ["validations"] = validations,
                ["expected_commands_by_tab"] = JObject.FromObject(AxExpectedCommandsByTab),
                ["missing_commands"] = JArray.FromObject(missingCommands),
                ["scope"] = "Live ribbon icon and delegate binding; no claim of end-to-end command success.",
                ["workflow_states"] = JObject.FromObject(workflowStates),
                ["context_menu_lifecycle_checks"] = contextMenuChecks,
                ["configuration_regressions"] = configurationRegressions,
                ["material_library"] = materialLibrary
            }.ToString(Formatting.Indented));
            if(!checksPass) {
                string missing=missingCommands.Count==0?"none":String.Join(", ",missingCommands);
                throw new InvalidOperationException("Button audit failed. Missing commands: "+missing+". See validations in the audit artifact.");
            }
        }
    }
}
