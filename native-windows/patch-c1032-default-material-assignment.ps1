param([string]$Root)
$ErrorActionPreference='Stop'

$controllerPath = Join-Path $Root 'PrePoMax/Controller.cs'
$mainPath = Join-Path $Root 'PrePoMax/Forms/FrmMain.cs'
foreach($p in @($controllerPath,$mainPath)){ if(!(Test-Path $p)){ throw "C10.32 missing: $p" } }

# ----------------------------------------------------------------------
# Controller: create one default structural-steel material and assign it
# to every unassigned solid mesh part through a real SolidSection.
# ----------------------------------------------------------------------
$c=[regex]::Replace((Get-Content $controllerPath -Raw),"\r\n?","`n")

$insertAnchor='        #endregion #################################################################################################################'+"`n`n"+'        #region Section menu'
$helper=@'
        public const string AsterMaxDefaultMaterialName = "Acero estructural - AsterMax";

        public void AsterMaxEnsureDefaultMaterialAndSections()
        {
            if (_model == null) return;

            string materialName = AsterMaxDefaultMaterialName;

            // Respect imported/user-defined material systems. AsterMax only creates
            // its default when the model has no material at all.
            if (_model.Materials.Count == 0)
            {
                Material material = new Material(materialName);
                material.Description = "Material predeterminado AsterMax. Revise propiedades antes del cálculo final.";
                material.TemperatureDependent = false;

                double young = CaeGlobals.StringPressureConverter.ConvertToCurrentUnits("210 GPa");
                double density = CaeGlobals.StringDensityConverter.ConvertToCurrentUnits("7850 kg/m^3");
                material.AddProperty(new Elastic(new double[][] {
                    new double[] { young, 0.30 }
                }));
                material.AddProperty(new Density(new double[][] {
                    new double[] { density }
                }));
                AddMaterialCommand(material);
            }
            else if (!_model.Materials.ContainsKey(materialName))
            {
                // Existing/imported materials take precedence. Do not silently
                // inject or overwrite engineering data in an existing model.
                return;
            }

            if (_model.Mesh == null || _model.Mesh.Parts == null || _model.Mesh.Parts.Count == 0) return;

            HashSet<string> assignedParts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in _model.Sections)
            {
                Section section = entry.Value;
                if (section != null &&
                    section.RegionType == RegionTypeEnum.PartName &&
                    !String.IsNullOrWhiteSpace(section.RegionName))
                    assignedParts.Add(section.RegionName);
            }

            int created = 0;
            foreach (var entry in _model.Mesh.Parts)
            {
                BasePart part = entry.Value;
                if (part == null || part.PartType != PartType.Solid) continue;
                if (assignedParts.Contains(entry.Key)) continue;

                string sectionName = _model.Sections.GetNextNumberedKey("AsterMax Auto Section");
                SolidSection section = new SolidSection(sectionName,
                                                        materialName,
                                                        entry.Key,
                                                        RegionTypeEnum.PartName,
                                                        1.0,
                                                        false);
                AddSectionCommand(section);
                assignedParts.Add(entry.Key);
                created++;
            }

            if (created > 0)
                _form.WriteDataToOutput("AsterMax: material predeterminado '" + materialName +
                                        "' asignado automáticamente a " + created + " pieza(s) sólida(s).");
        }

'@
if(-not $c.Contains('AsterMaxEnsureDefaultMaterialAndSections()')){
  $idx=$c.IndexOf($insertAnchor)
  if($idx -lt 0){ throw 'C10.32 Controller material insertion anchor missing.' }
  $c=$c.Substring(0,$idx)+$helper+$c.Substring($idx)
}
Set-Content $controllerPath $c -Encoding UTF8

# ----------------------------------------------------------------------
# FrmMain: call after interactive import, command-line import, and mesh.
# Material appears in the tree after CAD import; sections appear as soon
# as mesh parts exist.
# ----------------------------------------------------------------------
$m=[regex]::Replace((Get-Content $mainPath -Raw),"\r\n?","`n")

$interactiveAnchor='                    SetFrontBackView(true, true);   // animate must be true in order for the scale bar to work correctly'
$interactiveNew=@'
                    _controller.AsterMaxEnsureDefaultMaterialAndSections();
                    SetFrontBackView(true, true);   // animate must be true in order for the scale bar to work correctly
'@
if(-not $m.Contains('_controller.AsterMaxEnsureDefaultMaterialAndSections();')){
  if(-not $m.Contains($interactiveAnchor)){ throw 'C10.32 interactive import anchor missing.' }
  $m=$m.Replace($interactiveAnchor,$interactiveNew.TrimEnd())
}

# Startup/command-line import path has its own ImportFileAsync.
$startupAnchor='                                await _controller.ImportFileAsync(fileName, false);'+"`n"+'                                // Set to null, otherwise the previous OpenedFileName gets overwriten on Save'
$startupNew=@'
                                await _controller.ImportFileAsync(fileName, false);
                                _controller.AsterMaxEnsureDefaultMaterialAndSections();
                                // Set to null, otherwise the previous OpenedFileName gets overwriten on Save
'@
if(-not $m.Contains('await _controller.ImportFileAsync(fileName, false);'+"`n"+'                                _controller.AsterMaxEnsureDefaultMaterialAndSections();')){
  if(-not $m.Contains($startupAnchor)){ throw 'C10.32 startup import anchor missing.' }
  $m=$m.Replace($startupAnchor,$startupNew.TrimEnd())
}

# After a batch mesh completes, assign sections to all newly-created solid parts.
$meshAnchor='                _controller.UpdateExplodedView(true);'
$meshNew=@'
                _controller.UpdateExplodedView(true);
                _controller.AsterMaxEnsureDefaultMaterialAndSections();
'@
# C10.31 may already have code after UpdateExplodedView, so insert only the helper line.
if(-not $m.Contains('_controller.UpdateExplodedView(true);'+"`n"+'                _controller.AsterMaxEnsureDefaultMaterialAndSections();')){
  if(-not $m.Contains($meshAnchor)){ throw 'C10.32 post-mesh anchor missing.' }
  $m=$m.Replace($meshAnchor,$meshNew.TrimEnd())
}

Set-Content $mainPath $m -Encoding UTF8

Write-Host 'C10.32: default structural steel + automatic solid-part section assignment applied.' -ForegroundColor Green
