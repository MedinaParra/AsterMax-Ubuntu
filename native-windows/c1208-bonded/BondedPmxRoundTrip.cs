using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Serialization.Formatters;
using System.Runtime.Serialization.Formatters.Binary;
using System.Text;
using CaeGlobals;
using CaeMesh;
using CaeModel;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

// The only BinaryFormatter input admitted by this test is generated immediately
// below from trusted packaged classes. No user project or external stream is
// read by this native deserialization compatibility gate.
[Serializable]
public sealed class AsterMaxC1208SyntheticModelHolder
{
    public FeModel _model;
}

public static class AsterMaxC1208PmxRoundTrip
{
    private static FeModel seed;
    private static readonly JArray checks = new JArray();
    private static readonly UTF8Encoding utf8 = new UTF8Encoding(false);

    private static void Check(string name, bool pass)
    {
        var item = new JObject(); item.Add("name", name); item.Add("status", pass ? "PASS" : "FAIL"); checks.Add(item);
        if (!pass) throw new InvalidOperationException("Synthetic C12.08 PMX check failed: " + name);
    }
    private static void WriteJson(string path, JToken value) { File.WriteAllText(path, value.ToString(Formatting.Indented), utf8); }
    private static FeSurface Surface(FeModel model, string name, string nodeSet, string elementSet, int elementId)
    {
        var surface = new FeSurface(name, new[] { 10 * elementId }, null);
        surface.NodeSetName = nodeSet;
        surface.Area = 50.0;
        surface.SurfaceFaceTypes = FeSurfaceFaceTypes.SolidFaces;
        surface.AddElementFace(FeFaceName.S1, elementSet);
        model.Mesh.Surfaces.Add(name, surface);
        return surface;
    }
    private static JObject SelectionSurface(FeModel model, int elementId)
    {
        int[] ids = model.Mesh.Elements[elementId].GetVtkCellFromFaceName(FeFaceName.S1);
        var facet = new JObject();
        facet.Add("source_element_id", elementId); facet.Add("source_face", 1);
        facet.Add("nodes", new JArray(ids)); facet.Add("vtk_face_id", 10 * elementId);
        var surface = new JObject(); surface.Add("area_mm2", 50.0);
        surface.Add("node_ids", new JArray(ids.OrderBy(n => n))); surface.Add("facets", new JArray(facet));
        return surface;
    }
    public static void Create(string directory)
    {
        seed = new FeModel("C1208SyntheticBondedPmx");
        seed.UnitSystem = new UnitSystem(UnitSystemType.MM_TON_S_C);
        double[,] xyz = { { 0,0,0 }, { 0,10,0 }, { 0,0,10 }, { -10,0,0 },
            { 2.5,0,0 }, { 2.5,10,0 }, { 2.5,0,10 }, { 12.5,0,0 } };
        var coordinates = new JObject();
        for (int i=0; i<8; i++)
        {
            seed.Mesh.Nodes.Add(i+1,new FeNode(i+1,xyz[i,0],xyz[i,1],xyz[i,2]));
            coordinates.Add((i+1).ToString(System.Globalization.CultureInfo.InvariantCulture),new JArray(xyz[i,0],xyz[i,1],xyz[i,2]));
        }
        seed.Mesh.Elements.Add(1,new LinearTetraElement(1,new[] { 1,3,2,4 }));
        seed.Mesh.Elements.Add(2,new LinearTetraElement(2,new[] { 5,6,7,8 }));
        seed.Mesh.NodeSets.Add("FixedNodes",new FeNodeSet("FixedNodes",new[] { 4 }));
        seed.Mesh.NodeSets.Add("LoadNodes",new FeNodeSet("LoadNodes",new[] { 6,8 }));
        seed.Mesh.NodeSets.Add("MasterNodes",new FeNodeSet("MasterNodes",new[] { 1,2,3 }));
        seed.Mesh.NodeSets.Add("SlaveNodes",new FeNodeSet("SlaveNodes",new[] { 5,6,7 }));
        seed.Mesh.ElementSets.Add("AllElements",new FeElementSet("AllElements",new[] { 1,2 }));
        seed.Mesh.ElementSets.Add("MasterElements",new FeElementSet("MasterElements",new[] { 1 }));
        seed.Mesh.ElementSets.Add("SlaveElements",new FeElementSet("SlaveElements",new[] { 2 }));
        Surface(seed,"MasterSurface","MasterNodes","MasterElements",1);
        Surface(seed,"SlaveSurface","SlaveNodes","SlaveElements",2);
        var interaction = new SurfaceInteraction("SyntheticInteraction");
        interaction.AddProperty(new SurfaceBehavior());
        seed.SurfaceInteractions.Add(interaction.Name,interaction);
        var contact = new ContactPair("SyntheticContact",interaction.Name,"MasterSurface",RegionTypeEnum.SurfaceName,"SlaveSurface",RegionTypeEnum.SurfaceName);
        seed.ContactPairs.Add(contact.Name,contact);
        var material = new Material("SyntheticSteel");
        material.AddProperty(new ElasticWithDensity(210000.0,0.3,7.85e-9)); seed.Materials.Add(material.Name,material);
        var section = new SolidSection("SyntheticSection",material.Name,"AllElements",RegionTypeEnum.ElementSetName,1.0,false);
        seed.Sections.Add(section.Name,section);
        var step = new StaticStep("SyntheticStatic");
        if (!step.AddBoundaryCondition(new FixedBC("SyntheticFixed","FixedNodes",RegionTypeEnum.NodeSetName,false))) throw new InvalidOperationException("FixedBC fixture rejected.");
        if (!step.AddLoad(new CLoad("SyntheticLoad","LoadNodes",RegionTypeEnum.NodeSetName,0.0,-26000.0,0.0,false,false,0.0))) throw new InvalidOperationException("CLoad fixture rejected.");
        seed.StepCollection.AddStep(step,false);
        using (var file = File.Create(Path.Combine(directory,"seed.nrbf")))
        {
            var formatter = new BinaryFormatter(); formatter.AssemblyFormat = FormatterAssemblyStyle.Simple;
            formatter.Serialize(file,new object[] { new AsterMaxC1208SyntheticModelHolder { _model=seed } });
        }
        // PMX stores mesh arrays separately from the NRBF metadata. Exercise
        // those exact native mesh methods instead of inventing a second layout.
        using (var writer = new BinaryWriter(File.Create(Path.Combine(directory,"mesh.bin")))) FeMesh.WriteToBinaryFile(seed.Mesh,writer);
        var tie = new JObject(); tie.Add("name","Synthetic_Bonded"); tie.Add("position_tolerance_mm",3.0); tie.Add("adjust",false);
        tie.Add("master",SelectionSurface(seed,1)); tie.Add("slave",SelectionSurface(seed,2));
        var selections = new JObject(); selections.Add("ties",new JArray(tie));
        WriteJson(Path.Combine(directory,"selection.json"),selections);
        WriteJson(Path.Combine(directory,"coordinates.json"),coordinates);
    }

    private static string Fingerprint(Assembly application, FeModel model)
    {
        Type type=application.GetType("PrePoMax.AsterMaxModelFingerprint",true);
        MethodInfo extract=type.GetMethod("Extract",BindingFlags.Public|BindingFlags.Static);
        object value=extract.Invoke(null,new object[] { model });
        return (string)type.GetProperty("Sha256",BindingFlags.Public|BindingFlags.Instance).GetValue(value,null);
    }
    private static void FingerprintChange(Assembly application,FeModel model,string baseline,string name,Action change,Action restore)
    {
        change(); string modified=Fingerprint(application,model); restore(); string restored=Fingerprint(application,model);
        Check("Tie fingerprint changes on "+name+" and restores",modified!=baseline && restored==baseline);
    }
    public static JObject Complete(string directory,Assembly application)
    {
        // Production Tools applies AsterMaxCompatibleSerializationBinder.
        object[] root=Tools.LoadDumpFromFile<object[]>(Path.Combine(directory,"repaired.nrbf"));
        Check("native object-array and trusted holder reopen",root.Length==1 && root[0] is AsterMaxC1208SyntheticModelHolder);
        FeModel model=((AsterMaxC1208SyntheticModelHolder)root[0])._model;
        using (var reader=new BinaryReader(File.OpenRead(Path.Combine(directory,"mesh.bin")))) FeMesh.ReadFromBinaryFile(model.Mesh,reader,1004000);
        Check("native separate mesh arrays restored",model.Mesh.Nodes.Count==8 && model.Mesh.Elements.Count==2);
        Check("original coordinates exact",seed.Mesh.Nodes.All(n => model.Mesh.Nodes[n.Key].X==n.Value.X && model.Mesh.Nodes[n.Key].Y==n.Value.Y && model.Mesh.Nodes[n.Key].Z==n.Value.Z));
        Check("original element connectivity exact",seed.Mesh.Elements.All(e => model.Mesh.Elements[e.Key].NodeIds.SequenceEqual(e.Value.NodeIds)));
        Check("old node sets preserved",seed.Mesh.NodeSets.All(n => model.Mesh.NodeSets.ContainsKey(n.Key) && model.Mesh.NodeSets[n.Key].Labels.SequenceEqual(n.Value.Labels)));
        Check("old element sets preserved",seed.Mesh.ElementSets.All(e => model.Mesh.ElementSets.ContainsKey(e.Key) && model.Mesh.ElementSets[e.Key].Labels.SequenceEqual(e.Value.Labels)));
        Check("old surfaces preserved",seed.Mesh.Surfaces.All(s => model.Mesh.Surfaces.ContainsKey(s.Key) && model.Mesh.Surfaces[s.Key].FaceIds.SequenceEqual(s.Value.FaceIds)));
        Check("one native Tie replaces contact",model.Constraints.Count==1 && model.Constraints.Values.Single() is Tie && model.ContactPairs.Count==0);
        Tie tie=(Tie)model.Constraints.Values.Single();
        Check("native Tie semantics reopen",tie.Name=="Synthetic_Bonded" && tie.Active && tie.Valid && !tie.Adjust && tie.PositionTolerance==3.0 && tie.MasterRegionType==RegionTypeEnum.SurfaceName && tie.SlaveRegionType==RegionTypeEnum.SurfaceName);
        Check("new named editable surface references",tie.MasterRegionName=="Bonded_01_M" && tie.SlaveRegionName=="Bonded_01_S" && model.Mesh.Surfaces.Count==4);
        foreach (string role in new[] { tie.MasterRegionName,tie.SlaveRegionName })
        {
            FeSurface s=model.Mesh.Surfaces[role];
            Check("native face dictionary and selection "+role,s.Type==FeSurfaceType.Element && s.FaceIds.Length==1 && s.ElementFaces.Count==1 && s.ElementFaces.ContainsKey(FeFaceName.S1) && model.Mesh.NodeSets[s.NodeSetName].Labels.Length==3 && s.Area==50.0);
        }
        Check("materials and sections preserved",model.Materials.Count==1 && model.Materials.ContainsKey("SyntheticSteel") && model.Sections.Count==1 && model.Sections.ContainsKey("SyntheticSection"));
        StaticStep step=model.StepCollection.StepsList.OfType<StaticStep>().Single();
        CLoad load=step.Loads.Values.OfType<CLoad>().Single();
        Check("native load and supports preserved",step.BoundaryConditions.Count==1 && load.F1==0.0 && load.F2==-26000.0 && load.F3==0.0 && load.RegionName=="LoadNodes");
        string before=Fingerprint(application,model);
        FingerprintChange(application,model,before,"position tolerance",delegate { tie.PositionTolerance=3.25; },delegate { tie.PositionTolerance=3.0; });
        FingerprintChange(application,model,before,"adjust",delegate { tie.Adjust=true; },delegate { tie.Adjust=false; });
        FingerprintChange(application,model,before,"master surface",delegate { tie.MasterRegionName="MasterSurface"; },delegate { tie.MasterRegionName="Bonded_01_M"; });
        FingerprintChange(application,model,before,"slave surface",delegate { tie.SlaveRegionName="SlaveSurface"; },delegate { tie.SlaveRegionName="Bonded_01_S"; });
        FingerprintChange(application,model,before,"active",delegate { tie.Active=false; },delegate { tie.Active=true; });
        FingerprintChange(application,model,before,"remove",delegate { model.Constraints.Remove(tie.Name); },delegate { model.Constraints.Add(tie.Name,tie); });
        var extra=new Tie("ExtraSyntheticTie",3.0,false,"MasterSurface",RegionTypeEnum.SurfaceName,"SlaveSurface",RegionTypeEnum.SurfaceName,false);
        FingerprintChange(application,model,before,"add",delegate { model.Constraints.Add(extra.Name,extra); },delegate { model.Constraints.Remove(extra.Name); });
        Type bridge=application.GetType("PrePoMax.AsterMaxModelContractBridge",true);
        JObject contract=(JObject)bridge.GetMethod("Build",BindingFlags.Public|BindingFlags.Static).Invoke(null,new object[] { model });
        Check("compiled live FeModel bridge reads native Tie",((JArray)contract["bonded_ties"]).Count==1 && ((JArray)contract["contacts"]).Count==0);
        WriteJson(Path.Combine(directory,"reopened-contract.json"),contract);
        Type exporter=application.GetType("PrePoMax.AsterMaxCodeAsterNativeExporter",true);
        MethodInfo export=exporter.GetMethod("Export",BindingFlags.Public|BindingFlags.Static,null,new[] { typeof(FeModel),typeof(string),typeof(string) },null);
        JObject manifest=(JObject)export.Invoke(null,new object[] { model,Path.Combine(directory,"native-export"),"synthetic-reopened" });
        Check("compiled live model export accepts welded project",(int)manifest["bonded_pair_count"]==1 && (int)manifest["bonded_mpc_report"]["retained_rows"]==9);
        Check("compiled export retains force per-node semantics",(string)manifest["load_semantics"]=="PER_NODE_CLOAD" && (double)manifest["fy_per_node_n"]==-26000.0 && (double)manifest["fy_total_n"]==-52000.0);
        Check("export leaves model fingerprint unchanged",Fingerprint(application,model)==before);
        // Native resave/reopen ensures the appended metadata becomes an ordinary
        // valid serialized Tie, not a one-use reader accident.
        string resaved=Path.Combine(directory,"native-resaved.nrbf");
        using (var file=File.Create(resaved))
        {
            var formatter=new BinaryFormatter(); formatter.AssemblyFormat=FormatterAssemblyStyle.Simple; formatter.Serialize(file,root);
        }
        object[] roundtrip=Tools.LoadDumpFromFile<object[]>(resaved);
        FeModel reopened=((AsterMaxC1208SyntheticModelHolder)roundtrip[0])._model;
        Check("native resave and second reopen",reopened.Constraints.Count==1 && reopened.Constraints.Values.Single() is Tie && ((Tie)reopened.Constraints.Values.Single()).PositionTolerance==3.0);
        var report=new JObject(); report.Add("all_checks_pass",true); report.Add("private_user_geometry_included",false);
        report.Add("scope","TRUSTED_PACKAGED_ASSEMBLIES_SYNTHETIC_NRBF_AND_MESH_ROUNDTRIP");
        report.Add("production_compatibility_binder_executed",true); report.Add("live_model_bridge_executed",true);
        report.Add("live_model_export_executed",true); report.Add("tie_fingerprint_mutations_checked",7);
        report.Add("solver_execution","NOT_RUN"); report.Add("gui_interactive_validation","NOT_RUN"); report.Add("checks",checks);
        return report;
    }
}
