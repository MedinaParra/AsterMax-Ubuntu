using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using CaeModel;
using CaeGlobals;
using CaeMesh;
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
            return EvaluateAsterMaxSectionStates(_controller.Model);
        }

        private static Dictionary<string,AsterMaxSectionState> EvaluateAsterMaxSectionStates(FeModel model)
        {
            var states=new Dictionary<string,AsterMaxSectionState>();
            bool mesh=model.Mesh!=null && model.Mesh.Elements!=null && model.Mesh.Elements.Count>0;
            bool geometry=model.Geometry!=null && model.Geometry.Parts!=null && model.Geometry.Parts.Count>0;
            states["geometry"]=new AsterMaxSectionState(geometry||mesh?2:0,geometry?"Geometría importada.":mesh?"Modelo definido por malla importada.":"Obligatorio: importar geometría o malla.");
            var steps=model.StepCollection.StepsList.Where(s=>!(s is InitialStep)).ToArray();
            bool analysis=steps.Length==1 && steps[0].GetType()==typeof(StaticStep) && !steps[0].Nlgeom && steps[0].Active && steps[0].Valid;
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
                assignment.MultiplyAssignedElementCount==0 && assignment.MissingMaterialReferenceCount==0 && assignment.MissingSectionRegionCount==0 &&
                model.Sections.Values.All(s=>s is SolidSection && s.Active && s.Valid);
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
            bool loadValid=contract!=null && ValidAsterMaxLoadGroups(contract) &&
                steps.SelectMany(s=>s.Loads.Values).All(x=>x.Active&&x.Valid);
            states["supports"]=new AsterMaxSectionState(bc==0?0:supportValid?2:1,bc==0?"Obligatorio: definir apoyo y región.":
                supportValid?"Apoyo fijo con grupo de nodos válido.":"Revisar apoyo activo y región; Run admite un apoyo fijo. "+contractError);
            states["loads"]=new AsterMaxSectionState(loads==0?0:loadValid?2:1,loads==0?"Obligatorio: definir carga, componentes y región.":
                loadValid?"Fuerza nodal con grupo válido y componentes finitas.":"Revisar fuerza y región; Run admite una fuerza nodal. "+contractError);
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
            var meshNodes=contract["mesh"]?["nodes"] as JArray;
            if(meshNodes==null) return false;
            var ids=new HashSet<string>(meshNodes.Select(n=>(string)n["id"]));
            if(nodes.Any(n=>!ids.Contains((string)n))) return false;
            return true;
        }

        private static bool ValidAsterMaxLoadGroups(JObject contract)
        {
            var items=contract["loads"] as JArray;
            if(items==null||items.Count!=1) return false;
            string type=(string)items[0]["type"];
            bool perNode=String.Equals(type,"nodal_force_per_node",StringComparison.Ordinal);
            bool legacyTotal=String.Equals(type,"nodal_force_total",StringComparison.Ordinal);
            if(!perNode&&!legacyTotal) return false;
            string group=(string)items[0]["group"];
            var nodes=group==null?null:contract["mesh"]?["node_groups"]?[group] as JArray;
            if(nodes==null||nodes.Count==0) return false;
            var meshNodes=contract["mesh"]?["nodes"] as JArray;
            if(meshNodes==null) return false;
            var ids=new HashSet<string>(meshNodes.Select(n=>(string)n["id"]));
            if(nodes.Any(n=>!ids.Contains((string)n))) return false;
            string suffix=perNode?"_per_node_n":"_total_n";
            foreach(string axis in new[]{"fx","fy","fz"}) {
                double value=(double?)items[0][axis+suffix]??Double.NaN;
                if(Double.IsNaN(value)||Double.IsInfinity(value)) return false;
            }
            return true;
        }

        // Isolated native model fixtures: these check configuration states, never FEA results.
        private static FeModel CreateAsterMaxStatusFixture()
        {
            var model=new FeModel("Audit-C1010");
            model.UnitSystem=new UnitSystem(UnitSystemType.MM_TON_S_C);
            double[][] xyz={new[]{0.0,0.0,0.0},new[]{10.0,0.0,0.0},new[]{10.0,10.0,0.0},new[]{0.0,10.0,0.0},
                new[]{0.0,0.0,10.0},new[]{10.0,0.0,10.0},new[]{10.0,10.0,10.0},new[]{0.0,10.0,10.0}};
            for(int i=0;i<xyz.Length;i++) model.Mesh.Nodes.Add(i+1,new FeNode(i+1,xyz[i][0],xyz[i][1],xyz[i][2]));
            var ids=Enumerable.Range(1,8).ToArray();
            model.Mesh.Elements.Add(1,new LinearHexaElement(1,ids));
            model.Mesh.Parts.Add("Body",new MeshPart("Body",1,ids,new[]{1},new[]{typeof(LinearHexaElement)}));
            model.Mesh.ElementSets.Add("All",new FeElementSet("All",new[]{1}));
            model.Mesh.NodeSets.Add("FIXED",new FeNodeSet("FIXED",new[]{1,4,5,8}));
            model.Mesh.NodeSets.Add("LOAD",new FeNodeSet("LOAD",new[]{2,3,6,7}));
            var material=new Material("Steel");
            material.AddProperty(new Elastic(new[]{new[]{210000.0,0.3,20.0}}));
            model.Materials.Add(material.Name,material);
            model.Sections.Add("Solid",new SolidSection("Solid","Steel","Body",RegionTypeEnum.PartName,1,false));
            var step=new StaticStep("Step-1");
            step.AddBoundaryCondition(new FixedBC("Fixed","FIXED",RegionTypeEnum.NodeSetName,false));
            step.AddLoad(new CLoad("Force","LOAD",RegionTypeEnum.NodeSetName,100,0,0,false,false,0));
            model.StepCollection.AddStep(step,false);
            return model;
        }

        private static JArray AuditAsterMaxWorkflowStates()
        {
            var evidence=new JArray();
            Action<string,Action<FeModel>,string,int> check=(name,change,key,expected)=>{
                var model=CreateAsterMaxStatusFixture();
                change(model);
                var states=EvaluateAsterMaxSectionStates(model);
                int actual=states[key].State;
                if(actual!=expected) {
                    var assignment=AsterMaxAssignmentQualityGate.Evaluate(model);
                    var readiness=AsterMaxPreSolveReadiness.Evaluate(model);
                    string stateVector=String.Join(",",states.OrderBy(x=>x.Key,StringComparer.Ordinal)
                        .Select(x=>x.Key+"="+x.Value.State.ToString()));
                    throw new InvalidOperationException("Workflow status regression: "+name+" expected "+expected+" got "+actual+
                        " | states="+stateVector+
                        " | assignment="+assignment.AuditSummary()+
                        " | assignment_issues="+String.Join(",",assignment.Issues)+
                        " | readiness="+readiness.AuditSummary()+
                        " | readiness_issues="+String.Join(",",readiness.Issues));
                }
                evidence.Add(new JObject{["case"]=name,["section"]=key,["state"]=actual,["pass"]=true});
            };
            check("complete_native_part_assignment",m=>{},"ax-model",2);
            check("complete_element_set_assignment",m=>{m.Sections["Solid"].RegionType=RegionTypeEnum.ElementSetName;m.Sections["Solid"].RegionName="All";},"ax-model",2);
            check("missing_material",m=>m.Materials.Clear(),"materials",0);
            check("inactive_material",m=>m.Materials["Steel"].Active=false,"materials",1);
            check("missing_section",m=>m.Sections.Clear(),"assignments",0);
            check("inactive_section",m=>m.Sections["Solid"].Active=false,"assignments",1);
            check("missing_section_region",m=>m.Sections["Solid"].RegionName="Missing","assignments",1);
            check("duplicate_assignment",m=>m.Sections.Add("Other",new SolidSection("Other","Steel","All",RegionTypeEnum.ElementSetName,1,false)),"assignments",1);
            check("inactive_support",m=>m.StepCollection.StepsList[0].BoundaryConditions["Fixed"].Active=false,"supports",1);
            check("inactive_load",m=>m.StepCollection.StepsList[0].Loads["Force"].Active=false,"loads",1);
            check("dangling_load_group",m=>m.Mesh.NodeSets["LOAD"].Labels=new[]{999},"loads",1);
            check("incomplete_model_not_green",m=>m.Sections.Clear(),"ax-model",1);
            check("no_result_not_green",m=>{},"ax-solution",1);
            foreach(Step unsupported in new Step[]{new FrequencyStep("Frequency"),new SlipWearStep("SlipWear"),
                new StaticStep("Nonlinear"){Nlgeom=true},new StaticStep("Inactive"){Active=false}}) {
                var model=CreateAsterMaxStatusFixture();
                model.StepCollection.StepsList.Clear();
                model.StepCollection.AddStep(unsupported,false);
                if(EvaluateAsterMaxSectionStates(model)["ax-analysis"].State!=1)
                    throw new InvalidOperationException("Unsupported study must remain incomplete: "+unsupported.Name);
                bool rejected=false;
                try{AsterMaxModelContractBridge.Build(model);}
                catch(NotSupportedException ex){rejected=ex.Message.Contains("linear static study");}
                if(!rejected) throw new InvalidOperationException("Bridge silently accepted unsupported study: "+unsupported.Name);
                evidence.Add(new JObject{["case"]="reject_"+unsupported.Name,["pass"]=true});
            }
            string output=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"AsterMax-Audit-"+Guid.NewGuid().ToString("N"));
            try {
                AsterMaxCodeAsterNativeExporter.Export(CreateAsterMaxStatusFixture(),output,"audit");
                if(!System.IO.File.Exists(System.IO.Path.Combine(output,"audit.comm")))
                    throw new InvalidOperationException("Native assigned model did not export a solver definition.");
                var incomplete=CreateAsterMaxStatusFixture(); incomplete.Sections.Clear();
                bool rejected=false;
                try{AsterMaxCodeAsterNativeExporter.Export(incomplete,output,"must-not-export");}
                catch(InvalidOperationException ex){rejected=ex.Message.Contains("Material assignment incomplete");}
                if(!rejected) throw new InvalidOperationException("Native export accepted unassigned elements.");
                evidence.Add(new JObject{["case"]="native_export_accepts_assigned_rejects_unassigned",["pass"]=true,["solver_executed"]=false});
            }
            finally {if(System.IO.Directory.Exists(output)) System.IO.Directory.Delete(output,true);}
            return evidence;
        }

        private JObject AuditAsterMaxMaterialLibrary(string reportPath)
        {
            string path=System.IO.Path.Combine(Application.StartupPath,"AsterMaxReferenceMaterials.lib");
            var settings=new Newtonsoft.Json.JsonSerializerSettings {TypeNameHandling=Newtonsoft.Json.TypeNameHandling.Auto};
            var library=Newtonsoft.Json.JsonConvert.DeserializeObject<Forms.MaterialLibraryItem>(System.IO.File.ReadAllText(path),settings);
            var materials=library.Items.SelectMany(category=>category.Items).Select(item=>item.Tag).ToArray();
            if(materials.Length!=6||materials.Any(m=>m==null)) throw new InvalidOperationException("The six reference materials did not load.");
            var rows=new JArray();
            var units=new UnitSystem(UnitSystemType.MM_TON_S_C);
            var si=new UnitSystem(UnitSystemType.M_KG_S_C);
            foreach(Material original in materials) {
                var elastic=original.GetProperty<Elastic>() as Elastic;
                var density=original.GetProperty<Density>() as Density;
                if(elastic==null||density==null) throw new InvalidOperationException("Reference material is missing elastic properties or density: "+original.Name);
                double e=elastic.YoungsPoissonsTemp[0][0],nu=elastic.YoungsPoissonsTemp[0][1],rho=density.DensityTemp[0][0];
                if(!(e>0&&nu>-1&&nu<0.5&&rho>0)) throw new InvalidOperationException("Invalid reference properties: "+original.Name);
                var copy=original.DeepClone();
                copy.ConvertUnits(units,units,si);
                double siE=((Elastic)copy.GetProperty<Elastic>()).YoungsPoissonsTemp[0][0];
                double siRho=((Density)copy.GetProperty<Density>()).DensityTemp[0][0];
                if(Math.Abs(siE/e/1e6-1)>1e-9||Math.Abs(siRho/rho/1e12-1)>1e-9)
                    throw new InvalidOperationException("Reference material unit conversion failed: "+original.Name);
                copy.ConvertUnits(units,si,units);
                // Round-trip through the same serializer used for .lib persistence.
                copy=Newtonsoft.Json.JsonConvert.DeserializeObject<Material>(Newtonsoft.Json.JsonConvert.SerializeObject(copy,settings),settings);
                var model=CreateAsterMaxStatusFixture();model.Materials.Clear();model.Materials.Add(copy.Name,copy);
                model.Sections["Solid"].MaterialName=copy.Name;
                if(EvaluateAsterMaxSectionStates(model)["ax-model"].State!=2)
                    throw new InvalidOperationException("Reference material could not be assigned to a native body: "+copy.Name);
                if(Math.Abs(((Elastic)copy.GetProperty<Elastic>()).YoungsPoissonsTemp[0][0]/e-1)>1e-9 ||
                    Math.Abs(((Density)copy.GetProperty<Density>()).DensityTemp[0][0]/rho-1)>1e-9)
                    throw new InvalidOperationException("Reference material did not preserve properties: "+copy.Name);
                rows.Add(new JObject{["name"]=copy.Name,["e_mpa"]=e,["poisson"]=nu,["density_kg_m3"]=rho*1e12,
                    ["native_load_roundtrip_units_assignment_pass"]=true});
            }
            units.SetConverterUnits();
            int before=_controller.Model.Materials.Count;
            int copied=0;
            var copiedNames=new JArray();
            using(var dialog=new Forms.FrmMaterialLibrary(_controller)) {
                dialog.Show(this); Application.DoEvents();
                var tree=(CodersLabTreeView)dialog.Controls.Find("cltvLibrary",true)[0];
                var list=(ListView)dialog.Controls.Find("lvModelMaterials",true)[0];
                var method=typeof(Forms.FrmMaterialLibrary).GetMethod("btnCopyToModel_Click",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic);
                int initial=list.Items.Count;
                foreach(TreeNode node in AsterMaxLibraryNodes(tree.Nodes).ToArray()) {
                    if(node.Tag is Material && materials.Any(m=>m.Name==((Material)node.Tag).Name)) {
                        tree.SelectedNode=node;
                        method.Invoke(dialog,new object[]{null,EventArgs.Empty});
                        var expected=(Material)node.Tag;
                        var actual=list.Items[list.Items.Count-1].Tag as Material;
                        if(actual==null||actual.Name!=expected.Name)
                            throw new InvalidOperationException("Library copied a different material than the selected node: "+expected.Name);
                        var ee=((Elastic)expected.GetProperty<Elastic>()).YoungsPoissonsTemp[0];
                        var ae=((Elastic)actual.GetProperty<Elastic>()).YoungsPoissonsTemp[0];
                        double er=((Density)expected.GetProperty<Density>()).DensityTemp[0][0];
                        double ar=((Density)actual.GetProperty<Density>()).DensityTemp[0][0];
                        if(Math.Abs(ae[0]/ee[0]-1)>1e-9||Math.Abs(ae[1]-ee[1])>1e-12||Math.Abs(ar/er-1)>1e-9)
                            throw new InvalidOperationException("Library copy changed material properties: "+expected.Name);
                        copiedNames.Add(actual.Name);copied++;
                    }
                }
                if(copied!=6||list.Items.Count-initial!=6||copiedNames.Select(n=>(string)n).Distinct().Count()!=6)
                    throw new InvalidOperationException("Native library copy-to-model buttons did not copy six distinct materials.");
                tree.ExpandAll();
                using(var bitmap=new System.Drawing.Bitmap(dialog.Width,dialog.Height)) {
                    dialog.DrawToBitmap(bitmap,new System.Drawing.Rectangle(0,0,dialog.Width,dialog.Height));
                    bitmap.Save(reportPath+".buttons-MaterialLibrary.png");
                }
                dialog.DialogResult=DialogResult.Cancel; dialog.Close();
            }
            if(_controller.Model.Materials.Count!=before) throw new InvalidOperationException("Cancel must not commit test materials to the CAD smoke model.");
            return new JObject{["material_count"]=materials.Length,["native_dialog_copied"]=copied,["cancel_preserved_model"]=true,
                ["native_dialog_material_names"]=copiedNames,
                ["properties"]=rows,["scope"]="Native .lib loading, copy-to-model dialog, unit conversion, persistence and body assignment fixtures; no solver execution."};
        }

        private static IEnumerable<TreeNode> AsterMaxLibraryNodes(TreeNodeCollection nodes)
        {
            foreach(TreeNode node in nodes) {
                yield return node;
                foreach(TreeNode child in AsterMaxLibraryNodes(node.Nodes)) yield return child;
            }
        }
    }
}
