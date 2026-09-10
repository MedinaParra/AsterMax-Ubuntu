param([string]$Root)
$ErrorActionPreference='Stop'

# C10.04 — make the native Solve path compatible with the tetrahedral meshes
# produced by the STEP -> NetGen workflow. Keep all gates fail-closed.

$exporterPath=Join-Path $Root 'PrePoMax/AsterMaxCodeAsterNativeExporter.cs'
if(!(Test-Path $exporterPath)){ throw 'C10.04 requires the C9.61/C10 native Code_Aster exporter first.' }
$e=Get-Content $exporterPath -Raw

$e=$e.Replace('public const string Version = "C9.61-native-codeaster-v0";',
              'public const string Version = "C10.04-native-codeaster-tetra-v1";')

$old=@'
            string elementType=(string)mesh["element_type"];
            if(elementType!="HEXA8") throw new NotSupportedException("C9.61 native exporter v0 currently supports HEXA8 only.");
'@
$new=@'
            var supportedElementTypes=new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "HEXA8", "TETRA4", "TETRA10"
            };
            string[] actualElementTypes=elements.Cast<JObject>()
                .Select(x=>(string)x["type"])
                .Where(x=>!String.IsNullOrWhiteSpace(x))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(x=>x,StringComparer.OrdinalIgnoreCase)
                .ToArray();
            if(actualElementTypes.Length==0)
                throw new InvalidOperationException("The FE mesh contains no exportable volume element types.");
            foreach(string t in actualElementTypes)
                if(!supportedElementTypes.Contains(t))
                    throw new NotSupportedException("C10.04 native exporter does not support element type: "+t);
            string elementType=actualElementTypes.Length==1?actualElementTypes[0]:"MIXED";
'@
if(-not $e.Contains($old)){ throw 'C10.04 exporter element-type anchor missing.' }
$e=$e.Replace($old,$new)

$old=@'
            mail.Add("FINSF"); mail.Add(elementType);
            foreach(JObject e in elements.Cast<JObject>().OrderBy(e=>(string)e["id"]))
                mail.Add((string)e["id"]+" "+String.Join(" ",((JArray)e["nodes"]).Select(x=>(string)x)));
            mail.Add("FINSF");
'@
$new=@'
            mail.Add("FINSF");
            foreach(string currentType in actualElementTypes)
            {
                mail.Add(currentType);
                foreach(JObject element in elements.Cast<JObject>()
                    .Where(x=>String.Equals((string)x["type"],currentType,StringComparison.OrdinalIgnoreCase))
                    .OrderBy(x=>(string)x["id"]))
                {
                    JArray connectivity=(JArray)element["nodes"];
                    int expected=currentType=="HEXA8"?8:(currentType=="TETRA4"?4:10);
                    if(connectivity==null || connectivity.Count!=expected)
                        throw new InvalidOperationException(String.Format(CultureInfo.InvariantCulture,
                            "Element {0} has {1} nodes; {2} requires {3}.",
                            (string)element["id"],connectivity==null?0:connectivity.Count,currentType,expected));
                    if(connectivity.Select(x=>(string)x).Distinct(StringComparer.OrdinalIgnoreCase).Count()!=expected)
                        throw new InvalidOperationException("Element has duplicate node references: "+(string)element["id"]);
                    mail.Add((string)element["id"]+" "+String.Join(" ",connectivity.Select(x=>(string)x)));
                }
                mail.Add("FINSF");
            }
'@
if(-not $e.Contains($old)){ throw 'C10.04 ASTER mail element block anchor missing.' }
$e=$e.Replace($old,$new)

$anchor='                ["element_type"]=elementType,'
$insert=@'
                ["element_type"]=elementType,
                ["element_types"]=new JArray(actualElementTypes),
                ["tetrahedral_export_enabled"]=actualElementTypes.Any(x=>x=="TETRA4" || x=="TETRA10"),
'@
if(-not $e.Contains('["tetrahedral_export_enabled"]')){
    if(-not $e.Contains($anchor)){ throw 'C10.04 exporter manifest anchor missing.' }
    $e=$e.Replace($anchor,$insert.TrimEnd())
}
Set-Content $exporterPath $e -Encoding UTF8

# The pre-solve readiness gate previously rejected everything except LinearHexaElement.
$readinessPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxResultsWorkspace.cs'
if(!(Test-Path $readinessPath)){ throw 'C10.04 requires the C9.77 readiness gate first.' }
$r=Get-Content $readinessPath -Raw
$old=@'
                    if (!(e is CaeMesh.LinearHexaElement))
                    {
                        r.UnsupportedElementCount++;
                        continue;
                    }
                    if (e.NodeIds == null || e.NodeIds.Length != 8)
                    {
                        r.DegenerateConnectivityCount++;
                        continue;
                    }
'@
$new=@'
                    int expectedNodeCount = 0;
                    if (e is CaeMesh.LinearHexaElement) expectedNodeCount = 8;
                    else if (e is CaeMesh.LinearTetraElement) expectedNodeCount = 4;
                    else if (e is CaeMesh.ParabolicTetraElement) expectedNodeCount = 10;
                    else
                    {
                        r.UnsupportedElementCount++;
                        continue;
                    }
                    if (e.NodeIds == null || e.NodeIds.Length != expectedNodeCount)
                    {
                        r.DegenerateConnectivityCount++;
                        continue;
                    }
'@
if(-not $r.Contains($old)){ throw 'C10.04 readiness element-family anchor missing.' }
$r=$r.Replace($old,$new)
$r=$r.Replace('{1} nodes / {2} HEXA8 elements','{1} nodes / {2} supported volume elements')
$r=$r.Replace('unsupported_elements_for_current_code_aster_pmv','unsupported_elements_for_code_aster_c1004')
Set-Content $readinessPath $r -Encoding UTF8

# Improve the visible Mechanical workflow without changing native model ownership.
$uiPath=Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
if(!(Test-Path $uiPath)){ throw 'C10.04 requires AsterMaxNativeUi.cs.' }
$u=Get-Content $uiPath -Raw
$u=$u.Replace('TET4 baseline • TET10 next gate','TET4 / TET10 / HEXA8 native Code_Aster path')
$u=$u.Replace('Code_Aster ready path','Code_Aster | native solve')

if(-not $u.Contains('BuildRibbonPage("Materiales"')){
    $anchor='            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] {'
    $tab=@'
            ribbon.TabPages.Add(BuildRibbonPage("Materiales", new Control[] {
                CommandTile("Biblioteca", "MATERIALES", () => AsterMaxC1004MaterialAction(() => tsmiMaterialLibrary_Click(null, EventArgs.Empty)), true),
                CommandTile("Nuevo material", "MATERIALES", () => AsterMaxC1004MaterialAction(() => tsmiCreateMaterial_Click(null, EventArgs.Empty))),
                CommandTile("Editar material", "MATERIALES", () => AsterMaxC1004MaterialAction(() => tsmiEditMaterial_Click(null, EventArgs.Empty))),
                CommandTile("Asignar seccion", "SOLID", () => AsterMaxC1004MaterialAction(() => tsmiCreateSection_Click(null, EventArgs.Empty))),
                InfoCard("Material -> seccion solida -> malla -> BC/carga -> Solve")
            }));

            ribbon.TabPages.Add(BuildRibbonPage("Connections", new Control[] {
'@
    if(-not $u.Contains($anchor)){ throw 'C10.04 Materiales ribbon anchor missing.' }
    $u=$u.Replace($anchor,$tab)
}

if(-not $u.Contains('private void AsterMaxC1004MaterialAction(Action action)')){
    $anchor='        private void PolishNativeWorkspace()'
    $method=@'
        private void AsterMaxC1004MaterialAction(Action action)
        {
            try
            {
                if (_controller == null || _controller.Model == null)
                {
                    MessageBox.Show(this, "Primero crea o abre un modelo.", "Materiales",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return;
                }
                _controller.CurrentView = ViewGeometryModelResults.Model;
                action();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "Materiales", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

'@
    if(-not $u.Contains($anchor)){ throw 'C10.04 material helper anchor missing.' }
    $u=$u.Replace($anchor,$method+$anchor)
}
Set-Content $uiPath $u -Encoding UTF8

# Product caption for the integrated development line.
$globalsPath=Join-Path $Root 'PrePoMax/Globals.cs'
$g=Get-Content $globalsPath -Raw
$g=$g.Replace('AsterMax Mechanical — Native PMV','AsterMax Mechanical C10.04')
Set-Content $globalsPath $g -Encoding UTF8

Write-Host 'C10.04 tetrahedral native Code_Aster solve support injected.' -ForegroundColor Green
