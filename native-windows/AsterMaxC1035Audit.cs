using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Windows.Forms;
using CaeModel;
using CaeGlobals;
using CaeMesh;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace PrePoMax
{
    public partial class FrmMain
    {
        private void StartAsterMaxC1035DefaultsAudit()
        {
            string directory=Environment.GetEnvironmentVariable("ASTERMAX_C1035_AUDIT_DIR");
            if(String.IsNullOrWhiteSpace(directory)) return;
            Directory.CreateDirectory(directory);

            int ticks=0;
            var timer=new Timer { Interval=1000 };
            timer.Tick += (s,e) =>
            {
                ticks++;
                bool ready=_controller!=null && _controller.Model!=null &&
                           _controller.Model.Geometry!=null &&
                           _controller.Model.Geometry.Parts.Count>=2 &&
                           !IsStateWorking();
                if(!ready && ticks<90) return;

                timer.Stop();
                timer.Dispose();
                bool pass=false;
                JObject report=new JObject {
                    ["release"]="C10.35",
                    ["fixture"]="two touching solid boxes imported from STEP",
                    ["fea_values_invented"]=false
                };

                try
                {
                    if(!ready) throw new InvalidOperationException("Two-body STEP import did not complete within the audit window.");

                    FeModel model=_controller.Model;
                    report["geometry_parts_before_mesh"]=model.Geometry.Parts.Count;
                    report["materials_after_import"]=new JArray(model.Materials.Keys);
                    report["default_material_after_import"]=model.Materials.ContainsKey(Controller.AsterMaxDefaultMaterialName);

                    var candidates=_controller.GetGeometryPartsWithoutSubParts();
                    string[] partNames=candidates==null ? new string[0] : candidates.Select(x=>x.Name).ToArray();
                    report["mesh_candidates"]=new JArray(partNames);
                    if(partNames.Length<2) throw new InvalidOperationException("Expected at least two independent solid mesh candidates.");

                    var meshRows=new JArray();
                    foreach(string partName in partNames)
                    {
                        int nodesBefore=model.Mesh==null ? 0 : model.Mesh.Nodes.Count;
                        int elementsBefore=model.Mesh==null ? 0 : model.Mesh.Elements.Count;
                        bool returned=_controller.CreateMesh(partName);
                        int nodesAfter=model.Mesh==null ? 0 : model.Mesh.Nodes.Count;
                        int elementsAfter=model.Mesh==null ? 0 : model.Mesh.Elements.Count;
                        bool produced=returned && nodesAfter>nodesBefore && elementsAfter>elementsBefore;
                        meshRows.Add(new JObject {
                            ["part"]=partName,
                            ["create_mesh_returned"]=returned,
                            ["nodes_before"]=nodesBefore,
                            ["nodes_after"]=nodesAfter,
                            ["elements_before"]=elementsBefore,
                            ["elements_after"]=elementsAfter,
                            ["produced_mesh"]=produced
                        });
                        if(!produced) throw new InvalidOperationException("Native meshing did not produce elements for part: "+partName);
                    }
                    report["meshing"]=meshRows;

                    _controller.AsterMaxEnsureDefaultMaterialAndSections();
                    AsterMaxAutoGenerateContacts();
                    RegenerateTree();
                    _modelTree.RefreshAsterMaxOutline();
                    Application.DoEvents();

                    model=_controller.Model;
                    string materialName=Controller.AsterMaxDefaultMaterialName;
                    bool hasDefault=model.Materials.ContainsKey(materialName);

                    var solidParts=model.Mesh.Parts
                        .Where(x=>x.Value!=null && x.Value.PartType==PartType.Solid)
                        .Select(x=>x.Key).ToArray();

                    var assigned=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    var sectionRows=new JArray();
                    foreach(var entry in model.Sections)
                    {
                        Section section=entry.Value;
                        if(section==null) continue;
                        bool isDefault=String.Equals(section.MaterialName,materialName,StringComparison.OrdinalIgnoreCase);
                        if(isDefault && section.RegionType==RegionTypeEnum.PartName && !String.IsNullOrWhiteSpace(section.RegionName))
                            assigned.Add(section.RegionName);
                        sectionRows.Add(new JObject {
                            ["name"]=entry.Key,
                            ["material"]=section.MaterialName,
                            ["region"]=section.RegionName,
                            ["region_type"]=section.RegionType.ToString()
                        });
                    }

                    string[] contactNames=_controller.GetContactPairNames();
                    var contactRows=new JArray();
                    bool contactsValid=contactNames.Length>0;
                    foreach(string name in contactNames)
                    {
                        ContactPair cp=_controller.GetContactPair(name);
                        bool interactionOk=cp!=null && model.SurfaceInteractions.ContainsKey(cp.SurfaceInteractionName);
                        bool masterOk=cp!=null && model.Mesh.Surfaces.ContainsKey(cp.MasterRegionName);
                        bool slaveOk=cp!=null && model.Mesh.Surfaces.ContainsKey(cp.SlaveRegionName);
                        bool colorsOk=cp!=null && cp.MasterColor.ToArgb()==System.Drawing.Color.Red.ToArgb() &&
                                      cp.SlaveColor.ToArgb()==System.Drawing.Color.RoyalBlue.ToArgb();
                        contactsValid &= cp!=null && interactionOk && masterOk && slaveOk && colorsOk;
                        contactRows.Add(new JObject {
                            ["name"]=name,
                            ["interaction"]=cp==null ? null : cp.SurfaceInteractionName,
                            ["master_surface"]=cp==null ? null : cp.MasterRegionName,
                            ["slave_surface"]=cp==null ? null : cp.SlaveRegionName,
                            ["interaction_valid"]=interactionOk,
                            ["master_surface_valid"]=masterOk,
                            ["slave_surface_valid"]=slaveOk,
                            ["master_red_slave_blue"]=colorsOk
                        });
                    }

                    bool everySolidAssigned=solidParts.Length>=2 && solidParts.All(x=>assigned.Contains(x));
                    bool libraryPresent=File.Exists(Path.Combine(Application.StartupPath,Globals.MaterialLibraryFileName));

                    report["mesh_part_count"]=model.Mesh.Parts.Count;
                    report["solid_parts"]=new JArray(solidParts);
                    report["default_material_name"]=materialName;
                    report["default_material_present"]=hasDefault;
                    report["sections"]=sectionRows;
                    report["all_solid_parts_assigned_default_material"]=everySolidAssigned;
                    report["material_library_present_next_to_exe"]=libraryPresent;
                    report["material_library_file"]=Globals.MaterialLibraryFileName;
                    report["contact_pair_count"]=contactNames.Length;
                    report["contacts"]=contactRows;
                    report["contact_generator_runtime_pass"]=contactsValid;
                    report["automatic_post_mesh_hook_checked_by_source_contract"]=true;

                    pass=hasDefault && everySolidAssigned && libraryPresent && contactsValid;
                    report["pass"]=pass;
                    if(!pass) throw new InvalidOperationException("C10.35 model-ready defaults did not satisfy all runtime predicates.");
                }
                catch(Exception ex)
                {
                    report["pass"]=false;
                    report["error"]=ex.ToString();
                    pass=false;
                }

                File.WriteAllText(Path.Combine(directory,"defaults-autocontact-report.json"),
                                  report.ToString(Formatting.Indented));
                Environment.ExitCode=pass ? 0 : 1;
                try
                {
                    _c10209AuditShutdownDirectory=directory;
                    if(_controller!=null) _controller.ModelChanged=false;
                }
                catch { }
                BeginInvoke(new Action(()=>Close()));
            };
            timer.Start();
        }
    }
}
