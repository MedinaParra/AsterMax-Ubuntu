param([string]$Root)
$ErrorActionPreference='Stop'

$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$u = [regex]::Replace((Get-Content $ui -Raw), "\r\n?", "`n")

function Replace-RibbonTab([string]$Name,[string]$Body){
    $escaped=[regex]::Escape($Name)
    $pattern='(?s)\s*ribbon\.TabPages\.Add\(BuildRibbonPage\("' + $escaped + '",\s*new Control\[\]\s*\{.*?\}\)\);'
    $m=[regex]::Match($script:u,$pattern)
    if(-not $m.Success){ throw "C10.24 ribbon tab missing: $Name" }
    $replacement="`n`n            ribbon.TabPages.Add(BuildRibbonPage(`"$Name`", new Control[] {`n$Body`n            }));"
    $script:u=$script:u.Substring(0,$m.Index)+$replacement+$script:u.Substring($m.Index+$m.Length)
}

# Ribbon container
$ribbonPos=$u.IndexOf('Name = "asterMaxRibbon"')
if($ribbonPos -lt 0){ throw 'C10.24 ribbon control missing.' }
$tail=$u.Substring($ribbonPos)
$hm=[regex]::Match($tail,'(?m)^(?<i>\s*)Height\s*=\s*\d+,\s*$')
if(-not $hm.Success){ throw 'C10.24 ribbon height missing.' }
$abs=$ribbonPos+$hm.Index
$u=$u.Substring(0,$abs)+$hm.Groups['i'].Value+'Height = 132,'+$u.Substring($abs+$hm.Length)

$tail=$u.Substring($ribbonPos)
$pm=[regex]::Match($tail,'(?m)^(?<i>\s*)Padding\s*=\s*new Point\(\d+,\s*\d+\),\s*$')
if(-not $pm.Success){ throw 'C10.24 ribbon padding missing.' }
$abs=$ribbonPos+$pm.Index
$u=$u.Substring(0,$abs)+$pm.Groups['i'].Value+'Padding = new Point(12, 5),'+$u.Substring($abs+$pm.Length)

Replace-RibbonTab 'Inicio' @'
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
'@

Replace-RibbonTab 'Geometría' @'
                CommandTile("Importar STEP", "CAD", () => tsbImport.PerformClick(), true),
                CommandTile("Analizar", "GEOMETRÍA", () => tsmiGeometryAnalyze.PerformClick()),
                RibbonSeparator(),
                CommandTile("Ajustar", "VISTA", AsterMaxFitView),
                CommandTile("Isométrica", "VISTA", AsterMaxIsometricView),
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick())
'@

Replace-RibbonTab 'Modelo' @'
                CommandTile("Propiedades", "MODELO", () => tsmiEditModel.PerformClick()),
                CommandTile("Material", "MODELO", () => AsterMaxC1004MaterialAction(() => tsmiCreateMaterial_Click(null, EventArgs.Empty)), true),
                CommandTile("Sección", "MODELO", () => AsterMaxC1004MaterialAction(() => tsmiCreateSection_Click(null, EventArgs.Empty))),
                RibbonSeparator(),
                InfoCard("Materiales, secciones y scoping conectados al árbol real")
'@

Replace-RibbonTab 'Conexiones' @'
                InfoCard("Contactos y restricciones usan el árbol nativo y el scoping real"),
                StateCard("Ámbito", "Geometría / selección")
'@

Replace-RibbonTab 'Malla' @'
                CommandTile("Controles", "MALLA", () => tsmiCreateMeshingParameters.PerformClick()),
                CommandTile("Refinamiento", "MALLA", () => tsmiCreateMeshRefinement.PerformClick()),
                CommandTile("Generar malla", "MALLA", () => tsmiCreateMesh.PerformClick(), true),
                RibbonSeparator(),
                InfoCard("NetGen nativo • TET4 / TET10 / HEXA8")
'@

Replace-RibbonTab 'Entorno' @'
                CommandTile("Paso", "ANÁLISIS", () => AsterMaxC1004MaterialAction(() => tsmiCreateStep_Click(null, EventArgs.Empty)), true),
                CommandTile("Apoyo", "CONDICIÓN", () => AsterMaxC1004MaterialAction(() => tsmiCreateBC_Click(null, EventArgs.Empty))),
                CommandTile("Carga", "CONDICIÓN", () => AsterMaxC1004MaterialAction(() => tsmiCreateLoad_Click(null, EventArgs.Empty))),
                RibbonSeparator(),
                StateCard("Análisis", "Estructural estático")
'@

Replace-RibbonTab 'Solución' @'
                CommandTile("Verificar", "PREFLIGHT", () => ShowAsterMaxRuntimePreflight(), true),
                CommandTile("Contrato", "SOLVER", () => ExportAsterMaxModelContract()),
                CommandTile("Deck Aster", "CODE_ASTER", () => ExportAsterMaxCodeAsterDeck()),
                CommandTile("Ejecutar", "CODE_ASTER", () => RunAsterMaxNativeSolve(), true),
                CommandTile("Cancelar", "CODE_ASTER", () => CancelAsterMaxNativeSolve()),
                RibbonSeparator(),
                StateCard("Solver", "Code_Aster nativo")
'@

Replace-RibbonTab 'Resultados' @'
                CommandTile("Explorador", "RESULTADOS", () => OpenAsterMaxResultsExplorer(), true),
                CommandTile("Viewport FEA", "VTK", () => OpenAsterMaxResultsViewport(), true),
                CommandTile("Contornos", "RESULTADOS", () => tsbResultsColorContours.PerformClick()),
                CommandTile("Deformada", "RESULTADOS", () => tsbResultsDeformed.PerformClick()),
                CommandTile("Original", "RESULTADOS", () => tsbResultsUndeformed.PerformClick()),
                RibbonSeparator(),
                InfoCard("MED real • campos • min/max • probe")
'@

Replace-RibbonTab 'Vista' @'
                CommandTile("Auditoría", "REPORTE", () => OpenAsterMaxButtonAuditReport()),
                RibbonSeparator(),
                CommandTile("Ajustar", "CÁMARA", AsterMaxFitView),
                CommandTile("Frontal", "CÁMARA", AsterMaxFrontView),
                CommandTile("Superior", "CÁMARA", AsterMaxTopView),
                CommandTile("Derecha", "CÁMARA", AsterMaxRightView),
                CommandTile("Isométrica", "CÁMARA", AsterMaxIsometricView),
                RibbonSeparator(),
                CommandTile("Aristas", "VISUAL", () => tsbShowModelEdges.PerformClick())
'@

# Keep CommandTile dimensions predictable for C10.25 icon layer.
$cmdStart=$u.IndexOf('        private Button CommandTile(')
$cmdEnd=$u.IndexOf('        private Label InfoCard(', $cmdStart)
if($cmdStart -lt 0 -or $cmdEnd -lt 0){ throw 'C10.24 CommandTile method missing.' }
$cmd=$u.Substring($cmdStart,$cmdEnd-$cmdStart)
$cmd=[regex]::Replace($cmd,'Width\s*=\s*text\.Length\s*>\s*\d+\s*\?\s*\d+\s*:\s*\d+,','Width = text.Length > 13 ? 124 : 104,')
$cmd=[regex]::Replace($cmd,'Height\s*=\s*\d+,','Height = 70,',1)
$cmd=$cmd.Replace('Font = new Font("Segoe UI", 8.5f)','Font = new Font("Segoe UI", 8.25f)')
$u=$u.Substring(0,$cmdStart)+$cmd+$u.Substring($cmdEnd)

Set-Content $ui $u -Encoding UTF8
Write-Host 'C10.24: robust functional Mechanical ribbon rebuilt.' -ForegroundColor Green
