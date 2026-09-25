param([string]$Root)
$ErrorActionPreference='Stop'

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

function Replace-Required([string]$Old,[string]$New,[string]$Name) {
    if(-not $script:u.Contains($Old)) { throw "C10.24 ribbon anchor missing: $Name" }
    $script:u = $script:u.Replace($Old,$New)
}

# Ribbon container layout.
$ribbonPos = $u.IndexOf('Name = "asterMaxRibbon"')
if($ribbonPos -lt 0) { throw 'C10.24 ribbon control anchor missing.' }
$tail = $u.Substring($ribbonPos)
$hm = [regex]::Match($tail, '(?m)^(?<i>\s*)Height\s*=\s*\d+,\s*$')
if(-not $hm.Success) { throw 'C10.24 ribbon height anchor missing.' }
$abs = $ribbonPos + $hm.Index
$u = $u.Substring(0,$abs) + $hm.Groups['i'].Value + 'Height = 132,' + $u.Substring($abs + $hm.Length)

$tail = $u.Substring($ribbonPos)
$pm = [regex]::Match($tail, '(?m)^(?<i>\s*)Padding\s*=\s*new Point\(\d+,\s*\d+\),\s*$')
if(-not $pm.Success) { throw 'C10.24 ribbon padding anchor missing.' }
$abs = $ribbonPos + $pm.Index
$u = $u.Substring(0,$abs) + $pm.Groups['i'].Value + 'Padding = new Point(12, 5),' + $u.Substring($abs + $pm.Length)

# Inicio
Replace-Required '                CommandTile("New", "PROJECT", () => tsbNew.PerformClick()),' '                CommandTile("Nuevo", "ARCHIVO", () => tsbNew.PerformClick()),' 'Inicio/Nuevo'
Replace-Required '                CommandTile("Open", "PROJECT", () => tsbOpen.PerformClick()),' '                CommandTile("Abrir", "ARCHIVO", () => tsbOpen.PerformClick()),' 'Inicio/Abrir'
Replace-Required '                CommandTile("Import Geometry", "CAD", () => tsbImport.PerformClick(), true),' '                CommandTile("Importar", "GEOMETRÍA", () => tsbImport.PerformClick(), true),' 'Inicio/Importar'

$savePattern = '(?m)^(?<i>\s*)CommandTile\("[^"]+",\s*"[^"]+",\s*\(\)\s*=>\s*tsbSave\.PerformClick\(\)\),\s*$'
$sm = [regex]::Match($u, $savePattern)
if(-not $sm.Success) { throw 'C10.24 ribbon anchor missing: Inicio/Guardar' }
$si = $sm.Groups['i'].Value
$saveReplacement = $si + 'CommandTile("Guardar", "ARCHIVO", () => tsbSave.PerformClick()),' + "`n" +
                   $si + 'CommandTile("Deshacer", "EDICIÓN", () => tsmiUndo.PerformClick()),' + "`n" +
                   $si + 'CommandTile("Rehacer", "EDICIÓN", () => tsmiRedo.PerformClick()),'
$u = [regex]::Replace($u, $savePattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($x) $saveReplacement }, 1)
Replace-Required '                CommandTile("Fit", "VIEW", AsterMaxFitView),' '                CommandTile("Ajustar", "VISTA", AsterMaxFitView),' 'Inicio/Ajustar'
Replace-Required '                CommandTile("Isometric", "VIEW", AsterMaxIsometricView)' '                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView)' 'Inicio/Isométrica'

# Geometría
Replace-Required '                CommandTile("Import STEP", "CAD", () => tsbImport.PerformClick(), true),' '                CommandTile("Importar STEP", "CAD", () => tsbImport.PerformClick(), true),' 'Geometría/STEP'
Replace-Required '                CommandTile("Analyze Geometry", "CHECK", () => tsmiGeometryAnalyze.PerformClick()),' '                CommandTile("Analizar", "GEOMETRÍA", () => tsmiGeometryAnalyze.PerformClick()),' 'Geometría/Analizar'
$old = '                CommandTile("Fit", "VIEW", AsterMaxFitView),'
$new = @'
                CommandTile("Ajustar", "VISTA", AsterMaxFitView),
                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView),
'@
Replace-Required $old $new 'Geometría/Vistas'
Replace-Required '                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())' '                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick())' 'Geometría/Aristas'

# Modelo
Replace-Required '                CommandTile("Model Properties", "MODEL", () => tsmiEditModel.PerformClick()),' '                CommandTile("Propiedades", "MODELO", () => tsmiEditModel.PerformClick()),' 'Modelo/Propiedades'
Replace-Required '                CommandTile("Materials", "MODEL", () => tsmiModel.PerformClick()),' '                CommandTile("Material", "MODELO", () => tsmiCreateMaterial.PerformClick(), true),' 'Modelo/Material'
$old = '                InfoCard("Coordinate systems and named selections live in Outline")'
$new = @'
                CommandTile("Sección", "MODELO", () => tsmiCreateSection.PerformClick()),
                RibbonSeparator(),
                InfoCard("Materiales y secciones quedan vinculados al árbol real del modelo")
'@
Replace-Required $old $new 'Modelo/Sección'

# Conexiones
Replace-Required '                InfoCard("Connections and constraints are scoped from the real model tree"),' '                InfoCard("Contactos y restricciones usan el árbol nativo y el scoping real"),' 'Conexiones/Info'
Replace-Required '                StateCard("Scope", "Geometry / Named Selection")' '                StateCard("Ámbito", "Geometría / selección")' 'Conexiones/Ámbito'

# Malla
$old = '                CommandTile("Mesh Controls", "MESH", () => tsmiCreateMeshingParameters.PerformClick()),'
$new = @'
                CommandTile("Controles", "MALLA", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Refinamiento", "MALLA", () => tsmiCreateMeshRefinement.PerformClick()),
'@
Replace-Required $old $new 'Malla/Controles'
Replace-Required '                CommandTile("Generate Mesh", "MESH", () => tsmiCreateMesh.PerformClick(), true),' '                CommandTile("Generar malla", "MALLA", () => tsmiCreateMesh.PerformClick(), true),' 'Malla/Generar'
$old = '                InfoCard("TET4 baseline • TET10 next gate")'
$new = @'
                RibbonSeparator(),
                InfoCard("NetGen nativo • tamaño global y refinamientos locales")
'@
Replace-Required $old $new 'Malla/Info'

# Entorno
$old = '                InfoCard("Supports and loads remain connected to native scoping"),'
$new = @'
                CommandTile("Paso", "ANÁLISIS", () => tsmiCreateStep.PerformClick(), true),
                CommandTile("Apoyo", "CONDICIÓN", () => tsmiCreateBC.PerformClick()),
                CommandTile("Carga", "CONDICIÓN", () => tsmiCreateLoad.PerformClick()),
                RibbonSeparator(),
'@
Replace-Required $old $new 'Entorno/Comandos'
Replace-Required '                StateCard("Analysis", "Static Structural")' '                StateCard("Análisis", "Estructural estático")' 'Entorno/Estado'

# Solución
$old = '                StateCard("Solver", "Code_Aster integration path"),'
$new = @'
                CommandTile("Verificar", "MODELO", () => tsmiCheckModel.PerformClick()),
                CommandTile("Análisis", "SOLVER", () => tsmiCreateAnalysis.PerformClick()),
                CommandTile("Ejecutar", "CODE_ASTER", () => tsmiRunAnalysis.PerformClick(), true),
                CommandTile("Monitor", "CODE_ASTER", () => tsmiMonitorAnalysis.PerformClick()),
                RibbonSeparator(),
                StateCard("Solver", "Code_Aster nativo"),
'@
Replace-Required $old $new 'Solución/Comandos'
Replace-Required '                InfoCard("Solution requests stay in the analysis tree; no synthetic results")' '                InfoCard("Flujo nativo: verificar → ejecutar → monitorear → resultados")' 'Solución/Info'

# Resultados
$old = '                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick(), true),'
$new = @'
                CommandTile("Abrir", "RESULTADOS", () => tsmiResultsAnalysis.PerformClick()),
                CommandTile("Contornos", "RESULTADOS", () => tsbResultsColorContours.PerformClick(), true),
'@
Replace-Required $old $new 'Resultados/Abrir'
$old = '                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),'
$new = @'
                CommandTile("Deformada", "RESULTADOS", () => tsbResultsDeformed.PerformClick()),
                CommandTile("Original", "RESULTADOS", () => tsbResultsUndeformed.PerformClick()),
'@
Replace-Required $old $new 'Resultados/Deformada'
$old = '                InfoCard("Deformation • Equivalent Stress • Reactions")'
$new = @'
                RibbonSeparator(),
                InfoCard("Desplazamiento • tensión equivalente • reacciones")
'@
Replace-Required $old $new 'Resultados/Info'

# Vista
Replace-Required '                CommandTile("Fit", "CAMERA", AsterMaxFitView),' '                CommandTile("Ajustar", "CÁMARA", AsterMaxFitView),' 'Vista/Ajustar'
Replace-Required '                CommandTile("Front", "CAMERA", AsterMaxFrontView),' '                CommandTile("Frontal", "CÁMARA", AsterMaxFrontView),' 'Vista/Frontal'
Replace-Required '                CommandTile("Top", "CAMERA", AsterMaxTopView),' '                CommandTile("Superior", "CÁMARA", AsterMaxTopView),' 'Vista/Superior'
Replace-Required '                CommandTile("Right", "CAMERA", AsterMaxRightView),' '                CommandTile("Derecha", "CÁMARA", AsterMaxRightView),' 'Vista/Derecha'
Replace-Required '                CommandTile("Isometric", "CAMERA", AsterMaxIsometricView),' '                CommandTile("Isométrica", "CÁMARA", AsterMaxIsometricView),' 'Vista/Isométrica'
$old = '                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())'
$new = @'
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick()),
                CommandTile("Alámbrico", "VISUAL", () => tsbShowWireframeEdges.PerformClick()),
                CommandTile("Sin aristas", "VISUAL", () => tsbShowNoEdges.PerformClick())
'@
Replace-Required $old $new 'Vista/Visual'

# Compact CommandTile only.
$cmdStart = $u.IndexOf('        private Button CommandTile(')
$cmdEnd = $u.IndexOf('        private Label InfoCard(', $cmdStart)
if($cmdStart -lt 0 -or $cmdEnd -lt 0) { throw 'C10.24 CommandTile method anchors missing.' }
$cmd = $u.Substring($cmdStart, $cmdEnd-$cmdStart)
$cmd = $cmd.Replace('Width = text.Length > 14 ? 132 : 112,','Width = text.Length > 13 ? 124 : 104,')
$cmd = $cmd.Replace('Height = 62,','Height = 70,')
$cmd = $cmd.Replace('Font = new Font("Segoe UI", 8.5f)','Font = new Font("Segoe UI", 8.25f)')
$u = $u.Substring(0,$cmdStart) + $cmd + $u.Substring($cmdEnd)

Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.24: expanded functional Mechanical ribbon applied.' -ForegroundColor Green

$sm = [regex]::Match($u, $savePattern)
if(-not $sm.Success) { throw 'C10.24 ribbon anchor missing: Inicio/Guardar' }
$si = $sm.Groups['i'].Value
$saveReplacement = $si + 'CommandTile("Guardar", "ARCHIVO", () => tsbSave.PerformClick()),' + "`n" +
                   $si + 'CommandTile("Deshacer", "EDICIÓN", () => tsmiUndo.PerformClick()),' + "`n" +
                   $si + 'CommandTile("Rehacer", "EDICIÓN", () => tsmiRedo.PerformClick()),'
$u = [regex]::Replace($u, $savePattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($x) $saveReplacement }, 1)
Replace-Required '                CommandTile("Fit", "VIEW", AsterMaxFitView),' '                CommandTile("Ajustar", "VISTA", AsterMaxFitView),' 'Inicio/Ajustar'
Replace-Required '                CommandTile("Isometric", "VIEW", AsterMaxIsometricView)' '                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView)' 'Inicio/Isométrica'

# Geometría
Replace-Required '                CommandTile("Import STEP", "CAD", () => tsbImport.PerformClick(), true),' '                CommandTile("Importar STEP", "CAD", () => tsbImport.PerformClick(), true),' 'Geometría/STEP'
Replace-Required '                CommandTile("Analyze Geometry", "CHECK", () => tsmiGeometryAnalyze.PerformClick()),' '                CommandTile("Analizar", "GEOMETRÍA", () => tsmiGeometryAnalyze.PerformClick()),' 'Geometría/Analizar'
$old = '                CommandTile("Fit", "VIEW", AsterMaxFitView),'
$new = @'
                CommandTile("Ajustar", "VISTA", AsterMaxFitView),
                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView),
'@
Replace-Required $old $new 'Geometría/Vistas'
Replace-Required '                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())' '                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick())' 'Geometría/Aristas'

# Modelo
Replace-Required '                CommandTile("Model Properties", "MODEL", () => tsmiEditModel.PerformClick()),' '                CommandTile("Propiedades", "MODELO", () => tsmiEditModel.PerformClick()),' 'Modelo/Propiedades'
Replace-Required '                CommandTile("Materials", "MODEL", () => tsmiModel.PerformClick()),' '                CommandTile("Material", "MODELO", () => tsmiCreateMaterial.PerformClick(), true),' 'Modelo/Material'
$old = '                InfoCard("Coordinate systems and named selections live in Outline")'
$new = @'
                CommandTile("Sección", "MODELO", () => tsmiCreateSection.PerformClick()),
                RibbonSeparator(),
                InfoCard("Materiales y secciones quedan vinculados al árbol real del modelo")
'@
Replace-Required $old $new 'Modelo/Sección'

# Conexiones
Replace-Required '                InfoCard("Connections and constraints are scoped from the real model tree"),' '                InfoCard("Contactos y restricciones usan el árbol nativo y el scoping real"),' 'Conexiones/Info'
Replace-Required '                StateCard("Scope", "Geometry / Named Selection")' '                StateCard("Ámbito", "Geometría / selección")' 'Conexiones/Ámbito'

# Malla
$old = '                CommandTile("Mesh Controls", "MESH", () => tsmiCreateMeshingParameters.PerformClick()),'
$new = @'
                CommandTile("Controles", "MALLA", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Refinamiento", "MALLA", () => tsmiCreateMeshRefinement.PerformClick()),
'@
Replace-Required $old $new 'Malla/Controles'
Replace-Required '                CommandTile("Generate Mesh", "MESH", () => tsmiCreateMesh.PerformClick(), true),' '                CommandTile("Generar malla", "MALLA", () => tsmiCreateMesh.PerformClick(), true),' 'Malla/Generar'
$old = '                InfoCard("TET4 baseline • TET10 next gate")'
$new = @'
                RibbonSeparator(),
                InfoCard("NetGen nativo • tamaño global y refinamientos locales")
'@
Replace-Required $old $new 'Malla/Info'

# Entorno
$old = '                InfoCard("Supports and loads remain connected to native scoping"),'
$new = @'
                CommandTile("Paso", "ANÁLISIS", () => tsmiCreateStep.PerformClick(), true),
                CommandTile("Apoyo", "CONDICIÓN", () => tsmiCreateBC.PerformClick()),
                CommandTile("Carga", "CONDICIÓN", () => tsmiCreateLoad.PerformClick()),
                RibbonSeparator(),
'@
Replace-Required $old $new 'Entorno/Comandos'
Replace-Required '                StateCard("Analysis", "Static Structural")' '                StateCard("Análisis", "Estructural estático")' 'Entorno/Estado'

# Solución
$old = '                StateCard("Solver", "Code_Aster integration path"),'
$new = @'
                CommandTile("Verificar", "MODELO", () => tsmiCheckModel.PerformClick()),
                CommandTile("Análisis", "SOLVER", () => tsmiCreateAnalysis.PerformClick()),
                CommandTile("Ejecutar", "CODE_ASTER", () => tsmiRunAnalysis.PerformClick(), true),
                CommandTile("Monitor", "CODE_ASTER", () => tsmiMonitorAnalysis.PerformClick()),
                RibbonSeparator(),
                StateCard("Solver", "Code_Aster nativo"),
'@
Replace-Required $old $new 'Solución/Comandos'
Replace-Required '                InfoCard("Solution requests stay in the analysis tree; no synthetic results")' '                InfoCard("Flujo nativo: verificar → ejecutar → monitorear → resultados")' 'Solución/Info'

# Resultados
$old = '                CommandTile("Contours", "RESULT", () => tsbResultsColorContours.PerformClick(), true),'
$new = @'
                CommandTile("Abrir", "RESULTADOS", () => tsmiResultsAnalysis.PerformClick()),
                CommandTile("Contornos", "RESULTADOS", () => tsbResultsColorContours.PerformClick(), true),
'@
Replace-Required $old $new 'Resultados/Abrir'
$old = '                CommandTile("Deformed", "RESULT", () => tsbResultsDeformed.PerformClick()),'
$new = @'
                CommandTile("Deformada", "RESULTADOS", () => tsbResultsDeformed.PerformClick()),
                CommandTile("Original", "RESULTADOS", () => tsbResultsUndeformed.PerformClick()),
'@
Replace-Required $old $new 'Resultados/Deformada'
$old = '                InfoCard("Deformation • Equivalent Stress • Reactions")'
$new = @'
                RibbonSeparator(),
                InfoCard("Desplazamiento • tensión equivalente • reacciones")
'@
Replace-Required $old $new 'Resultados/Info'

# Vista
Replace-Required '                CommandTile("Fit", "CAMERA", AsterMaxFitView),' '                CommandTile("Ajustar", "CÁMARA", AsterMaxFitView),' 'Vista/Ajustar'
Replace-Required '                CommandTile("Front", "CAMERA", AsterMaxFrontView),' '                CommandTile("Frontal", "CÁMARA", AsterMaxFrontView),' 'Vista/Frontal'
Replace-Required '                CommandTile("Top", "CAMERA", AsterMaxTopView),' '                CommandTile("Superior", "CÁMARA", AsterMaxTopView),' 'Vista/Superior'
Replace-Required '                CommandTile("Right", "CAMERA", AsterMaxRightView),' '                CommandTile("Derecha", "CÁMARA", AsterMaxRightView),' 'Vista/Derecha'
Replace-Required '                CommandTile("Isometric", "CAMERA", AsterMaxIsometricView),' '                CommandTile("Isométrica", "CÁMARA", AsterMaxIsometricView),' 'Vista/Isométrica'
$old = '                CommandTile("Edges", "DISPLAY", () => tsbShowModelEdges.PerformClick())'
$new = @'
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick()),
                CommandTile("Alámbrico", "VISUAL", () => tsbShowWireframeEdges.PerformClick()),
                CommandTile("Sin aristas", "VISUAL", () => tsbShowNoEdges.PerformClick())
'@
Replace-Required $old $new 'Vista/Visual'

# Compact CommandTile only.
$cmdStart = $u.IndexOf('        private Button CommandTile(')
$cmdEnd = $u.IndexOf('        private Label InfoCard(', $cmdStart)
if($cmdStart -lt 0 -or $cmdEnd -lt 0) { throw 'C10.24 CommandTile method anchors missing.' }
$cmd = $u.Substring($cmdStart, $cmdEnd-$cmdStart)
$cmd = $cmd.Replace('Width = text.Length > 14 ? 132 : 112,','Width = text.Length > 13 ? 124 : 104,')
$cmd = $cmd.Replace('Height = 62,','Height = 70,')
$cmd = $cmd.Replace('Font = new Font("Segoe UI", 8.5f)','Font = new Font("Segoe UI", 8.25f)')
$u = $u.Substring(0,$cmdStart) + $cmd + $u.Substring($cmdEnd)

Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.24: expanded functional Mechanical ribbon applied.' -ForegroundColor Green
