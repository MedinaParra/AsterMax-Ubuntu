using System;
using System.Collections.Generic;
using System.Linq;
using CaeGlobals;
using CaeMesh;
using CaeModel;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    internal static class AsterMaxSurfaceMechanicsContract
    {
        public static JObject Build(FeModel model)
        {
            JObject root=AsterMaxModelContractBridge.Build(model);
            JObject mesh=(JObject)root["mesh"];
            JObject nodeGroups=(JObject)mesh["node_groups"] ?? new JObject();
            JObject surfaceGroups=BuildSurfaceGroups(model);
            mesh["surface_groups"]=surfaceGroups;
            JObject volumeGroups=BuildVolumeGroups(model);
            mesh["volume_groups"]=volumeGroups;
            EnrichMaterialDensities(model,(JArray)root["materials"]);
            root["material_assignments"]=BuildMaterialAssignments(model,volumeGroups);
            root["amplitudes"]=BuildAmplitudes(model);

            JArray supports=new JArray();
            JArray loads=new JArray();
            string probeGroup=null;
            int stepCount=0;
            foreach(Step step in model.StepCollection.StepsList)
            {
                if(step is InitialStep) continue;
                stepCount++;
                foreach(var entry in step.BoundaryConditions)
                {
                    BoundaryCondition bc=entry.Value;
                    if(bc is FixedBC fixedBc)
                    {
                        string group=RegionToNodeGroup(model,fixedBc.RegionName,fixedBc.RegionType,nodeGroups);
                        supports.Add(new JObject {
                            ["name"]=fixedBc.Name,["type"]="fixed",["group"]=group,
                            ["dx"]=0.0,["dy"]=0.0,["dz"]=0.0
                        });
                    }
                    else if(bc is DisplacementRotation disp)
                    {
                        if(!double.IsNaN(disp.UR1) || !double.IsNaN(disp.UR2) || !double.IsNaN(disp.UR3))
                            throw new NotSupportedException("Rotational displacement is not supported for the current 3D solid backend.");
                        string group=RegionToNodeGroup(model,disp.RegionName,disp.RegionType,nodeGroups);
                        JObject item=new JObject { ["name"]=disp.Name,["type"]="displacement",["group"]=group };
                        AddDof(item,"dx",disp.U1); AddDof(item,"dy",disp.U2); AddDof(item,"dz",disp.U3);
                        if(item.Count<=3) throw new InvalidOperationException("Displacement support has no constrained translational DOF: "+disp.Name);
                        supports.Add(item);
                    }
                    else if(bc is AsterMaxFrictionlessBC frictionless)
                    {
                        RequireSurface(model,frictionless.RegionName);
                        supports.Add(new JObject {
                            ["name"]=frictionless.Name,["type"]="frictionless_normal",
                            ["surface"]=frictionless.RegionName,["dnor"]=0.0
                        });
                    }
                    else
                        throw new NotSupportedException("Unsupported Code_Aster boundary condition: "+bc.GetType().Name);
                }

                foreach(var entry in step.Loads)
                {
                    Load load=entry.Value;
                    if(load is CLoad cload)
                    {
                        string group=RegionToNodeGroup(model,cload.RegionName,cload.RegionType,nodeGroups);
                        loads.Add(new JObject {
                            ["name"]=cload.Name,["type"]="nodal_force_per_node",["group"]=group,
                            ["fx_per_node_n"]=cload.F1,["fy_per_node_n"]=cload.F2,["fz_per_node_n"]=cload.F3,
                            ["amplitude"]=ResolveAmplitude(model,cload.AmplitudeName)
                        });
                        if(probeGroup==null) probeGroup=group;
                    }
                    else if(load is DLoad pressure)
                    {
                        if(pressure.RegionType!=RegionTypeEnum.SurfaceName)
                            throw new NotSupportedException("Pressure requires a named surface for the native Code_Aster backend.");
                        FeSurface surface=RequireSurface(model,pressure.RegionName);
                        loads.Add(new JObject {
                            ["name"]=pressure.Name,["type"]="pressure",["surface"]=pressure.RegionName,
                            ["pressure_mpa"]=pressure.Magnitude,["probe_group"]=surface.NodeSetName,
                            ["amplitude"]=ResolveAmplitude(model,pressure.AmplitudeName)
                        });
                        if(probeGroup==null) probeGroup=surface.NodeSetName;
                    }
                    else if(load is STLoad traction)
                    {
                        if(traction.RegionType!=RegionTypeEnum.SurfaceName)
                            throw new NotSupportedException("Surface traction requires a named surface for the native Code_Aster backend.");
                        FeSurface surface=RequireSurface(model,traction.RegionName);
                        loads.Add(new JObject {
                            ["name"]=traction.Name,["type"]="surface_traction",["surface"]=traction.RegionName,
                            ["fx_n_per_mm2"]=traction.F1,["fy_n_per_mm2"]=traction.F2,["fz_n_per_mm2"]=traction.F3,
                            ["probe_group"]=surface.NodeSetName,["amplitude"]=ResolveAmplitude(model,traction.AmplitudeName)
                        });
                        if(probeGroup==null) probeGroup=surface.NodeSetName;
                    }
                    else if(load is GravityLoad gravity)
                    {
                        double magnitude=Math.Sqrt(gravity.F1*gravity.F1+gravity.F2*gravity.F2+gravity.F3*gravity.F3);
                        if(!(magnitude>0) || double.IsNaN(magnitude) || double.IsInfinity(magnitude))
                            throw new InvalidOperationException("Gravity magnitude must be finite and greater than zero: "+gravity.Name);
                        string group=RegionToVolumeGroup(gravity.RegionName,gravity.RegionType,volumeGroups);
                        loads.Add(new JObject {
                            ["name"]=gravity.Name,["type"]="gravity",["volume_group"]=group,
                            ["gravity_mm_s2"]=magnitude,
                            ["direction"]=new JArray(gravity.F1/magnitude,gravity.F2/magnitude,gravity.F3/magnitude),
                            ["amplitude"]=ResolveAmplitude(model,gravity.AmplitudeName)
                        });
                    }
                    else if(load is CentrifLoad rotation)
                    {
                        double axisNorm=Math.Sqrt(rotation.N1*rotation.N1+rotation.N2*rotation.N2+rotation.N3*rotation.N3);
                        if(!(axisNorm>0) || double.IsNaN(axisNorm) || double.IsInfinity(axisNorm))
                            throw new InvalidOperationException("Centrifugal rotation axis must be finite and non-zero: "+rotation.Name);
                        double omega=rotation.RotationalSpeed;
                        if(double.IsNaN(omega) || double.IsInfinity(omega) || omega<0)
                            throw new InvalidOperationException("Rotational speed must be finite and non-negative: "+rotation.Name);
                        string group=RegionToVolumeGroup(rotation.RegionName,rotation.RegionType,volumeGroups);
                        loads.Add(new JObject {
                            ["name"]=rotation.Name,["type"]="rotation",["volume_group"]=group,
                            ["omega_rad_s"]=omega,
                            ["axis"]=new JArray(rotation.N1/axisNorm,rotation.N2/axisNorm,rotation.N3/axisNorm),
                            ["center_mm"]=new JArray(rotation.X,rotation.Y,rotation.Z),
                            ["amplitude"]=ResolveAmplitude(model,rotation.AmplitudeName)
                        });
                    }
                    else
                        throw new NotSupportedException("Unsupported Code_Aster load: "+load.GetType().Name);
                }
            }
            if(stepCount!=1) throw new NotSupportedException("Native static structural backend currently requires exactly one non-initial step.");
            if(supports.Count==0) throw new InvalidOperationException("At least one support is required.");
            if(loads.Count==0) throw new InvalidOperationException("At least one load is required.");
            root["supports"]=supports;
            root["loads"]=loads;
            root["postprocess"]=new JObject { ["displacement_probe_group"]=probeGroup };
            return root;
        }

        private static string ResolveAmplitude(FeModel model,string name)
        {
            if(String.IsNullOrWhiteSpace(name) || name==Load.DefaultAmplitudeName) return null;
            if(model.Amplitudes==null || !model.Amplitudes.ContainsKey(name))
                throw new InvalidOperationException("Load references missing amplitude: "+name);
            AmplitudeTabular tab=model.Amplitudes[name] as AmplitudeTabular;
            if(tab==null)
                throw new NotSupportedException("Native Code_Aster backend currently supports tabular amplitudes only: "+name);
            if(tab.TimeAmplitude==null || tab.TimeAmplitude.Length<2)
                throw new InvalidOperationException("Amplitude requires at least two time/value points: "+name);
            return name;
        }

        private static JObject BuildAmplitudes(FeModel model)
        {
            JObject result=new JObject();
            if(model.Amplitudes==null) return result;
            foreach(var pair in model.Amplitudes.OrderBy(x=>x.Key,StringComparer.Ordinal))
            {
                AmplitudeTabular tab=pair.Value as AmplitudeTabular;
                if(tab==null) continue;
                if(tab.TimeAmplitude==null || tab.TimeAmplitude.Length<2)
                    throw new InvalidOperationException("Amplitude requires at least two points: "+pair.Key);
                JArray points=new JArray();
                double previous=Double.NegativeInfinity;
                foreach(double[] raw in tab.TimeAmplitude)
                {
                    if(raw==null || raw.Length<2) throw new InvalidOperationException("Invalid amplitude point: "+pair.Key);
                    double time=raw[0]+tab.ShiftX;
                    double value=raw[1]+tab.ShiftY;
                    if(Double.IsNaN(time)||Double.IsInfinity(time)||Double.IsNaN(value)||Double.IsInfinity(value))
                        throw new InvalidOperationException("Amplitude contains non-finite values: "+pair.Key);
                    if(time<=previous) throw new InvalidOperationException("Amplitude time values must be strictly increasing: "+pair.Key);
                    previous=time;
                    points.Add(new JArray(time,value));
                }
                result[pair.Key]=new JObject {
                    ["time_span"]=tab.TimeSpan.ToString(),
                    ["points"]=points,
                    ["interpolation"]="LINEAR",
                    ["extrapolation_left"]="CONSTANT",
                    ["extrapolation_right"]="CONSTANT"
                };
            }
            return result;
        }

        private static void AddDof(JObject item,string name,double value)
        {
            if(double.IsNaN(value)) return;
            item[name]=double.IsPositiveInfinity(value)?0.0:value;
        }

        private static string RegionToNodeGroup(FeModel model,string regionName,RegionTypeEnum regionType,JObject groups)
        {
            if(regionType==RegionTypeEnum.NodeSetName)
            {
                if(groups[regionName]==null) throw new InvalidOperationException("Node group not found: "+regionName);
                return regionName;
            }
            if(regionType==RegionTypeEnum.SurfaceName)
            {
                FeSurface surface=RequireSurface(model,regionName);
                if(String.IsNullOrWhiteSpace(surface.NodeSetName) || groups[surface.NodeSetName]==null)
                    throw new InvalidOperationException("Surface node group not found: "+regionName);
                return surface.NodeSetName;
            }
            throw new NotSupportedException("Native Code_Aster backend requires named node-set or surface scoping: "+regionType);
        }

        private static string RegionToVolumeGroup(string regionName,RegionTypeEnum regionType,JObject groups)
        {
            string key;
            if(regionType==RegionTypeEnum.PartName) key="PART::"+regionName;
            else if(regionType==RegionTypeEnum.ElementSetName) key="ESET::"+regionName;
            else throw new NotSupportedException("Body loads require a named part or element set. Region: "+regionType);
            if(groups[key]==null) throw new InvalidOperationException("Volume group not found: "+key);
            return key;
        }

        private static JObject BuildVolumeGroups(FeModel model)
        {
            JObject result=new JObject();
            if(model.Mesh.Parts!=null)
            {
                foreach(var pair in model.Mesh.Parts.OrderBy(x=>x.Key,StringComparer.Ordinal))
                {
                    if(pair.Value==null || pair.Value.Labels==null || pair.Value.Labels.Length==0) continue;
                    JArray ids=new JArray();
                    foreach(int id in pair.Value.Labels.OrderBy(x=>x))
                        if(model.Mesh.Elements.ContainsKey(id)) ids.Add("E"+id);
                    if(ids.Count>0) result["PART::"+pair.Key]=ids;
                }
            }
            if(model.Mesh.ElementSets!=null)
            {
                foreach(var pair in model.Mesh.ElementSets.OrderBy(x=>x.Key,StringComparer.Ordinal))
                {
                    if(pair.Value==null || pair.Value.Labels==null || pair.Value.Labels.Length==0) continue;
                    JArray ids=new JArray();
                    foreach(int id in pair.Value.Labels.OrderBy(x=>x))
                        if(model.Mesh.Elements.ContainsKey(id)) ids.Add("E"+id);
                    if(ids.Count>0) result["ESET::"+pair.Key]=ids;
                }
            }
            return result;
        }

        private static JArray BuildMaterialAssignments(FeModel model,JObject volumeGroups)
        {
            JArray result=new JArray();
            if(model.Sections==null) return result;
            foreach(var pair in model.Sections.OrderBy(x=>x.Key,StringComparer.Ordinal))
            {
                Section section=pair.Value;
                if(section==null) continue;
                SolidSection solid=section as SolidSection;
                if(solid==null || solid.TwoD)
                    throw new NotSupportedException("C10.27 native backend currently supports 3D SolidSection material assignments only: "+pair.Key);
                if(String.IsNullOrWhiteSpace(solid.MaterialName) || model.Materials==null || !model.Materials.ContainsKey(solid.MaterialName))
                    throw new InvalidOperationException("Section material is missing: "+pair.Key);
                string group=RegionToVolumeGroup(solid.RegionName,solid.RegionType,volumeGroups);
                result.Add(new JObject {
                    ["section"]=solid.Name,
                    ["material"]=solid.MaterialName,
                    ["volume_group"]=group
                });
            }
            return result;
        }

        private static void EnrichMaterialDensities(FeModel model,JArray materials)
        {
            if(materials==null) return;
            foreach(Material material in model.Materials.Values)
            {
                double? rho=null;
                ElasticWithDensity ewd=material.GetProperty<ElasticWithDensity>() as ElasticWithDensity;
                if(ewd!=null && ewd.Density>0) rho=ewd.Density;
                if(rho==null)
                {
                    Density density=material.GetProperty<Density>() as Density;
                    if(density!=null && density.DensityTemp!=null && density.DensityTemp.Length>0 &&
                       density.DensityTemp[0]!=null && density.DensityTemp[0].Length>0 && density.DensityTemp[0][0]>0)
                        rho=density.DensityTemp[0][0];
                }
                if(rho==null) continue;
                JObject target=materials.Cast<JObject>().FirstOrDefault(x=>
                    String.Equals((string)x["name"],material.Name,StringComparison.Ordinal));
                if(target!=null)
                {
                    target["density_tonne_per_mm3"]=rho.Value;
                    target["density_source"]="AsterMax material library";
                }
            }
        }

        private static FeSurface RequireSurface(FeModel model,string name)
        {
            if(String.IsNullOrWhiteSpace(name) || model.Mesh.Surfaces==null || !model.Mesh.Surfaces.ContainsKey(name))
                throw new InvalidOperationException("Surface not found: "+(name??"<null>"));
            FeSurface surface=model.Mesh.Surfaces[name];
            if(surface==null || surface.ElementFaces==null || surface.ElementFaces.Count==0)
                throw new InvalidOperationException("Surface has no element-face definition: "+name);
            return surface;
        }

        private static JObject BuildSurfaceGroups(FeModel model)
        {
            JObject result=new JObject();
            if(model.Mesh.Surfaces==null) return result;
            int skinId=1;
            foreach(var pair in model.Mesh.Surfaces.OrderBy(x=>x.Key,StringComparer.Ordinal))
            {
                FeSurface surface=pair.Value;
                if(surface==null || surface.ElementFaces==null || surface.ElementFaces.Count==0) continue;
                JArray skin=new JArray();
                foreach(var facePair in surface.ElementFaces.OrderBy(x=>x.Key.ToString(),StringComparer.Ordinal))
                {
                    string setName=facePair.Value;
                    if(String.IsNullOrWhiteSpace(setName) || model.Mesh.ElementSets==null || !model.Mesh.ElementSets.ContainsKey(setName))
                        throw new InvalidOperationException("Surface "+pair.Key+" refers to missing element set: "+setName);
                    FeElementSet set=model.Mesh.ElementSets[setName];
                    if(set==null || set.Labels==null) continue;
                    foreach(int elementId in set.Labels.OrderBy(x=>x))
                    {
                        if(!model.Mesh.Elements.ContainsKey(elementId))
                            throw new InvalidOperationException("Surface refers to missing element: "+elementId);
                        FeElement3D volume=model.Mesh.Elements[elementId] as FeElement3D;
                        if(volume==null) throw new NotSupportedException("Surface mechanics currently requires 3D volume elements.");
                        int[] faceNodes=volume.GetVtkCellFromFaceName(facePair.Key);
                        string type=faceNodes.Length==3?"TRIA3":faceNodes.Length==6?"TRIA6":faceNodes.Length==4?"QUAD4":null;
                        if(type==null) throw new NotSupportedException("Unsupported surface face node count: "+faceNodes.Length);
                        JArray ids=new JArray();
                        foreach(int nodeId in faceNodes) ids.Add("N"+nodeId);
                        skin.Add(new JObject {
                            ["id"]="SF"+(skinId++),["type"]=type,["nodes"]=ids,
                            ["parent_element"]="E"+elementId,["face"]=facePair.Key.ToString()
                        });
                    }
                }
                if(skin.Count>0)
                    result[pair.Key]=new JObject {
                        ["area_mm2"]=surface.Area,["node_group"]=surface.NodeSetName,["elements"]=skin
                    };
            }
            return result;
        }
    }
}
