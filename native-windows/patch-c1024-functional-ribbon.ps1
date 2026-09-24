param([string]$Root)
$ErrorActionPreference='Stop'

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

function Replace-Required([string]$Text,[string]$Old,[string]$New,[string]$Name) {
    if(-not $Text.Contains($Old)) { throw "C10.24 ribbon anchor missing: $Name" }
    return $Text.Replace($Old,$New)
}

# Give the ribbon a little more vertical breathing room for a denser Mechanical workflow.
$u = Replace-Required $u '                Height = 118,' '                Height = 132,' 'ribbon height'
$u = Replace-Required $u '                Padding = new Point(16, 5),' '                Padding = new Point(12, 5),' 'ribbon tab padding'

$homeOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Inicio", new Control[] {
                CommandTile("New", "PROJECT", () => tsbNew.PerformClick()),
                CommandTile("Open", "PROJECT", () => tsbOpen.PerformClick()),
                CommandTile("Import Geometry", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Save", "PROJECT", () => tsbSave.PerformClick()),
                RibbonSeparator(),
                CommandTile("Fit", "VIEW", AsterMaxFitView),
                CommandTile("Isometric", "VIEW", AsterMaxIsometricView)
            }));
'@
$homeNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Inicio", new Control[] {
                CommandTile("Nuevo", "ARCHIVO", () => tsbNew.PerformClick()),
                CommandTile("Abrir", "ARCHIVO", () => tsbOpen.PerformClick()),
                CommandTile("Importar", "GEOMETRÍA", () => tsbImport.PerformClick(), true),
                CommandTile("Guardar", "ARCHIVO", () => tsbSave.PerformClick()),
                RibbonSeparator(),
                CommandTile("Deshacer", "EDICIÓN", () => tsmiUndo.PerformClick()),
                CommandTile("Rehacer", "EDICIÓN", () => tsmiRedo.PerformClick()),
                RibbonSeparator(),
                CommandTile("Ajustar", "VISTA", AsterMaxFitView),
                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView)
            }));
'@
$u = Replace-Required $u $homeOld $homeNew 'Inicio'

$geometryOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Geometría", new Control[] {
                CommandTile("Import STEP", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Analyze Geometry", "CHECK", () => tsmiGeometryAnalyze.PerformClick()),
                RibbonSeparator(),
                CommandTile("Fit", "VIEW", AsterMaxFitView),
                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())
            }));
'@
$geometryNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Geometría", new Control[] {
                CommandTile("Importar STEP", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Analizar", "GEOMETRÍA", () => tsmiGeometryAnalyze.PerformClick()),
                RibbonSeparator(),
                CommandTile("Ajustar", "VISTA", AsterMaxFitView),
                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView),
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick())
            }));
'@
$u = Replace-Required $u $geometryOld $geometryNew 'Geometría'

$modelOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Modelo", new Control[] {
                CommandTile("Model Properties", "MODEL", () => tsmiEditModel.PerformClick()),
                CommandTile("Materials", "MODEL", () => tsmiModel.PerformClick()),
                InfoCard("Coordinate systems and named selections live in Outline")
            }));
'@
$modelNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Modelo", new Control[] {
                CommandTile("Propiedades", "MODELO", () => tsmiEditModel.PerformClick()),
                CommandTile("Material", "MODELO", () => tsmiCreateMaterial.PerformClick(), true),
                CommandTile("Sección", "MODELO", () => tsmiCreateSection.PerformClick()),
                RibbonSeparator(),
                InfoCard("Materiales y secciones quedan vinculados al árbol real del modelo")
            }));
'@
$u = Replace-Required $u $modelOld $modelNew 'Modelo'

$meshOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Malla", new Control[] {
                CommandTile("Mesh Controls", "MESH", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Generate Mesh", "MESH", () => tsmiCreateMesh.PerformClick(), true),
                InfoCard("TET4 baseline • TET10 next gate")
            }));
'@
$meshNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Malla", new Control[] {
                CommandTile("Controles", "MALLA", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Refinamiento", "MALLA", () => tsmiCreateMeshRefinement.PerformClick()),
                CommandTile("Generar malla", "MALLA", () => tsmiCreateMesh.PerformClick(), true),
                RibbonSeparator(),
                InfoCard("NetGen nativo • tamaño global y refinamientos locales")
            }));
'@
$u = Replace-Required $u $meshOld $meshNew 'Malla'

$environmentOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Entorno", new Control[] {
                InfoCard("Supports and loads remain connected to native scoping"),
                StateCard("Analysis", "Static Structural")
            }));
'@
$environmentNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Entorno", new Control[] {
                CommandTile("Paso", "ANÁLISIS", () => tsmiCreateStep.PerformClick(), true),
                CommandTile("Apoyo", "CONDICIÓN", () => tsmiCreateBC.PerformClick()),
                CommandTile("Carga", "CONDICIÓN", () => tsmiCreateLoad.PerformClick()),
                RibbonSeparator(),
                StateCard("Análisis", "Estructural estático")
            }));
'@
$u = Replace-Required $u $environmentOld $environmentNew 'Entorno'

$solutionOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Solución", new Control[] {
                StateCard("Solver", "Code_Aster integration path"),
                InfoCard("Solution requests stay in the analysis tree; no synthetic results")
            }));
'@
$solutionNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Solución", new Control[] {
                CommandTile("Verificar", "MODELO", () => tsmiCheckModel.PerformClick()),
                CommandTile("Análisis", "SOLVER", () => tsmiCreateAnalysis.PerformClick()),
                CommandTile("Ejecutar", "CODE_ASTER", () => tsmiRunAnalysis.PerformClick(), true),
                CommandTile("Monitor", "CODE_ASTER", () => tsmiMonitorAnalysis.PerformClick()),
                RibbonSeparator(),
                StateCard("Solver", "Code_Aster nativo")
            }));
'@
$u = Replace-Required $u $solutionOld $solutionNew 'Solución'

$resultsOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Resultados", new Control[] {
                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick(), true),
                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),
                InfoCard("Deformation • Equivalent Stress • Reactions")
            }));
'@
$resultsNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Resultados", new Control[] {
                CommandTile("Abrir", "RESULTADOS", () => tsmiResultsAnalysis.PerformClick()),
                CommandTile("Contornos", "RESULTADOS", () => tsbResultsColorContours.PerformClick(), true),
                CommandTile("Deformada", "RESULTADOS", () => tsbResultsDeformed.PerformClick()),
                CommandTile("Original", "RESULTADOS", () => tsbResultsUndeformed.PerformClick()),
                RibbonSeparator(),
                InfoCard("Desplazamiento • tensión equivalente • reacciones")
            }));
'@
$u = Replace-Required $u $resultsOld $resultsNew 'Resultados'

$viewOld = @'
            ribbon.TabPages.Add(BuildRibbonPage("Vista", new Control[] {
                CommandTile("Fit", "CAMERA", AsterMaxFitView),
                CommandTile("Front", "CAMERA", AsterMaxFrontView),
                CommandTile("Top", "CAMERA", AsterMaxTopView),
                CommandTile("Right", "CAMERA", AsterMaxRightView),
                CommandTile("Isometric", "CAMERA", AsterMaxIsometricView),
                RibbonSeparator(),
                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())
            }));
'@
$viewNew = @'
            ribbon.TabPages.Add(BuildRibbonPage("Vista", new Control[] {
                CommandTile("Ajustar", "CÁMARA", AsterMaxFitView),
                CommandTile("Frontal", "CÁMARA", AsterMaxFrontView),
                CommandTile("Superior", "CÁMARA", AsterMaxTopView),
                CommandTile("Derecha", "CÁMARA", AsterMaxRightView),
                CommandTile("Isométrica", "CÁMARA", AsterMaxIsometricView),
                RibbonSeparator(),
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick()),
                CommandTile("Alámbrico", "VISUAL", () => tsbShowWireframeEdges.PerformClick()),
                CommandTile("Sin aristas", "VISUAL", () => tsbShowNoEdges.PerformClick())
            }));
'@
$u = Replace-Required $u $viewOld $viewNew 'Vista'

# Make tiles a little more compact so more commands fit at 1366px while retaining legibility.
$u = Replace-Required $u '                Width = text.Length > 14 ? 132 : 112,' '                Width = text.Length > 13 ? 124 : 104,' 'tile width'
$u = Replace-Required $u '                Height = 62,' '                Height = 70,' 'tile height'
$u = Replace-Required $u '                Font = new Font("Segoe UI", 8.5f)' '                Font = new Font("Segoe UI", 8.25f)' 'tile font'

Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.24: expanded functional Mechanical ribbon applied.' -ForegroundColor Green
