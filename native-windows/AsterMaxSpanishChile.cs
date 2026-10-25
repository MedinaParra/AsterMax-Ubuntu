using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using System.Windows.Forms;

namespace PrePoMax
{
    internal static class AsterMaxSpanishChile
    {
        private static readonly Dictionary<string, string> Exact = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            {"Home","Inicio"},{"Geometry","Geometría"},{"Model","Modelo"},{"Connections","Conexiones"},{"Mesh","Malla"},{"Environment","Entorno"},{"Solution","Solución"},{"Results","Resultados"},{"View","Vista"},
            {"File","Archivo"},{"Edit","Editar"},{"Tools","Herramientas"},{"Help","Ayuda"},{"New","Nuevo"},{"Open","Abrir"},{"Save","Guardar"},{"Save As","Guardar como"},{"Close","Cerrar"},{"Cancel","Cancelar"},{"OK","Aceptar"},{"Apply","Aplicar"},
            {"Yes","Sí"},{"No","No"},{"Delete","Eliminar"},{"Rename","Renombrar"},{"Import","Importar"},{"Export","Exportar"},{"Import Geometry","Importar geometría"},{"Import STEP","Importar STEP"},{"Analyze Geometry","Analizar geometría"},
            {"Model Properties","Propiedades del modelo"},{"Materials","Materiales"},{"Material","Material"},{"Section","Sección"},{"Sections","Secciones"},{"Coordinate Systems","Sistemas de coordenadas"},{"Named Selections","Selecciones nombradas"},
            {"Mesh Controls","Controles de malla"},{"Generate Mesh","Generar malla"},{"Local Mesh Controls","Controles locales de malla"},{"Supports","Apoyos"},{"Loads","Cargas"},{"Supports / BCs","Apoyos / CC"},{"BCs","Condiciones de borde"},
            {"Analysis","Análisis"},{"Analyses","Análisis"},{"Static Structural","Estructural estático"},{"Solver","Solver"},{"Solve","Resolver"},{"Cancel Solve","Cancelar solución"},{"Contours","Contornos"},{"Deformed","Deformada"},{"Edges","Aristas"},
            {"Fit","Ajustar"},{"Front","Frontal"},{"Top","Superior"},{"Right","Derecha"},{"Isometric","Isométrica"},{"Graphics","Gráficos"},{"Outline","Árbol del modelo"},{"Project","Proyecto"},{"Scope","Alcance"},{"Display","Visualización"},
            {"Camera","Cámara"},{"Check","Verificar"},{"Report","Informe"},{"Audit","Auditoría"},{"Settings","Configuración"},{"General","General"},{"Name","Nombre"},{"Type","Tipo"},{"Value","Valor"},{"Status","Estado"},{"Ready","Listo"},{"Running","Ejecutando"},
            {"Failed","Falló"},{"Cancelled","Cancelado"},{"Cancelling","Cancelando"},{"Postprocessing","Postprocesando"},{"Previous successful result","Resultado exitoso anterior"},{"Solution Information","Información de la solución"},{"Deformation","Deformación"},
            {"Equivalent Stress","Esfuerzo equivalente"},{"Reactions","Reacciones"},{"Nodes","Nodos"},{"Elements","Elementos"},{"Part","Pieza"},{"Parts","Piezas"},{"Geometry / Named Selection","Geometría / Selección nombrada"}
        };

        private static readonly KeyValuePair<string, string>[] Phrase =
        {
            new KeyValuePair<string,string>("Mechanical Analysis","Análisis mecánico"), new KeyValuePair<string,string>("Code_Aster ready path","Code_Aster listo"),
            new KeyValuePair<string,string>("Code_Aster integration path","Integración con Code_Aster"), new KeyValuePair<string,string>("Please check the output window","Revisa la ventana de salida"),
            new KeyValuePair<string,string>("Errors occurred during meshing","Ocurrieron errores durante el mallado"), new KeyValuePair<string,string>("Material assignment incomplete","Asignación de material incompleta"),
            new KeyValuePair<string,string>("Open project","Abrir proyecto"), new KeyValuePair<string,string>("Save project","Guardar proyecto"), new KeyValuePair<string,string>("Import geometry","Importar geometría"),
            new KeyValuePair<string,string>("Create mesh","Crear malla"), new KeyValuePair<string,string>("Meshing parameters","Parámetros de mallado"), new KeyValuePair<string,string>("Boundary conditions","Condiciones de borde"),
            new KeyValuePair<string,string>("Initial conditions","Condiciones iniciales"), new KeyValuePair<string,string>("Field output","Salida de campo"), new KeyValuePair<string,string>("History output","Salida histórica")
        };

        public static void Start(Form main)
        {
            Thread.CurrentThread.CurrentCulture = CultureInfo.GetCultureInfo("es-CL");
            Thread.CurrentThread.CurrentUICulture = CultureInfo.GetCultureInfo("es-CL");
            CultureInfo.DefaultThreadCurrentCulture = CultureInfo.GetCultureInfo("es-CL");
            CultureInfo.DefaultThreadCurrentUICulture = CultureInfo.GetCultureInfo("es-CL");

            // C10.57: translate the main form once. The former 350 ms timer recursively
            // rescanned every open form/tree/toolstrip on the UI thread and could race
            // controls while dialogs were being closed or rebuilt.
            TranslateForm(main);
            Application.Idle -= TranslateOpenFormsOnIdle;
            Application.Idle += TranslateOpenFormsOnIdle;
        }

        private static readonly HashSet<Form> TranslatedForms = new HashSet<Form>();

        private static void TranslateOpenFormsOnIdle(object sender, EventArgs e)
        {
            // Only translate newly opened forms once; never rescan the whole UI periodically.
            var snapshot = new List<Form>();
            foreach (Form form in Application.OpenForms) snapshot.Add(form);
            foreach (Form form in snapshot)
            {
                if (form == null || form.IsDisposed || form.Disposing || TranslatedForms.Contains(form)) continue;
                TranslateForm(form);
                TranslatedForms.Add(form);
                form.FormClosed += delegate { TranslatedForms.Remove(form); };
            }
        }

        private static void TranslateForm(Form form)
        {
            if (form == null || form.IsDisposed || form.Disposing) return;
            if (!String.IsNullOrWhiteSpace(form.Text)) form.Text = Translate(form.Text);
            TranslateControls(form.Controls);
        }

        private static void TranslateControls(Control.ControlCollection controls)
        {
            if (controls == null) return;
            foreach (Control control in controls)
            {
                if (control == null || control.IsDisposed || control.Disposing) continue;
                if (!(control is TextBox) && !(control is RichTextBox) && !(control is ComboBox) && !String.IsNullOrWhiteSpace(control.Text)) control.Text = Translate(control.Text);

                MenuStrip menu = control as MenuStrip; if (menu != null) TranslateItems(menu.Items);
                ToolStrip tool = control as ToolStrip; if (tool != null) TranslateItems(tool.Items);
                TreeView tree = control as TreeView; if (tree != null) TranslateNodes(tree.Nodes);
                DataGridView grid = control as DataGridView;
                if (grid != null && !grid.IsDisposed)
                    foreach (DataGridViewColumn column in grid.Columns)
                        if (column != null && !String.IsNullOrWhiteSpace(column.HeaderText)) column.HeaderText = Translate(column.HeaderText);

                if (!control.IsDisposed && !control.Disposing) TranslateControls(control.Controls);
            }
        }

        private static void TranslateItems(ToolStripItemCollection items)
        {
            if (items == null) return;
            // Copy references first: dropdown collections can mutate while a menu/dialog closes.
            var snapshot = new List<ToolStripItem>();
            foreach (ToolStripItem item in items) if (item != null) snapshot.Add(item);
            foreach (ToolStripItem item in snapshot)
            {
                if (item.IsDisposed) continue;
                string text = item.Text;
                if (!String.IsNullOrWhiteSpace(text)) item.Text = Translate(text);
                ToolStripDropDownItem drop = item as ToolStripDropDownItem;
                if (drop != null && !drop.IsDisposed && drop.HasDropDownItems) TranslateItems(drop.DropDownItems);
            }
        }

        private static void TranslateNodes(TreeNodeCollection nodes)
        {
            if (nodes == null) return;
            foreach (TreeNode node in nodes)
            {
                if (node == null || node.TreeView != null && node.TreeView.IsDisposed) continue;
                string text = node.Text;
                if (!String.IsNullOrWhiteSpace(text)) node.Text = Translate(text);
                if (node.Nodes != null && node.Nodes.Count > 0) TranslateNodes(node.Nodes);
            }
        }

        private static string Translate(string input)
        {
            if (String.IsNullOrWhiteSpace(input)) return input;
            string exact;
            if (Exact.TryGetValue(input.Trim(), out exact))
            {
                if (input.StartsWith(" ")) exact = " " + exact;
                if (input.EndsWith(" ")) exact = exact + " ";
                return exact;
            }
            string result = input;
            for (int i = 0; i < Phrase.Length; i++) result = ReplaceIgnoreCase(result, Phrase[i].Key, Phrase[i].Value);
            return result;
        }

        private static string ReplaceIgnoreCase(string text, string oldValue, string newValue)
        {
            int start = 0;
            while (true)
            {
                int index = text.IndexOf(oldValue, start, StringComparison.OrdinalIgnoreCase);
                if (index < 0) break;
                text = text.Substring(0, index) + newValue + text.Substring(index + oldValue.Length);
                start = index + newValue.Length;
            }
            return text;
        }
    }
}
