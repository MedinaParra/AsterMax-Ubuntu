using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;
using System.Windows.Forms;

namespace PrePoMax
{
    internal static class AsterMaxSpanishChile
    {
        private static readonly Dictionary<string, string> Exact =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                {"Home","Inicio"},{"Geometry","Geometría"},{"Model","Modelo"},
                {"Connections","Conexiones"},{"Mesh","Malla"},{"Environment","Entorno"},
                {"Solution","Solución"},{"Results","Resultados"},{"View","Vista"},
                {"File","Archivo"},{"Edit","Editar"},{"Tools","Herramientas"},{"Help","Ayuda"},
                {"New","Nuevo"},{"Open","Abrir"},{"Save","Guardar"},{"Save As","Guardar como"},
                {"Close","Cerrar"},{"Cancel","Cancelar"},{"OK","Aceptar"},{"Apply","Aplicar"},
                {"Yes","Sí"},{"No","No"},{"Delete","Eliminar"},{"Rename","Renombrar"},
                {"Import","Importar"},{"Export","Exportar"},{"Import Geometry","Importar geometría"},
                {"Import STEP","Importar STEP"},{"Analyze Geometry","Analizar geometría"},
                {"Model Properties","Propiedades del modelo"},{"Materials","Materiales"},
                {"Material","Material"},{"Section","Sección"},{"Sections","Secciones"},
                {"Coordinate Systems","Sistemas de coordenadas"},{"Named Selections","Selecciones nombradas"},
                {"Mesh Controls","Controles de malla"},{"Generate Mesh","Generar malla"},
                {"Local Mesh Controls","Controles locales de malla"},{"Supports","Apoyos"},
                {"Loads","Cargas"},{"Supports / BCs","Apoyos / CC"},{"BCs","Condiciones de borde"},
                {"Analysis","Análisis"},{"Analyses","Análisis"},{"Static Structural","Estructural estático"},
                {"Solver","Solver"},{"Solve","Resolver"},{"Cancel Solve","Cancelar solución"},
                {"Contours","Contornos"},{"Deformed","Deformada"},{"Edges","Aristas"},
                {"Fit","Ajustar"},{"Front","Frontal"},{"Top","Superior"},{"Right","Derecha"},
                {"Isometric","Isométrica"},{"Graphics","Gráficos"},{"Outline","Árbol del modelo"},
                {"Project","Proyecto"},{"Scope","Alcance"},{"Display","Visualización"},
                {"Camera","Cámara"},{"Check","Verificar"},{"Report","Informe"},{"Audit","Auditoría"},
                {"Settings","Configuración"},{"General","General"},{"Name","Nombre"},{"Type","Tipo"},
                {"Value","Valor"},{"Status","Estado"},{"Ready","Listo"},{"Running","Ejecutando"},
                {"Failed","Falló"},{"Cancelled","Cancelado"},{"Cancelling","Cancelando"},
                {"Postprocessing","Postprocesando"},{"Previous successful result","Resultado exitoso anterior"},
                {"Solution Information","Información de la solución"},{"Deformation","Deformación"},
                {"Equivalent Stress","Esfuerzo equivalente"},{"Reactions","Reacciones"},
                {"Nodes","Nodos"},{"Elements","Elementos"},{"Part","Pieza"},{"Parts","Piezas"},
                {"Geometry / Named Selection","Geometría / Selección nombrada"}
            };

        private static readonly KeyValuePair<string, string>[] Phrase =
        {
            new KeyValuePair<string,string>("Mechanical Analysis","Análisis mecánico"),
            new KeyValuePair<string,string>("Code_Aster ready path","Code_Aster listo"),
            new KeyValuePair<string,string>("Code_Aster integration path","Integración con Code_Aster"),
            new KeyValuePair<string,string>("Coordinate systems and named selections live in Outline","Los sistemas de coordenadas y selecciones nombradas están en el árbol del modelo"),
            new KeyValuePair<string,string>("Connections and constraints are scoped from the real model tree","Las conexiones y restricciones se definen desde el árbol real del modelo"),
            new KeyValuePair<string,string>("Supports and loads remain connected to native scoping","Los apoyos y cargas mantienen el alcance nativo"),
            new KeyValuePair<string,string>("Solution requests stay in the analysis tree; no synthetic results","Las solicitudes de solución quedan en el árbol de análisis; sin resultados sintéticos"),
            new KeyValuePair<string,string>("Deformation • Equivalent Stress • Reactions","Deformación • Esfuerzo equivalente • Reacciones"),
            new KeyValuePair<string,string>("TET4 baseline • TET10 next gate","Base TET4 • siguiente etapa TET10"),
            new KeyValuePair<string,string>("Please check the output window","Revisa la ventana de salida"),
            new KeyValuePair<string,string>("Errors occurred during meshing","Ocurrieron errores durante el mallado"),
            new KeyValuePair<string,string>("Material assignment incomplete","Asignación de material incompleta"),
            new KeyValuePair<string,string>("Inactive or invalid support","Apoyo inactivo o inválido"),
            new KeyValuePair<string,string>("Inactive or invalid load","Carga inactiva o inválida"),
            new KeyValuePair<string,string>("Node group is empty or contains missing mesh nodes","El grupo de nodos está vacío o contiene nodos inexistentes"),
            new KeyValuePair<string,string>("Open project","Abrir proyecto"),
            new KeyValuePair<string,string>("Save project","Guardar proyecto"),
            new KeyValuePair<string,string>("Import geometry","Importar geometría"),
            new KeyValuePair<string,string>("Create mesh","Crear malla"),
            new KeyValuePair<string,string>("Meshing parameters","Parámetros de mallado"),
            new KeyValuePair<string,string>("Boundary conditions","Condiciones de borde"),
            new KeyValuePair<string,string>("Initial conditions","Condiciones iniciales"),
            new KeyValuePair<string,string>("Field output","Salida de campo"),
            new KeyValuePair<string,string>("History output","Salida histórica")
        };

        private static System.Windows.Forms.Timer _timer;

        public static void Start(Form main)
        {
            Thread.CurrentThread.CurrentCulture = CultureInfo.GetCultureInfo("es-CL");
            Thread.CurrentThread.CurrentUICulture = CultureInfo.GetCultureInfo("es-CL");
            CultureInfo.DefaultThreadCurrentCulture = CultureInfo.GetCultureInfo("es-CL");
            CultureInfo.DefaultThreadCurrentUICulture = CultureInfo.GetCultureInfo("es-CL");

            TranslateForm(main);

            if (_timer == null)
            {
                _timer = new System.Windows.Forms.Timer();
                _timer.Interval = 350;
                _timer.Tick += delegate
                {
                    foreach (Form form in Application.OpenForms)
                        TranslateForm(form);
                };
                _timer.Start();
            }
        }

        private static void TranslateForm(Form form)
        {
            if (form == null || form.IsDisposed) return;
            if (!String.IsNullOrWhiteSpace(form.Text)) form.Text = Translate(form.Text);
            TranslateControls(form.Controls);

            foreach (Control control in form.Controls)
                TranslateSpecial(control);
        }

        private static void TranslateControls(Control.ControlCollection controls)
        {
            foreach (Control control in controls)
            {
                if (!(control is TextBox) && !(control is RichTextBox) && !(control is ComboBox))
                {
                    if (!String.IsNullOrWhiteSpace(control.Text))
                        control.Text = Translate(control.Text);
                }

                MenuStrip menu = control as MenuStrip;
                if (menu != null) TranslateItems(menu.Items);

                ToolStrip tool = control as ToolStrip;
                if (tool != null) TranslateItems(tool.Items);

                TreeView tree = control as TreeView;
                if (tree != null) TranslateNodes(tree.Nodes);

                DataGridView grid = control as DataGridView;
                if (grid != null)
                {
                    foreach (DataGridViewColumn column in grid.Columns)
                        if (!String.IsNullOrWhiteSpace(column.HeaderText))
                            column.HeaderText = Translate(column.HeaderText);
                }

                TranslateControls(control.Controls);
            }
        }

        private static void TranslateSpecial(Control root)
        {
            MenuStrip menu = root as MenuStrip;
            if (menu != null) TranslateItems(menu.Items);
            ToolStrip tool = root as ToolStrip;
            if (tool != null) TranslateItems(tool.Items);
            TreeView tree = root as TreeView;
            if (tree != null) TranslateNodes(tree.Nodes);
            foreach (Control child in root.Controls) TranslateSpecial(child);
        }

        private static void TranslateItems(ToolStripItemCollection items)
        {
            foreach (ToolStripItem item in items)
            {
                if (!String.IsNullOrWhiteSpace(item.Text))
                    item.Text = Translate(item.Text);
                ToolStripDropDownItem drop = item as ToolStripDropDownItem;
                if (drop != null) TranslateItems(drop.DropDownItems);
            }
        }

        private static void TranslateNodes(TreeNodeCollection nodes)
        {
            foreach (TreeNode node in nodes)
            {
                if (!String.IsNullOrWhiteSpace(node.Text))
                    node.Text = Translate(node.Text);
                TranslateNodes(node.Nodes);
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
            for (int i = 0; i < Phrase.Length; i++)
                result = ReplaceIgnoreCase(result, Phrase[i].Key, Phrase[i].Value);
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
