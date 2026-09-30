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
                            ["fx_per_node_n"]=cload.F1,["fy_per_node_n"]=cload.F2,["fz_per_node_n"]=cload.F3
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
                            ["pressure_mpa"]=pressure.Magnitude,["probe_group"]=surface.NodeSetName
                        });
                        if(probeGroup==null) probeGroup=surface.NodeSetName;
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
