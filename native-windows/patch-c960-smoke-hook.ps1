param([string]$Root)
$ErrorActionPreference = 'Stop'
$path = Join-Path $Root 'PrePoMax/AsterMaxModelContractBridge.cs'
if(!(Test-Path $path)){ throw 'C9.60 bridge source missing.' }
$t = Get-Content $path -Raw
if($t.Contains('ExportDeterministicSmoke')) { Write-Host 'C9.60 smoke hook already present.'; exit 0 }
$anchor = '        public static string Export(FeModel model, string fileName)'
if(-not $t.Contains($anchor)){ throw 'C9.60 Export anchor missing.' }
$method = @'
        // CI proof path: constructs a real FeModel using the same CaeModel/CaeMesh classes used by the GUI,
        // then passes it through Build(). The returned JSON is a model-definition artifact, never an FEA result.
        public static string ExportDeterministicSmoke(string fileName)
        {
            FeModel model = new FeModel("C9.60 Native Bridge Smoke");
            model.UnitSystem = new UnitSystem(UnitSystemType.MM_TON_S_C);
            model.Mesh.Nodes.Add(1, new FeNode(1, 0, 0, 0));
            model.Mesh.Nodes.Add(2, new FeNode(2, 100, 0, 0));
            model.Mesh.Nodes.Add(3, new FeNode(3, 100, 10, 0));
            model.Mesh.Nodes.Add(4, new FeNode(4, 0, 10, 0));
            model.Mesh.Nodes.Add(5, new FeNode(5, 0, 0, 10));
            model.Mesh.Nodes.Add(6, new FeNode(6, 100, 0, 10));
            model.Mesh.Nodes.Add(7, new FeNode(7, 100, 10, 10));
            model.Mesh.Nodes.Add(8, new FeNode(8, 0, 10, 10));
            model.Mesh.Elements.Add(1, new LinearHexaElement(1, new int[] { 1,2,3,4,5,6,7,8 }));
            model.Mesh.NodeSets.Add("FIXED", new FeNodeSet("FIXED", new int[] { 1,4,5,8 }));
            model.Mesh.NodeSets.Add("LOAD", new FeNodeSet("LOAD", new int[] { 2,3,6,7 }));

            Material steel = new Material("StructuralSteel");
            steel.AddProperty(new ElasticWithDensity(210000.0, 0.30, 7.85E-9));
            model.Materials.Add(steel.Name, steel);

            StaticStep step = new StaticStep("Static Structural");
            if(!step.AddBoundaryCondition(new FixedBC("FixedSupport", "FIXED", RegionTypeEnum.NodeSetName, false)))
                throw new InvalidOperationException("StaticStep rejected FixedBC in C9.60 smoke model.");
            if(!step.AddLoad(new CLoad("AxialForce", "LOAD", RegionTypeEnum.NodeSetName, 2500.0, 0.0, 0.0, false, false, 0.0)))
                throw new InvalidOperationException("StaticStep rejected CLoad in C9.60 smoke model.");
            model.StepCollection.AddStep(step, false);

            return Export(model, fileName);
        }

'@
$t = $t.Replace($anchor, $method + $anchor)
Set-Content $path $t -Encoding UTF8
Write-Host 'C9.60 deterministic native bridge smoke hook injected.' -ForegroundColor Green
