param([string]$Root, [string]$OutDir)
$ErrorActionPreference = 'Stop'

if([string]::IsNullOrWhiteSpace($OutDir)){ $OutDir = Join-Path $PSScriptRoot 'out-c957' }
New-Item -ItemType Directory -Force $OutDir | Out-Null

$proj = Join-Path $Root 'PrePoMax/PrePoMax.csproj'
$ui = Join-Path $Root 'PrePoMax/Forms/AsterMaxNativeUi.cs'
$modelTree = Join-Path $Root 'UserControls/ModelTree.cs'
if(!(Test-Path $proj)){ throw 'PrePoMax.csproj not found' }
if(!(Test-Path $ui)){ throw 'AsterMaxNativeUi.cs not found; apply AsterMax patch first' }

$p = Get-Content $proj -Raw
$u = Get-Content $ui -Raw
$m = Get-Content $modelTree -Raw

function Gate([string]$name,[bool]$pass,[string]$evidence,[string]$kind='capability'){
  [pscustomobject]@{ name=$name; pass=$pass; kind=$kind; evidence=$evidence }
}

$checks = @()
$checks += Gate 'cad_step_import_source' ($p -match 'CImportFile\.cs') 'native import command is compiled'
$checks += Gate 'units_mm_contract' (($u -match 'mm\s+\|\s+N\s+\|\s+MPa') -and ($u -match 'Mechanical Analysis')) 'GUI exposes mm/N/MPa engineering contract'
$checks += Gate 'geometry_preparation' (($p -match 'Command\\0030_Geometry') -and ($u -match 'Analyze Geometry')) 'geometry command family and GUI geometry check are present'
$checks += Gate 'materials_model_prep' (($p -match 'Material') -and ($u -match 'Materials')) 'material model source and GUI entry are present'
$checks += Gate 'mesh_generation' (($p -match 'Meshing') -and ($u -match 'Generate Mesh')) 'meshing source and native GUI command are present'
$checks += Gate 'boundary_conditions' (($p -match 'BoundaryConditions') -and ($m -match 'BoundaryCondition') -and ($u -match 'Environment')) 'BC command family, tree support and Environment stage are present'
$checks += Gate 'loads' (($p -match 'Load') -and ($m -match 'Loads')) 'load source family and model-tree load branch are present'
$checks += Gate 'analysis_steps' (($p -match 'Step') -and ($m -match '_steps')) 'analysis-step source and tree branch are present'
$checks += Gate 'analysis_jobs' (($p -match 'Analysis') -and ($m -match '_analyses')) 'analysis/job source and Solution tree branch are present'
$checks += Gate 'postprocess_results' (($p -match 'CaeResults') -and ($u -match 'Contours') -and ($u -match 'Deformed')) 'results library and contour/deformed GUI commands are present'
$checks += Gate 'vtk_visualization' (Test-Path (Join-Path $Root 'vtkControl/vtkControl.csproj')) 'VTK visualization project is compiled'
$checks += Gate 'solver_target_code_aster' (($u -match 'Code_Aster') -and -not ($u -match 'CalculiX|Calculix')) 'user-facing AsterMax UI is Code_Aster-only' 'strategy'
$checks += Gate 'no_synthetic_results_claim' ($u -match 'no synthetic results') 'GUI explicitly rejects synthetic-result claims' 'integrity'

$required = @('cad_step_import_source','units_mm_contract','geometry_preparation','materials_model_prep','mesh_generation','boundary_conditions','loads','analysis_steps','analysis_jobs','postprocess_results','vtk_visualization','solver_target_code_aster','no_synthetic_results_claim')
$failed = $checks | Where-Object { $_.name -in $required -and -not $_.pass }

$gaps = @(
  [pscustomobject]@{ area='Code_Aster solver adapter'; state='NOT_IMPLEMENTED'; priority='P0'; note='No verified native export/launch/result-import loop yet.' },
  [pscustomobject]@{ area='BC/load runtime demo'; state='NOT_RUNTIME_PROVEN'; priority='P0'; note='Source capability exists, but CI does not yet create and verify a constrained loaded model.' },
  [pscustomobject]@{ area='Mesh quality proof'; state='PARTIAL'; priority='P0'; note='Generate Mesh exists; quality metrics and deterministic TET10 gate are not yet proven.' },
  [pscustomobject]@{ area='Professional postprocess'; state='PARTIAL'; priority='P1'; note='Contour/deformed rendering exists; probe, min/max labels, reaction summary and export evidence are next.' },
  [pscustomobject]@{ area='Comparison harness'; state='NOT_IMPLEMENTED'; priority='P1'; note='Need deterministic benchmark metrics for solver-to-reference comparison without vendor branding in product UI.' }
)

$report = [pscustomobject]@{
  release='C9.57'
  title='FEA Readiness Contract'
  generated_utc=(Get-Date).ToUniversalTime().ToString('O')
  contract='CAD/STEP(mm) -> model prep -> mesh -> BC/load -> analysis -> Code_Aster -> postprocess'
  checks_total=$checks.Count
  checks_passed=($checks | Where-Object pass).Count
  readiness_contract_pass=($failed.Count -eq 0)
  checks=$checks
  gaps=$gaps
  solver_policy='Code_Aster only; CalculiX is not an AsterMax solver route.'
  simulation_results='NONE_GENERATED_BY_HARNESS'
}

$path = Join-Path $OutDir 'C9.57_FEA_READINESS.json'
$report | ConvertTo-Json -Depth 8 | Set-Content $path -Encoding UTF8
$checks | Format-Table -AutoSize | Out-String | Write-Host
Write-Host "C9.57 readiness report: $path"
if($failed.Count -gt 0){
  $names = ($failed | ForEach-Object name) -join ', '
  throw "C9.57 readiness contract failed: $names"
}
