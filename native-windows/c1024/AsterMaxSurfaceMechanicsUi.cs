using System;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using CaeGlobals;
using CaeModel;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void CreateAsterMaxPressure()
        {
            tsmiCreateLoad_Click(null,new EventArgs<int>(2));
        }

        private void CreateAsterMaxFrictionlessSupport()
        {
            if(_controller==null || _controller.Model==null || _controller.Model.Mesh==null)
            {
                MessageBox.Show(this,"Primero crea o abre un modelo mallado.","AsterMax · Frictionless Support",MessageBoxButtons.OK,MessageBoxIcon.Information);
                return;
            }
            string[] surfaces=_controller.Model.Mesh.Surfaces==null?new string[0]:
                _controller.Model.Mesh.Surfaces.Keys.OrderBy(x=>x,StringComparer.OrdinalIgnoreCase).ToArray();
            string[] steps=_controller.Model.StepCollection.StepsList.Where(x=>x is StaticStep).Select(x=>x.Name).ToArray();
            if(surfaces.Length==0 || steps.Length==0)
            {
                MessageBox.Show(this,"Se necesita al menos una superficie nombrada y un análisis Static Structural.","AsterMax · Frictionless Support",MessageBoxButtons.OK,MessageBoxIcon.Warning);
                return;
            }

            using(Form form=new Form())
            {
                form.Text="AsterMax · Frictionless Support";
                form.StartPosition=FormStartPosition.CenterParent;
                form.FormBorderStyle=FormBorderStyle.FixedDialog;
                form.MinimizeBox=false; form.MaximizeBox=false;
                form.ClientSize=new Size(430,190);
                var l1=new Label{Text="Análisis",Left=18,Top=22,Width=100};
                var c1=new ComboBox{Left=130,Top=18,Width=275,DropDownStyle=ComboBoxStyle.DropDownList};
                c1.Items.AddRange(steps); c1.SelectedIndex=0;
                var l2=new Label{Text="Superficie",Left=18,Top=62,Width=100};
                var c2=new ComboBox{Left=130,Top=58,Width=275,DropDownStyle=ComboBoxStyle.DropDownList};
                c2.Items.AddRange(surfaces); c2.SelectedIndex=0;
                var l3=new Label{Text="Nombre",Left=18,Top=102,Width=100};
                var t=new TextBox{Left=130,Top=98,Width=275,Text="Frictionless Support"};
                var ok=new Button{Text="Crear",Left=245,Top=143,Width=75,DialogResult=DialogResult.OK};
                var cancel=new Button{Text="Cancelar",Left=330,Top=143,Width=75,DialogResult=DialogResult.Cancel};
                form.Controls.AddRange(new Control[]{l1,c1,l2,c2,l3,t,ok,cancel});
                form.AcceptButton=ok; form.CancelButton=cancel;
                if(form.ShowDialog(this)!=DialogResult.OK) return;

                string baseName=String.IsNullOrWhiteSpace(t.Text)?"Frictionless Support":t.Text.Trim();
                string name=baseName; int suffix=2;
                var existing=_controller.GetAllBoundaryConditionNames();
                while(existing.Contains(name,StringComparer.OrdinalIgnoreCase)) name=baseName+" "+suffix++;
                _controller.AddBoundaryConditionCommand((string)c1.SelectedItem,new AsterMaxFrictionlessBC(name,(string)c2.SelectedItem,false));
                tsslState.Text="Frictionless Support creado";
                tsslState.ToolTipText="Code_Aster: FACE_IMPO / DNOR=0 sobre superficie nombrada";
            }
        }
    }
}
