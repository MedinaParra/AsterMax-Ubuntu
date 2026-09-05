using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using CaeGlobals;
using CaeMesh;
using CaeModel;

namespace PrePoMax.AsterMaxAI
{
    // CI-only structural setup qualification. It consumes the real STEP->NetGen mesh created by C8.60,
    // then uses the native Controller model APIs to add material/section/step/BC/load. It does not run a solver.
    internal sealed class AsterMaxStructuralSetupHarness
    {
        private readonly Controller _controller;
        public AsterMaxStructuralSetupHarness(Controller controller) { _controller = controller; }

        public void RunIfRequested()
        {
            if (!String.Equals(Environment.GetEnvironmentVariable("ASTERMAX_STRUCTURAL_SETUP_FIXTURE"), "1", StringComparison.Ordinal)) return;
            string evidencePath = Environment.GetEnvironmentVariable("ASTERMAX_STRUCTURAL_SETUP_EVIDENCE_PATH");
            bool meshPresent=false, materialAdded=false, sectionAdded=false, stepAdded=false, fixedAdded=false, loadAdded=false;
            bool regionsDistinct=false, fixedRegionNonEmpty=false, loadNodeExists=false, modelValidityPass=false, setupQualified=false;
            int fixedNodeCount=0, loadNodeId=-1, materialCount=0, sectionCount=0, stepCount=0, bcCount=0, loadCount=0;
            double minX=Double.NaN, maxX=Double.NaN, loadX=Double.NaN, loadY=Double.NaN, loadZ=Double.NaN;
            string meshPartName="", unitSystem="", error="";
            const string materialName="AsterMax Steel Demo";
            const string sectionName="AsterMax Solid Section";
            const string stepName="Static Structural";
            const string fixedSetName="FIXED_XMIN";
            const string fixedName="Fixed Support";
            const string loadName="Force XMAX";
            try
            {
                FeModel model=_controller.Model;
                FeMesh mesh=model==null?null:model.Mesh;
                meshPresent=mesh!=null && mesh.Parts!=null && mesh.Parts.Count>0 && mesh.Nodes!=null && mesh.Nodes.Count>0 && mesh.Elements!=null && mesh.Elements.Count>0;
                if(!meshPresent) throw new InvalidOperationException("C8.61 requires the qualified C8.60 FE mesh in the current model.");
                if(model.Materials.Count!=0 || model.Sections.Count!=0 || model.StepCollection.StepsList.Count!=0)
                    throw new InvalidOperationException("C8.61 requires an unconfigured FE model; refusing to mix qualification data with existing setup.");

                meshPartName=mesh.Parts.First().Key;
                unitSystem=model.UnitSystem==null?"null":model.UnitSystem.ToString();
                minX=mesh.Nodes.Values.Min(n=>n.X); maxX=mesh.Nodes.Values.Max(n=>n.X);
                double tol=Math.Max(1E-6,(maxX-minX)*1E-6);
                int[] fixedIds=mesh.Nodes.Values.Where(n=>Math.Abs(n.X-minX)<=tol).Select(n=>n.Id).OrderBy(id=>id).ToArray();
                if(fixedIds.Length==0) throw new InvalidOperationException("No nodes found on the minimum-X boundary.");
                FeNode loadNode=mesh.Nodes.Values.OrderByDescending(n=>n.X).ThenBy(n=>n.Id).First();
                loadNodeId=loadNode.Id; loadX=loadNode.X; loadY=loadNode.Y; loadZ=loadNode.Z;
                fixedNodeCount=fixedIds.Length;
                fixedRegionNonEmpty=fixedNodeCount>0;
                loadNodeExists=mesh.Nodes.ContainsKey(loadNodeId);
                regionsDistinct=!fixedIds.Contains(loadNodeId) && Math.Abs(loadX-minX)>tol;
                if(!regionsDistinct) throw new InvalidOperationException("Fixed and load regions are not spatially distinct.");

                _controller.AddNodeSet(new FeNodeSet(fixedSetName,fixedIds));

                Material material=new Material(materialName);
                // Values are intentionally recorded as model-system values; C8.61 does not claim a solver-unit interpretation.
                material.AddProperty(new Elastic(new double[][] { new double[] { 210000.0, 0.30, 293.15 } }));
                _controller.AddMaterial(material);
                materialAdded=model.Materials.ContainsKey(materialName);

                SolidSection section=new SolidSection(sectionName,materialName,meshPartName,RegionTypeEnum.PartName,1.0,false);
                _controller.AddSection(section);
                sectionAdded=model.Sections.ContainsKey(sectionName);

                StaticStep step=new StaticStep(stepName,true);
                _controller.AddStep(step,false);
                stepAdded=model.StepCollection.GetStep(stepName)!=null;

                FixedBC fixedBc=new FixedBC(fixedName,fixedSetName,RegionTypeEnum.NodeSetName,false);
                _controller.AddBoundaryCondition(stepName,fixedBc);
                fixedAdded=model.StepCollection.GetStep(stepName).BoundaryConditions.ContainsKey(fixedName);

                // Point load on the deterministic maximum-X mesh node. Numeric component is setup evidence only; no solver claim.
                CLoad force=new CLoad(loadName,loadNodeId,1000.0,0.0,0.0,false,false,0.0);
                _controller.AddLoad(stepName,force);
                loadAdded=model.StepCollection.GetStep(stepName).Loads.ContainsKey(loadName);

                materialCount=model.Materials.Count; sectionCount=model.Sections.Count; stepCount=model.StepCollection.StepsList.Count;
                bcCount=model.StepCollection.GetStep(stepName).BoundaryConditions.Count;
                loadCount=model.StepCollection.GetStep(stepName).Loads.Count;

                var invalid=model.CheckValidity(new System.Collections.Generic.List<Tuple<NamedClass,string>>());
                modelValidityPass=invalid!=null && invalid.Length==0;
                setupQualified=meshPresent && materialAdded && sectionAdded && stepAdded && fixedAdded && loadAdded && fixedRegionNonEmpty && loadNodeExists && regionsDistinct && modelValidityPass;
                if(!setupQualified) throw new InvalidOperationException("Structural setup qualification gate did not pass.");

                _controller.CurrentView=ViewGeometryModelResults.Model;
                _controller.DrawSymbolsForStep(stepName,true);
            }
            catch(Exception ex) { error=ex.GetType().Name+": "+ex.Message; }
            WriteEvidence(evidencePath,meshPresent,materialAdded,sectionAdded,stepAdded,fixedAdded,loadAdded,regionsDistinct,
                          fixedRegionNonEmpty,loadNodeExists,modelValidityPass,setupQualified,fixedNodeCount,loadNodeId,
                          materialCount,sectionCount,stepCount,bcCount,loadCount,minX,maxX,loadX,loadY,loadZ,meshPartName,unitSystem,error);
        }

        private static bool Finite(double v){return !Double.IsNaN(v)&&!Double.IsInfinity(v);}
        private static string Num(double v){return Finite(v)?v.ToString("R",CultureInfo.InvariantCulture):"null";}
        private static string Json(string s){return "\""+(s??"").Replace("\\","\\\\").Replace("\"","\\\"").Replace("\r"," ").Replace("\n"," ")+"\"";}
        private static void WriteEvidence(string path,bool mesh,bool mat,bool sec,bool step,bool fixedBc,bool load,bool distinct,bool fixedNonEmpty,bool loadExists,bool valid,bool qualified,
            int fixedNodes,int loadNode,int mats,int secs,int steps,int bcs,int loads,double minX,double maxX,double lx,double ly,double lz,string part,string units,string error)
        {
            if(String.IsNullOrWhiteSpace(path)) return; string dir=Path.GetDirectoryName(path); if(!String.IsNullOrWhiteSpace(dir))Directory.CreateDirectory(dir);
            string j="{\n"+
                "  \"schema\": \"astermax.structural-model-setup-qualification.v1\",\n"+
                "  \"native_fe_mesh_present\": "+(mesh?"true":"false")+",\n"+
                "  \"mesh_part_name\": "+Json(part)+",\n"+
                "  \"model_unit_system_observed\": "+Json(units)+",\n"+
                "  \"material_added\": "+(mat?"true":"false")+",\n"+
                "  \"material_name\": \"AsterMax Steel Demo\",\n  \"elastic_E_model_value\": 210000.0,\n  \"poisson_ratio\": 0.30,\n"+
                "  \"material_solver_unit_interpretation_qualified\": false,\n"+
                "  \"solid_section_added\": "+(sec?"true":"false")+",\n"+
                "  \"static_step_added\": "+(step?"true":"false")+",\n"+
                "  \"fixed_support_added\": "+(fixedBc?"true":"false")+",\n"+
                "  \"fixed_node_count\": "+fixedNodes.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"fixed_region_nonempty\": "+(fixedNonEmpty?"true":"false")+",\n"+
                "  \"load_added\": "+(load?"true":"false")+",\n"+
                "  \"load_node_id\": "+loadNode.ToString(CultureInfo.InvariantCulture)+",\n"+
                "  \"load_node_exists\": "+(loadExists?"true":"false")+",\n"+
                "  \"load_vector_model_values\": [1000.0,0.0,0.0],\n"+
                "  \"xmin_xmax_mm\": ["+Num(minX)+","+Num(maxX)+"],\n"+
                "  \"load_node_xyz_mm\": ["+Num(lx)+","+Num(ly)+","+Num(lz)+"],\n"+
                "  \"fixed_and_load_regions_distinct\": "+(distinct?"true":"false")+",\n"+
                "  \"material_count\": "+mats+",\n  \"section_count\": "+secs+",\n  \"step_count\": "+steps+",\n  \"bc_count\": "+bcs+",\n  \"load_count\": "+loads+",\n"+
                "  \"model_check_validity_pass\": "+(valid?"true":"false")+",\n"+
                "  \"structural_setup_qualified\": "+(qualified?"true":"false")+",\n"+
                "  \"solver_executed\": false,\n  \"solver_verified\": false,\n  \"industrial_validation\": false,\n  \"ansys_equivalence\": false,\n"+
                "  \"error\": "+Json(error)+"\n}";
            File.WriteAllText(path,j,Encoding.UTF8);
        }
    }
}
