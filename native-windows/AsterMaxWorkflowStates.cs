using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using CaeModel;
using CaeGlobals;
using UserControls;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void SelectAsterMaxAnalysisType()
        {
            if (_controller == null || _controller.Model == null || _controller.Model.Mesh == null) {
                MessageBox.Show(this,"Primero cree el modelo y genere o importe la malla. Luego seleccione el tipo de estudio.","Type Analysis");
                return;
            }
            _controller.CurrentView = ViewGeometryModelResults.Model;
            if (_controller.GetAllSteps().Length == 0) tsmiCreateStep_Click(null,EventArgs.Empty);
            else tsmiEditStep_Click(null,EventArgs.Empty);
        }

        private Dictionary<string,AsterMaxSectionState> BuildAsterMaxSectionStates()
        {
            var states=new Dictionary<string,AsterMaxSectionState>();
            var model=_controller.Model;
            bool mesh=model.Mesh!=null && model.Mesh.Elements!=null && model.Mesh.Elements.Count>0;
            bool geometry=model.Geometry!=null && model.Geometry.Parts!=null && model.Geometry.Parts.Count>0;
            states["geometry"]=new AsterMaxSectionState(geometry||mesh?2:0,geometry?"Geometría importada.":mesh?"Modelo definido por malla importada.":"Obligatorio: importar geometría o malla.");
            var steps=model.StepCollection.StepsList.Where(s=>!(s is InitialStep)).ToArray();
            bool analysis=steps.Length==1 && steps[0] is StaticStep && !steps[0].Nlgeom && steps[0].Active && steps[0].Valid;
            states["ax-analysis"]=new AsterMaxSectionState(steps.Length==0?0:analysis?2:1,
                steps.Length==0?"Obligatorio: seleccionar el tipo de estudio con doble clic.":analysis?
                "Estudio estático lineal seleccionado; compatible con el puente Code_Aster.":
                "Tipo/configuración no soportado por Run: el puente admite un estudio estático lineal. Edite el estudio.");
            JObject contract=null; string contractError=null;
            try { contract=AsterMaxModelContractBridge.Build(model); } catch(Exception ex) { contractError=ex.Message; }
            int materialCount=model.Materials.Count;
            bool materials=materialCount==1;
            foreach(var entry in model.Materials) {
                var elastic=entry.Value.GetProperty<Elastic>() as Elastic;
                var density=entry.Value.GetProperty<ElasticWithDensity>() as ElasticWithDensity;
                double e=Double.NaN,nu=Double.NaN;
                if(elastic!=null && elastic.YoungsPoissonsTemp!=null && elastic.YoungsPoissonsTemp.Length>0 && elastic.YoungsPoissonsTemp[0].Length>=2) {
                    e=elastic.YoungsPoissonsTemp[0][0]; nu=elastic.YoungsPoissonsTemp[0][1];
                } else if(density!=null) { e=density.YoungsModulus; nu=density.PoissonsRatio; }
                materials &= entry.Value.Active && entry.Value.Valid && e>0 && !Double.IsInfinity(e) && nu>-1 && nu<0.5;
            }
            states["materials"]=new AsterMaxSectionState(materialCount==0?0:materials?2:1,materialCount==0?
                "Obligatorio: definir material, módulo E y coeficiente de Poisson.":materials?
                "Material elástico válido: E positivo y -1 < ν < 0,5.":"Revisar E, ν y material activo. El puente admite un material.");
            var assignment=AsterMaxAssignmentQualityGate.Evaluate(model);
            bool assigned=mesh && assignment.SectionCount>0 && assignment.UnassignedElementCount==0 &&
                assignment.MultiplyAssignedElementCount==0 && assignment.MissingMaterialReferenceCount==0 && assignment.MissingSectionRegionCount==0;
            states["assignments"]=new AsterMaxSectionState(model.Sections.Count==0?0:assigned&&materials?2:1,
                assigned&&materials?"Todos los elementos tienen una asignación de material válida y única.":
                "Obligatorio: asignar material a toda la malla; revisar sección, región y elementos sin asignación.");
            var readiness=AsterMaxPreSolveReadiness.Evaluate(model);
            bool meshValid=mesh && readiness.NodeCount>0 && readiness.UnsupportedElementCount==0 &&
                readiness.MissingNodeReferenceCount==0 && readiness.DegenerateConnectivityCount==0 && assignment.NonPositiveCenterJacobianCount==0;
            states["ax-mesh"]=new AsterMaxSectionState(!mesh?0:meshValid?2:1,!mesh?
                "Obligatorio: generar malla volumétrica.":meshValid?"Malla presente y conectividad compatible. Esto no certifica convergencia.":
                "Revisar unidades, conectividad, nodos y tipo de elementos.");
            int bc=steps.Sum(s=>s.BoundaryConditions.Count),loads=steps.Sum(s=>s.Loads.Count);
            bool supportValid=contract!=null && ValidAsterMaxGroups(contract,"supports","fixed") &&
                steps.SelectMany(s=>s.BoundaryConditions.Values).All(x=>x.Active&&x.Valid);
            bool loadValid=contract!=null && ValidAsterMaxGroups(contract,"loads","nodal_force_total") &&
                steps.SelectMany(s=>s.Loads.Values).All(x=>x.Active&&x.Valid);
            states["supports"]=new AsterMaxSectionState(bc==0?0:supportValid?2:1,bc==0?"Obligatorio: definir apoyo y región.":
                supportValid?"Apoyo fijo con grupo de nodos válido.":"Revisar apoyo activo y región; Run admite un apoyo fijo.");
            states["loads"]=new AsterMaxSectionState(loads==0?0:loadValid?2:1,loads==0?"Obligatorio: definir carga, componentes y región.":
                loadValid?"Fuerza nodal con grupo válido y componentes finitas.":"Revisar fuerza y región; Run admite una fuerza nodal.");
            bool configured=geometry||mesh;
            configured &= analysis&&materials&&assigned&&meshValid&&supportValid&&loadValid;
            states["ax-model"]=new AsterMaxSectionState(configured?2:1,configured?"Configuración obligatoria completa; falta preflight de runtime y resolver.":"Completar los pasos resaltados en amarillo.");
            states["ax-solution"]=new AsterMaxSectionState(1,configured?"Configuración lista. Ejecute Runtime y Solve; no hay resultado validado por este indicador.":"Complete el modelo antes de resolver.");
            states["ax-coordinates"]=new AsterMaxSectionState(1,"Sistema cartesiano global. Los sistemas locales no están integrados en el puente.");
            states["ax-connections"]=new AsterMaxSectionState(1,"Opcional para un sólido continuo; los contactos no están soportados por el puente actual.");
            states["ax-selections"]=new AsterMaxSectionState(1,"Opcional: grupos para delimitar regiones. No es un paso obligatorio independiente.");
            return states;
        }

        private static bool ValidAsterMaxGroups(JObject contract,string name,string type)
        {
            var items=contract[name] as JArray;
            if(items==null||items.Count!=1||(string)items[0]["type"]!=type) return false;
            string group=(string)items[0]["group"];
            var nodes=group==null?null:contract["mesh"]?["node_groups"]?[group] as JArray;
            if(nodes==null||nodes.Count==0) return false;
            if(name=="loads") foreach(string field in new[]{"fx_total_n","fy_total_n","fz_total_n"}) {
                double value=(double?)items[0][field]??Double.NaN;
                if(Double.IsNaN(value)||Double.IsInfinity(value)) return false;
            }
            return true;
        }
    }
}
