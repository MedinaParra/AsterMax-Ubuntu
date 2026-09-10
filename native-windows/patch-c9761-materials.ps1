param([string]$Root)
$ErrorActionPreference='Stop'
$p=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$ui=Get-Content $p -Raw
$anchor='            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] {'
$tabs=@'
            ribbon.TabPages.Add(BuildRibbonPage("Materiales", new Control[] {
                CommandTile("Biblioteca", "MATERIALES", () => AsterMaxMaterialAction(() => tsmiMaterialLibrary_Click(null, EventArgs.Empty)), true),
                CommandTile("Nuevo material", "MATERIALES", () => AsterMaxMaterialAction(() => tsmiCreateMaterial_Click(null, EventArgs.Empty))),
                CommandTile("Editar material", "MATERIALES", () => AsterMaxMaterialAction(() => tsmiEditMaterial_Click(null, EventArgs.Empty))),
                CommandTile("Asignar a pieza", "SECCION SOLIDA", () => AsterMaxMaterialAction(() => tsmiCreateSection_Click(null, EventArgs.Empty))),
                InfoCard("Biblioteca > copiar al modelo > guardar. Luego asignar mediante una seccion solida.")
            }));
            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] {
'@
if(-not $ui.Contains($anchor)){throw 'Ribbon anchor missing'}
$ui=$ui.Replace($anchor,$tabs)
$ui=$ui.Replace('tab == "Model" || tab == "Connections"','tab == "Materiales" || tab == "Model" || tab == "Connections"')
$anchor='        private void AsterMaxSelectWorkspace(string tab)'
$methods=@'
        private void AsterMaxMaterialAction(Action action)
        {
            try {
                if (_controller == null || _controller.Model == null || _controller.Model.Mesh == null ||
                    _controller.Model.Mesh.Parts.Count == 0) {
                    MessageBox.Show(this, "Primero importa una geometria y genera su malla.", "Materiales",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                AsterMaxSelectWorkspace("Materiales");
                AsterMaxEnsureMaterialLibrary();
                action();
            } catch (Exception ex) {
                MessageBox.Show(this, ex.Message, "Materiales", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private string AsterMaxEnsureMaterialLibrary()
        {
            string path = System.IO.Path.Combine(Application.StartupPath, Globals.MaterialLibraryFileName);
            if (!System.IO.File.Exists(path)) {
                var root = new PrePoMax.Forms.MaterialLibraryItem("Materiales_AsterMax") { Expanded = true };
                var steel = new Material("Acero_elastico_referencia");
                steel.Description = "Referencia elastica a temperatura ambiente; no define grado, limite de fluencia ni plasticidad. " +
                    "E=210000 MPa; nu=0.3; densidad=7850 kg/m3. SSAB Precision Steel Tube Handbook, p.187. " +
                    "https://www.ssab.com/-/media/C7B2AA431A3545C38796EA08EC59B148.ashx";
                steel.AddProperty(new Elastic(new double[][] { new double[] {210000, 0.3, 20} }));
                // Native material libraries use mm, tonne, second, Celsius.
                steel.AddProperty(new Density(new double[][] { new double[] {7.85e-9, 20} }));
                root.Items.Add(new PrePoMax.Forms.MaterialLibraryItem(steel.Name) { Tag = steel });
                var settings = new Newtonsoft.Json.JsonSerializerSettings {
                    TypeNameHandling = Newtonsoft.Json.TypeNameHandling.Auto
                };
                System.IO.File.WriteAllText(path, Newtonsoft.Json.JsonConvert.SerializeObject(root,
                    Newtonsoft.Json.Formatting.Indented, settings));
            }
            return path;
        }

        private void AsterMaxPrepareMaterialSmoke()
        {
            string path = AsterMaxEnsureMaterialLibrary();
            var root = Newtonsoft.Json.JsonConvert.DeserializeObject<PrePoMax.Forms.MaterialLibraryItem>(
                System.IO.File.ReadAllText(path), new Newtonsoft.Json.JsonSerializerSettings {
                    TypeNameHandling = Newtonsoft.Json.TypeNameHandling.Auto
                });
            var steel = root.Items[0].Tag;
            var mm = new UnitSystem(UnitSystemType.MM_TON_S_C);
            var si = new UnitSystem(UnitSystemType.M_KG_S_C);
            steel.ConvertUnits(mm, mm, si);
            if (Math.Abs(((Elastic)steel.GetProperty<Elastic>()).YoungsPoissonsTemp[0][0] - 210e9) > 1 ||
                Math.Abs(((Density)steel.GetProperty<Density>()).DensityTemp[0][0] - 7850) > 1e-6)
                throw new Exception("Material library SI unit conversion failed");
            steel.ConvertUnits(mm, si, mm);
            _controller.AddMaterialCommand(steel);
            string part = null;
            foreach (var entry in _controller.Model.Mesh.Parts) { part = entry.Key; break; }
            _controller.AddSectionCommand(new SolidSection("Seccion_acero", steel.Name, part,
                RegionTypeEnum.PartName, 1, false));
            AsterMaxVerifyMaterialSmoke();
        }

        private void AsterMaxVerifyMaterialSmoke()
        {
            var steel = _controller.Model.Materials["Acero_elastico_referencia"];
            var elastic = (Elastic)steel.GetProperty<Elastic>();
            var density = (Density)steel.GetProperty<Density>();
            var section = (SolidSection)_controller.Model.Sections["Seccion_acero"];
            if (Math.Abs(elastic.YoungsPoissonsTemp[0][0] - 210000) > 1e-6 ||
                Math.Abs(elastic.YoungsPoissonsTemp[0][1] - 0.3) > 1e-12 ||
                Math.Abs(density.DensityTemp[0][0] - 7.85e-9) > 1e-18 ||
                section.MaterialName != steel.Name || section.RegionType != RegionTypeEnum.PartName ||
                !_controller.Model.Mesh.Parts.ContainsKey(section.RegionName))
                throw new Exception("Material properties or solid section assignment changed");
        }

'@
if(-not $ui.Contains($anchor)){throw 'Material methods anchor missing'}
$ui=$ui.Replace($anchor,$methods+$anchor)
$ui=$ui.Replace('                                string expectedHash = AsterMaxProjectMeshHash();',
 '                                AsterMaxPrepareMaterialSmoke();' + [Environment]::NewLine +
 '                                string expectedHash = AsterMaxProjectMeshHash();')
$ui=$ui.Replace('                                    _controller.Open(projectPath);',
 '                                    _controller.Open(projectPath);' + [Environment]::NewLine +
 '                                    AsterMaxVerifyMaterialSmoke();')
$ui=$ui.Replace('                                "\"project_roundtrip\":true," +',
 '                                "\"material_roundtrip\":true," +' + [Environment]::NewLine +
 '                                "\"project_roundtrip\":true," +')
Set-Content $p $ui -Encoding UTF8
$g=Join-Path $Root 'PrePoMax/Globals.cs'
Set-Content $g ((Get-Content $g -Raw).Replace('AsterMax Mechanical C9.76','AsterMax Mechanical C9.76.1')) -Encoding UTF8

$ui=Get-Content $p -Raw
$anchor='                            AsterMaxSmokeTrace.Stage(_args, "project_roundtrip_passed");'
$replacement=@'
                            TabControl materialRibbon = Controls.Find("asterMaxRibbon", true)[0] as TabControl;
                            TabPage materialPage = null;
                            foreach (TabPage page in materialRibbon.TabPages)
                                if (page.Text == "Materiales") materialPage = page;
                            if (materialPage == null) throw new Exception("Materiales ribbon page is missing");
                            materialRibbon.SelectedTab = materialPage;
                            materialRibbon.PerformLayout();
                            materialRibbon.Refresh();
                            if (materialRibbon.SelectedTab != materialPage || !materialPage.Visible)
                                throw new Exception("Materiales ribbon page is not visible");
                            AsterMaxSmokeTrace.Stage(_args, "materials_ribbon_visible");
                            AsterMaxSmokeTrace.Stage(_args, "project_roundtrip_passed");
'@
if(-not $ui.Contains($anchor)){throw 'Visible material ribbon smoke anchor missing'}
Set-Content $p ($ui.Replace($anchor,$replacement)) -Encoding UTF8
